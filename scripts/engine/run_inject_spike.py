"""WI-3.0 Spike: Enhanced Input simulation in cooked Development and Shipping builds.

Tests that InjectInputForAction with a runtime-created UInputAction drives ACharacter
movement in both Development and Shipping configurations offscreen.
Pass: distance >= 1,000 cm in both builds.
Evidence written to: reports/P3/spike_inject.json
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from src.gameforge_ide.core.settings import get_settings  # noqa: E402

from src.gameforge_ide.core import jobs  # noqa: E402
from src.gameforge_ide.unreal.live_editor import LiveEditorLink  # noqa: E402
from src.gameforge_ide.unreal.toolchain import UnrealToolchain  # noqa: E402

NAME = "GFInjectSpike"
VALIDATION_ROOT = (get_settings().require_dev("validation_root") / r"GFInjectSpike")
REPORT_PATH = REPO_ROOT / "reports" / "P3" / "spike_inject.json"
MAP_PATH = "/Game/Maps/SpikeMap"

SPIKE_CHARACTER_H = """#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "SpikeCharacter.generated.h"

UCLASS()
class GFINJECTSPIKE_API ASpikeCharacter : public ACharacter
{
	GENERATED_BODY()
public:
	ASpikeCharacter();
};
"""

SPIKE_CHARACTER_CPP = """#include "SpikeCharacter.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"

ASpikeCharacter::ASpikeCharacter()
{
	PrimaryActorTick.bCanEverTick = false;
	bUseControllerRotationYaw = false;
	if (GetCapsuleComponent())
	{
		GetCapsuleComponent()->InitCapsuleSize(42.f, 96.0f);
	}
	if (GetCharacterMovement())
	{
		GetCharacterMovement()->bOrientRotationToMovement = true;
		GetCharacterMovement()->RotationRate = FRotator(0.f, 540.f, 0.f);
		GetCharacterMovement()->MaxWalkSpeed = 600.f;
	}
}
"""

SPIKE_FLOOR_H = """#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Components/BoxComponent.h"
#include "SpikeFloor.generated.h"

UCLASS()
class GFINJECTSPIKE_API ASpikeFloor : public AActor
{
	GENERATED_BODY()
public:
	ASpikeFloor();
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UBoxComponent> Box;
};
"""

SPIKE_FLOOR_CPP = """#include "SpikeFloor.h"

ASpikeFloor::ASpikeFloor()
{
	PrimaryActorTick.bCanEverTick = false;
	Box = CreateDefaultSubobject<UBoxComponent>(TEXT("FloorBox"));
	Box->InitBoxExtent(FVector(20000.f, 20000.f, 100.f));
	Box->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	RootComponent = Box;
}
"""

SPIKE_PLAYER_CONTROLLER_H = """#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "SpikePlayerController.generated.h"

class UInputAction;
class UInputMappingContext;

UCLASS()
class GFINJECTSPIKE_API ASpikePlayerController : public APlayerController
{
	GENERATED_BODY()
public:
	ASpikePlayerController();
	UInputAction* FindAction(FName ActionId) const;
	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> MappingContext;
	bool IsContextAdded() const { return bContextAdded; }

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	void BuildDefaultInput();
	void HandleMove(const FInputActionValue& Value);

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<UInputAction>> Actions;

	bool bContextAdded = false;
};
"""

SPIKE_PLAYER_CONTROLLER_CPP = """#include "SpikePlayerController.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "InputCoreTypes.h"
#include "GameFramework/Pawn.h"

ASpikePlayerController::ASpikePlayerController()
{
}

UInputAction* ASpikePlayerController::FindAction(FName ActionId) const
{
	const TObjectPtr<UInputAction>* Found = Actions.Find(ActionId);
	return Found ? Found->Get() : nullptr;
}

