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

    # 7. Convert switch on FKey (e.g. switch (Key)) to if/else if chain
    if cpp and (re.search(r'\bswitch\s*\(\s*Key\s*\)', cpp) or 'case EKeys::' in cpp):
        cpp, switch_fixed = _convert_key_switch_to_if(cpp)
        if switch_fixed:
            notes.append("converted invalid switch statement on FKey to if/else chains")

    # 8. Fix FVector .ToFloat() and FQuat rotation hallucinations
    if cpp and ".ToFloat()" in cpp:
        cpp = re.sub(
            r'FQuat\s*\(\s*(?:FVector(?:\([^)]*\)|::\w+))\s*,\s*(\w+)\.ToFloat\(\)\s*\)',
            r'\1.Rotation().Quaternion()',
            cpp,
        )
        cpp = re.sub(r'(\b\w+)\.ToFloat\(\)', r'\1.Size()', cpp)
        notes.append("fixed invalid FVector::ToFloat() and FQuat construction")

    out = dict(files)
    if h:
        out["GFGameImpl.h"] = h
    if cpp:
        out["GFGameImpl.cpp"] = cpp
    return out, notes


def _convert_key_switch_to_if(cpp_text: str) -> Tuple[str, bool]:
    """Converts invalid C++ switch statements on FKey (e.g. switch (Key)) to if/else chains."""
    switch_iter = list(re.finditer(r"\bswitch\s*\(\s*(\w+)\s*\)\s*\{", cpp_text))
    if not switch_iter:
        return cpp_text, False

    offset = 0
    modified = False
    result_text = cpp_text

    for m in switch_iter:
        start_idx = m.start() + offset
        var_name = m.group(1)

        open_brace = m.end() - 1 + offset
        depth = 1
        pos = open_brace + 1
        n = len(result_text)
        while pos < n and depth > 0:
            ch = result_text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1

        if depth != 0:
            continue

        close_brace = pos - 1
        body = result_text[open_brace + 1 : close_brace]

        if var_name.lower() != "key" and "EKeys::" not in body:
            continue

        label_pat = re.compile(r"(?:case\s+(.*?)(?<!:):(?!:)|default\s*(?<!:):(?!:))", re.DOTALL)
        splits = list(label_pat.finditer(body))
        if not splits:
            continue

        branches = []
        pending_conditions = []
        for i, split in enumerate(splits):
            is_default = "default" in split.group(0)
            val = split.group(1).strip() if not is_default and split.group(1) else None

            start_pos = split.end()
            end_pos = splits[i + 1].start() if i + 1 < len(splits) else len(body)
            branch_content = body[start_pos:end_pos]

            if val:
                pending_conditions.append(f"{var_name} == {val}")

            substantive = re.sub(r"//[^\n]*", "", branch_content).strip()
            if substantive or is_default or (i + 1 == len(splits)):
                lines = branch_content.strip().splitlines()
                clean_lines = []
                for l in lines:
                    if re.match(r"^\s*break\s*;\s*$", l):
                        continue
                    clean_lines.append(l)
                branch_clean = "\n".join(clean_lines).strip()
                cond = " || ".join(pending_conditions)
                branches.append((cond, is_default, branch_clean))
                pending_conditions = []

        if not branches:
            continue

        line_start = result_text.rfind("\n", 0, start_idx) + 1
        switch_line = result_text[line_start:start_idx]
        indent = re.match(r"^\s*", switch_line).group(0)

        out_lines = []
        first = True
        for cond, is_def, code in branches:
            if not cond and not is_def:
                continue
            if is_def:
                if out_lines:
                    if code:
                        out_lines.append(f"{indent}else\n{indent}{{\n\t{code}\n{indent}}}")
                else:
                    if code:
                        out_lines.append(f"{indent}{{\n\t{code}\n{indent}}}")
            else:
                prefix = f"{indent}if ({cond})" if first else f"{indent}else if ({cond})"
                first = False
                out_lines.append(f"{prefix}\n{indent}{{\n\t{code}\n{indent}}}")

        replacement = "\n".join(l for l in out_lines if l)
        old_slice_len = (close_brace + 1) - start_idx
        result_text = result_text[:start_idx] + replacement + result_text[close_brace + 1:]
        offset += len(replacement) - old_slice_len
        modified = True

    return result_text, modified


HINTS = {
    "C2039": "A member or function was not found (e.g. FVector has no .ToFloat(); or function defined in .cpp but not declared in GFGameImpl.h).",
    "C3861": "An identifier is used but not declared. Declare helper functions as private members of AGFGameImpl.",
    "C2065": "A variable is undeclared. Member variables must be declared in the class in GFGameImpl.h; check naming (e.g. bBombPlanted vs BombPlanted).",
    "C3668": "An 'override' does not match the base signature. Copy the signature exactly from the contract, including const.",
    "C1189": "GFGameImpl.generated.h may only be included once, in GFGameImpl.h, as the last include.",
    "C2511": "A definition's signature does not match its declaration; make them identical.",
    "C2662": "A const member function calls a non-const member or modifies state; remove the modification or the const.",
    "C2440": "Type conversion error: check FString/TEXT usage, pointer vs object types, or FKey (FKey cannot convert to int; use if (Key == EKeys::X) instead).",
    "C2450": "FKey cannot be used in a switch expression (it is a struct, not an integer or enum). In Unreal Engine, replace switch(Key) with if (Key == EKeys::X) { ... } else if (Key == EKeys::Y) { ... }.",
    "C2046": "Illegal case label: if switching on FKey or a non-integral type, use if (Key == EKeys::X) instead of switch/case.",
    "C4060": "Switch statement contains no valid case labels: switch on FKey fails type conversion. Replace switch with if/else chains using EKeys.",
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
