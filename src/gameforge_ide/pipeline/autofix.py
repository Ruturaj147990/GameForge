"""Deterministic repair rung (runs before asking a model).

Mechanical C++ mistakes that models make repeatedly are fixed by code, not by another model
call: missing member declarations, missing const on the framework's const overrides, and the
generated header included from the .cpp. Each fix is recorded. Anything else goes to the model
with error-code-specific hints.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CONST_OVERRIDES = {
    "GetStatusText",
    "GetSecondaryStatusText",
    "GetControlsText",
    "GetCameraFocus",
    "GetCameraDistance",
    "GetCameraPitch",
    "GetCameraYaw",
    "GetCameraFOV",
}

_DEF = re.compile(
    r"^(?P<ret>[A-Za-z_][\w:<>,\s\*&]*?)\s+AGFGameImpl::(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?P<const>const)?\s*(?:override)?\s*\{",
    re.M)


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _declared_names(header: str) -> set:
    body = _strip_comments(header)
    return set(re.findall(r"\b(\w+)\s*\(", body))


def _make_member_func_const(name: str, h: str, cpp: str) -> Tuple[str, str, bool]:
    """Adds const to the declaration of member function `name` in header and its definition in cpp."""
    modified = False
    decl_pat = re.compile(rf"^(\s*(?:virtual\s+)?[\w:<>\*&]+(?:\s+[\*&])?\s+{name}\s*\([^)]*\))(?!\s*const)\s*(?:override)?\s*;", re.M)
    if decl_pat.search(h):
        h = decl_pat.sub(r"\1 const;", h)
        modified = True

    def_pat = re.compile(rf"^((?:[\w:<>\*&]+(?:\s+[\*&])?\s+)?\w+::{name}\s*\([^)]*\))(?!\s*const)\s*(?:override)?\s*\{{", re.M)
    if def_pat.search(cpp):
        cpp = def_pat.sub(r"\1 const\n{", cpp)
        modified = True

    return h, cpp, modified


def _default_return_for(ret_type: str) -> str:
    r = ret_type.strip().rstrip("&").strip()
    if r == "void":
        return ""
    if r == "bool":
        return "return false;"
    if r in ("int", "int32", "int64", "uint32", "uint8", "float", "double", "size_t"):
        return "return 0;"
    if r == "FVector":
        return "return FVector::ZeroVector;"
    if r == "FRotator":
        return "return FRotator::ZeroRotator;"
    if r == "FQuat":
        return "return FQuat::Identity;"
    if r == "FString":
        return "return FString();"
    if r == "FName":
        return "return FName();"
    if r == "FText":
        return "return FText::GetEmpty();"
    if r.endswith("*"):
        return "return nullptr;"
    return f"return {r}();"


def _stub_missing_definitions(h: str, cpp: str, class_name: Optional[str] = None) -> Tuple[str, List[str]]:
    """Synthesizes default definitions in cpp for member functions declared in h but not defined in cpp."""
    notes = []
    if not h or not cpp:
        return cpp, notes

    stripped_h = _strip_comments(h)
    class_blocks = list(re.finditer(r"class\s+(?:\w+_API\s+)?(?P<cls>\w+)(?:\s*:[^{;]+)?\{(?P<body>[\s\S]*?)\};", stripped_h))

    blocks_to_check = []
    if class_blocks:
        for cb in class_blocks:
            c_cls = cb.group("cls")
            if class_name and c_cls != class_name:
                continue
            blocks_to_check.append((c_cls, cb.group("body")))
    elif class_name:
        blocks_to_check.append((class_name, stripped_h))

    decl_pat = re.compile(
        r"^\s*(?:virtual\s+|static\s+)?(?P<ret>[\w:<>\*&]+(?:\s+[\*&])?)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*(?P<const>const)?\s*(?:override)?\s*;",
        re.M,
    )

    new_stubs = []
    for cls, body in blocks_to_check:
        def_pat = re.compile(rf"{cls}::(?P<name>\w+)\s*\(", re.M)
        existing_defs = set(def_pat.findall(cpp))

        for m in decl_pat.finditer(body):
            name = m.group("name")
            if (
                name in existing_defs
                or name == cls
                or name.startswith("DECLARE_")
                or name in ("GENERATED_BODY", "UCLASS", "UPROPERTY")
            ):
                continue

            raw_ret = m.group("ret").strip()
            ret = re.sub(r"\b(virtual|static|public:|private:|protected:)\b", "", raw_ret).strip()
            ret = ret.replace("public:", "").replace("private:", "").replace("protected:", "").strip()
            if not ret:
                continue

            params = m.group("params").strip()
            clean_params = re.sub(r"\s*=\s*[^,)]+", "", params).strip()
            is_const = bool(m.group("const"))
            const_suffix = " const" if is_const else ""

            ret_stmt = _default_return_for(ret)
            body_stmt = f"\t{ret_stmt}\n" if ret_stmt else ""

            stub = f"{ret} {cls}::{name}({clean_params}){const_suffix}\n{{\n{body_stmt}}}\n"
            new_stubs.append(stub)
            notes.append(f"synthesized missing definition for {cls}::{name} (preventing LNK2019)")
            existing_defs.add(name)

    if new_stubs:
        cpp = cpp.rstrip() + "\n\n// Definitions synthesized by GameForge autofix for declared helpers\n" + "\n".join(new_stubs)

    return cpp, notes


def autofix(files: Dict[str, str], diags: Optional[List[Dict]] = None) -> Tuple[Dict[str, str], List[str]]:
    h_key = next((k for k in files if k.endswith("GFGameImpl.h")), "GFGameImpl.h")
    cpp_key = next((k for k in files if k.endswith("GFGameImpl.cpp")), "GFGameImpl.cpp")
    h = files.get(h_key, "")
    cpp = files.get(cpp_key, "")
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

    # 9. Fix invalid Unreal color constants (UE 5.7.4 Math/Color.h invariants)
    if cpp and ("FLinearColor::Grey" in cpp or "FLinearColor::Orange" in cpp):
        if "FLinearColor::Grey" in cpp:
            cpp = cpp.replace("FLinearColor::Grey", "FLinearColor::Gray")
            notes.append("replaced invalid FLinearColor::Grey with FLinearColor::Gray")
        if "FLinearColor::Orange" in cpp:
            cpp = cpp.replace("FLinearColor::Orange", "FLinearColor(FColor::Orange)")
            notes.append("replaced invalid FLinearColor::Orange with FLinearColor(FColor::Orange)")

    # 10. Fix C2662: const member functions calling non-const helpers
    if diags:
        for d in diags:
            if d.get("code") == "C2662":
                msg = d.get("message", "")
                m_fn = re.search(r"::(?P<name>\w+)\s*\(", msg)
                if m_fn:
                    fname = m_fn.group("name")
                    h, cpp, ok = _make_member_func_const(fname, h, cpp)
                    if ok:
                        notes.append(f"added const to {fname} (fixing C2662)")

    # Static analysis: find member functions called from inside const member functions
    const_defs = list(re.finditer(r"\b\w+::(?P<name>\w+)\s*\([^)]*\)\s*const\s*(?:override)?\s*\{", cpp))
    for m_def in const_defs:
        open_brace = m_def.end() - 1
        depth = 1
        pos = open_brace + 1
        n = len(cpp)
        while pos < n and depth > 0:
            if cpp[pos] == "{":
                depth += 1
            elif cpp[pos] == "}":
                depth -= 1
            pos += 1
        if depth == 0:
            body = cpp[open_brace + 1 : pos - 1]
            called_names = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", body))
            declared = _declared_names(h)
            for cname in called_names:
                if cname in declared and cname not in CONST_OVERRIDES and cname != "AGFGameImpl":
                    if re.search(rf"\b{cname}\s*\([^)]*\)(?!\s*const)\s*;", h):
                        h, cpp, ok = _make_member_func_const(cname, h, cpp)
                        if ok:
                            notes.append(f"added const to helper {cname} called from const method {m_def.group('name')}")

    cpp, stub_notes = _stub_missing_definitions(h, cpp, class_name="AGFGameImpl")
    notes.extend(stub_notes)

    out = dict(files)
    if h:
        out[h_key] = h
    if cpp:
        out[cpp_key] = cpp

    # Synthesize missing definitions for any other class (.h/.cpp pairs)
    for fn, c_content in list(out.items()):
        if fn.endswith(".cpp") and fn != cpp_key:
            stem = fn[:-4]
            h_matching = f"{stem}.h"
            if h_matching in out:
                h_c = out[h_matching]
                m_cls = re.search(r"class\s+(?:\w+_API\s+)?(?P<cls>\w+)\s*:\s*public", h_c)
                if m_cls:
                    cls_name = m_cls.group("cls")
                    new_cpp_c, c_notes = _stub_missing_definitions(h_c, c_content, class_name=cls_name)
                    if new_cpp_c != c_content:
                        out[fn] = new_cpp_c
                        notes.extend(c_notes)

    # 11. Fix C4458: declaration of 'World' hides class member across any C++ file
    for fn, content in list(out.items()):
        if fn.endswith((".cpp", ".h")):
            if "UWorld* World = GetWorld();" in content or "UWorld* World = InWorld;" in content or "UWorld* CurrentWorld = GetWorld();" in content:
                new_c = re.sub(r"\bUWorld\*\s+World\s*=\s*(?:GetWorld\(\)|InWorld);", "UWorld* CurrentWorld = GetWorld();", content)
                new_c = re.sub(r"(!\s*)World\b", r"\g<1>CurrentWorld", new_c)
                new_c = re.sub(r"\bWorld\s*\?", "CurrentWorld ?", new_c)
                new_c = re.sub(r"\bWorld\s*->", "CurrentWorld->", new_c)
                new_c = re.sub(r"\bWorld\s*==\s*nullptr", "CurrentWorld == nullptr", new_c)
                new_c = re.sub(r"\bWorld\s*!=\s*nullptr", "CurrentWorld != nullptr", new_c)
                out[fn] = new_c
                notes.append(f"renamed shadowing World to CurrentWorld in {fn} (fixing C4458)")

    if diags:
        for d in diags:
            if d.get("code") == "C4458":
                msg = d.get("message", "")
                m_var = re.search(r"declaration of '(\w+)' hides class member", msg)
                d_file = Path(d.get("file") or "").name
                for fn, content in list(out.items()):
                    if Path(fn).name == d_file and m_var:
                        var_name = m_var.group(1)
                        if var_name != "World":
                            repl = f"Local{var_name}"
                            new_c = re.sub(rf"\b([\w:<>\*&]+\s+){var_name}\b", rf"\g<1>{repl}", content)
                            new_c = re.sub(rf"\b{var_name}\b", repl, new_c)
                            out[fn] = new_c
                            notes.append(f"renamed shadowing {var_name} to {repl} in {fn} (fixing C4458)")
            if d.get("code") == "C2065" and "'World'" in d.get("message", ""):
                d_file = Path(d.get("file") or "").name
                for fn, content in list(out.items()):
                    if Path(fn).name == d_file:
                        new_c = re.sub(r"(!\s*)World\b", r"\g<1>CurrentWorld", content)
                        new_c = re.sub(r"\bWorld\s*\?", "CurrentWorld ?", new_c)
                        new_c = re.sub(r"\bWorld\s*->", "CurrentWorld->", new_c)
                        out[fn] = new_c
                        notes.append(f"repaired undeclared World to CurrentWorld in {fn} (fixing C2065)")

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
    "C2039": "A member or function was not found (e.g. FVector has no .ToFloat(); FLinearColor has no ::Grey or ::Orange -- use FLinearColor::Gray or FLinearColor(FColor::Orange); or function defined in .cpp but not declared in GFGameImpl.h).",
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
