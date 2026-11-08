#include "GameForgePlayer.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameForgeGameState.h"
#include "GameForgeGameDefinition.h"
#include "GameForgeKitActors.h"
#include "GameForgeKitBoard.h"
#include "GameForgeKitUI.h"
#include "GameForgeVisuals.h"
#include "Animation/AnimInstance.h"
#include "Blueprint/UserWidget.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/LocalPlayer.h"
#include "Engine/SkeletalMesh.h"
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
#include "Components/SkeletalMeshComponent.h"
#include "TimerManager.h"
#include "EngineUtils.h"
#include "Engine/OverlapResult.h"
#include "GameFramework/DamageType.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
	UGameForgeGameDefinition* LoadGameDefinition()
	{
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
		return DefAsset;
	}

	void EmitUiMessage(const UObject* Ctx, const FString& Text, float Seconds)
	{
		const FString Escaped = Text.ReplaceCharWithEscapedChar();
		UGameForgeEventLibrary::EmitGameForgeEvent(Ctx, FName(TEXT("ui.message")), TEXT("GameMode"),
			FString::Printf(TEXT("{\"text\":\"%s\",\"seconds\":%.2f}"), *Escaped, Seconds));
	}
}

// ── Character ─────────────────────────────────────────────────────────────────

AGameForgeCharacter::AGameForgeCharacter()
{
	PrimaryActorTick.bCanEverTick = true;

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

	ProxyBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProxyBody"));
	ProxyBody->SetupAttachment(RootComponent);
	ProxyBody->SetCollisionProfileName(TEXT("NoCollision"));
	ProxyBody->SetRelativeLocation(FVector(0.f, 0.f, -25.f));
	ProxyBody->SetRelativeScale3D(FVector(0.65f, 0.65f, 1.25f));
	ProxyBody->SetVisibility(false);

	ProxyHead = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProxyHead"));
	ProxyHead->SetupAttachment(RootComponent);
	ProxyHead->SetCollisionProfileName(TEXT("NoCollision"));
	ProxyHead->SetRelativeLocation(FVector(0.f, 0.f, 62.f));
	ProxyHead->SetRelativeScale3D(FVector(0.42f, 0.42f, 0.42f));
	ProxyHead->SetVisibility(false);

	// A visor shows which way the primitive body faces.
	ProxyVisor = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProxyVisor"));
	ProxyVisor->SetupAttachment(RootComponent);
	ProxyVisor->SetCollisionProfileName(TEXT("NoCollision"));
	ProxyVisor->SetRelativeLocation(FVector(18.f, 0.f, 64.f));
	ProxyVisor->SetRelativeScale3D(FVector(0.12f, 0.32f, 0.1f));
	ProxyVisor->SetVisibility(false);

	bUseControllerRotationYaw = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate = FRotator(0.f, 720.f, 0.f);
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

	ApplyMovementSettings();
	ApplyCameraMode();
	if (!bVisualsApplied)
	{
		ApplyVisuals(FString(), FString());
	}

	if (WeaponMesh && WeaponMesh->GetStaticMesh() == nullptr)
	{
		WeaponMesh->SetVisibility(false);
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

void AGameForgeCharacter::ApplyMovementSettings()
{
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->MaxWalkSpeed = bSprinting ? MoveSpeed * SprintMultiplier : MoveSpeed;
		Move->JumpZVelocity = JumpVelocity;
		Move->AirControl = FMath::Clamp(AirControl, 0.f, 1.f);
		Move->GravityScale = FMath::Clamp(GravityScale, 0.1f, 10.f);
		Move->BrakingDecelerationWalking = 2400.f;   // crisp stops instead of ice-skating
		Move->MaxAcceleration = 3000.f;
		Move->bCanWalkOffLedgesWhenCrouching = true;
	}
	JumpMaxCount = FMath::Clamp(MaxJumps, 1, 4);
}

void AGameForgeCharacter::SetSprinting(bool bNewSprinting)
{
	bSprinting = bNewSprinting;
	ApplyMovementSettings();
}

void AGameForgeCharacter::ApplyVisuals(const FString& MeshPath, const FString& AnimClassPath)
{
	bVisualsApplied = true;
	USkeletalMeshComponent* SkelComp = GetMesh();
	bool bHasSkeletal = SkelComp && SkelComp->GetSkeletalMeshAsset() != nullptr;

	if (SkelComp && !bHasSkeletal)
	{
		TArray<FString> Candidates;
		if (!MeshPath.IsEmpty())
		{
			Candidates.Add(MeshPath);
		}
		Candidates.Add(TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"));
		Candidates.Add(TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple"));
		for (const FString& Path : Candidates)
		{
			if (USkeletalMesh* SKM = LoadObject<USkeletalMesh>(nullptr, *Path))
			{
				SkelComp->SetSkeletalMeshAsset(SKM);
				SkelComp->SetRelativeLocation(FVector(0.f, 0.f, -90.f));
				SkelComp->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
				bHasSkeletal = true;
				break;
			}
		}
		if (bHasSkeletal)
		{
			const FString AnimPath = AnimClassPath.IsEmpty()
				? FString(TEXT("/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C"))
				: AnimClassPath;
			if (UClass* AnimClass = LoadClass<UAnimInstance>(nullptr, *AnimPath))
			{
				SkelComp->SetAnimInstanceClass(AnimClass);
			}
		}
	}

	const bool bFirstPerson = (CameraMode == EGameForgeCameraMode::FirstPerson);
	const bool bUseProxy = !bHasSkeletal;
	for (UStaticMeshComponent* Part : { ProxyBody.Get(), ProxyHead.Get(), ProxyVisor.Get() })
	{
		if (!Part)
		{
			continue;
		}
		Part->SetVisibility(bUseProxy);
		Part->SetOwnerNoSee(bFirstPerson);
	}
	if (bUseProxy)
	{
		GameForgeVisuals::SetBasicShape(ProxyBody, TEXT("Cylinder"));
		GameForgeVisuals::SetBasicShape(ProxyHead, TEXT("Sphere"));
		GameForgeVisuals::SetBasicShape(ProxyVisor, TEXT("Cube"));
		GameForgeVisuals::Tint(ProxyBody, BodyColor);
		GameForgeVisuals::Tint(ProxyHead, FLinearColor(0.95f, 0.8f, 0.65f));
		GameForgeVisuals::Tint(ProxyVisor, FLinearColor(0.05f, 0.05f, 0.08f));
	}
	else if (SkelComp)
	{
		for (int32 Slot = 0; Slot < SkelComp->GetNumMaterials(); ++Slot)
		{
			if (UMaterialInstanceDynamic* MID = SkelComp->CreateAndSetMaterialInstanceDynamic(Slot))
			{
				MID->SetVectorParameterValue(TEXT("Tint"), BodyColor);
			}
		}
	}
}

void AGameForgeCharacter::ApplyCameraMode()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	switch (CameraMode)
	{
	case EGameForgeCameraMode::TopDown:
		CameraBoom->TargetArmLength = 1500.f;
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetUsingAbsoluteRotation(true);   // the camera must not spin when the character turns
		CameraBoom->SetRelativeRotation(FRotator(-60.f, 0.f, 0.f));
		CameraBoom->bInheritYaw = false;
		CameraBoom->bDoCollisionTest = false;          // walls between camera and player must not zoom the view in
		CameraBoom->bEnableCameraLag = true;
		CameraBoom->CameraLagSpeed = 8.f;
		bUseControllerRotationYaw = false;
		GetCharacterMovement()->bOrientRotationToMovement = true;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(false);
		}
		if (WeaponMesh)
		{
			WeaponMesh->SetVisibility(false);
		}
		if (PC)
		{
			PC->bShowMouseCursor = true;   // cursor aiming
		}
		break;
	case EGameForgeCameraMode::FirstPerson:
		CameraBoom->TargetArmLength = 0.f;
		CameraBoom->bDoCollisionTest = false;
		CameraBoom->bEnableCameraLag = false;
		CameraBoom->SetRelativeLocation(FVector(0, 0, 68.f));
		CameraBoom->bUsePawnControlRotation = true;
		bUseControllerRotationYaw = true;
		GetCharacterMovement()->bOrientRotationToMovement = false;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(true);
		}
		if (WeaponMesh)
		{
			if (WeaponMesh->GetStaticMesh() == nullptr)
			{
				// A simple view-model so the player can see they are holding something.
				GameForgeVisuals::SetBasicShape(WeaponMesh, TEXT("Cube"));
				GameForgeVisuals::Tint(WeaponMesh, FLinearColor(0.12f, 0.12f, 0.14f));
			}
			WeaponMesh->AttachToComponent(Camera, FAttachmentTransformRules::SnapToTargetIncludingScale);
			WeaponMesh->SetRelativeLocation(FVector(40.f, 18.f, -16.f));
			WeaponMesh->SetRelativeRotation(FRotator::ZeroRotator);
			WeaponMesh->SetRelativeScale3D(FVector(0.45f, 0.08f, 0.1f));
			WeaponMesh->SetOwnerNoSee(false);
			WeaponMesh->SetVisibility(true);
		}
		if (PC)
		{
			PC->bShowMouseCursor = false;
		}
		break;
	case EGameForgeCameraMode::SideScroller:
		CameraBoom->TargetArmLength = 1200.f;
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->SetUsingAbsoluteRotation(true);
		CameraBoom->SetRelativeRotation(FRotator(-5.f, -90.f, 0.f));
		CameraBoom->bInheritYaw = false;
		CameraBoom->bDoCollisionTest = false;
		CameraBoom->bEnableCameraLag = true;
		CameraBoom->CameraLagSpeed = 10.f;
		bUseControllerRotationYaw = false;
		GetCharacterMovement()->bOrientRotationToMovement = true;
		// Keep the side-scroller on its lane.
		GetCharacterMovement()->SetPlaneConstraintEnabled(true);
		GetCharacterMovement()->SetPlaneConstraintNormal(FVector(0.f, 1.f, 0.f));
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(false);
		}
		if (WeaponMesh)
		{
			WeaponMesh->SetVisibility(false);
		}
		if (PC)
		{
			PC->bShowMouseCursor = false;
		}
		break;
	default:
		CameraBoom->TargetArmLength = 420.f;
		CameraBoom->bDoCollisionTest = true;
		CameraBoom->bUsePawnControlRotation = true;
		CameraBoom->SetUsingAbsoluteRotation(false);
		CameraBoom->SetRelativeLocation(FVector(0.f, 0.f, 40.f));
		CameraBoom->SocketOffset = FVector(0.f, 45.f, 25.f);   // over-the-shoulder framing
		CameraBoom->bEnableCameraLag = true;
		CameraBoom->CameraLagSpeed = 12.f;
		bUseControllerRotationYaw = false;
		GetCharacterMovement()->bOrientRotationToMovement = true;
		if (GetMesh())
		{
			GetMesh()->SetOwnerNoSee(false);
			if (WeaponMesh)
			{
				if (WeaponMesh->GetStaticMesh() != nullptr && GetMesh()->DoesSocketExist(FName(TEXT("hand_rSocket"))))
				{
					WeaponMesh->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetIncludingScale, FName(TEXT("hand_rSocket")));
					WeaponMesh->SetRelativeLocation(FVector::ZeroVector);
					WeaponMesh->SetRelativeRotation(FRotator::ZeroRotator);
					WeaponMesh->SetRelativeScale3D(FVector(0.12f, 0.45f, 0.15f));
					WeaponMesh->SetOwnerNoSee(false);
					WeaponMesh->SetVisibility(true);
				}
				else
				{
					WeaponMesh->SetVisibility(false);
				}
			}
		}
		if (PC)
		{
			PC->bShowMouseCursor = false;
		}
		break;
	}
	// Keep proxy-body owner visibility in sync with the camera mode.
	const bool bFirstPerson = (CameraMode == EGameForgeCameraMode::FirstPerson);
	for (UStaticMeshComponent* Part : { ProxyBody.Get(), ProxyHead.Get(), ProxyVisor.Get() })
	{
		if (Part)
		{
			Part->SetOwnerNoSee(bFirstPerson);
		}
	}
}

void AGameForgeCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bDead && GetActorLocation().Z < KillZ)
	{
		FellOutOfWorld(*GetDefault<UDamageType>());
	}
	if (AGameForgeGameState* GS = GetWorld() ? GetWorld()->GetGameState<AGameForgeGameState>() : nullptr)
	{
		if (AttributeSet)
		{
			const float H = AttributeSet->GetHealth();
			if (!FMath::IsNearlyEqual(GS->GetStat(FName(TEXT("player.health"))), H))
			{
				GS->SetStat(FName(TEXT("player.health")), H);
			}
			if (H <= 0.f && !bDead)
			{
				bDead = true;
				if (UCharacterMovementComponent* Move = GetCharacterMovement())
				{
					Move->DisableMovement();
				}
			}
		}
	}
}

void AGameForgeCharacter::ResetForRespawn()
{
	bDead = false;
	if (AttributeSet)
	{
		AttributeSet->SetMaxHealth(MaxHealth);
		AttributeSet->SetHealth(MaxHealth);
		AttributeSet->ResetDeathState();
	}
	if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
	{
		GS->SetStat(FName(TEXT("player.health")), MaxHealth);
	}
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->StopMovementImmediately();
		Move->SetMovementMode(MOVE_Walking);
	}
	ApplyMovementSettings();
}

