"""Free-form game host framework (UE 5.7 C++).

The framework owns everything that small and large models get wrong most often: camera, input
routing, HUD, lighting, cooked engine meshes, multi-primitive prop spawning, and the -GFSelfTest
plumbing in shipped builds.
The model writes ONE class, AGFGameImpl : AGFGameBase, in GFGameImpl.h / GFGameImpl.cpp.

API_DOC is the exact contract given to the authoring model.
"""

from __future__ import annotations

from typing import Dict

API_DOC = r'''
You are writing the gameplay for an Unreal Engine 5.7 C++ game. A host framework already exists.
Write exactly two files: GFGameImpl.h and GFGameImpl.cpp, defining:

    UCLASS()
    class __API__ AGFGameImpl : public AGFGameBase
    {
        GENERATED_BODY()
    public:
        // override the virtuals you need
    };

GFGameImpl.h must start with:
    #pragma once
    #include "CoreMinimal.h"
    #include "GFGameBase.h"
    #include "GFGameImpl.generated.h"
GFGameImpl.cpp must start with:
    #include "GFGameImpl.h"

AGFGameBase (already implemented; do not redefine) gives you:
  Virtuals to override (all optional except RunSelfTest):
    virtual void StartGame();                                  // build the scene; called at start and on restart
    virtual void OnClicked(AActor* Actor, const FVector& Point); // left click; Actor may be nullptr
    virtual void OnKey(FKey Key);                              // any key pressed (EKeys::SpaceBar, EKeys::A, ...)
    virtual void OnTick(float DeltaSeconds);                   // every frame
    virtual FString GetStatusText() const;                     // primary HUD line (score, health, turn, result)
    virtual FString GetSecondaryStatusText() const;            // secondary HUD line (wave, timer, ammo, inventory, lap)
    virtual FString GetControlsText() const;                   // shown at the bottom of the screen
    virtual FVector GetCameraFocus() const;                    // world point the camera dynamically tracks (default 0,0,0)
    virtual float GetCameraDistance() const;                   // default 1500 (cm)
    virtual float GetCameraPitch() const;                      // default -60 degrees (-85 top-down, -25 third-person)
    virtual float GetCameraYaw() const;                        // default 0 degrees
    virtual float GetCameraFOV() const;                        // default 60 degrees
    virtual bool RunSelfTest(FString& OutReport);              // REQUIRED: drive the game through its own
                                                               // functions (call OnClicked/OnKey/OnTick directly),
                                                               // check the rules, return true only if they hold
  Helpers:
    AActor* SpawnShape(EGFShape Shape, const FVector& Location, const FVector& Scale, const FLinearColor& Color);
        // EGFShape::Cube, Sphere, Cylinder, Cone, Plane. Basic shapes are 100 cm. Returns the actor.
        // Scale is a MULTIPLIER: FVector(1.f) = 100 cm, FVector(0.5f) = 50 cm. Never pass 100 for "1 metre".
    AActor* SpawnProp(const FString& Recipe, const FVector& Location, const FVector& Scale, const FLinearColor& Color);
        // Spawns a multi-primitive compound prop ("crate", "pillar", "tree", "turret", "vehicle", "portal") and
        // returns its root shape actor.
    AActor* SpawnText(const FString& Text, const FVector& Location, float HeightCm, const FLinearColor& Color);
        // 3D text label in the world, facing the camera. Destroyed by ClearShapes like shapes.
    void SetText(AActor* TextActor, const FString& Text);
    void SetShapeColor(AActor* Shape, const FLinearColor& Color);
    void MoveShape(AActor* Shape, const FVector& Location);
    void DestroyShape(AActor* Shape);
    void ClearShapes();                                        // destroys every shape this game spawned
    bool IsKeyDown(FKey Key) const;                            // for held keys (movement)
    void RestartGame();                                        // ClearShapes() + StartGame()
    FRandomStream Rng;                                         // seeded randomness
  Rules:
    - Copy override signatures EXACTLY, including const: e.g.
      virtual FString GetStatusText() const override;   virtual FString GetControlsText() const override;
      virtual bool RunSelfTest(FString& OutReport) override;   virtual void OnClicked(AActor* Actor, const FVector& Point) override;
    - Every member function and member variable you use in GFGameImpl.cpp MUST be declared inside the class in
      GFGameImpl.h. Helper functions are private member functions of AGFGameImpl.
    - Include "GFGameImpl.generated.h" ONLY in GFGameImpl.h, as its last #include. Never include it in the .cpp.
    - Use Rng (inherited) for randomness: Rng.RandRange(0, N - 1), Rng.FRandRange(a, b).
    - RESTART RULE: RestartGame() destroys every shape and then calls StartGame(). So StartGame() must begin by
      resetting ALL of your state: Empty()/Reset() every array or map that holds shapes, and reset every score,
      timer and flag. Never keep pointers to shapes across a restart.
    - World units are centimetres; +Z is up; the floor is at Z=0. Keep the play area within about 2000 cm.
    - Keep all game state in UPROPERTY() members or plain C++ members of AGFGameImpl.
    - Use only Engine/Core APIs already included by the framework (CoreMinimal, GameFramework, Math).
    - FKey is a C++ struct, NOT an integer or enum: NEVER write switch (Key); you MUST use if (Key == EKeys::W) else if (Key == EKeys::S) instead.
    - FVector has no .ToFloat() member: to rotate an actor towards a direction, use Actor->SetActorRotation(Direction.Rotation()); for vector length, use Direction.Size().
    - Do not create new UCLASSes, components, widgets, or assets. Do not use Blueprints.
    - RunSelfTest must not rely on real time passing; call OnTick(0.1f) in a loop if needed.
    - Use TEXT("...") for string literals and FString::Printf for formatting.
'''

