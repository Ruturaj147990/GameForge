# P3 — Deterministic Scenario QA Harness (handover)

**Branch:** `master` (no feature branches). **Depends on:** P2 accepted. **Decisions:** AD-12, AD-19. **Resolves:** F-09.
**Estimate:** 2–3 weeks. **Read first:** `../01_ARCHITECTURE.md` §3.2, §3.5; `../03_RESEARCH_2026-10-31.md` R6, R11;
`../06_ENGINE_NOTES_UE57.md`.

## Objective

Prove playability by **replaying input inside the real game**: headless, with no window focus, against a packaged
build (Development **and** Shipping). This needs four runtime pieces in `GameForgeRuntime` (event bus, scenario
subsystem, autopilot, minimal Enhanced-Input player) and three host pieces (scenario schema, generator, runner).

**Scope boundary.** There is no rules engine and no `game.won`/`game.lost` yet (P5). P3 scenarios assert on kit events
(`pickup.collected`, `guard.spotted_player`, `objective.completed`, …), which already exist as log lines and move onto
the bus here.

---

## WI-3.0 Spike (do first; it gates the phase)

The riskiest assumption is that `InjectInputForAction` with **runtime-created** `UInputAction` objects drives
`ACharacter` movement in a **cooked Shipping** build. Build the smallest test that proves or refutes it:
- In a throwaway C++ project scaffolded by `toolchain.scaffold_cpp_project` and named `GFInjectSpike`, write a
  PlayerController that creates `IA_Move` at runtime (code in WI-3.3), and a GameMode whose `BeginPlay` starts a timer
  that injects `(0,1)` for 2 s and logs the pawn's travelled distance to a file
  (`FFileHelper::SaveStringToFile`, not `UE_LOG`).
- Package it in Development and Shipping (`toolchain.package(..., configuration="Shipping")`). Run each with
  `-RenderOffscreen -unattended -nosplash`.
- **Pass:** distance ≥ 1,000 cm in both builds. Record `reports/P3/spike_inject.json`.
- **If it fails:** stop and write a QUESTIONS.md entry with the logs. The fallback design (CQTestEnhancedInput-style
  `UEnhancedPlayerInput::InjectInputForAction` on the player input object) needs Claude's review.

---

## WI-3.1 Event bus (C++) + event-name parity

**New files:** `Source/GameForgeRuntime/Public/GameForgeEvents.h`, `Private/GameForgeEvents.cpp`,
`Public/GameForgeEventNames.h`.

`GameForgeEventNames.h` holds one macro line per catalogue event. It is parsed by a Python test against
`design/events_catalog.py`:

```cpp
#pragma once
// Keep identical to src/gameforge_ide/design/events_catalog.py (tests/unit/test_event_names_parity.py).
#define GF_EVENT_NAMES(X) \
    X(GameStarted, "game.started") X(GameWon, "game.won") X(GameLost, "game.lost") X(GameRestarted, "game.restarted") \
    X(GamePaused, "game.paused") X(GameResumed, "game.resumed") \
    X(PlayerSpawned, "player.spawned") X(PlayerDamaged, "player.damaged") X(PlayerDied, "player.died") \
    X(PlayerRespawned, "player.respawned") X(PlayerJumped, "player.jumped") \
    X(PickupCollected, "pickup.collected") X(CheckpointReached, "checkpoint.reached") X(GoalReached, "goal.reached") \
    X(HazardTouched, "hazard.touched") X(EnemySpawned, "enemy.spawned") X(EnemyAttacked, "enemy.attacked") \
    X(EnemyKilled, "enemy.killed") X(WaveStarted, "wave.started") X(WaveCleared, "wave.cleared") \
    X(GuardState, "guard.state") X(GuardSpottedPlayer, "guard.spotted_player") X(GuardLostPlayer, "guard.lost_player") \
    X(DialogueLine, "dialogue.line") X(ObjectiveStarted, "objective.started") X(ObjectiveUpdated, "objective.updated") \
    X(ObjectiveCompleted, "objective.completed") X(SaveLoaded, "save.loaded") X(SaveWritten, "save.written") \
    X(InteractUsed, "interact.used") X(DoorOpened, "door.opened") X(DoorClosed, "door.closed") \
    X(SwitchToggled, "switch.toggled") X(LandmarkDiscovered, "landmark.discovered") \
    X(BoardMove, "board.move") X(BoardWin, "board.win") X(BoardDraw, "board.draw") X(TurnEnded, "turn.ended") \
    X(CardPlayed, "card.played") X(LaneResolved, "lane.resolved") X(MatchWon, "match.won") X(MatchLost, "match.lost")

namespace GFEvent
{
#define GF_DECLARE_NAME(Id, Str) inline const FName Id(TEXT(Str));
    GF_EVENT_NAMES(GF_DECLARE_NAME)
#undef GF_DECLARE_NAME
}
```