void ASpikePlayerController::BuildDefaultInput()
{
	if (Actions.Num() > 0) { return; }
	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_Spike"));
	UInputAction* Move = NewObject<UInputAction>(this, FName(TEXT("IA_Move")));
	Move->ValueType = EInputActionValueType::Axis2D;
	Actions.Add(FName(TEXT("IA_Move")), Move);

	auto Swizzle = [this]() { return NewObject<UInputModifierSwizzleAxis>(MappingContext); };
	auto Negate = [this]() { return NewObject<UInputModifierNegate>(MappingContext); };
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::W); M.Modifiers.Add(Swizzle()); }
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::S); M.Modifiers.Add(Swizzle()); M.Modifiers.Add(Negate()); }
	MappingContext->MapKey(Move, EKeys::D);
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::A); M.Modifiers.Add(Negate()); }
}

void ASpikePlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	BuildDefaultInput();
	if (UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(InputComponent))
	{
		EIC->BindAction(FindAction(TEXT("IA_Move")), ETriggerEvent::Triggered, this, &ASpikePlayerController::HandleMove);
	}
}

void ASpikePlayerController::BeginPlay()
{
	Super::BeginPlay();
	BuildDefaultInput();
	if (!bContextAdded)
	{
		if (UEnhancedInputLocalPlayerSubsystem* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
		{
			Sub->AddMappingContext(MappingContext, 0);
			bContextAdded = true;
		}
	}
}

void ASpikePlayerController::HandleMove(const FInputActionValue& Value)
{
	const FVector2D Axis = Value.Get<FVector2D>();
	if (APawn* P = GetPawn())
	{
		const FRotator Yaw(0.f, GetControlRotation().Yaw, 0.f);
		P->AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Axis.Y);
		P->AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Axis.X);
	}
}
"""

SPIKE_GAME_MODE_H = """#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SpikeGameMode.generated.h"

UCLASS()
class GFINJECTSPIKE_API ASpikeGameMode : public AGameModeBase
{
	GENERATED_BODY()
public:
	ASpikeGameMode();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
private:
	void FinishSpike();

	FVector StartLocation = FVector::ZeroVector;
	float WarmupSeconds = 0.5f;
	float InjectionSecondsRemaining = 2.0f;
	bool bInjecting = false;
	bool bFinished = false;
	FString OutPath;
};
"""

SPIKE_GAME_MODE_CPP = """#include "SpikeGameMode.h"
#include "SpikeCharacter.h"
#include "SpikePlayerController.h"
#include "SpikeFloor.h"
#include "EnhancedInputSubsystems.h"
#include "InputActionValue.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

ASpikeGameMode::ASpikeGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	DefaultPawnClass = ASpikeCharacter::StaticClass();
	PlayerControllerClass = ASpikePlayerController::StaticClass();
}

void ASpikeGameMode::BeginPlay()
{
	Super::BeginPlay();

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	GetWorld()->SpawnActor<ASpikeFloor>(FVector(0.f, 0.f, -100.f), FRotator::ZeroRotator, SpawnParams);

	if (!FParse::Value(FCommandLine::Get(), TEXT("GFSpikeOut="), OutPath) || OutPath.IsEmpty())
	{
		OutPath = FPaths::ProjectSavedDir() / TEXT("GameForge/spike_inject_result.json");
	}
}

void ASpikeGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bFinished) { return; }

	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	ASpikePlayerController* SPC = Cast<ASpikePlayerController>(PC);

	if (!bInjecting)
	{
		if (Pawn && SPC && SPC->IsContextAdded())
		{
			WarmupSeconds -= DeltaSeconds;
			if (WarmupSeconds <= 0.f)
			{
				StartLocation = Pawn->GetActorLocation();
				bInjecting = true;
				InjectionSecondsRemaining = 2.0f;
			}
		}
		return;
	}

	if (bInjecting)
	{
		if (Pawn && SPC)
		{
			if (ULocalPlayer* LP = SPC->GetLocalPlayer())
			{
				if (UEnhancedInputLocalPlayerSubsystem* Sub = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
				{
					if (UInputAction* MoveAct = SPC->FindAction(TEXT("IA_Move")))
					{
						static const TArray<UInputModifier*> NoModifiers;
						static const TArray<UInputTrigger*> NoTriggers;
						Sub->InjectInputForAction(MoveAct, FInputActionValue(FVector2D(0.f, 1.f)), NoModifiers, NoTriggers);
					}
				}
			}
		}

		InjectionSecondsRemaining -= DeltaSeconds;
		if (InjectionSecondsRemaining <= 0.0f)
		{
			FinishSpike();
		}
	}
}

