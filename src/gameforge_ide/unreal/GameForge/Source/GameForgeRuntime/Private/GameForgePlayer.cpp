#include "GameForgePlayer.h"

#include "Camera/CameraComponent.h"
#include "Engine/LocalPlayer.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputCoreTypes.h"
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
		CameraBoom->TargetArmLength = 1400.f;
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetRelativeRotation(FRotator(-60.f, 0.f, 0.f));
		CameraBoom->bInheritYaw = false;
		break;
	case EGameForgeCameraMode::FirstPerson:
		CameraBoom->TargetArmLength = 0.f;
		CameraBoom->SetRelativeLocation(FVector(0, 0, 64.f));
		bUseControllerRotationYaw = true;
		GetCharacterMovement()->bOrientRotationToMovement = false;
		break;
	case EGameForgeCameraMode::SideScroller:
		CameraBoom->TargetArmLength = 1200.f;
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
		CameraBoom->bInheritYaw = false;
		break;
	default:
		break; // ThirdPerson: constructor defaults
	}
}

UInputAction* AGameForgePlayerController::FindAction(FName ActionId) const
{
	const TObjectPtr<UInputAction>* Found = Actions.Find(ActionId);
	return Found ? Found->Get() : nullptr;
}

void AGameForgePlayerController::BuildDefaultInput()
{
	if (Actions.Num() > 0)
	{
		return;
	}
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
		EIC->BindAction(FindAction(TEXT("IA_Move")), ETriggerEvent::Triggered, this, &AGameForgePlayerController::HandleMove);
		EIC->BindAction(FindAction(TEXT("IA_Look")), ETriggerEvent::Triggered, this, &AGameForgePlayerController::HandleLook);
		EIC->BindAction(FindAction(TEXT("IA_Jump")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleJumpStarted);
		EIC->BindAction(FindAction(TEXT("IA_Jump")), ETriggerEvent::Completed, this, &AGameForgePlayerController::HandleJumpCompleted);
		EIC->BindAction(FindAction(TEXT("IA_Select")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleSelect);
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

void AGameForgePlayerController::HandleLook(const FInputActionValue& Value)
{
	const FVector2D Axis = Value.Get<FVector2D>();
	AddYawInput(Axis.X);
	AddPitchInput(-Axis.Y);
}

void AGameForgePlayerController::HandleJumpStarted(const FInputActionValue& Value)
{
	if (ACharacter* C = Cast<ACharacter>(GetPawn()))
	{
		C->Jump();
		UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerJumped, C->GetName(), TEXT("{}"));
	}
}

void AGameForgePlayerController::HandleJumpCompleted(const FInputActionValue& Value)
{
	if (ACharacter* C = Cast<ACharacter>(GetPawn()))
	{
		C->StopJumping();
	}
}

void AGameForgePlayerController::HandleSelect(const FInputActionValue& Value)
{
	FVector2D Mouse;
	if (GetMousePosition(Mouse.X, Mouse.Y))
	{
		SelectAtScreenPosition(Mouse);
	}
}

AActor* AGameForgePlayerController::SelectAtScreenPosition(FVector2D ScreenPosition)
{
	FHitResult Hit;
	if (!GetHitResultAtScreenPosition(ScreenPosition, ECC_Visibility, false, Hit) || !Hit.GetActor())
	{
		return nullptr;
	}
	AActor* Target = Hit.GetActor();
	UGameForgeEventLibrary::EmitGameForgeEvent(this, FName(TEXT("interact.used")), Target->GetName(), TEXT("{\"via\":\"select\"}"));
	return Target;
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