GAME_BASE_H = r'''#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "InputCoreTypes.h"
#include "Math/RandomStream.h"
#include "GFGameBase.generated.h"

class UStaticMesh;
class UMaterialInterface;

UENUM()
enum class EGFShape : uint8 { Cube, Sphere, Cylinder, Cone, Plane };

UCLASS(Abstract)
class __API__ AGFGameBase : public AActor
{
	GENERATED_BODY()

public:
	AGFGameBase();
	virtual void Tick(float DeltaSeconds) override;

	virtual void StartGame() {}
	virtual void OnClicked(AActor* Actor, const FVector& Point) {}
	virtual void OnKey(FKey Key) {}
	virtual void OnTick(float DeltaSeconds) {}
	virtual FString GetStatusText() const { return FString(); }
	virtual FString GetSecondaryStatusText() const { return FString(); }
	virtual FString GetControlsText() const { return TEXT("R: restart   |   Esc: quit"); }
	virtual FVector GetCameraFocus() const { return FVector::ZeroVector; }
	virtual float GetCameraDistance() const { return 1500.f; }
	virtual float GetCameraPitch() const { return -60.f; }
	virtual float GetCameraYaw() const { return 0.f; }
	virtual float GetCameraFOV() const { return 60.f; }
	virtual bool RunSelfTest(FString& OutReport) { OutReport = TEXT("no self-test implemented"); return false; }

	AActor* SpawnShape(EGFShape Shape, const FVector& Location, const FVector& Scale, const FLinearColor& Color);
	AActor* SpawnProp(const FString& Recipe, const FVector& Location, const FVector& Scale, const FLinearColor& Color);
	AActor* SpawnText(const FString& Text, const FVector& Location, float HeightCm, const FLinearColor& Color);
	void SetText(AActor* TextActor, const FString& Text);
	void SetShapeColor(AActor* Shape, const FLinearColor& Color);
	void MoveShape(AActor* Shape, const FVector& Location);
	void DestroyShape(AActor* Shape);
	void ClearShapes();
	bool IsKeyDown(FKey Key) const;
	void RestartGame();
	int32 NumShapes() const { return SpawnedShapes.Num(); }

	FRandomStream Rng;

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY() TArray<TObjectPtr<AActor>> SpawnedShapes;
	UPROPERTY() TObjectPtr<UStaticMesh> Meshes[5];
	UPROPERTY() TObjectPtr<UMaterialInterface> ShapeMaterial;
};
'''