`GameForgeEvents.h`:

```cpp
#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "GameForgeEvents.generated.h"

GAMEFORGERUNTIME_API DECLARE_LOG_CATEGORY_EXTERN(LogGameForgeEvents, Log, All);

USTRUCT(BlueprintType)
struct GAMEFORGERUNTIME_API FGameForgeEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FName Name;
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float Time = 0.f;     // seconds since this game instance started
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString Source;       // emitting actor name (diagnostics only)
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FName Entity;         // GDS entity id (the actor's EntityId); matching uses this
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString DataJson;     // a JSON object, "{}" when empty
};

DECLARE_MULTICAST_DELEGATE_OneParam(FOnGameForgeEvent, const FGameForgeEvent&);

/** One bus per game instance: in-game listeners, a JSONL file that works in Shipping, and a log line when logging exists. */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeEventBus : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UGameForgeEventBus* Get(const UObject* WorldContext);

	void Emit(FName Name, const FString& Source, const FString& DataJson = TEXT("{}"), FName Entity = NAME_None);
	/** Events named Name; when Entity is not None, only those whose Entity matches. */
	int32 Count(FName Name, FName Entity = NAME_None) const;
	const TArray<FGameForgeEvent>& History() const { return Events; }
	const FString& SessionFile() const { return SessionPath; }

	FOnGameForgeEvent OnEvent;

private:
	TArray<FGameForgeEvent> Events;     // bounded to MaxEvents
	FString SessionPath;
	double StartSeconds = 0.0;
	static constexpr int32 MaxEvents = 20000;
};

UCLASS()
class GAMEFORGERUNTIME_API UGameForgeEventLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintCallable, Category = "GameForge|Events", meta = (WorldContext = "WorldContextObject"))
	static void EmitGameForgeEvent(const UObject* WorldContextObject, FName Name, const FString& Source, const FString& DataJson,
		FName Entity = NAME_None);
};
```

`GameForgeEvents.cpp`:

```cpp
#include "GameForgeEvents.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"

DEFINE_LOG_CATEGORY(LogGameForgeEvents);

void UGameForgeEventBus::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	StartSeconds = FPlatformTime::Seconds();
	FString Override;
	if (FParse::Value(FCommandLine::Get(), TEXT("GFEventsOut="), Override) && !Override.IsEmpty())
	{
		SessionPath = Override;
	}
	else
	{
		SessionPath = FPaths::ProjectSavedDir() / TEXT("GameForge/events") /
			(FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")) + TEXT(".jsonl"));
	}
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(SessionPath), true);
}

UGameForgeEventBus* UGameForgeEventBus::Get(const UObject* WorldContext)
{
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContext, EGetWorldErrorMode::ReturnNull) : nullptr;
	UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UGameForgeEventBus>() : nullptr;
}

void UGameForgeEventBus::Emit(FName Name, const FString& Source, const FString& DataJson, FName Entity)
{
	FGameForgeEvent Ev;
	Ev.Name = Name;
	Ev.Source = Source;
	Ev.Entity = Entity;
	Ev.DataJson = DataJson.TrimStartAndEnd().StartsWith(TEXT("{")) ? DataJson : TEXT("{}");
	Ev.Time = static_cast<float>(FPlatformTime::Seconds() - StartSeconds);
	if (Events.Num() < MaxEvents)
	{
		Events.Add(Ev);
	}
	const FString Line = FString::Printf(TEXT("{\"e\":\"%s\",\"t\":%.3f,\"src\":\"%s\",\"ent\":\"%s\",\"d\":%s}"),
		*Name.ToString(), Ev.Time, *Source.ReplaceCharWithEscapedChar(),
		Entity.IsNone() ? TEXT("") : *Entity.ToString(), *Ev.DataJson);
	UE_LOG(LogGameForgeEvents, Display, TEXT("GF_EVENT %s"), *Line);           // compiled out in Shipping (fine)
	FFileHelper::SaveStringToFile(Line + TEXT("\n"), *SessionPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
		&IFileManager::Get(), FILEWRITE_Append);                                // works in every configuration
	OnEvent.Broadcast(Ev);
}

int32 UGameForgeEventBus::Count(FName Name, FName Entity) const
{
	int32 N = 0;
	for (const FGameForgeEvent& Ev : Events)
	{
		N += (Ev.Name == Name && (Entity.IsNone() || Ev.Entity == Entity)) ? 1 : 0;
	}
	return N;
}

void UGameForgeEventLibrary::EmitGameForgeEvent(const UObject* WorldContextObject, FName Name, const FString& Source,
	const FString& DataJson, FName Entity)
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(WorldContextObject))
	{
		Bus->Emit(Name, Source, DataJson, Entity);
	}
}
```

