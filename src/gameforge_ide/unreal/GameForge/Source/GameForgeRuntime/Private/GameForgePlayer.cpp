#include "GameForgePlayer.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameForgeGameState.h"
#include "GameForgeGameDefinition.h"
#include "GameForgeKitActors.h"
#include "GameForgeKitBoard.h"
#include "GameForgeKitUI.h"
#include "Blueprint/UserWidget.h"
#include "Camera/CameraComponent.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Kismet/GameplayStatics.h"
#include "CollisionQueryParams.h"

// ── Character ─────────────────────────────────────────────────────────────────

AGameForgeCharacter::AGameForgeCharacter()
{
	AbilitySystemComponent = CreateDefaultSubobject<UAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet = CreateDefaultSubobject<UGameForgeAttributeSet>(TEXT("AttributeSet"));

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 400.f;
	CameraBoom->bUsePawnControlRotation = true;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom);

	WeaponMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(Camera);
	WeaponMesh->SetCollisionProfileName(TEXT("NoCollision"));
	WeaponMesh->SetCastShadow(false);

	bUseControllerRotationYaw = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate = FRotator(0.f, 540.f, 0.f);
}

void AGameForgeCharacter::BeginPlay()
{
	Super::BeginPlay();
	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->InitAbilityActorInfo(this, this);
		AttributeSet->SetMaxHealth(MaxHealth);
		AttributeSet->SetHealth(MaxHealth);
	}

	if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
	{
		GS->SetStat(FName(TEXT("player.health")), MaxHealth);
	}

	GetCharacterMovement()->MaxWalkSpeed = MoveSpeed;
	GetCharacterMovement()->JumpZVelocity = JumpVelocity;
	ApplyCameraMode();

	if (WeaponMesh && WeaponMesh->GetStaticMesh() == nullptr)
	{
		if (UStaticMesh* DefaultGunMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
		{
			WeaponMesh->SetStaticMesh(DefaultGunMesh);
		}
	}

	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerSpawned, GetName(), TEXT("{}"));
}

void AGameForgeCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->InitAbilityActorInfo(this, this);
	}
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
		CameraBoom->bDoCollisionTest = true;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(false);
		}
		if (WeaponMesh)
		{
			WeaponMesh->SetVisibility(false);
		}
		break;
	case EGameForgeCameraMode::FirstPerson:
		CameraBoom->TargetArmLength = 0.f;
		CameraBoom->bDoCollisionTest = false;
		CameraBoom->SetRelativeLocation(FVector(0, 0, 68.f));
		bUseControllerRotationYaw = true;
		GetCharacterMovement()->bOrientRotationToMovement = false;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(true);
		}
		if (WeaponMesh)
		{
			WeaponMesh->AttachToComponent(Camera, FAttachmentTransformRules::SnapToTargetIncludingScale);
			WeaponMesh->SetRelativeLocation(FVector(35.f, 15.f, -12.f));
			WeaponMesh->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
			WeaponMesh->SetRelativeScale3D(FVector(0.12f, 0.45f, 0.15f));
			WeaponMesh->SetOwnerNoSee(false);
			WeaponMesh->SetVisibility(true);
		}
		break;
	case EGameForgeCameraMode::SideScroller:
		CameraBoom->TargetArmLength = 1200.f;
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
		CameraBoom->bInheritYaw = false;
		CameraBoom->bDoCollisionTest = true;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(false);
		}
		if (WeaponMesh)
		{
			WeaponMesh->SetVisibility(false);
		}
		break;
	default:
		CameraBoom->TargetArmLength = 400.f;
		CameraBoom->bDoCollisionTest = true;
		CameraBoom->bUsePawnControlRotation = true;
		CameraBoom->SetRelativeLocation(FVector::ZeroVector);
		bUseControllerRotationYaw = false;
		GetCharacterMovement()->bOrientRotationToMovement = true;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(false);
			if (WeaponMesh)
			{
				WeaponMesh->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetIncludingScale, FName(TEXT("hand_rSocket")));
				WeaponMesh->SetRelativeLocation(FVector::ZeroVector);
				WeaponMesh->SetRelativeRotation(FRotator::ZeroRotator);
				WeaponMesh->SetRelativeScale3D(FVector(0.12f, 0.45f, 0.15f));
				WeaponMesh->SetOwnerNoSee(false);
				WeaponMesh->SetVisibility(true);
			}
		}
		break;
	}
}

void AGameForgeCharacter::PerformAttack()
{
	if (bProjectileAttack || CameraMode == EGameForgeCameraMode::FirstPerson)
	{
		PerformRangedAttack();
	}
	else
	{
		PerformMeleeAttack();
	}
}