GAME_BASE_CPP = r'''#include "GFGameBase.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/TextRenderActor.h"
#include "Components/TextRenderComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

AGFGameBase::AGFGameBase()
{
	PrimaryActorTick.bCanEverTick = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cone(TEXT("/Engine/BasicShapes/Cone.Cone"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Mat(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	Meshes[0] = Cube.Object; Meshes[1] = Sphere.Object; Meshes[2] = Cylinder.Object;
	Meshes[3] = Cone.Object; Meshes[4] = Plane.Object;
	ShapeMaterial = Mat.Object;
	Rng.Initialize(0x5EED);
}

void AGFGameBase::BeginPlay()
{
	Super::BeginPlay();
	StartGame();
}

void AGFGameBase::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	OnTick(DeltaSeconds);
}

AActor* AGFGameBase::SpawnShape(EGFShape Shape, const FVector& Location, const FVector& Scale, const FLinearColor& Color)
{
	UWorld* World = GetWorld();
	if (!World) return nullptr;
	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* A = World->SpawnActor<AStaticMeshActor>(Location, FRotator::ZeroRotator, Params);
	if (!A) return nullptr;
	A->SetMobility(EComponentMobility::Movable);
	UStaticMeshComponent* C = A->GetStaticMeshComponent();
	C->SetStaticMesh(Meshes[FMath::Clamp((int32)Shape, 0, 4)]);
	C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	C->SetCollisionResponseToAllChannels(ECR_Ignore);
	C->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	if (ShapeMaterial)
	{
		if (UMaterialInstanceDynamic* MID = C->CreateDynamicMaterialInstance(0, ShapeMaterial))
		{
			MID->SetVectorParameterValue(TEXT("Color"), Color);
		}
	}
	FVector S = Scale;
	if (S.GetMax() > 25.f)
	{
		UE_LOG(LogTemp, Warning, TEXT("GF_HOST SpawnShape scale %s looks like centimetres; using %s"), *S.ToString(), *(S / 100.f).ToString());
		S /= 100.f;
	}
	A->SetActorScale3D(S);
	SpawnedShapes.Add(A);
	return A;
}

AActor* AGFGameBase::SpawnProp(const FString& Recipe, const FVector& Location, const FVector& Scale, const FLinearColor& Color)
{
	FString R = Recipe.ToLower();
	if (R.Contains(TEXT("tree")))
	{
		AActor* Trunk = SpawnShape(EGFShape::Cylinder, Location + FVector(0.f, 0.f, 60.f * Scale.Z), FVector(0.35f * Scale.X, 0.35f * Scale.Y, 1.2f * Scale.Z), FLinearColor(0.38f, 0.24f, 0.12f));
		SpawnShape(EGFShape::Cone, Location + FVector(0.f, 0.f, 160.f * Scale.Z), FVector(1.6f * Scale.X, 1.6f * Scale.Y, 1.8f * Scale.Z), Color);
		return Trunk;
	}
	if (R.Contains(TEXT("turret")) || R.Contains(TEXT("tower")))
	{
		AActor* Base = SpawnShape(EGFShape::Cylinder, Location + FVector(0.f, 0.f, 40.f * Scale.Z), FVector(1.1f * Scale.X, 1.1f * Scale.Y, 0.8f * Scale.Z), FLinearColor(0.3f, 0.32f, 0.38f));
		SpawnShape(EGFShape::Sphere, Location + FVector(0.f, 0.f, 100.f * Scale.Z), FVector(0.8f * Scale.X, 0.8f * Scale.Y, 0.8f * Scale.Z), Color);
		return Base;
	}
	if (R.Contains(TEXT("vehicle")) || R.Contains(TEXT("car")) || R.Contains(TEXT("kart")))
	{
		AActor* Chassis = SpawnShape(EGFShape::Cube, Location + FVector(0.f, 0.f, 35.f * Scale.Z), FVector(1.8f * Scale.X, 1.0f * Scale.Y, 0.5f * Scale.Z), Color);
		SpawnShape(EGFShape::Cube, Location + FVector(-15.f * Scale.X, 0.f, 70.f * Scale.Z), FVector(0.9f * Scale.X, 0.8f * Scale.Y, 0.4f * Scale.Z), Color * 0.8f);
		return Chassis;
	}
	if (R.Contains(TEXT("pillar")) || R.Contains(TEXT("column")))
	{
		AActor* Col = SpawnShape(EGFShape::Cylinder, Location + FVector(0.f, 0.f, 120.f * Scale.Z), FVector(0.7f * Scale.X, 0.7f * Scale.Y, 2.4f * Scale.Z), Color);
		SpawnShape(EGFShape::Cube, Location + FVector(0.f, 0.f, 250.f * Scale.Z), FVector(1.0f * Scale.X, 1.0f * Scale.Y, 0.25f * Scale.Z), Color * 0.85f);
		return Col;
	}
	return SpawnShape(EGFShape::Cube, Location, Scale, Color);
}

AActor* AGFGameBase::SpawnText(const FString& Text, const FVector& Location, float HeightCm, const FLinearColor& Color)
{
	UWorld* World = GetWorld();
	if (!World) return nullptr;
	FActorSpawnParameters Params;
	Params.Owner = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const FRotator Facing(-GetCameraPitch(), GetCameraYaw() + 180.f, 0.f);
	ATextRenderActor* A = World->SpawnActor<ATextRenderActor>(Location, Facing, Params);
	if (!A) return nullptr;
	UTextRenderComponent* T = A->GetTextRender();
	T->SetText(FText::FromString(Text));
	T->SetWorldSize(FMath::Clamp(HeightCm, 5.f, 1000.f));
	T->SetTextRenderColor(Color.ToFColor(true));
	T->SetHorizontalAlignment(EHTA_Center);
	T->SetVerticalAlignment(EVRTA_TextCenter);
	SpawnedShapes.Add(A);
	return A;
}

void AGFGameBase::SetText(AActor* TextActor, const FString& Text)
{
	if (ATextRenderActor* A = Cast<ATextRenderActor>(TextActor))
	{
		A->GetTextRender()->SetText(FText::FromString(Text));
	}
}

void AGFGameBase::SetShapeColor(AActor* Shape, const FLinearColor& Color)
{
	if (AStaticMeshActor* A = Cast<AStaticMeshActor>(Shape))
	{
		if (UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(A->GetStaticMeshComponent()->GetMaterial(0)))
		{
			MID->SetVectorParameterValue(TEXT("Color"), Color);
		}
	}
}

void AGFGameBase::MoveShape(AActor* Shape, const FVector& Location)
{
	if (IsValid(Shape)) Shape->SetActorLocation(Location);
}

void AGFGameBase::DestroyShape(AActor* Shape)
{
	if (IsValid(Shape))
	{
		SpawnedShapes.Remove(Shape);
		Shape->Destroy();
	}
}

void AGFGameBase::ClearShapes()
{
	for (AActor* A : SpawnedShapes)
	{
		if (IsValid(A)) A->Destroy();
	}
	SpawnedShapes.Reset();
}

bool AGFGameBase::IsKeyDown(FKey Key) const
{
	const APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	return PC && PC->IsInputKeyDown(Key);
}

void AGFGameBase::RestartGame()
{
	ClearShapes();
	StartGame();
}
'''