**Retrofit the existing kit actors.** First add `UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") FName EntityId;`
to `AGameForgePickup`, `AGameForgeGuard` and `AGameForgeQuestGiver`, and pass it as the `Entity` argument of every emit
(the objective subsystem passes `NAME_None`). Then add a bus `Emit` **next to** each existing
`UE_LOG(... "GF_EVENT ...")`. Keep the old log lines: the M13–M15 demo scripts parse them until P6.

| File:line (2026-10-31) | Old log | New bus event | Source | Data |
|---|---|---|---|---|
| `GameForgePickup.cpp:81` | `GF_EVENT pickup` | `GFEvent::PickupCollected` | `GetName()` | `{"objective":"<ObjectiveId>","by":"<pawn name>"}` |
| `GameForgeGuard.cpp:43` | `guard_state` | `GFEvent::GuardState`; also `GuardSpottedPlayer` when the new state is Chase and `GuardLostPlayer` when it is Search | guard name | `{"state":"Chase","prev":"Patrol"}` |
| `GameForgeObjectives.cpp:39` | `objective_load` | `SaveLoaded` | slot | `{"objectives":N}` |
| `:72` | `objective_start` | `ObjectiveStarted` | id | `{"target":N}` |
| `:85` | `objective_progress` | `ObjectiveUpdated` | id | `{"progress":P,"target":N}` |
| `:89` | `objective_complete` | `ObjectiveCompleted` | id | `{}` |
| `:107` | `objective_save` | `SaveWritten` | slot | `{"ok":true}` |
| `:156` | `dialogue` | `DialogueLine` | giver name | `{"line":"<escaped>"}` |

Escape strings in Data with `ReplaceCharWithEscapedChar()`. Never hand-build JSON from unescaped user text.

**Test** `tests/unit/test_event_names_parity.py`: regex `X\((\w+), "([a-z0-9_.]+)"\)` over the header; the set of strings
equals `design.events_catalog.all_events()`.

---

## WI-3.2 Minimal kit player: `AGameForgeCharacter`, `AGameForgePlayerController`, `AGameForgeGameModeBase`

**New files:** `Public/GameForgePlayer.h`, `Private/GameForgePlayer.cpp`. **Build.cs:** add `"EnhancedInput"` to
`PublicDependencyModuleNames`. **Plugin:** add `{"Name": "EnhancedInput", "Enabled": true}` to `GameForge.uplugin`
`Plugins`.

```cpp
// GameForgePlayer.h
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "GameForgePlayer.generated.h"

class UCameraComponent; class USpringArmComponent; class UInputAction; class UInputMappingContext;

UENUM(BlueprintType)
enum class EGameForgeCameraMode : uint8 { ThirdPerson, TopDown, FirstPerson, SideScroller };

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeCharacter : public ACharacter
{
	GENERATED_BODY()
public:
	AGameForgeCharacter();
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge") TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge") TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") EGameForgeCameraMode CameraMode = EGameForgeCameraMode::ThirdPerson;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") float MoveSpeed = 600.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") float JumpVelocity = 650.f;
	UFUNCTION(BlueprintCallable, Category = "GameForge") void ApplyCameraMode();
protected:
	virtual void BeginPlay() override;
};

/** Builds its Enhanced Input actions at runtime (no input assets needed; works in cooked builds). */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgePlayerController : public APlayerController
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintCallable, Category = "GameForge|Input") UInputAction* FindAction(FName ActionId) const;
	/** Same path the IA_Select handler uses after reading the mouse: hit-test at a screen position and select. */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Input") AActor* SelectAtScreenPosition(FVector2D ScreenPosition);
	UPROPERTY(Transient, BlueprintReadOnly, Category = "GameForge|Input") TObjectPtr<UInputMappingContext> MappingContext;
protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	void BuildDefaultInput();
	void HandleMove(const FInputActionValue& Value);
	void HandleLook(const FInputActionValue& Value);
	void HandleJumpStarted(const FInputActionValue& Value);
	void HandleJumpCompleted(const FInputActionValue& Value);
	void HandleSelect(const FInputActionValue& Value);
	UPROPERTY(Transient) TMap<FName, TObjectPtr<UInputAction>> Actions;
	bool bContextAdded = false;
};

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGameModeBase : public AGameModeBase
{
	GENERATED_BODY()
public:
	AGameForgeGameModeBase();
	virtual void StartPlay() override;   // emits game.started
};
```

