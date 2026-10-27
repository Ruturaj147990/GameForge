"""Model-backed code authoring for free-form games, with provenance.

ModelAuthor picks the hosted heavy tier when the workspace has enabled and opted in to one
(Blueprint v2 §3), otherwise the strongest local coder. Every exchange is written to the
evidence folder. Output is parsed into files; nothing the model writes runs until the
pipeline's static safety scan, the compiler and the packaged self-test have judged it.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..backend.providers.ollama_provider import OllamaProvider
from ..backend.providers.router import ModelRouter

LOCAL_AUTHOR_MODEL = "gameforge-qwen3.5-9b:latest"

_FILE_BLOCK = re.compile(r"===\s*FILE:\s*(?P<name>[\w./-]+)\s*===\s*\n(?P<body>.*?)\n===\s*END FILE\s*===", re.S)
_FENCE = re.compile(r"(?:^|\n)[#*`\s]*(?:File:\s*)?(?P<name>GF\w+\.(?:h|cpp))[`*:\s]*\n```[a-zA-Z+]*\n(?P<body>.*?)\n```", re.S)


def parse_files(text: str, allowed: Tuple[str, ...] = ("GFGameImpl.h", "GFGameImpl.cpp")) -> Dict[str, str]:
    """Accept '=== FILE: x === ... === END FILE ===' blocks, or a filename line followed by a fenced block."""
    files: Dict[str, str] = {}
    for m in _FILE_BLOCK.finditer(text):
        body = re.sub(r"^```[a-zA-Z+]*\n|\n```\s*$", "", m["body"].strip())
        files[Path(m["name"]).name] = body.strip() + "\n"
    if not files:
        for m in _FENCE.finditer(text):
            files[Path(m["name"]).name] = m["body"].strip() + "\n"
    return {k: v for k, v in files.items() if k in allowed}


FORBIDDEN = [
    (r"\bsystem\s*\(", "process execution"), (r"CreateProc", "process execution"), (r"ShellExecute", "process execution"),
    (r"\bpopen\b", "process execution"), (r"IFileManager|FFileHelper|PlatformFile|DeleteFile|\bremove\s*\(", "file system access"),
    (r"FSocket|ISocketSubsystem|HttpModule|FHttp", "network access"), (r"#include\s*<windows\.h>|Windows/AllowWindowsPlatformTypes", "raw OS headers"),
    (r"\basm\b|__asm", "inline assembly"), (r"FPlatformMisc::RequestExit|QuitGame", "process control (the framework owns exit)"),
]


def safety_scan(files: Dict[str, str]) -> List[str]:
    """Static gate before compilation: generated gameplay code may not touch processes, files or network."""
    issues = []
    for name, src in files.items():
        for pattern, why in FORBIDDEN:
            if re.search(pattern, src):
                issues.append(f"{name}: forbidden construct ({why}): /{pattern}/")
    h = files.get("GFGameImpl.h", "")
    if h and '#include "GFGameImpl.generated.h"' not in h:
        issues.append('GFGameImpl.h: must include "GFGameImpl.generated.h" as the last include')
    if h and "AGFGameImpl" not in h:
        issues.append("GFGameImpl.h: must declare class AGFGameImpl : public AGFGameBase")
    if not any("RunSelfTest" in s for s in files.values()):
        issues.append("RunSelfTest is not implemented")
    return issues


class ModelAuthor:
    def __init__(self, workspace_root: Path, transcript_dir: Path, router: Optional[ModelRouter] = None,
                 local_model: str = LOCAL_AUTHOR_MODEL):
        self.router = router or ModelRouter()
        self.router.attach_hosted(Path(workspace_root))
        self.transcript_dir = Path(transcript_dir)
        self.local_model = local_model
        self.calls = 0
        route = self.router.route_hosted("author")
        if route:
            self.provider_id, self.model = route
            self.tier = "hosted"
        else:
            self.provider_id, self.model, self.tier = "ollama", local_model, "local"

    def describe(self) -> str:
        return f"{self.tier}:{self.provider_id}/{self.model}"

    def complete(self, system: str, messages: List[Dict[str, str]], label: str, max_tokens: int = 8192) -> str:
        self.calls += 1
        t0 = time.time()
        if self.tier == "hosted":
            prov = self.router.get_provider(self.provider_id)
            flat = "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)
            text = prov.complete(self.model, flat, system_prompt=system, temperature=0.2, max_tokens=max_tokens).content
        else:
            prov = OllamaProvider(timeout_seconds=900)
            res = prov.chat_with_tools(self.model, [{"role": "system", "content": system}] + messages, [],
                                       num_ctx=32768, temperature=0.2, max_tokens=max_tokens)
            text = res["content"]
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        (self.transcript_dir / f"{self.calls:02d}_{label}.md").write_text(
            f"# {label}\n\nmodel: {self.describe()}  seconds: {time.time() - t0:.1f}\n\n## request\n\n"
            + json.dumps(messages, indent=1)[:20000] + "\n\n## response\n\n" + text, encoding="utf-8")
        return text