HOST_H = r'''#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/HUD.h"
#include "GameFramework/PlayerController.h"
#include "GFHost.generated.h"

class AGFGameBase;
class ACameraActor;

UCLASS()
class __API__ AGFHostGameMode : public AGameModeBase
{
	GENERATED_BODY()
public:
	AGFHostGameMode();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	AGFGameBase* GetGame() const { return Game; }
	void ApplyViewTarget(APlayerController* PC);
private:
	void EnsureLighting();
	void UpdateCameraTransform();
	void RunSelfTest();
	void CaptureEvidence();
	void FinishSelfTest();
	UPROPERTY() TObjectPtr<AGFGameBase> Game;
	UPROPERTY() TObjectPtr<ACameraActor> Camera;
	FTimerHandle SelfTestTimer;
	bool bSelfTestPassed = false;
};

UCLASS()
class __API__ AGFHostController : public APlayerController
{
	GENERATED_BODY()
public:
	AGFHostController();
	virtual void SetupInputComponent() override;
	virtual void BeginPlay() override;
private:
	void OnLeftClick();
	void OnAnyKey(FKey Key);
};

UCLASS()
class __API__ AGFHostHUD : public AHUD
{
	GENERATED_BODY()
public:
	virtual void DrawHUD() override;
};
'''