```cpp
// GameForgePlayer.cpp (key parts; complete the obvious boilerplate)
#include "GameForgePlayer.h"
#include "Camera/CameraComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"

AGameForgeCharacter::AGameForgeCharacter()
{
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 400.f;
	CameraBoom->bUsePawnControlRotation = true;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom);
	bUseControllerRotationYaw = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate = FRotator(0.f, 540.f, 0.f);
}

void AGameForgeCharacter::BeginPlay()
{
	Super::BeginPlay();
	GetCharacterMovement()->MaxWalkSpeed = MoveSpeed;
	GetCharacterMovement()->JumpZVelocity = JumpVelocity;
	ApplyCameraMode();
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerSpawned, GetName(), TEXT("{}"));
}

void AGameForgeCharacter::ApplyCameraMode()
{
	switch (CameraMode)
	{
	case EGameForgeCameraMode::TopDown:
		CameraBoom->TargetArmLength = 1400.f; CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetRelativeRotation(FRotator(-60.f, 0.f, 0.f)); CameraBoom->bInheritYaw = false; break;
	case EGameForgeCameraMode::FirstPerson:
		CameraBoom->TargetArmLength = 0.f; CameraBoom->SetRelativeLocation(FVector(0, 0, 64.f));
		bUseControllerRotationYaw = true; GetCharacterMovement()->bOrientRotationToMovement = false; break;
	case EGameForgeCameraMode::SideScroller:
		CameraBoom->TargetArmLength = 1200.f; CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetRelativeRotation(FRotator(0.f, -90.f, 0.f)); CameraBoom->bInheritYaw = false; break;
	default: break; // ThirdPerson: constructor defaults
	}
}

UInputAction* AGameForgePlayerController::FindAction(FName ActionId) const
{
	const TObjectPtr<UInputAction>* Found = Actions.Find(ActionId);
	return Found ? Found->Get() : nullptr;
}

void AGameForgePlayerController::BuildDefaultInput()
{
	if (Actions.Num() > 0) { return; }
	MappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_GameForge"));
	auto Make = [this](const TCHAR* Id, EInputActionValueType Type) {
		UInputAction* A = NewObject<UInputAction>(this, FName(Id));
		A->ValueType = Type;
		Actions.Add(FName(Id), A);
		return A;
	};
	UInputAction* Move = Make(TEXT("IA_Move"), EInputActionValueType::Axis2D);    // X = right, Y = forward
	UInputAction* Look = Make(TEXT("IA_Look"), EInputActionValueType::Axis2D);
	UInputAction* Jump = Make(TEXT("IA_Jump"), EInputActionValueType::Boolean);
	UInputAction* Select = Make(TEXT("IA_Select"), EInputActionValueType::Boolean);
	Make(TEXT("IA_Interact"), EInputActionValueType::Boolean);                     // bound in P5
	auto Swizzle = [this]() { return NewObject<UInputModifierSwizzleAxis>(MappingContext); }; // default order YXZ
	auto Negate = [this]() { return NewObject<UInputModifierNegate>(MappingContext); };
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::W); M.Modifiers.Add(Swizzle()); }
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::S); M.Modifiers.Add(Swizzle()); M.Modifiers.Add(Negate()); }
	MappingContext->MapKey(Move, EKeys::D);
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::A); M.Modifiers.Add(Negate()); }
	MappingContext->MapKey(Look, EKeys::Mouse2D);
	MappingContext->MapKey(Jump, EKeys::SpaceBar);
	MappingContext->MapKey(Select, EKeys::LeftMouseButton);
	MappingContext->MapKey(FindAction(TEXT("IA_Interact")), EKeys::E);
}

void AGameForgePlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	BuildDefaultInput();
	if (UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(InputComponent))
	{
		EIC->BindAction(FindAction("IA_Move"), ETriggerEvent::Triggered, this, &AGameForgePlayerController::HandleMove);
		EIC->BindAction(FindAction("IA_Look"), ETriggerEvent::Triggered, this, &AGameForgePlayerController::HandleLook);
		EIC->BindAction(FindAction("IA_Jump"), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleJumpStarted);
		EIC->BindAction(FindAction("IA_Jump"), ETriggerEvent::Completed, this, &AGameForgePlayerController::HandleJumpCompleted);
		EIC->BindAction(FindAction("IA_Select"), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleSelect);
	}
}

void AGameForgePlayerController::BeginPlay()
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

void AGameForgePlayerController::HandleMove(const FInputActionValue& Value)
{
	const FVector2D Axis = Value.Get<FVector2D>();
	if (APawn* P = GetPawn())
	{
		const FRotator Yaw(0.f, GetControlRotation().Yaw, 0.f);
		P->AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), Axis.Y);
		P->AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), Axis.X);
	}
}
// HandleLook: AddYawInput(Axis.X); AddPitchInput(-Axis.Y).
// HandleJumpStarted/Completed: Cast<ACharacter>(GetPawn())->Jump()/StopJumping(); emit PlayerJumped on Started.
// HandleSelect: FVector2D Mouse; if (GetMousePosition(Mouse.X, Mouse.Y)) SelectAtScreenPosition(Mouse);

AActor* AGameForgePlayerController::SelectAtScreenPosition(FVector2D ScreenPosition)
{
	FHitResult Hit;
	if (!GetHitResultAtScreenPosition(ScreenPosition, ECC_Visibility, false, Hit) || !Hit.GetActor()) { return nullptr; }
	AActor* Target = Hit.GetActor();
	UGameForgeEventLibrary::EmitGameForgeEvent(this, FName("interact.used"), Target->GetName(), TEXT("{\"via\":\"select\"}"));
	return Target;      // P5: IGameForgeSelectable::Execute_OnSelected(Target, this)
}

AGameForgeGameModeBase::AGameForgeGameModeBase()
{
	DefaultPawnClass = AGameForgeCharacter::StaticClass();
	PlayerControllerClass = AGameForgePlayerController::StaticClass();
}

void AGameForgeGameModeBase::StartPlay()
{
	Super::StartPlay();
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GameStarted, GetName(), TEXT("{}"));
}
```

