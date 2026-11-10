"""Procedural PBR texture-set generator (roadmap M11 step 4). Provenance class: ``procedural``.

From one seeded, tileable fBm height field it derives a full Unreal-ready set:

- ``T_<name>_BaseColor.png``  sRGB colour, varied by height (import: sRGB on, default compression)
- ``T_<name>_Normal.png``     tangent-space normal, DirectX/Unreal convention (green = -dHeight/dV;
                              import: sRGB off, ``TC_Normalmap``)
- ``T_<name>_ORM.png``        packed R = ambient occlusion, G = roughness, B = metallic
                              (import: sRGB off, ``TC_Masks``)
- ``T_<name>_Height.png``     grey height (import: sRGB off, ``TC_Grayscale``)

All maps tile seamlessly because the noise lattice and the derivatives wrap around the edges. Only numpy is
needed; PNGs are written with zlib directly. A JSON manifest records the spec, channel roles, import hints and
SHA-256 of every file, and ``validate_texture_set`` re-reads the PNGs to check them.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

GENERATOR = "GameForge-ProceduralPBR-V1"
GENERATOR_VERSION = "1.0.0"
MAPS = {
    "BaseColor": {"srgb": True, "compression": "TC_Default", "channels": 3},
    "Normal": {"srgb": False, "compression": "TC_Normalmap", "channels": 3},
    "ORM": {"srgb": False, "compression": "TC_Masks", "channels": 3},
    "Height": {"srgb": False, "compression": "TC_Grayscale", "channels": 1},
}


@dataclass
class PBRTextureSpec:
    name: str
    size: int = 512
    seed: int = 0
    base_color: tuple[float, float, float] = (0.45, 0.38, 0.30)
    color_variation: float = 0.35
    roughness_range: tuple[float, float] = (0.45, 0.9)
    metallic: float = 0.0
    normal_strength: float = 4.0
    ao_strength: float = 0.8
    base_frequency: int = 4
    octaves: int = 5
    persistence: float = 0.5
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError("name must be non-empty and alphanumeric/underscore")
        if self.size < 16 or self.size > 4096 or self.size & (self.size - 1):
            raise ValueError("size must be a power of two between 16 and 4096")
        if not all(0.0 <= c <= 1.0 for c in self.base_color):
            raise ValueError("base_color components must be in [0, 1]")
        lo, hi = self.roughness_range
        if not 0.0 <= lo <= hi <= 1.0:
            raise ValueError("roughness_range must satisfy 0 <= low <= high <= 1")
        if not 0.0 <= self.metallic <= 1.0:
            raise ValueError("metallic must be in [0, 1]")
        if self.base_frequency < 1 or self.size % self.base_frequency:
            raise ValueError("base_frequency must be >= 1 and divide size")
        if not 1 <= self.octaves <= 10:
            raise ValueError("octaves must be in [1, 10]")


# ── noise ──────────────────────────────────────────────────────────────────

def _value_noise(size: int, freq: int, rng: np.random.Generator) -> np.ndarray:
    """Tileable value noise: a freq x freq random lattice, smoothstep-interpolated with wrap-around."""
    lattice = rng.random((freq, freq))
    coords = np.arange(size) * freq / size
    i0 = np.floor(coords).astype(int)
    t = coords - i0
    t = t * t * (3.0 - 2.0 * t)
    i1 = (i0 + 1) % freq
    i0 %= freq
    top = lattice[i0][:, i0] * (1 - t)[None, :] + lattice[i0][:, i1] * t[None, :]
    bottom = lattice[i1][:, i0] * (1 - t)[None, :] + lattice[i1][:, i1] * t[None, :]
    return top * (1 - t)[:, None] + bottom * t[:, None]


def height_field(spec: PBRTextureSpec) -> np.ndarray:
    rng = np.random.default_rng(spec.seed)
    total, amp, norm = np.zeros((spec.size, spec.size)), 1.0, 0.0
    for octave in range(spec.octaves):
        freq = spec.base_frequency * (2 ** octave)
        if freq > spec.size:
            break
        total += amp * _value_noise(spec.size, freq, rng)
        norm += amp
        amp *= spec.persistence
    total /= norm
    return (total - total.min()) / max(total.max() - total.min(), 1e-9)


def _blur(img: np.ndarray, radius: int) -> np.ndarray:
    out = img.copy()
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for d in range(-radius, radius + 1):
            acc += np.roll(out, d, axis=axis)
        out = acc / (2 * radius + 1)
    return out


def derive_maps(spec: PBRTextureSpec, height: np.ndarray) -> dict[str, np.ndarray]:
    """Float maps in [0, 1]: BaseColor (H,W,3), Normal (H,W,3, encoded), ORM (H,W,3), Height (H,W)."""
    # Central differences with wrap so the normal map tiles. Unreal's tangent space is DirectX-style (+Y down
    # the texture), so the green channel is the negated V-gradient of an OpenGL-style map.
    du = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dv = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    n = np.stack([-du * spec.normal_strength, dv * spec.normal_strength, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = n * 0.5 + 0.5

    shade = 1.0 - spec.color_variation + spec.color_variation * height
    base = np.clip(np.asarray(spec.base_color)[None, None, :] * shade[..., None], 0.0, 1.0)

    cavity = np.clip(_blur(height, max(1, spec.size // 128)) - height, 0.0, None)
    ao = np.clip(1.0 - spec.ao_strength * cavity / max(cavity.max(), 1e-9), 0.0, 1.0)
    lo, hi = spec.roughness_range
    rough = lo + (hi - lo) * (1.0 - height)
    orm = np.stack([ao, rough, np.full_like(height, spec.metallic)], axis=-1)
    return {"BaseColor": base, "Normal": normal, "ORM": orm, "Height": height}


# ── PNG I/O (8-bit, no interlace) ──────────────────────────────────────────

def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path: Path, img: np.ndarray) -> None:
    arr = np.clip(np.rint(img * 255.0), 0, 255).astype(np.uint8)
    channels = 1 if arr.ndim == 2 else arr.shape[2]
    color_type = {1: 0, 3: 2, 4: 6}[channels]
    h, w = arr.shape[:2]
    rows = arr.reshape(h, w * channels)
    raw = b"".join(b"\x00" + rows[y].tobytes() for y in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0))
                     + _png_chunk(b"IDAT", zlib.compress(raw, 6)) + _png_chunk(b"IEND", b""))


def read_png(path: Path) -> np.ndarray:
    """Reads 8-bit greyscale/RGB/RGBA non-interlaced PNGs (any filter type); returns uint8 (H,W[,C])."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, header = 8, b"", None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    if header is None:
        raise ValueError("PNG has no IHDR chunk")
    w, h, depth, color_type, _, _, interlace = header
    if depth != 8 or interlace:
        raise ValueError("only 8-bit non-interlaced PNGs are supported")
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    stride = w * channels
    raw = zlib.decompress(idat)
    out = np.zeros((h, stride), dtype=np.int32)
    prev = np.zeros(stride, dtype=np.int32)
    for y in range(h):
        ftype = raw[y * (stride + 1)]
        line = np.frombuffer(raw, np.uint8, stride, y * (stride + 1) + 1).astype(np.int32)
        if ftype == 0:
            cur = line
        elif ftype == 2:
            cur = (line + prev) & 0xFF
        else:  # Sub / Average / Paeth need the reconstructed left neighbour: do them per byte.
            cur = np.zeros(stride, dtype=np.int32)
            for x in range(stride):
                a = cur[x - channels] if x >= channels else 0
                b = prev[x]
                c = prev[x - channels] if x >= channels else 0
                if ftype == 1:
                    pred = a
                elif ftype == 3:
                    pred = (a + b) // 2
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[x] = (line[x] + pred) & 0xFF
        out[y], prev = cur, cur
    arr = out.astype(np.uint8)
    return arr.reshape(h, w) if channels == 1 else arr.reshape(h, w, channels)