HOST_CPP = r'''#include "GFHost.h"
#include "GFGameBase.h"
#include "GFGameImpl.h"
#include "GFTitle.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InputComponent.h"
#include "Components/LightComponent.h"
#include "Engine/Canvas.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "TimerManager.h"
#include "UnrealClient.h"

AGFHostGameMode::AGFHostGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	DefaultPawnClass = nullptr;
	PlayerControllerClass = AGFHostController::StaticClass();
	HUDClass = AGFHostHUD::StaticClass();
}

void AGFHostGameMode::BeginPlay()
{
	Super::BeginPlay();
	EnsureLighting();
	Game = GetWorld()->SpawnActor<AGFGameImpl>(AGFGameImpl::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator);
	if (!Game)
	{
		UE_LOG(LogTemp, Error, TEXT("GF_HOST could not spawn AGFGameImpl"));
		return;
	}
	const float Pitch = Game->GetCameraPitch();
	const float Yaw = Game->GetCameraYaw();
	const FRotator CamRot(Pitch, Yaw, 0.f);
	const FVector Dir = CamRot.Vector();
	Camera = GetWorld()->SpawnActor<ACameraActor>(ACameraActor::StaticClass(),
		Game->GetCameraFocus() - Dir * Game->GetCameraDistance(), CamRot);
	if (Camera)
	{
		UCameraComponent* Cam = Camera->GetCameraComponent();
		Cam->SetFieldOfView(FMath::Clamp(Game->GetCameraFOV(), 30.f, 110.f));
		Cam->bConstrainAspectRatio = false;
		Cam->PostProcessSettings.bOverride_MotionBlurAmount = true;
		Cam->PostProcessSettings.MotionBlurAmount = 0.f;
		Cam->PostProcessSettings.bOverride_AutoExposureBias = true;
		Cam->PostProcessSettings.AutoExposureBias = -1.0f;
	}
	if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		ApplyViewTarget(PC);
	}
	UE_LOG(LogTemp, Log, TEXT("GF_READY %s"), GFTitle::Title());
	if (FParse::Param(FCommandLine::Get(), TEXT("GFSelfTest")))
	{
		GetWorldTimerManager().SetTimer(SelfTestTimer, this, &AGFHostGameMode::RunSelfTest, 1.0f, false);
	}
}

void AGFHostGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UpdateCameraTransform();
}

void AGFHostGameMode::UpdateCameraTransform()
{
	if (!Game || !Camera) return;
	const float Pitch = Game->GetCameraPitch();
	const float Yaw = Game->GetCameraYaw();
	const FRotator CamRot(Pitch, Yaw, 0.f);
	const FVector Dir = CamRot.Vector();
	Camera->SetActorLocationAndRotation(Game->GetCameraFocus() - Dir * Game->GetCameraDistance(), CamRot);
}

void AGFHostGameMode::ApplyViewTarget(APlayerController* PC)
{
	if (PC && Camera) PC->SetViewTarget(Camera);
}

void AGFHostGameMode::EnsureLighting()
{
	for (TActorIterator<ADirectionalLight> It(GetWorld()); It; ++It)
	{
		return;
	}
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ADirectionalLight* Sun = GetWorld()->SpawnActor<ADirectionalLight>(ADirectionalLight::StaticClass(),
		FVector(0.f, 0.f, 1000.f), FRotator(-50.f, 35.f, 0.f), Params);
	if (Sun && Sun->GetLightComponent())
	{
		Sun->GetRootComponent()->SetMobility(EComponentMobility::Movable);
		Sun->GetLightComponent()->SetIntensity(10.f);
	}
}

void AGFHostGameMode::RunSelfTest()
{
	FString Report;
	bSelfTestPassed = Game && Game->RunSelfTest(Report);
	UpdateCameraTransform();
	if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		ApplyViewTarget(PC);
		const bool bCameraOk = PC->GetViewTarget() == Camera;
		Report += FString::Printf(TEXT(" camera_ok=%d"), bCameraOk ? 1 : 0);
		bSelfTestPassed = bSelfTestPassed && bCameraOk;
	}
	if (Game)
	{
		Report += FString::Printf(TEXT(" status=\"%s\""), *Game->GetStatusText());
	}
	UE_LOG(LogTemp, Display, TEXT("GF_SELFTEST %s %s"), bSelfTestPassed ? TEXT("PASS") : TEXT("FAIL"), *Report);
	GetWorldTimerManager().SetTimer(SelfTestTimer, this, &AGFHostGameMode::CaptureEvidence, 3.0f, false);
}

void AGFHostGameMode::CaptureEvidence()
{
	UE_LOG(LogTemp, Display, TEXT("GF_SCENE shapes=%d status=\"%s\""), Game ? Game->NumShapes() : -1,
		Game ? *Game->GetStatusText() : TEXT(""));
	FString Shot;
	if (FParse::Value(FCommandLine::Get(), TEXT("GFShot="), Shot))
	{
		FScreenshotRequest::RequestScreenshot(Shot, true, false);
	}
	GetWorldTimerManager().SetTimer(SelfTestTimer, this, &AGFHostGameMode::FinishSelfTest, 2.0f, false);
}

void AGFHostGameMode::FinishSelfTest()
{
	FPlatformMisc::RequestExitWithStatus(false, bSelfTestPassed ? 0 : 3);
}

AGFHostController::AGFHostController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = true;
	DefaultMouseCursor = EMouseCursor::Hand;
	bAutoManageActiveCameraTarget = false;
}

void AGFHostController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameAndUI Mode;
	Mode.SetHideCursorDuringCapture(false);
	Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(Mode);
	if (AGFHostGameMode* GM = GetWorld()->GetAuthGameMode<AGFHostGameMode>())
	{
		GM->ApplyViewTarget(this);
	}
}

void AGFHostController::SetupInputComponent()
{
	Super::SetupInputComponent();
	InputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &AGFHostController::OnLeftClick);
	InputComponent->BindKey(EKeys::AnyKey, IE_Pressed, this, &AGFHostController::OnAnyKey);
}

void AGFHostController::OnLeftClick()
{
	AGFHostGameMode* GM = GetWorld()->GetAuthGameMode<AGFHostGameMode>();
	if (!GM || !GM->GetGame()) return;
	FHitResult Hit;
	GetHitResultUnderCursor(ECC_Visibility, false, Hit);
	GM->GetGame()->OnClicked(Hit.GetActor(), Hit.Location);
}

void AGFHostController::OnAnyKey(FKey Key)
{
	if (Key == EKeys::LeftMouseButton) return;
	if (Key == EKeys::Escape)
	{
		UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
		return;
	}
	AGFHostGameMode* GM = GetWorld()->GetAuthGameMode<AGFHostGameMode>();
	if (!GM || !GM->GetGame()) return;
	if (Key == EKeys::R)
	{
		GM->GetGame()->RestartGame();
		return;
	}
	GM->GetGame()->OnKey(Key);
}

void AGFHostHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas || !GEngine) return;
	const AGFHostGameMode* GM = GetWorld()->GetAuthGameMode<AGFHostGameMode>();
	const AGFGameBase* Game = GM ? GM->GetGame() : nullptr;
	const float Scale = FMath::Max(1.f, Canvas->ClipY / 720.f);
	DrawText(GFTitle::Title(), FLinearColor::White, 24.f * Scale, 18.f * Scale, GEngine->GetLargeFont(), 1.6f * Scale);
	if (Game)
	{
		DrawText(Game->GetStatusText(), FLinearColor(1.f, 0.85f, 0.3f), 24.f * Scale, 60.f * Scale, GEngine->GetLargeFont(), 1.3f * Scale);
		const FString Secondary = Game->GetSecondaryStatusText();
		if (!Secondary.IsEmpty())
		{
			DrawText(Secondary, FLinearColor(0.55f, 0.9f, 1.f), 24.f * Scale, 96.f * Scale, GEngine->GetMediumFont(), 1.15f * Scale);
		}
		DrawText(Game->GetControlsText(), FLinearColor(0.75f, 0.75f, 0.8f), 24.f * Scale, Canvas->ClipY - 40.f * Scale,
			GEngine->GetSmallFont(), 1.2f * Scale);
	}
}
'''