**API checks before you compile** (open the headers in `E:\UE\UE_5.7\Engine\Plugins\EnhancedInput\Source\EnhancedInput\Public\`):
`UInputMappingContext::MapKey` (returns `FEnhancedActionKeyMapping&`), `FEnhancedActionKeyMapping::Modifiers`,
`UInputModifierSwizzleAxis` (default `Order`), `UInputAction::ValueType` (public UPROPERTY). If any of these differ in
5.7.4, use the engine's replacement **and say so in the commit message**. Do not invent wrappers.

**Generated projects** (toolchain scaffolder) must write `Config/DefaultInput.ini` with:
```ini
[/Script/Engine.InputSettings]
DefaultPlayerInputClass=/Script/EnhancedInput.EnhancedPlayerInput
DefaultInputComponentClass=/Script/EnhancedInput.EnhancedInputComponent
```
Add this as `toolchain.ENHANCED_INPUT_INI`, applied when `module_deps` contains `"EnhancedInput"`. The legacy recipes
don't use it, so they stay unaffected.

---

## WI-3.3 Autopilot component (physically honest movement)

**New files:** `Public/GameForgeAutopilot.h`, `Private/GameForgeAutopilot.cpp`. **Build.cs:** `NavigationSystem` is
already a dependency.

```cpp
USTRUCT(BlueprintType)
struct FGameForgeLeg
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString Target;
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float DistanceCm = 0.f;   // path length actually travelled
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float Seconds = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float MaxStepCm = 0.f;    // largest single-frame displacement
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString Result;            // ARRIVED | TELEPORT_SUSPECTED | STUCK | NO_PATH | TIMEOUT
};