FVector AGameForgeCharacter::ComputeAimDirection(FVector& OutMuzzle) const
{
	const FVector Chest = GetActorLocation() + FVector(0.f, 0.f, 35.f);
	APlayerController* PC = Cast<APlayerController>(GetController());

	switch (CameraMode)
	{
	case EGameForgeCameraMode::FirstPerson:
	{
		const FVector Fwd = Camera ? Camera->GetForwardVector() : GetActorForwardVector();
		OutMuzzle = (Camera ? Camera->GetComponentLocation() : Chest) + Fwd * 60.f;
		return Fwd;
	}
	case EGameForgeCameraMode::TopDown:
	{
		// Aim at the cursor on the ground plane (the camera points 60 degrees down, so its forward vector used to
		// fire every shot into the floor).
		FVector Dir = GetActorForwardVector();
		if (PC)
		{
			FHitResult Hit;
			if (PC->GetHitResultUnderCursor(ECC_Visibility, false, Hit))
			{
				FVector ToCursor = Hit.ImpactPoint - GetActorLocation();
				ToCursor.Z = 0.f;
				if (ToCursor.SizeSquared() > 100.f)
				{
					Dir = ToCursor.GetSafeNormal();
				}
			}
		}
		Dir.Z = 0.f;
		Dir = Dir.GetSafeNormal();
		OutMuzzle = Chest + Dir * 70.f;
		return Dir;
	}
	case EGameForgeCameraMode::SideScroller:
	{
		FVector Dir = GetActorForwardVector();
		Dir.Z = 0.f;
		Dir = Dir.GetSafeNormal();
		OutMuzzle = Chest + Dir * 70.f;
		return Dir;
	}
	default:
	{
		// Third person: shoot where the crosshair (camera centre) points.
		FVector Dir = GetActorForwardVector();
		if (Camera)
		{
			const FVector CamLoc = Camera->GetComponentLocation();
			const FVector CamFwd = Camera->GetForwardVector();
			FHitResult Hit;
			FCollisionQueryParams Params(SCENE_QUERY_STAT(GameForgeAim), false, this);
			const FVector TraceEnd = CamLoc + CamFwd * 10000.f;
			const FVector AimPoint = GetWorld()->LineTraceSingleByChannel(Hit, CamLoc, TraceEnd, ECC_Visibility, Params)
				? Hit.ImpactPoint : TraceEnd;
			Dir = (AimPoint - Chest).GetSafeNormal();
		}
		OutMuzzle = Chest + Dir * 70.f;
		return Dir;
	}
	}
}