# ── generation + validation ────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def generate_texture_set(spec: PBRTextureSpec, output_dir: str | Path, asset_registry=None) -> dict:
    """Writes the four PNGs plus ``<name>_pbr_manifest.json``; returns the manifest dict."""
    spec.validate()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    maps = derive_maps(spec, height_field(spec))
    files = {}
    for role, img in maps.items():
        path = out / f"T_{spec.name}_{role}.png"
        write_png(path, img)
        files[role] = {"path": str(path), "sha256": _sha256(path), **MAPS[role]}
    manifest = {"name": spec.name, "generator": GENERATOR, "generator_version": GENERATOR_VERSION,
                "provenance": "procedural", "license": "CC0-1.0", "spec": asdict(spec), "size": spec.size,
                "normal_convention": "DirectX (Unreal)", "orm_packing": {"R": "AO", "G": "Roughness", "B": "Metallic"},
                "files": files}
    if asset_registry is not None:
        from ...backend.assets.registry import AssetRecord
        ids = {}
        for role, info in files.items():
            rid = asset_registry.register(AssetRecord(
                name=f"T_{spec.name}_{role}", asset_type="texture", purpose=f"{role} map of {spec.name}",
                provenance="procedural", backend=GENERATOR, backend_version=GENERATOR_VERSION, license="CC0-1.0",
                spec={**asdict(spec), "role": role}, tags=[spec.name, "pbr", *spec.tags]))
            asset_registry.advance(rid, "SPEC", True, "spec validated")
            asset_registry.advance(rid, "GENERATE", True, artifact_path=info["path"])
            ids[role] = rid
        manifest["registry_ids"] = ids
    (out / f"{spec.name}_pbr_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def validate_texture_set(manifest: dict, min_std: float = 2.0, tile_ratio: float = 3.0) -> dict:
    """Re-reads every PNG and checks hash, resolution, channel content, normal unit length and tiling.

    Tiling: the step across the wrap seam (last column → first column, last row → first row) must be no
    larger than ``tile_ratio`` times the mean interior step; a non-tiling map has a visible seam.
    """
    if not isinstance(manifest, dict) or "files" not in manifest or "size" not in manifest:
        return {"valid": False, "errors": ["manifest missing 'files' or 'size'"], "metrics": {}}
    errors, metrics = [], {}
    size = manifest["size"]
    for role, info in manifest["files"].items():
        path = Path(info["path"])
        if not path.exists():
            errors.append(f"{role}: file missing")
            continue
        if _sha256(path) != info["sha256"]:
            errors.append(f"{role}: sha256 mismatch")
        img = read_png(path).astype(np.float64)
        m = {"shape": list(img.shape)}
        if img.shape[0] != size or img.shape[1] != size or size & (size - 1):
            errors.append(f"{role}: resolution {img.shape[:2]} is not {size}x{size} power of two")
        chans = img[..., None] if img.ndim == 2 else img
        if chans.shape[2] != info["channels"]:
            errors.append(f"{role}: {chans.shape[2]} channels, expected {info['channels']}")
        stds = [float(chans[..., c].std()) for c in range(chans.shape[2])]
        m["channel_std"] = [round(s, 2) for s in stds]
        varying = stds[:2] if role in ("ORM", "Normal") else stds  # metallic / normal Z may be ~constant
        if any(s < min_std for s in varying):
            errors.append(f"{role}: a channel is (near) constant: std {m['channel_std']}")
        lum = chans.mean(axis=2)
        interior = (np.abs(np.diff(lum, axis=1)).mean() + np.abs(np.diff(lum, axis=0)).mean()) / 2
        seam = (np.abs(lum[:, 0] - lum[:, -1]).mean() + np.abs(lum[0, :] - lum[-1, :]).mean()) / 2
        m["seam_to_interior_step"] = round(float(seam / max(interior, 1e-9)), 3)
        if seam > tile_ratio * max(interior, 1e-9):
            errors.append(f"{role}: does not tile (seam step {seam:.2f} vs interior {interior:.2f})")
        if role == "Normal":
            n = chans / 255.0 * 2.0 - 1.0
            length = np.linalg.norm(n, axis=-1)
            m["normal_length_min_max"] = [round(float(length.min()), 3), round(float(length.max()), 3)]
            m["normal_z_min"] = round(float(n[..., 2].min()), 3)
            if length.min() < 0.95 or length.max() > 1.05:
                errors.append(f"{role}: decoded normals are not unit length {m['normal_length_min_max']}")
            if n[..., 2].min() <= 0.0:
                errors.append(f"{role}: normals point into the surface (z <= 0)")
        metrics[role] = m
    return {"valid": not errors, "errors": errors, "metrics": metrics}