UCLASS(ClassGroup = (GameForge), meta = (BlueprintSpawnableComponent))
class GAMEFORGERUNTIME_API UGameForgeAutopilotComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UGameForgeAutopilotComponent();
	/** Starts walking to Target via NavMesh using injected IA_Move input. Returns false if no path. */
	bool MoveTo(const FVector& Target, const FString& Label, float AcceptRadiusCm = 120.f, float TimeoutS = 60.f);
	bool IsActive() const { return bActive; }
	const TArray<FGameForgeLeg>& Legs() const { return CompletedLegs; }
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
private:
	void Finish(const FString& Result);
	TArray<FVector> Path; int32 PathIndex = 0; bool bActive = false;
	FGameForgeLeg Current; FVector LastPos = FVector::ZeroVector; float Accept = 120.f; float Timeout = 60.f;
	float StuckTimer = 0.f; FVector StuckAnchor = FVector::ZeroVector;
	TArray<FGameForgeLeg> CompletedLegs;
};
```

Tick algorithm (implement exactly):
1. If not active, return. Find `APawn* Pawn = Cast<APawn>(GetOwner())` and `AGameForgePlayerController* PC`. If PC is
   missing → `Finish("NO_CONTROLLER")`.
2. `Pos = Pawn->GetActorLocation()`. `Step = FVector::Dist2D(Pos, LastPos)`, `Current.DistanceCm += Step`,
   `Current.MaxStepCm = max(…)`, `Current.Seconds += DeltaTime`, `LastPos = Pos`.
3. **Teleport detection:** `MaxSpeed = Pawn->GetMovementComponent()->GetMaxSpeed()`. If
   `Step > MaxSpeed * DeltaTime * 1.5f + 50.f` → `Finish("TELEPORT_SUSPECTED")`.
4. **Stuck detection:** if `FVector::Dist2D(Pos, StuckAnchor) > 50` reset `StuckAnchor = Pos, StuckTimer = 0`, else
   `StuckTimer += DeltaTime`. If `StuckTimer > 3` → `Finish("STUCK")`.
5. Timeout → `Finish("TIMEOUT")`.
6. Advance `PathIndex` while the next point is within `Accept` (2D). Reaching the last point → `Finish("ARRIVED")`.
7. `Dir = (Path[PathIndex] - Pos).GetSafeNormal2D()`. `Yaw = FRotator(0, PC->GetControlRotation().Yaw, 0)`.
   `Input = FVector2D(FVector::DotProduct(Dir, RightAxis(Yaw)), FVector::DotProduct(Dir, ForwardAxis(Yaw)))`.
   `Subsystem->InjectInputForAction(PC->FindAction("IA_Move"), FInputActionValue(Input), {}, {})`.
   (`Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer())`.)
8. `MoveTo`: `UNavigationPath* NavPath = UNavigationSystemV1::FindPathToLocationSynchronously(GetWorld(), Pawn->GetActorLocation(), Target, Pawn)`;
   no path or `!NavPath->IsValid()` → leg result `NO_PATH`, return false. Copy `NavPath->PathPoints`.

The autopilot **never** calls `SetActorLocation`, `SimpleMoveToLocation` or `AddMovementInput` directly. It only
injects input, so CharacterMovement physics decides where the pawn goes.

---

## WI-3.4 Scenario subsystem

**New files:** `Public/GameForgeScenario.h`, `Private/GameForgeScenario.cpp`.

Class: `UGameForgeScenarioSubsystem : public UGameInstanceSubsystem, public FTickableGameObject`.
- `Initialize`: parse `-GFScenario=<path>` and `-GFScenarioOut=<path>` with `FParse::Value`. If both are present,
  load the JSON (`FFileHelper::LoadFileToString` + `FJsonSerializer::Deserialize`) and validate it: `schema ==
  "scenario/1"`, steps array present. On error → write the result with `"passed": false, "error": "..."` and request
  exit. Subscribe to `UGameForgeEventBus::OnEvent` (bus initialised first: call
  `Collection.InitializeDependency(UGameForgeEventBus::StaticClass())`).
- `IsTickable()` → `bLoaded && !bFinished`. `GetTickableTickType()` → `Conditional`. `GetStatId()` →
  `RETURN_QUICK_DECLARE_CYCLE_STAT(UGameForgeScenarioSubsystem, STATGROUP_Tickables)`.
- `Tick(Dt)`:
  1. Wait for `PlayerController(0)` with a pawn and a NavMesh present (`UNavigationSystemV1::GetCurrent` not null)
     for up to 30 s, then start. Record `start_delay_s`.
  2. Global timeout `timeout_s` → fail `"SCENARIO_TIMEOUT"`.
  3. Execute the current step (state machine below). When all steps are done, evaluate `expect`, write the result
     and exit.

Steps (each is an object with one key):

| Step | Behaviour | Fails with |
|---|---|---|
| `navigate_to {tag, accept_radius_cm=120, timeout_s=60}` | First actor with `Tags.Contains(tag)` (`UGameplayStatics::GetAllActorsWithTag`). Add the autopilot to the pawn once (`NewObject` + `RegisterComponent`) and `MoveTo(target location)`. Step done when the leg finishes ARRIVED. | `NO_TARGET`, or the leg's result |
| `navigate_to_point {x,y,z, ...}` | Same, to a point | same |
| `inject {action, value, hold_s=0}` | `value`: bool → `FInputActionValue(true)`; a number → axis1d; `[x,y]` → axis2d. `hold_s=0` → one `InjectInputForAction`; otherwise `Start...` then `Stop...` after `hold_s` | `UNKNOWN_ACTION` |
| `wait_event {e, count=1, entity?, timeout_s=30}` | Done when `Bus->Count(e, entity) >= count` (`entity` = GDS entity id) | `EVENT_TIMEOUT` |
| `wait_s {seconds}` | — | — |
| `select_actor {tag}` | `PC->ProjectWorldLocationToScreen(actor bounds origin)` → `PC->SelectAtScreenPosition`. Done if it returns the target or a component owner equal to the target | `NOT_SELECTABLE` |
| `look_at {tag}` | Set control rotation yaw toward the target (this is camera setup, not movement) | `NO_TARGET` |

Expectations, evaluated after the steps (or when a step fails, as `"skipped"`):
`{"event": e, "entity"?: id}` (count ≥ 1), `{"event_count": e, "entity"?: id, "min": n, "max"?: m}`, `{"no_event": e}`, and
`{"legs_ok": true}` (every leg ARRIVED, none TELEPORT_SUSPECTED).

Captures: `{"on_event": e, "screenshot": "won.png"}` → `FScreenshotRequest::RequestScreenshot(OutDir / name, false, false)`
the first time `e` is seen. Captures are evidence and never pass/fail criteria in P3.

**Result file** (`-GFScenarioOut`), written with `FFileHelper::SaveStringToFile` (UTF-8, no BOM):
```json
{"schema": "scenario_result/1", "scenario_id": "...", "passed": true, "duration_s": 41.2, "start_delay_s": 3.1,
 "build": {"configuration": "Development|Shipping", "engine": "5.7.4"},
 "steps": [{"i": 0, "kind": "navigate_to", "status": "DONE", "t0": 3.1, "t1": 9.8, "detail": {...}}],
 "legs": [{"target": "GF_Pickup_1", "distance_cm": 1650.2, "seconds": 3.0, "max_step_cm": 11.2, "result": "ARRIVED"}],
 "expect": [{"expect": {"event": "pickup.collected"}, "ok": true, "observed": 3}],
 "failures": [], "events_file": "<bus session path>"}