TITLE_H = r'''#pragma once
#include "CoreMinimal.h"
namespace GFTitle { inline const TCHAR* Title() { return TEXT("__TITLE__"); } }
'''


def framework_sources(project_name: str, title: str) -> Dict[str, str]:
    api = project_name.upper() + "_API"
    safe_title = "".join(c for c in title if c not in '"\\\n\r')[:60]
    files = {"GFGameBase.h": GAME_BASE_H, "GFGameBase.cpp": GAME_BASE_CPP, "GFHost.h": HOST_H,
             "GFHost.cpp": HOST_CPP, "GFTitle.h": TITLE_H.replace("__TITLE__", safe_title)}
    return {f"Source/{project_name}/{k}": v.replace("__API__", api) for k, v in files.items()}


def api_doc(project_name: str) -> str:
    return API_DOC.replace("__API__", project_name.upper() + "_API")


REFERENCE_IMPL_H = r'''#pragma once
#include "CoreMinimal.h"
#include "GFGameBase.h"
#include "GFGameImpl.generated.h"

UCLASS()
class __API__ AGFGameImpl : public AGFGameBase
{
	GENERATED_BODY()
public:
	virtual void StartGame() override;
	virtual void OnClicked(AActor* Actor, const FVector& Point) override;
	virtual FString GetStatusText() const override;
	virtual FString GetControlsText() const override { return TEXT("Click every cube   |   R: restart   |   Esc: quit"); }
	virtual float GetCameraDistance() const override { return 1300.f; }
	virtual bool RunSelfTest(FString& OutReport) override;
private:
	UPROPERTY() TArray<TObjectPtr<AActor>> Targets;
	TSet<AActor*> Hit;
};
'''