void AGameForgeCharacter::PerformRangedAttack()
{
	float CurTime = GetWorld()->GetTimeSeconds();
	if (CurTime - LastAttackTime < AttackCooldown)
	{
		return;
	}
	LastAttackTime = CurTime;

	FVector SpawnLoc = Camera ? (Camera->GetComponentLocation() + Camera->GetForwardVector() * 80.f)
	                          : (GetActorLocation() + GetActorForwardVector() * 80.f);
	FRotator SpawnRot = Camera ? Camera->GetComponentRotation() : GetActorRotation();

	FActorSpawnParameters Params;
	Params.Instigator = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AGameForgeProjectile* Proj = GetWorld()->SpawnActor<AGameForgeProjectile>(
		AGameForgeProjectile::StaticClass(), SpawnLoc, SpawnRot, Params);
	if (Proj)
	{
		Proj->Damage = AttackDamage;
		Proj->Movement->InitialSpeed = ProjectileSpeed;
		Proj->Movement->MaxSpeed = ProjectileSpeed;
	}
}

void AGameForgeCharacter::PerformMeleeAttack()
{
	float CurTime = GetWorld()->GetTimeSeconds();
	if (CurTime - LastAttackTime < AttackCooldown)
	{
		return;
	}
	LastAttackTime = CurTime;

	FVector Start = GetActorLocation();
	FVector End = Start + GetActorForwardVector() * AttackRange;

	FHitResult Hit;
	FCollisionQueryParams Params;
	Params.AddIgnoredActor(this);

	if (GetWorld()->SweepSingleByChannel(Hit, Start, End, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(60.f), Params))
	{
		if (Hit.GetActor())
		{
			UGameForgeDamageLibrary::ApplyDamage(Hit.GetActor(), this, AttackDamage);
		}
	}
}

void AGameForgeCharacter::PerformInteract()
{
	FVector Start = GetActorLocation();
	FVector End = Start + GetActorForwardVector() * 200.f;

	TArray<FHitResult> Hits;
	FCollisionQueryParams Params;
	Params.AddIgnoredActor(this);

	if (GetWorld()->SweepMultiByChannel(Hits, Start, End, FQuat::Identity, ECC_WorldDynamic, FCollisionShape::MakeSphere(100.f), Params))
	{
		for (const FHitResult& Hit : Hits)
		{
			if (AActor* Act = Hit.GetActor())
			{
				if (IGameForgeInteractable* Inter = Cast<IGameForgeInteractable>(Act))
				{
					if (Inter->CanInteract(GetController()))
					{
						Inter->Interact(GetController());
						UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::InteractUsed, Act->GetName(), TEXT("{}"));
						break;
					}
				}
			}
		}
	}
}

void AGameForgeCharacter::FellOutOfWorld(const UDamageType& dmgType)
{
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerDied, GetName(), TEXT("{\"cause\":\"fell\"}"));
	Super::FellOutOfWorld(dmgType);
}