```
Then exit with `FPlatformMisc::RequestExitWithStatus(false, Passed ? 0 : 3)`. If `RequestExitWithStatus` is not
available in 5.7.4, use `FPlatformMisc::RequestExit(false)` and rely on the result file. Note the substitution in the
commit message. Get the build configuration from `LexToString(FApp::GetBuildConfiguration())`.

The subsystem is compiled into every configuration (no `#if !UE_BUILD_SHIPPING`) and does nothing unless both
command-line arguments are present. **Security:** the scenario path is only read; nothing is executed from it.

---

## WI-3.5 Host side: schema, generator, runner

**`src/gameforge_ide/qa/scenario.py`:** pydantic models mirroring the JSON above (`Scenario`, step union with one key
per step, `Expectation` union, `ScenarioResult`), `extra="forbid"`, plus `Scenario.to_file(path)`.

**`src/gameforge_ide/qa/manifest.py`:** the level manifest (written by assembly; P6 automates it):
```python
class ManifestActor(BaseModel):
    actor_id: str; tag: str; cls: str; entity_id: Optional[str] = None
    location: Tuple[float, float, float]; yaw: float = 0.0
class LevelManifest(BaseModel):
    schema_: Literal["level_manifest/1"] = Field("level_manifest/1", alias="schema")
    level_id: str; map: str; player_start: Tuple[float, float, float]; actors: List[ManifestActor]
```
It lives at `<project>/GameForge/levels/<level_id>.manifest.json`.

**`src/gameforge_ide/qa/generate.py`:** `generate(gds, manifests) -> (list[Scenario], list[ScenarioGap])`. For each
`acceptance.scenarios` ref:

| Condition (from `derived_from`) | Generated steps | Expect (P3) | Expect added in P5 |
|---|---|---|---|
| `CountAtLeast(pickup.collected, n)` | `navigate_to` the n nearest pickups (greedy nearest-neighbour from player_start, by tag) | `event_count pickup.collected min n`, `legs_ok` | `event game.won` (win refs) |
| `EventOccurred(goal.reached)` | `navigate_to` the goal tag | `event goal.reached`, `legs_ok` | `game.won` |
| `EventOccurred(guard.spotted_player)` / `caught_by_guard` | `navigate_to_point` 600 cm in front of the guard (from its yaw), then `wait_event guard.spotted_player` | `event guard.spotted_player` | `game.lost` |
| `StatCompare(player.health <= 0)` | `navigate_to` the nearest hazard/enemy tag, then `wait_s 10` | `event player.died` | `game.lost` |
| `EventOccurred(objective.completed)` | `navigate_to` quest giver → pickups tagged with its objective → back to the giver | `event objective.completed` | — |
| `TimerElapsed(s)` | `wait_s s+2` | — (P5) | `game.won` or `game.lost` |
| `smoke` | `wait_s 5` | `event game.started`, `no_event player.died` | — |
| anything else | — | ScenarioGap("needs P5 rules engine" or "no strategy for <kind>") | |

**`src/gameforge_ide/qa/runner.py`:**
```python
def run_packaged(exe: Path, scenario: Scenario, out_dir: Path, timeout_s: float, extra_args=()) -> ScenarioResult:
    """Launch the packaged game binary (<Name>/Binaries/Win64/<Name>.exe, not the launcher) via core.jobs.spawn with:
       -GFScenario=<abs> -GFScenarioOut=<abs> -GFEventsOut=<abs> -RenderOffscreen -ResX=1280 -ResY=720 -unattended
       -nosplash -nosound. Wait for exit (timeout → kill tree, result TIMEOUT). Parse the result file; a missing
       file is a failure ('NO_RESULT'), never a pass. Copy events + screenshots into out_dir."""
```
Also `run_editor_game(uproject, …)`, which uses `UnrealEditor.exe <uproject> -game` with the same arguments for
fast iteration without packaging. It is evidence of class "game in editor build", and reports record the class.

**Forge step:** `forge/handlers/scenario.py`, kind `scenario`. Its inputs are `{"scenario_ids": [...], "configuration":
"Development"}`. It finds the packaged exe from `ctx.shared["package"]["exe"]`, runs every `must_pass` scenario and
returns ok only if all pass. Artifacts are the result files.