void ASpikeGameMode::FinishSpike()
{
	if (bFinished) { return; }
	bFinished = true;
	bInjecting = false;

	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	FVector EndLocation = Pawn ? Pawn->GetActorLocation() : StartLocation;
	float Dist2D = FVector::Dist2D(StartLocation, EndLocation);
	float Dist3D = FVector::Dist(StartLocation, EndLocation);

	FString Json = FString::Printf(
		TEXT("{\\\"passed\\\": %s, \\\"distance_cm\\\": %.2f, \\\"distance_3d_cm\\\": %.2f, \\\"start\\\": [%.1f, %.1f, %.1f], \\\"end\\\": [%.1f, %.1f, %.1f]}"),
		Dist2D >= 1000.f ? TEXT("true") : TEXT("false"),
		Dist2D, Dist3D,
		StartLocation.X, StartLocation.Y, StartLocation.Z,
		EndLocation.X, EndLocation.Y, EndLocation.Z
	);

	IFileManager::Get().MakeDirectory(*FPaths::GetPath(OutPath), true);
	FFileHelper::SaveStringToFile(Json, *OutPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);

	FPlatformMisc::RequestExit(false);
}
"""


def build_spike_level(uproject: Path) -> bool:
    link = LiveEditorLink(uproject)
    link.prepare_project()
    link.launch(["-RenderOffscreen", "-ResX=1280", "-ResY=720"], log_path=VALIDATION_ROOT / "level_editor.log")
    try:
        link.connect(discovery_timeout_s=300)
        link.call("new_level", {"level_path": MAP_PATH})
        link.call("spawn_actor", {
            "actor_class": "StaticMeshActor", "label": "Spike_Floor",
            "static_mesh": "/Engine/BasicShapes/Cube.Cube",
            "location": {"x": 0, "y": 0, "z": -50}, "scale": {"x": 100, "y": 100, "z": 1}
        })
        link.call("spawn_actor", {
            "actor_class": "DirectionalLight", "label": "Spike_Sun",
            "light_intensity": 6.0, "mobility": "Movable",
            "rotation": {"pitch": -45, "yaw": 30, "roll": 0}, "location": {"x": 0, "y": 0, "z": 800}
        })
        link.call("spawn_actor", {
            "actor_class": "PlayerStart", "label": "Spike_PlayerStart",
            "location": {"x": 0, "y": 0, "z": 100}
        })
        link.call("save_all", {})
        return True
    finally:
        link.stop()


def run_binary(exe: Path, out_json: Path, timeout_s: float = 60.0) -> dict:
    if out_json.exists():
        out_json.unlink()
    argv = [
        str(exe),
        "-RenderOffscreen",
        "-unattended",
        "-nosplash",
        "-nosound",
        f"-GFSpikeOut={out_json}",
    ]
    proc = jobs.spawn(argv)
    try:
        code = proc.wait(timeout=timeout_s)
    except Exception as exc:
        UnrealToolchain.kill_tree(proc)
        raise RuntimeError(f"Binary run timed out or failed: {exc}")
    if not out_json.exists():
        raise RuntimeError(f"Binary exited with code {code} but no result JSON written at {out_json}")
    return json.loads(out_json.read_text(encoding="utf-8"))


def main() -> int:
    print(f"=== Starting WI-3.0 Enhanced Input Injection Spike ===")
    tc = UnrealToolchain()

    if VALIDATION_ROOT.exists():
        try:
            shutil.rmtree(VALIDATION_ROOT)
        except Exception as exc:
            print(f"Warning cleaning validation root: {exc}")

    VALIDATION_ROOT.mkdir(parents=True, exist_ok=True)
    extra_files = {
        f"Source/{NAME}/SpikeCharacter.h": SPIKE_CHARACTER_H,
        f"Source/{NAME}/SpikeCharacter.cpp": SPIKE_CHARACTER_CPP,
        f"Source/{NAME}/SpikeFloor.h": SPIKE_FLOOR_H,
        f"Source/{NAME}/SpikeFloor.cpp": SPIKE_FLOOR_CPP,
        f"Source/{NAME}/SpikePlayerController.h": SPIKE_PLAYER_CONTROLLER_H,
        f"Source/{NAME}/SpikePlayerController.cpp": SPIKE_PLAYER_CONTROLLER_CPP,
        f"Source/{NAME}/SpikeGameMode.h": SPIKE_GAME_MODE_H,
        f"Source/{NAME}/SpikeGameMode.cpp": SPIKE_GAME_MODE_CPP,
    }

    print(f"Scaffolding {NAME}...")
    scaffold = tc.scaffold_cpp_project(
        VALIDATION_ROOT,
        NAME,
        extra_files=extra_files,
        module_deps=["EnhancedInput"],
        default_map=MAP_PATH,
        game_mode=f"/Script/{NAME}.SpikeGameMode",
    )
    uproject = Path(scaffold["uproject"])

    print(f"Building {NAME}Editor...")
    b_editor = tc.build(uproject, f"{NAME}Editor", log_dir=VALIDATION_ROOT / "logs")
    if not b_editor.ok:
        print(f"Editor build FAILED: {b_editor.errors} {b_editor.diagnostics}")
        return 1
    print(f"Editor build OK ({b_editor.duration_s}s)")

    print(f"Creating level {MAP_PATH} via LiveEditorLink...")
    if not build_spike_level(uproject):
        print("Level creation FAILED")
        return 1
    print(f"Level {MAP_PATH} created.")

    # 1. Package Development
    dev_archive = VALIDATION_ROOT / "package_dev"
    print(f"Packaging Development to {dev_archive}...")
    b_pkg_dev = tc.package(uproject, dev_archive, configuration="Development")
    if not b_pkg_dev.ok:
        print(f"Development package FAILED: {b_pkg_dev.errors} {b_pkg_dev.diagnostics}")
        return 1
    dev_exe = dev_archive / "Windows" / f"{NAME}.exe"
    print(f"Development package OK ({b_pkg_dev.duration_s}s), exe={dev_exe}")

    # Run Development
    dev_out = VALIDATION_ROOT / "spike_dev_result.json"
    print(f"Running Development binary...")
    t0 = time.monotonic()
    dev_res = run_binary(dev_exe, dev_out)
    dev_duration = round(time.monotonic() - t0, 2)
    print(f"Development result: {dev_res} (took {dev_duration}s)")

    # 2. Package Shipping
    ship_archive = VALIDATION_ROOT / "package_ship"
    print(f"Packaging Shipping to {ship_archive}...")
    b_pkg_ship = tc.package(uproject, ship_archive, configuration="Shipping")
    if not b_pkg_ship.ok:
        print(f"Shipping package FAILED: {b_pkg_ship.errors} {b_pkg_ship.diagnostics}")
        return 1
    ship_exe = ship_archive / "Windows" / f"{NAME}.exe"
    print(f"Shipping package OK ({b_pkg_ship.duration_s}s), exe={ship_exe}")

    # Run Shipping
    ship_out = VALIDATION_ROOT / "spike_ship_result.json"
    print(f"Running Shipping binary...")
    t0 = time.monotonic()
    ship_res = run_binary(ship_exe, ship_out)
    ship_duration = round(time.monotonic() - t0, 2)
    print(f"Shipping result: {ship_res} (took {ship_duration}s)")

    # Verify pass criteria
    dev_dist = dev_res.get("distance_cm", 0.0)
    ship_dist = ship_res.get("distance_cm", 0.0)
    passed = (dev_dist >= 1000.0) and (ship_dist >= 1000.0)

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": passed,
        "criteria": "distance_cm >= 1000.0 in both Development and Shipping builds",
        "development": {
            "exe": str(dev_exe),
            "distance_cm": dev_dist,
            "result": dev_res,
            "duration_s": dev_duration,
            "package_duration_s": b_pkg_dev.duration_s,
        },
        "shipping": {
            "exe": str(ship_exe),
            "distance_cm": ship_dist,
            "result": ship_res,
            "duration_s": ship_duration,
            "package_duration_s": b_pkg_ship.duration_s,
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"Wrote spike evidence to {REPORT_PATH}")
    print(f"SPIKE VERDICT: {'PASS' if passed else 'FAIL'}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
