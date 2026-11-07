"""Deterministic repair rung (runs before asking a model).

Mechanical C++ mistakes that models make repeatedly are fixed by code, not by another model
call: missing member declarations, missing const on the framework's const overrides, and the
generated header included from the .cpp. Each fix is recorded. Anything else goes to the model
with error-code-specific hints.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

CONST_OVERRIDES = {"GetStatusText", "GetControlsText", "GetCameraFocus", "GetCameraDistance", "GetCameraPitch"}

_DEF = re.compile(
    r"^(?P<ret>[A-Za-z_][\w:<>,\s\*&]*?)\s+AGFGameImpl::(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?P<const>const)?\s*(?:override)?\s*\{",
    re.M)


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _declared_names(header: str) -> set:
    body = _strip_comments(header)
    return set(re.findall(r"\b(\w+)\s*\(", body))


def autofix(files: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    h = files.get("GFGameImpl.h", "")
    cpp = files.get("GFGameImpl.cpp", "")
    notes: List[str] = []

    # 1. generated header must only be included by the header, last
    if "GFGameImpl.generated.h" in cpp:
        cpp = re.sub(r'^\s*#include\s+"GFGameImpl\.generated\.h"\s*\n', "", cpp, flags=re.M)
        notes.append("removed GFGameImpl.generated.h include from the .cpp")
    if h and '#include "GFGameImpl.generated.h"' in h:
        lines = h.split("\n")
        incs = [i for i, l in enumerate(lines) if l.strip().startswith("#include")]
        gen = next(i for i, l in enumerate(lines) if "GFGameImpl.generated.h" in l)
        if incs and gen != incs[-1]:
            line = lines.pop(gen)
            incs = [i for i, l in enumerate(lines) if l.strip().startswith("#include")]
            lines.insert(incs[-1] + 1, line)
            h = "\n".join(lines)
            notes.append("moved GFGameImpl.generated.h to be the last include")

    # 2. const on the framework's const virtuals (header and definitions)
    for name in CONST_OVERRIDES:
        pat_h = re.compile(rf"(virtual\s+[\w:<>]+\s+{name}\s*\(\s*\))\s*(override)")
        if pat_h.search(h):
            h = pat_h.sub(r"\1 const \2", h)
            notes.append(f"added const to {name} declaration")
        pat_c = re.compile(rf"(AGFGameImpl::{name}\s*\(\s*\))\s*\{{")
        if pat_c.search(cpp):
            cpp = pat_c.sub(r"\1 const\n{", cpp)
            notes.append(f"added const to {name} definition")

    # 3. member functions defined in the .cpp but never declared in the class
    declared = _declared_names(h)
    missing = []
    for m in _DEF.finditer(_strip_comments(cpp)):
        name = m["name"]
        if name in declared or name == "AGFGameImpl":
            continue
        ret = " ".join(m["ret"].split())
        params = " ".join(m["params"].split())
        missing.append(f"\t{ret} {name}({params}){' const' if m['const'] else ''};")
        declared.add(name)
    if missing and h:
        idx = h.rfind("};")
        if idx != -1:
            h = h[:idx] + "private:\n\t// declarations added by GameForge autofix\n" + "\n".join(missing) + "\n" + h[idx:]
            notes.append("declared missing member functions: " + ", ".join(
                re.search(r"(\w+)\(", d).group(1) for d in missing))

    # 4. a constructor defined without declaration
    if re.search(r"AGFGameImpl::AGFGameImpl\s*\(", cpp) and not re.search(r"\bAGFGameImpl\s*\(\s*\)\s*;", h):
        idx = h.find("GENERATED_BODY()")
        if idx != -1:
            end = idx + len("GENERATED_BODY()")
            h = h[:end] + "\npublic:\n\tAGFGameImpl();" + h[end:]
            notes.append("declared the constructor")

    # 5. Fix AActor::IsAlive() hallucinations -> IsValid()
    if cpp and "->IsAlive()" in cpp:
        cpp = re.sub(r'(\b\w+)->IsAlive\(\)', r'IsValid(\1)', cpp)
        notes.append("replaced invalid AActor::IsAlive() with IsValid()")

    # 6. Fix AActor::AddActorWorldRotation(FVector(...)) -> FRotator(...)
    if cpp and re.search(r'AddActorWorldRotation\s*\(\s*FVector\(', cpp):
        cpp = re.sub(r'AddActorWorldRotation\s*\(\s*FVector\(', 'AddActorWorldRotation(FRotator(', cpp)
        notes.append("replaced invalid FVector with FRotator in AddActorWorldRotation")

    out = dict(files)
    if h:
        out["GFGameImpl.h"] = h
    if cpp:
        out["GFGameImpl.cpp"] = cpp
    return out, notes


HINTS = {
    "C2039": "A function is defined as AGFGameImpl::X in the .cpp but X is not declared in the class in GFGameImpl.h. Declare it.",
    "C3861": "An identifier is used but not declared. Declare helper functions as private members of AGFGameImpl.",
    "C2065": "A variable is undeclared. Member variables must be declared in the class in GFGameImpl.h; inherited Rng exists only inside member functions.",
    "C3668": "An 'override' does not match the base signature. Copy the signature exactly from the contract, including const.",
    "C1189": "GFGameImpl.generated.h may only be included once, in GFGameImpl.h, as the last include.",
    "C2511": "A definition's signature does not match its declaration; make them identical.",
    "C2662": "A const member function calls a non-const member or modifies state; remove the modification or the const.",
    "C2440": "Type conversion error: check FString/TEXT usage and pointer vs object types.",
    "LNK2019": "A declared function has no definition; define it in GFGameImpl.cpp or remove the declaration.",
    "LNK2001": "A declared function or static has no definition; define it in GFGameImpl.cpp.",
}


def hints_for(diags: List[Dict]) -> str:
    codes = []
    for d in diags:
        c = d.get("code")
        if c in HINTS and c not in codes:
            codes.append(c)
    return "\n".join(f"- {c}: {HINTS[c]}" for c in codes)