void AGameForgeCharacter::PerformAttack()
{
	if (bDead)
	{
		return;
	}
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

	FVector SpawnLoc;
	const FVector AimDir = ComputeAimDirection(SpawnLoc);
	const FRotator SpawnRot = AimDir.Rotation();

	if (CameraMode == EGameForgeCameraMode::TopDown || CameraMode == EGameForgeCameraMode::SideScroller)
	{
		SetActorRotation(FRotator(0.f, SpawnRot.Yaw, 0.f));
	}

	FActorSpawnParameters Params;
	Params.Instigator = this;
	Params.Owner = this;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AGameForgeProjectile* Proj = GetWorld()->SpawnActor<AGameForgeProjectile>(
		AGameForgeProjectile::StaticClass(), SpawnLoc, SpawnRot, Params);
	if (Proj)
	{
		Proj->Damage = AttackDamage;
		Proj->Movement->InitialSpeed = ProjectileSpeed;
		Proj->Movement->MaxSpeed = ProjectileSpeed;
		Proj->Movement->Velocity = AimDir * ProjectileSpeed;
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

	// Soft lock-on: turn towards the closest living enemy in reach so melee is usable with any camera.
	AGameForgeEnemy* Closest = nullptr;
	float ClosestDistSq = FMath::Square(AttackRange * 1.6f);
	for (TActorIterator<AGameForgeEnemy> It(GetWorld()); It; ++It)
	{
		AGameForgeEnemy* E = *It;
		if (!E || E->IsDead())
		{
			continue;
		}
		const float D = FVector::DistSquared(E->GetActorLocation(), GetActorLocation());
		if (D < ClosestDistSq)
		{
			ClosestDistSq = D;
			Closest = E;
		}
	}
	if (Closest)
	{
		FVector To = Closest->GetActorLocation() - GetActorLocation();
		To.Z = 0.f;
		if (!To.IsNearlyZero())
		{
			SetActorRotation(To.Rotation());
		}
	}

	// Multi-hit sweep in front of the character: every enemy in the arc is struck (the old single sweep stopped at
	// the first wall or pickup it touched).
	const FVector Start = GetActorLocation() + GetActorForwardVector() * 40.f;
	const FVector End = GetActorLocation() + GetActorForwardVector() * AttackRange;
	TArray<FHitResult> Hits;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(GameForgeMelee), false, this);
	FCollisionObjectQueryParams ObjParams;
	ObjParams.AddObjectTypesToQuery(ECC_Pawn);
	ObjParams.AddObjectTypesToQuery(ECC_PhysicsBody);
	ObjParams.AddObjectTypesToQuery(ECC_WorldDynamic);
	GetWorld()->SweepMultiByObjectType(Hits, Start, End, FQuat::Identity, ObjParams, FCollisionShape::MakeSphere(75.f), Params);

	TSet<AActor*> Struck;
	for (const FHitResult& Hit : Hits)
	{
		AActor* A = Hit.GetActor();
		if (A && A != this && !Struck.Contains(A))
		{
			Struck.Add(A);
			UGameForgeDamageLibrary::ApplyDamage(A, this, AttackDamage);
		}
	}
}