// ── Player Controller ─────────────────────────────────────────────────────────

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
	UInputAction* Move = Make(TEXT("IA_Move"), EInputActionValueType::Axis2D);
	UInputAction* Look = Make(TEXT("IA_Look"), EInputActionValueType::Axis2D);
	UInputAction* Jump = Make(TEXT("IA_Jump"), EInputActionValueType::Boolean);
	UInputAction* Select = Make(TEXT("IA_Select"), EInputActionValueType::Boolean);
	UInputAction* Attack = Make(TEXT("IA_Attack"), EInputActionValueType::Boolean);
	UInputAction* Fire = Make(TEXT("IA_Fire"), EInputActionValueType::Boolean);
	UInputAction* Interact = Make(TEXT("IA_Interact"), EInputActionValueType::Boolean);

	auto Swizzle = [this]() { return NewObject<UInputModifierSwizzleAxis>(MappingContext); };
	auto Negate = [this]() { return NewObject<UInputModifierNegate>(MappingContext); };

	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::W); M.Modifiers.Add(Swizzle()); }
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::S); M.Modifiers.Add(Swizzle()); M.Modifiers.Add(Negate()); }
	MappingContext->MapKey(Move, EKeys::D);
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::A); M.Modifiers.Add(Negate()); }

	MappingContext->MapKey(Look, EKeys::Mouse2D);
	MappingContext->MapKey(Jump, EKeys::SpaceBar);
	MappingContext->MapKey(Select, EKeys::LeftMouseButton);
	MappingContext->MapKey(Attack, EKeys::LeftMouseButton);
	MappingContext->MapKey(Fire, EKeys::LeftMouseButton);
	MappingContext->MapKey(Interact, EKeys::E);
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
		EIC->BindAction(FindAction(TEXT("IA_Attack")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleAttack);
		EIC->BindAction(FindAction(TEXT("IA_Fire")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleAttack);
		EIC->BindAction(FindAction(TEXT("IA_Interact")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleInteract);
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
	if (IsLocalController())
	{
		UGameForgeHUDWidget* HUD = CreateWidget<UGameForgeHUDWidget>(this, UGameForgeHUDWidget::StaticClass());
		if (HUD)
		{
			HUD->AddToViewport(0);
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

void AGameForgePlayerController::HandleAttack(const FInputActionValue& Value)
{
	if (AGameForgeCharacter* C = Cast<AGameForgeCharacter>(GetPawn()))
	{
		C->PerformAttack();
	}
}

void AGameForgePlayerController::HandleInteract(const FInputActionValue& Value)
{
	if (AGameForgeCharacter* C = Cast<AGameForgeCharacter>(GetPawn()))
	{
		C->PerformInteract();
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
	if (IGameForgeSelectable* Sel = Cast<IGameForgeSelectable>(Hit.GetComponent()))
	{
		Sel->OnSelected(this);
	}
	else if (IGameForgeSelectable* SelActor = Cast<IGameForgeSelectable>(Target))
	{
		SelActor->OnSelected(this);
	}
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::InteractUsed, Target->GetName(), TEXT("{\"via\":\"select\"}"));
	return Target;
}

// ── GameModeBase & GameMode ───────────────────────────────────────────────────

AGameForgeGameModeBase::AGameForgeGameModeBase()
{
	DefaultPawnClass = AGameForgeCharacter::StaticClass();
	PlayerControllerClass = AGameForgePlayerController::StaticClass();
	GameStateClass = AGameForgeGameState::StaticClass();
}

void AGameForgeGameModeBase::StartPlay()
{
	Super::StartPlay();
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GameStarted, GetName(), TEXT("{}"));
}

AGameForgeGameMode::AGameForgeGameMode()
{
	DefaultPawnClass = AGameForgeCharacter::StaticClass();
	PlayerControllerClass = AGameForgePlayerController::StaticClass();
	GameStateClass = AGameForgeGameState::StaticClass();
}

void AGameForgeGameMode::StartPlay()
{
	Super::StartPlay();

	// Read player parameters from definition
	const UGameForgeRuntimeSettings* Settings = GetDefault<UGameForgeRuntimeSettings>();
	UGameForgeGameDefinition* DefAsset = (Settings && !Settings->GameDefinition.IsNull())
		? Settings->GameDefinition.LoadSynchronous()
		: nullptr;
	if (!DefAsset)
	{
		DefAsset = LoadObject<UGameForgeGameDefinition>(nullptr, TEXT("/Game/GameForge/GD_Main.GD_Main"));
	}
	if (!DefAsset)
	{
		DefAsset = LoadObject<UGameForgeGameDefinition>(nullptr, TEXT("/Game/GameForge/GD_Main"));
	}

	if (DefAsset)
	{
		TSharedPtr<FJsonObject> Def = DefAsset->GetParsed();
		if (Def.IsValid())
		{
			APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
			AGameForgeCharacter* Char = PC ? Cast<AGameForgeCharacter>(PC->GetPawn()) : nullptr;
			if (Char)
			{
				// 1. Camera mode parsing
				FString CamModeStr;
				const TSharedPtr<FJsonObject>* PlayerObj = nullptr;
				if (Def->TryGetObjectField(TEXT("player"), PlayerObj) && PlayerObj)
				{
					(*PlayerObj)->TryGetStringField(TEXT("camera"), CamModeStr);
				}
				if (CamModeStr.IsEmpty())
				{
					Def->TryGetStringField(TEXT("camera"), CamModeStr);
				}

				if (CamModeStr.Equals(TEXT("first_person"), ESearchCase::IgnoreCase) ||
					CamModeStr.Equals(TEXT("fps"), ESearchCase::IgnoreCase) ||
					CamModeStr.Equals(TEXT("FirstPerson"), ESearchCase::IgnoreCase))
				{
					Char->CameraMode = EGameForgeCameraMode::FirstPerson;
					Char->bProjectileAttack = true;
				}
				else if (CamModeStr.Equals(TEXT("top_down"), ESearchCase::IgnoreCase) ||
						 CamModeStr.Equals(TEXT("TopDown"), ESearchCase::IgnoreCase))
				{
					Char->CameraMode = EGameForgeCameraMode::TopDown;
				}
				else if (CamModeStr.Equals(TEXT("side_scroller"), ESearchCase::IgnoreCase) ||
						 CamModeStr.Equals(TEXT("SideScroller"), ESearchCase::IgnoreCase))
				{
					Char->CameraMode = EGameForgeCameraMode::SideScroller;
				}
				else if (CamModeStr.Equals(TEXT("third_person"), ESearchCase::IgnoreCase) ||
						 CamModeStr.Equals(TEXT("ThirdPerson"), ESearchCase::IgnoreCase))
				{
					Char->CameraMode = EGameForgeCameraMode::ThirdPerson;
				}
				Char->ApplyCameraMode();

				// 2. Player attributes
				if (PlayerObj && *PlayerObj)
				{
					double Speed = 600.0, JumpZ = 650.0, MaxHP = 100.0;
					int32 LivesVal = 0;
					(*PlayerObj)->TryGetNumberField(TEXT("move_speed"), Speed);
					(*PlayerObj)->TryGetNumberField(TEXT("jump_velocity"), JumpZ);
					(*PlayerObj)->TryGetNumberField(TEXT("max_health"), MaxHP);
					(*PlayerObj)->TryGetNumberField(TEXT("lives"), LivesVal);

					FString AttackMode;
					if ((*PlayerObj)->TryGetStringField(TEXT("attack_mode"), AttackMode))
					{
						if (AttackMode.Equals(TEXT("projectile"), ESearchCase::IgnoreCase) ||
							AttackMode.Equals(TEXT("ranged"), ESearchCase::IgnoreCase))
						{
							Char->bProjectileAttack = true;
						}
					}
					double AtkDamage = 0.0;
					if ((*PlayerObj)->TryGetNumberField(TEXT("attack_damage"), AtkDamage) && AtkDamage > 0.0)
					{
						Char->AttackDamage = static_cast<float>(AtkDamage);
					}
					double ProjSpeed = 0.0;
					if ((*PlayerObj)->TryGetNumberField(TEXT("projectile_speed"), ProjSpeed) && ProjSpeed > 0.0)
					{
						Char->ProjectileSpeed = static_cast<float>(ProjSpeed);
					}

					Char->MoveSpeed = static_cast<float>(Speed);
					Char->JumpVelocity = static_cast<float>(JumpZ);
					Char->MaxHealth = static_cast<float>(MaxHP);
					Char->Lives = LivesVal;

					Char->GetCharacterMovement()->MaxWalkSpeed = Char->MoveSpeed;
					Char->GetCharacterMovement()->JumpZVelocity = Char->JumpVelocity;
					if (Char->AttributeSet)
					{
						Char->AttributeSet->SetMaxHealth(Char->MaxHealth);
						Char->AttributeSet->SetHealth(Char->MaxHealth);
					}
				}
			}
		}
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.AddUObject(this, &AGameForgeGameMode::HandleEvent);
	}
}

void AGameForgeGameMode::HandleEvent(const FGameForgeEvent& Event)
{
	if (Event.Name == GFEvent::PlayerDied)
	{
		APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
		if (AGameForgeCharacter* Char = PC ? Cast<AGameForgeCharacter>(PC->GetPawn()) : nullptr)
		{
			if (Char->Lives > 0 && !RespawnTransform.GetLocation().IsZero())
			{
				Char->Lives--;
				Char->SetActorTransform(RespawnTransform);
				if (Char->AttributeSet)
				{
					Char->AttributeSet->SetHealth(Char->MaxHealth);
				}
				UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerRespawned, Char->GetName(), TEXT("{}"));
			}
		}
	}
}

void AGameForgeGameMode::EndGame(bool bWon, const FString& Reason)
{
	if (bEnded) return;
	bEnded = true;

	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (APawn* P = PC->GetPawn())
		{
			P->DisableInput(PC);
		}
	}

	UGameForgeEventLibrary::EmitGameForgeEvent(
		this,
		bWon ? GFEvent::GameWon : GFEvent::GameLost,
		GetName(),
		FString::Printf(TEXT("{\"reason\":\"%s\"}"), *Reason)
	);
}

void AGameForgeGameMode::RestartCurrentGame()
{
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GameRestarted, GetName(), TEXT("{}"));
	UGameplayStatics::OpenLevel(this, FName(*UGameplayStatics::GetCurrentLevelName(this)));
}