---

## WI-3.6 Kit testbed project and re-verification of earlier traversal claims

`scripts/engine/kit_testbed.py`, which supersedes `package_kit_selftest.py`; keep that file until this item passes, then
`git rm` it. Steps:
1. Scaffold `GFKitTest` (C++, plugin enabled, `module_deps += ["EnhancedInput", "AIModule", "NavigationSystem"]`)
   into `E:\GameForge\validation\P3_kittest_<date>`. Set `GlobalDefaultGameMode=/Script/GameForgeRuntime.GameForgeGameModeBase`.
2. Build the level through ops: floor 6,000×6,000 cm, NavMeshBoundsVolume, PlayerStart; 3 `AGameForgePickup` tagged
   `GF_Pickup_1..3` and `GF_E_relics`, with `EntityId=relics` and `ObjectiveId=relics`; 1 `AGameForgeQuestGiver` tagged `GF_Giver` (objective `relics`,
   target 3); 1 `AGameForgeGuard` tagged `GF_Guard_1` with 2 patrol points; a wall block between the start and one
   pickup, so the path is not a straight line. `nav_rebuild` → `nav_find_path` sanity check. Write
   `GameForge/levels/level_1.manifest.json` from `actors_in_level` read-back (tags, locations, yaw).
3. Package **Development** and **Shipping**.
4. Scenarios (generated by `qa/generate.py` from a hand-written GDS of the testbed, plus two controls):
   - `collect_3`: expect `pickup.collected ×3`, `legs_ok`.
   - `quest_complete`: expect `objective.completed`.
   - `spotted_by_guard`: expect `guard.spotted_player`.
   - Control **A**, `teleport_cheat`: a test-only actor `AGameForgeTeleportCheat` (in a `GameForgeTestOnly` folder,
     excluded from Shipping by `#if !UE_BUILD_SHIPPING`) moves the pawn with `SetActorLocation` during a leg. The
     scenario **must fail** with `TELEPORT_SUSPECTED`. Development only.
   - Control **B**, `impossible`: expect `pickup.collected ×4` with 3 pickups. It **must fail**.
5. Run all of them on Development, and the first three on Shipping too. Evidence: `reports/P3/kit_testbed_scenarios.json`
   with every result file, the configuration, the exit code and timings.
6. **Re-verification of earlier claims** (`reports/P3/reverify_traversal.json`): the M8 village traversal, the M13
   pickup walk-in and the M15 guard chase were measured with `pie_move_player_to` on a DefaultPawn. Rebuild each
   *situation* in the testbed (village: a 40 m path; pickup walk-in; guard: approach from the front) and run it through
   the autopilot. For each old claim, record `{old_report, old_method: "SimpleMoveToLocation on DefaultPawn",
   new_result, legs}`. Update `docs/00_STATUS.md`: a row is PASS only if the new result passes.

## Phase exit gate
1. Spike WI-3.0 PASS (or a Claude-approved alternative).
2. In a **Development** package launched headless (no window focus), `collect_3`, `quest_complete` and
   `spotted_by_guard` pass, and controls A and B fail for the right reasons.
3. The same three pass in a **Shipping** package (result file only, no logs).
4. Event-name parity test, scenario schema tests and generator unit tests (with fixture manifests) are green.
5. `reports/P3/reverify_traversal.json` written and the status matrix corrected.

## Failure cases and prevention
- **Input injected before the mapping context is added:** the scenario waits for `PlayerController` + pawn, and the PC
  adds its context in `BeginPlay`. The first `inject` step should also check `bContextAdded` through a small
  accessor, and wait one frame if it is false.
- **Offscreen viewport has no mouse position:** `select_actor` uses projection plus `GetHitResultAtScreenPosition`,
  never the OS cursor.
- **NavMesh not built in the cooked level:** assembly must run `nav_rebuild` and save the level. The scenario waits up to
  30 s for the nav system and fails `NO_NAVMESH` otherwise.
- **Shipping:** no logs and no console commands. Everything goes through the result and event files. Do not use
  `-ExecCmds` in scenario runs.
- **Exit codes:** some launch paths return 0 even after `RequestExit`. The result file is authoritative.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 3.0 | DONE | 2026-10-31T13:25Z | 2026-10-31T13:32Z | reports/P3/spike_inject.json (PASS: dev 1112.34cm, ship 1111.86cm >= 1000cm) |
| 3.1 | DONE | 2026-10-31T13:35Z | 2026-10-31T13:42Z | GameForgeEvents bus, GameForgeEventNames.h, retrofitted kit actors (EntityId), test_event_names_parity (1 passed), C++ build PASS |
| 3.2 | TODO | | | |
| 3.3 | TODO | | | |
| 3.4 | TODO | | | |
| 3.5 | TODO | | | |
| 3.6 | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