void AGameForgeCharacter::PerformInteract()
{
	if (bDead)
	{
		return;
	}
	FVector Start = GetActorLocation();
	FVector End = Start + GetActorForwardVector() * 200.f;

	TArray<FHitResult> Hits;
	FCollisionQueryParams Params;
	Params.AddIgnoredActor(this);

	// Interactables may sit on static or dynamic channels; overlap everything around the player.
	TArray<FOverlapResult> Overlaps;
	FCollisionObjectQueryParams ObjParams(FCollisionObjectQueryParams::AllObjects);
	GetWorld()->OverlapMultiByObjectType(Overlaps, Start + GetActorForwardVector() * 80.f, FQuat::Identity, ObjParams,
		FCollisionShape::MakeSphere(180.f), Params);
	for (const FOverlapResult& O : Overlaps)
	{
		if (AActor* Act = O.GetActor())
		{
			if (IGameForgeInteractable* Inter = Cast<IGameForgeInteractable>(Act))
			{
				if (Inter->CanInteract(GetController()))
				{
					Inter->Interact(GetController());
					UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::InteractUsed, Act->GetName(), TEXT("{}"));
					return;
				}
				EmitUiMessage(this, TEXT("Locked"), 1.5f);
				return;
			}
		}
	}
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
	// Do not call Super: it destroys the pawn, which left the player with no character and no way to continue.
	if (bDead)
	{
		return;
	}
	UGameForgeEventLibrary::EmitGameForgeEvent(this, FName(TEXT("player.fell")), GetName(), TEXT("{\"cause\":\"fell\"}"));
	// Route through the attribute set so player.health, player.damaged and player.died stay consistent.
	if (!UGameForgeDamageLibrary::ApplyDamage(this, nullptr, 1000000.f))
	{
		bDead = true;
		UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerDied, GetName(), TEXT("{\"cause\":\"fell\"}"));
	}
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->StopMovementImmediately();
		Move->DisableMovement();
	}
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
	UInputAction* PrimaryAttack = Make(TEXT("IA_PrimaryAttack"), EInputActionValueType::Boolean);
	UInputAction* RollDice = Make(TEXT("IA_RollDice"), EInputActionValueType::Boolean);
	UInputAction* Interact = Make(TEXT("IA_Interact"), EInputActionValueType::Boolean);
	UInputAction* Sprint = Make(TEXT("IA_Sprint"), EInputActionValueType::Boolean);
	UInputAction* Pause = Make(TEXT("IA_Pause"), EInputActionValueType::Boolean);
	UInputAction* Restart = Make(TEXT("IA_Restart"), EInputActionValueType::Boolean);
	// Pause and restart must work while the game is paused / over.
	Pause->bTriggerWhenPaused = true;
	Restart->bTriggerWhenPaused = true;

	auto Swizzle = [this]() { return NewObject<UInputModifierSwizzleAxis>(MappingContext); };
	auto Negate = [this]() { return NewObject<UInputModifierNegate>(MappingContext); };

	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::W); M.Modifiers.Add(Swizzle()); }
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::S); M.Modifiers.Add(Swizzle()); M.Modifiers.Add(Negate()); }
	MappingContext->MapKey(Move, EKeys::D);
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::A); M.Modifiers.Add(Negate()); }
	// Arrow keys as an alternative layout.
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::Up); M.Modifiers.Add(Swizzle()); }
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::Down); M.Modifiers.Add(Swizzle()); M.Modifiers.Add(Negate()); }
	MappingContext->MapKey(Move, EKeys::Right);
	{ FEnhancedActionKeyMapping& M = MappingContext->MapKey(Move, EKeys::Left); M.Modifiers.Add(Negate()); }
	// Gamepad.
	MappingContext->MapKey(Move, EKeys::Gamepad_Left2D);
	MappingContext->MapKey(Look, EKeys::Gamepad_Right2D);

	MappingContext->MapKey(Look, EKeys::Mouse2D);
	MappingContext->MapKey(Jump, EKeys::SpaceBar);
	MappingContext->MapKey(Jump, EKeys::Gamepad_FaceButton_Bottom);
	MappingContext->MapKey(Select, EKeys::LeftMouseButton);
	MappingContext->MapKey(Attack, EKeys::LeftMouseButton);
	MappingContext->MapKey(Attack, EKeys::Gamepad_RightTrigger);
	MappingContext->MapKey(Fire, EKeys::LeftMouseButton);
	MappingContext->MapKey(PrimaryAttack, EKeys::LeftMouseButton);
	MappingContext->MapKey(RollDice, EKeys::LeftMouseButton);
	MappingContext->MapKey(Interact, EKeys::E);
	MappingContext->MapKey(Interact, EKeys::Gamepad_FaceButton_Left);
	MappingContext->MapKey(Sprint, EKeys::LeftShift);
	MappingContext->MapKey(Sprint, EKeys::Gamepad_LeftThumbstick);
	MappingContext->MapKey(Pause, EKeys::P);
	MappingContext->MapKey(Pause, EKeys::Gamepad_Special_Right);
	MappingContext->MapKey(Restart, EKeys::R);
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
		EIC->BindAction(FindAction(TEXT("IA_PrimaryAttack")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleAttack);
		EIC->BindAction(FindAction(TEXT("IA_RollDice")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleSelect);
		EIC->BindAction(FindAction(TEXT("IA_Interact")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleInteract);
		EIC->BindAction(FindAction(TEXT("IA_Sprint")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleSprintStarted);
		EIC->BindAction(FindAction(TEXT("IA_Sprint")), ETriggerEvent::Completed, this, &AGameForgePlayerController::HandleSprintCompleted);
		EIC->BindAction(FindAction(TEXT("IA_Pause")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandlePause);
		EIC->BindAction(FindAction(TEXT("IA_Restart")), ETriggerEvent::Started, this, &AGameForgePlayerController::HandleRestart);
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
		// Mouse input goes to the game (clicks select board cells / fire) while the cursor stays usable.
		FInputModeGameOnly Mode;
		SetInputMode(Mode);
		UGameForgeHUDWidget* HUD = CreateWidget<UGameForgeHUDWidget>(this, UGameForgeHUDWidget::StaticClass());
		if (HUD)
		{
			HUD->AddToViewport(0);
		}
	}
}

bool AGameForgePlayerController::IsGameplayBlocked() const
{
	if (IsPaused())
	{
		return true;
	}
	if (const AGameForgeGameMode* GM = GetWorld() ? GetWorld()->GetAuthGameMode<AGameForgeGameMode>() : nullptr)
	{
		return GM->IsGameOver();
	}
	return false;
}

void AGameForgePlayerController::HandleMove(const FInputActionValue& Value)
{
	if (IsGameplayBlocked())
	{
		return;
	}
	const FVector2D Axis = Value.Get<FVector2D>();
	if (APawn* P = GetPawn())
	{
		FRotator BasisRot = FRotator(0.f, GetControlRotation().Yaw, 0.f);
		if (AGameForgeCharacter* GFChar = Cast<AGameForgeCharacter>(P))
		{
			if (GFChar->IsDead())
			{
				return;
			}
			if (GFChar->CameraMode == EGameForgeCameraMode::TopDown)
			{
				BasisRot = GFChar->Camera ? FRotator(0.f, GFChar->Camera->GetComponentRotation().Yaw, 0.f) : FRotator::ZeroRotator;
			}
			else if (GFChar->CameraMode == EGameForgeCameraMode::SideScroller)
			{
				// Side view: A/D move along the lane (world X); W/S are ignored so the player stays on the lane.
				P->AddMovementInput(FVector(1.f, 0.f, 0.f), Axis.X);
				return;
			}
		}
		P->AddMovementInput(FRotationMatrix(BasisRot).GetUnitAxis(EAxis::X), Axis.Y);
		P->AddMovementInput(FRotationMatrix(BasisRot).GetUnitAxis(EAxis::Y), Axis.X);
	}
}

void AGameForgePlayerController::HandleLook(const FInputActionValue& Value)
{
	if (IsGameplayBlocked())
	{
		return;
	}
	if (const AGameForgeCharacter* GFChar = Cast<AGameForgeCharacter>(GetPawn()))
	{
		if (GFChar->CameraMode == EGameForgeCameraMode::TopDown || GFChar->CameraMode == EGameForgeCameraMode::SideScroller)
		{
			return;
		}
	}
	const FVector2D Axis = Value.Get<FVector2D>();
	AddYawInput(Axis.X);
	AddPitchInput(-Axis.Y);
}

void AGameForgePlayerController::HandleJumpStarted(const FInputActionValue& Value)
{
	if (IsGameplayBlocked())
	{
		return;
	}
	if (AGameForgeCharacter* GFChar = Cast<AGameForgeCharacter>(GetPawn()))
	{
		if (GFChar->IsDead())
		{
			return;
		}
	}
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
	if (IsGameplayBlocked())
	{
		return;
	}
	FVector2D Mouse;
	if (GetMousePosition(Mouse.X, Mouse.Y))
	{
		SelectAtScreenPosition(Mouse);
	}
}

void AGameForgePlayerController::HandleAttack(const FInputActionValue& Value)
{
	if (IsGameplayBlocked())
	{
		return;
	}
	if (AGameForgeCharacter* C = Cast<AGameForgeCharacter>(GetPawn()))
	{
		C->PerformAttack();
	}
}

void AGameForgePlayerController::HandleInteract(const FInputActionValue& Value)
{
	if (IsGameplayBlocked())
	{
		return;
	}
	if (AGameForgeCharacter* C = Cast<AGameForgeCharacter>(GetPawn()))
	{
		C->PerformInteract();
	}
}

void AGameForgePlayerController::HandleSprintStarted(const FInputActionValue& Value)
{
	if (AGameForgeCharacter* C = Cast<AGameForgeCharacter>(GetPawn()))
	{
		C->SetSprinting(true);
	}
}

void AGameForgePlayerController::HandleSprintCompleted(const FInputActionValue& Value)
{
	if (AGameForgeCharacter* C = Cast<AGameForgeCharacter>(GetPawn()))
	{
		C->SetSprinting(false);
	}
}

void AGameForgePlayerController::HandlePause(const FInputActionValue& Value)
{
	if (const AGameForgeGameMode* GM = GetWorld() ? GetWorld()->GetAuthGameMode<AGameForgeGameMode>() : nullptr)
	{
		if (GM->IsGameOver())
		{
			return;
		}
	}
	const bool bNowPaused = !IsPaused();
	SetPause(bNowPaused);
	UGameForgeEventLibrary::EmitGameForgeEvent(this, bNowPaused ? GFEvent::GamePaused : GFEvent::GameResumed, GetName(), TEXT("{}"));
}

void AGameForgePlayerController::HandleRestart(const FInputActionValue& Value)
{
	AGameForgeGameMode* GM = GetWorld() ? GetWorld()->GetAuthGameMode<AGameForgeGameMode>() : nullptr;
	// Restart is only offered on the end screen or while paused, so a stray R press never wipes progress.
	if (GM && (GM->IsGameOver() || IsPaused()))
	{
		SetPause(false);
		GM->RestartCurrentGame();
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
	ConfigurePlayer(UGameplayStatics::GetPlayerController(this, 0));
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GameStarted, GetName(), TEXT("{}"));
}

void AGameForgeGameModeBase::RestartPlayer(AController* NewPlayer)
{
	Super::RestartPlayer(NewPlayer);
	ConfigurePlayer(NewPlayer);
}

void AGameForgeGameModeBase::ConfigurePlayer(AController* Controller)
{
	if (!Controller)
	{
		return;
	}
	AGameForgeCharacter* Char = Cast<AGameForgeCharacter>(Controller->GetPawn());
	if (!Char)
	{
		return;
	}

	UGameForgeGameDefinition* DefAsset = LoadGameDefinition();
	TSharedPtr<FJsonObject> Def;
	if (DefAsset)
	{
		Def = DefAsset->GetParsed();
	}
	if (!Def.IsValid())
	{
		Char->ApplyVisuals(FString(), FString());
		return;
	}

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

	// 2. Player attributes
	FString MeshPath, AnimPath;
	if (PlayerObj && *PlayerObj)
	{
		const TSharedPtr<FJsonObject>& P = *PlayerObj;
		double Speed = Char->MoveSpeed, JumpZ = Char->JumpVelocity, MaxHP = Char->MaxHealth;
		int32 LivesVal = 0;
		P->TryGetNumberField(TEXT("move_speed"), Speed);
		P->TryGetNumberField(TEXT("jump_velocity"), JumpZ);
		P->TryGetNumberField(TEXT("max_health"), MaxHP);
		P->TryGetNumberField(TEXT("lives"), LivesVal);

		FString AttackMode;
		if (P->TryGetStringField(TEXT("attack_mode"), AttackMode))
		{
			if (AttackMode.Equals(TEXT("projectile"), ESearchCase::IgnoreCase) ||
				AttackMode.Equals(TEXT("ranged"), ESearchCase::IgnoreCase))
			{
				Char->bProjectileAttack = true;
			}
			else if (AttackMode.Equals(TEXT("melee"), ESearchCase::IgnoreCase) && Char->CameraMode != EGameForgeCameraMode::FirstPerson)
			{
				Char->bProjectileAttack = false;
			}
		}
		double V = 0.0;
		if (P->TryGetNumberField(TEXT("attack_damage"), V) && V > 0.0) { Char->AttackDamage = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("attack_range"), V) && V > 0.0) { Char->AttackRange = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("attack_cooldown"), V) && V > 0.0) { Char->AttackCooldown = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("projectile_speed"), V) && V > 0.0) { Char->ProjectileSpeed = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("air_control"), V)) { Char->AirControl = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("gravity_scale"), V) && V > 0.0) { Char->GravityScale = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("sprint_multiplier"), V) && V >= 1.0) { Char->SprintMultiplier = static_cast<float>(V); }
		if (P->TryGetNumberField(TEXT("kill_z"), V)) { Char->KillZ = static_cast<float>(V); }
		int32 Jumps = Char->MaxJumps;
		if (P->TryGetNumberField(TEXT("max_jumps"), Jumps)) { Char->MaxJumps = FMath::Clamp(Jumps, 1, 4); }
		bool bDouble = false;
		if (P->TryGetBoolField(TEXT("double_jump"), bDouble) && bDouble) { Char->MaxJumps = FMath::Max(Char->MaxJumps, 2); }

		const TArray<TSharedPtr<FJsonValue>>* Tint = nullptr;
		if (P->TryGetArrayField(TEXT("material_tint"), Tint) && Tint && Tint->Num() >= 3)
		{
			TArray<double> Values;
			for (const TSharedPtr<FJsonValue>& C : *Tint) { Values.Add(C->AsNumber()); }
			const FLinearColor Parsed = GameForgeVisuals::ColorFromArray(Values, Char->BodyColor);
			// A pure-white tint means "no tint"; keep the readable default player colour then.
			if (!Parsed.Equals(FLinearColor::White))
			{
				Char->BodyColor = Parsed;
			}
		}
		P->TryGetStringField(TEXT("mesh"), MeshPath);
		P->TryGetStringField(TEXT("anim_class"), AnimPath);

		Char->MoveSpeed = static_cast<float>(Speed);
		Char->JumpVelocity = static_cast<float>(JumpZ);
		Char->MaxHealth = static_cast<float>(MaxHP);
		Char->Lives = LivesVal;

		if (Char->AttributeSet)
		{
			Char->AttributeSet->SetMaxHealth(Char->MaxHealth);
			Char->AttributeSet->SetHealth(Char->MaxHealth);
		}
		if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
		{
			GS->SetStat(FName(TEXT("player.health")), Char->MaxHealth);
			GS->SetStat(FName(TEXT("player.max_health")), Char->MaxHealth);
			if (LivesVal > 0)
			{
				GS->SetStat(FName(TEXT("player.lives")), static_cast<float>(LivesVal));
			}
		}
	}
	Char->ApplyMovementSettings();
	Char->ApplyCameraMode();
	Char->ApplyVisuals(MeshPath, AnimPath);
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

	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		if (APawn* P = PC->GetPawn())
		{
			InitialTransform = P->GetActorTransform();
			bHasInitialTransform = true;
		}
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.AddUObject(this, &AGameForgeGameMode::HandleEvent);
	}
}

