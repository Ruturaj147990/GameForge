import sys, os
from pathlib import Path
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from src.gameforge_ide.unreal.live_editor import LiveEditorLink

up = Path(r"E:\GameForge\validation\live_ops_probe\GFProbe.uproject")
link = LiveEditorLink(up)
link.prepare_project()
link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"])
try:
    link.connect(900)
    snippet = """
import unreal, json
bp_lib = [m for m in dir(unreal.BlueprintEditorLibrary) if not m.startswith('_')]
ed_classes = [c for c in dir(unreal) if 'Graph' in c or 'Blueprint' in c or 'K2' in c or 'Pin' in c]
out = {
    'BlueprintEditorLibrary': bp_lib,
    'ed_classes': ed_classes,
    'has_EdGraph': hasattr(unreal, 'EdGraph'),
    'has_EdGraphNode': hasattr(unreal, 'EdGraphNode'),
    'has_EdGraphPin': hasattr(unreal, 'EdGraphPin'),
}
print('@@DIAG@@' + json.dumps(out))
"""
    res = link._rx.run_command(snippet, exec_mode="ExecuteStatement")
    for o in (res.get("output") or []):
        text = o.get("output") if isinstance(o, dict) else str(o)
        for line in text.splitlines():
            if "@@DIAG@@" in line:
                print(line)
finally:
    link.stop()