REFERENCE_IMPL_CPP = r'''#include "GFGameImpl.h"

void AGFGameImpl::StartGame()
{
	Targets.Reset();
	Hit.Reset();
	for (int32 Y = 0; Y < 3; ++Y)
	{
		for (int32 X = 0; X < 3; ++X)
		{
			Targets.Add(SpawnShape(EGFShape::Cube, FVector((1 - Y) * 250.f, (X - 1) * 250.f, 50.f),
				FVector(1.5f), FLinearColor(0.2f, 0.45f, 1.f)));
		}
	}
	SpawnText(TEXT("CLICK EVERY CUBE"), FVector(450.f, 0.f, 60.f), 70.f, FLinearColor(1.f, 0.85f, 0.3f));
}

void AGFGameImpl::OnClicked(AActor* Actor, const FVector& Point)
{
	if (Actor && Targets.Contains(Actor) && !Hit.Contains(Actor))
	{
		Hit.Add(Actor);
		SetShapeColor(Actor, FLinearColor(0.2f, 0.9f, 0.3f));
	}
}

FString AGFGameImpl::GetStatusText() const
{
	return Hit.Num() == Targets.Num() ? FString(TEXT("All cubes found - you win!"))
		: FString::Printf(TEXT("Cubes clicked: %d / %d"), Hit.Num(), Targets.Num());
}

bool AGFGameImpl::RunSelfTest(FString& OutReport)
{
	OnClicked(nullptr, FVector::ZeroVector);
	const bool bIgnoresEmpty = Hit.Num() == 0;
	for (AActor* T : Targets) { OnClicked(T, FVector::ZeroVector); }
	OnClicked(Targets[0], FVector::ZeroVector);
	const bool bAll = Hit.Num() == 9;
	OutReport = FString::Printf(TEXT("ignores_empty=%d all_clicked=%d"), bIgnoresEmpty, bAll);
	return bIgnoresEmpty && bAll;
}
'''


def reference_impl(project_name: str) -> Dict[str, str]:
    api = project_name.upper() + "_API"
    return {f"Source/{project_name}/GFGameImpl.h": REFERENCE_IMPL_H.replace("__API__", api),
            f"Source/{project_name}/GFGameImpl.cpp": REFERENCE_IMPL_CPP}