void AGameForgeGameMode::HandleEvent(const FGameForgeEvent& Event)
{
	if (Event.Name == GFEvent::GameWon || Event.Name == GFEvent::GameLost)
	{
		// The rules subsystem ends the game by emitting these events; the mode used to ignore them, so the player
		// kept running around after winning or losing.
		if (!bEnded)
		{
			bEnded = true;
			GetWorldTimerManager().ClearTimer(RespawnTimer);
			if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
			{
				if (APawn* P = PC->GetPawn())
				{
					if (ACharacter* C = Cast<ACharacter>(P))
					{
						C->GetCharacterMovement()->StopMovementImmediately();
					}
				}
				PC->bShowMouseCursor = true;
			}
		}
		return;
	}

	if (Event.Name == GFEvent::PlayerDied && !bEnded)
	{
		APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
		AGameForgeCharacter* Char = PC ? Cast<AGameForgeCharacter>(PC->GetPawn()) : nullptr;
		if (Char && Char->Lives > 0)
		{
			Char->Lives--;
			if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
			{
				GS->SetStat(FName(TEXT("player.lives")), static_cast<float>(Char->Lives));
			}
		}
		EmitUiMessage(this, (Char && Char->Lives > 0) ? FString::Printf(TEXT("You died - %d lives left"), Char->Lives)
			: FString(TEXT("You died")), RespawnDelay);
		// Respawn after a short delay unless a lose condition ended the game in the meantime (previously the
		// player respawned only when Lives > 0 *and* a checkpoint had been touched, otherwise stayed dead forever).
		GetWorldTimerManager().SetTimer(RespawnTimer, this, &AGameForgeGameMode::RespawnPlayerNow, RespawnDelay, false);
	}
}

