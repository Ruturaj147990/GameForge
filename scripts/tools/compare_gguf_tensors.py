import gguf
import numpy as np
import json
import time
from pathlib import Path

BASE_GGUF = Path(r"E:\GameForge\models\ollama\blobs\sha256-f5f1dd8920d417aac2718b0bda3403da274301efdd6760b4f0f4b864ff2ad57d")
FINAL_GGUF = Path(r"E:\GameForge\artifacts\gameforge-27b\gameforge-27b-q4_k_m.gguf")

def compare_ggufs():
    print("Loading base GGUF...")
    r_base = gguf.GGUFReader(str(BASE_GGUF))
    print("Loading final GGUF...")
    r_final = gguf.GGUFReader(str(FINAL_GGUF))

    assert len(r_base.tensors) == len(r_final.tensors), "Tensor count mismatch!"
    total_tensors = len(r_base.tensors)
    print(f"Total tensors: {total_tensors}")

    base_by_name = {t.name: t for t in r_base.tensors}
    final_by_name = {t.name: t for t in r_final.tensors}

    changed_tensors = []
    identical_count = 0

    with open(BASE_GGUF, "rb") as f_b, open(FINAL_GGUF, "rb") as f_f:
        for idx, (name, t_b) in enumerate(base_by_name.items()):
            t_f = final_by_name[name]
            assert t_b.n_bytes == t_f.n_bytes
            assert t_b.data_offset == t_f.data_offset
            
            f_b.seek(t_b.data_offset)
            bytes_b = f_b.read(t_b.n_bytes)
            
            f_f.seek(t_f.data_offset)
            bytes_f = f_f.read(t_f.n_bytes)

            if bytes_b != bytes_f:
                # Tensor changed!
                arr_b = np.frombuffer(bytes_b, dtype=np.float32 if t_b.tensor_type == 0 else np.uint8)
                arr_f = np.frombuffer(bytes_f, dtype=np.float32 if t_f.tensor_type == 0 else np.uint8)
                diff = np.abs(arr_f.astype(np.float64) - arr_b.astype(np.float64))
                max_diff = float(np.max(diff))
                mean_diff = float(np.mean(diff))
                l2_diff = float(np.linalg.norm(diff))
                
                changed_tensors.append({
                    "tensor_name": name,
                    "tensor_type": str(t_b.tensor_type),
                    "shape": [int(x) for x in t_b.shape],
                    "offset": t_b.data_offset,
                    "n_bytes": t_b.n_bytes,
                    "max_absolute_delta": max_diff,
                    "mean_delta": mean_diff,
                    "l2_delta": l2_diff
                })
                print(f"[CHANGED] {name}: max_delta={max_diff:.8e}, l2_delta={l2_diff:.8e}")
            else:
                identical_count += 1

    # Check vision projector tensors specifically
    vision_tensors = [t for t in base_by_name.keys() if "v." in t or "vision" in t or "mm." in t]
    vision_changed = [t for t in changed_tensors if t["tensor_name"] in vision_tensors]

    print(f"\nSummary:")
    print(f"Total Tensors: {total_tensors}")
    print(f"Identical Tensors: {identical_count}")
    print(f"Changed Tensors: {len(changed_tensors)}")
    print(f"Vision Tensors Count: {len(vision_tensors)}, Changed: {len(vision_changed)}")

    result = {
        "base_path": str(BASE_GGUF),
        "final_path": str(FINAL_GGUF),
        "total_tensors": total_tensors,
        "identical_tensors": identical_count,
        "changed_tensors_count": len(changed_tensors),
        "changed_tensors": changed_tensors,
        "vision_tensors_count": len(vision_tensors),
        "vision_tensors_changed": len(vision_changed),
        "vision_projector_invariant": "PRESERVED_BITWISE_IDENTICAL" if len(vision_changed) == 0 else "MODIFIED"
    }

    out_file = Path(r"E:\GameForge\reports\gameforge-27b\acceptance\tensor_diff_audit.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, indent=2))
    print(f"Audit results written to {out_file}")

if __name__ == "__main__":
    compare_ggufs()
