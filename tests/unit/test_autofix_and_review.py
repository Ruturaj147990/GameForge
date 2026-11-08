"""Deterministic repair rung and vision-review parsing."""

from src.gameforge_ide.pipeline.autofix import autofix, hints_for
from src.gameforge_ide.pipeline.vision_review import _parse

H = '''#pragma once
#include "CoreMinimal.h"
#include "GFGameImpl.generated.h"
#include "GFGameBase.h"
UCLASS()
class X_API AGFGameImpl : public AGFGameBase
{
    GENERATED_BODY()
public:
    virtual FString GetStatusText() override;
    virtual bool RunSelfTest(FString& OutReport) override;
private:
    int32 Score = 0;
};
'''
CPP = '''#include "GFGameImpl.h"
#include "GFGameImpl.generated.h"
AGFGameImpl::AGFGameImpl() {}
FString AGFGameImpl::GetStatusText()
{
    return TEXT("x");
}
void AGFGameImpl::SpawnMole(int32 Count, const FVector& Where)
{
}
float AGFGameImpl::Spread() const
{
    return 1.f;
}
bool AGFGameImpl::RunSelfTest(FString& OutReport) { return true; }
'''


def test_autofix_repairs_the_common_model_mistakes():
    out, notes = autofix({"GFGameImpl.h": H, "GFGameImpl.cpp": CPP})
    h, cpp = out["GFGameImpl.h"], out["GFGameImpl.cpp"]
    assert "GFGameImpl.generated.h" not in cpp
    lines = [l.strip() for l in h.splitlines() if l.strip().startswith("#include")]
    assert lines[-1] == '#include "GFGameImpl.generated.h"'
    assert "virtual FString GetStatusText() const override;" in h
    assert "AGFGameImpl::GetStatusText() const" in cpp
    assert "void SpawnMole(int32 Count, const FVector& Where);" in h
    assert "float Spread() const;" in h
    assert "AGFGameImpl();" in h
    assert len(notes) >= 5


def test_autofix_is_idempotent_and_leaves_clean_code_alone():
    once, _ = autofix({"GFGameImpl.h": H, "GFGameImpl.cpp": CPP})
    twice, notes = autofix(once)
    assert twice == once and notes == []


def test_hints_are_keyed_by_error_code_and_deduplicated():
    text = hints_for([{"code": "C2039"}, {"code": "C2039"}, {"code": "C3668"}, {"code": "C2450"}, {"code": "C2046"}, {"code": "C9999"}])
    assert text.count("C2039") == 1 and "C3668" in text and "C2450" in text and "C2046" in text and "C9999" not in text
    assert "FKey cannot be used in a switch expression" in text


def test_autofix_converts_fkey_switch_to_if_else():
    cpp_bad = '''#include "GFGameImpl.h"
void AGFGameImpl::OnKey(FKey Key)
{
	switch (Key)
	{
	case EKeys::W:
		MoveUp();
		break;
	case EKeys::S:
		MoveDown();
		break;
	case EKeys::A:
	case EKeys::Left:
		MoveLeft();
		break;
	default:
		DoOther();
		break;
	}
}
'''
    out, notes = autofix({"GFGameImpl.h": H, "GFGameImpl.cpp": cpp_bad})
    cpp = out["GFGameImpl.cpp"]
    assert "switch (Key)" not in cpp
    assert "if (Key == EKeys::W)" in cpp
    assert "else if (Key == EKeys::S)" in cpp
    assert "Key == EKeys::A || Key == EKeys::Left" in cpp
    assert "else" in cpp
    assert any("switch statement on FKey" in n for n in notes)


def test_autofix_repairs_tofloat_and_fquat_construction():
    cpp_bad = '''#include "GFGameImpl.h"
void AGFGameImpl::SpawnBullet(const FVector& Origin, const FVector& Direction)
{
	FQuat Rot = FQuat(FVector(0, 0, 1), Direction.ToFloat());
	float speed = Direction.ToFloat();
}
'''
    out, notes = autofix({"GFGameImpl.h": H, "GFGameImpl.cpp": cpp_bad})
    cpp = out["GFGameImpl.cpp"]
    assert ".ToFloat()" not in cpp
    assert "Direction.Rotation().Quaternion()" in cpp
    assert any("ToFloat" in n for n in notes)


def test_vision_verdict_parsing():
    assert _parse('```json\n{"matches_request": false, "problems": ["too many"]}\n```')["problems"] == ["too many"]
    assert _parse("no json here") is None