void AGameForgeGameMode::RespawnPlayerNow()
{
	if (bEnded)
	{
		return;
	}
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	AGameForgeCharacter* Char = PC ? Cast<AGameForgeCharacter>(PC->GetPawn()) : nullptr;
	if (!Char)
	{
		if (PC)
		{
			RestartPlayer(PC);
		}
		return;
	}
	FTransform Target = RespawnTransform;
	if (Target.GetLocation().IsNearlyZero())
	{
		if (bHasInitialTransform)
		{
			Target = InitialTransform;
		}
		else if (AActor* Start = FindPlayerStart(PC))
		{
			Target = Start->GetActorTransform();
		}
	}
	Char->SetActorLocationAndRotation(Target.GetLocation(), Target.GetRotation(), false, nullptr, ETeleportType::TeleportPhysics);
	Char->ResetForRespawn();
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PlayerRespawned, Char->GetName(), TEXT("{}"));
}

void AGameForgeGameMode::EndGame(bool bWon, const FString& Reason)
{
	if (bEnded) return;
	// The event handler flips bEnded and freezes the player.
	UGameForgeEventLibrary::EmitGameForgeEvent(
		this,
		bWon ? GFEvent::GameWon : GFEvent::GameLost,
		GetName(),
		FString::Printf(TEXT("{\"reason\":\"%s\"}"), *Reason.ReplaceCharWithEscapedChar())
	);
	bEnded = true;
}

void AGameForgeGameMode::RestartCurrentGame()
{
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GameRestarted, GetName(), TEXT("{}"));
	UGameplayStatics::OpenLevel(this, FName(*UGameplayStatics::GetCurrentLevelName(this)));
}
