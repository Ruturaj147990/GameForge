#include "GameForgeKitActors.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameState.h"
#include "GameForgePlayer.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "TimerManager.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Components/CapsuleComponent.h"
#include "Animation/AnimInstance.h"
#include "Navigation/PathFollowingComponent.h"
#include "NavigationSystem.h"
#include "GameForgeGameDefinition.h"
#include "GameForgeVisuals.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

// ── Hazard ────────────────────────────────────────────────────────────────────

AGameForgeHazard::AGameForgeHazard()
{
	PrimaryActorTick.bCanEverTick = true;
	Trigger = CreateDefaultSubobject<UBoxComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Trigger->SetBoxExtent(FVector(100.f, 100.f, 50.f));

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(1.0f, 1.0f, 0.2f));
	}
}

void AGameForgeHazard::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	Trigger->SetBoxExtent(FVector(ShapeExtent, ShapeExtent, 50.f));
	// The visual used to stay a 1 m tile whatever the damage area was; match it to the trigger and make it read as
	// danger. Very large hazards are invisible kill volumes (fall catchers), so they are not drawn.
	if (Mesh)
	{
		if (ShapeExtent > 2000.f)
		{
			Mesh->SetVisibility(false);
		}
		else
		{
			Mesh->SetRelativeScale3D(FVector(ShapeExtent / 50.f, ShapeExtent / 50.f, 0.1f));
			GameForgeVisuals::Tint(Mesh, bInstantKill ? FLinearColor(0.9f, 0.05f, 0.02f) : FLinearColor(1.f, 0.35f, 0.f));
		}
	}
	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AGameForgeHazard::OnOverlapBegin);
	Trigger->OnComponentEndOverlap.AddDynamic(this, &AGameForgeHazard::OnOverlapEnd);
}

void AGameForgeHazard::OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (APawn* P = Cast<APawn>(OtherActor))
	{
		if (P->IsPlayerControlled())
		{
			OverlappingPawns.Add(P);
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				Bus->Emit(GFEvent::HazardTouched, GetName(), TEXT("{}"), EntityId);
			}

			if (bInstantKill)
			{
				UGameForgeDamageLibrary::ApplyDamage(P, this, 10000.f);
			}
		}
	}
}

void AGameForgeHazard::OnOverlapEnd(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex)
{
	if (OtherActor)
	{
		OverlappingPawns.Remove(OtherActor);
	}
}

void AGameForgeHazard::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bInstantKill || OverlappingPawns.Num() == 0)
	{
		return;
	}

	TickTimer += DeltaSeconds;
	if (TickTimer >= 0.5f)
	{
		TickTimer = 0.f;
		for (auto It = OverlappingPawns.CreateIterator(); It; ++It)
		{
			if (AActor* Act = It->Get())
			{
				UGameForgeDamageLibrary::ApplyDamage(Act, this, DamagePerSecond * 0.5f);
			}
			else
			{
				It.RemoveCurrent();
			}
		}
	}
}

// ── Checkpoint ────────────────────────────────────────────────────────────────

AGameForgeCheckpoint::AGameForgeCheckpoint()
{
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->SetSphereRadius(150.f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(1.0f, 1.0f, 0.1f));
	}
}

void AGameForgeCheckpoint::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	GameForgeVisuals::Tint(Mesh, FLinearColor(0.2f, 0.6f, 1.f));
	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AGameForgeCheckpoint::OnOverlapBegin);
}

void AGameForgeCheckpoint::OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (bActivateOnce && bActivated)
	{
		return;
	}

	if (APawn* P = Cast<APawn>(OtherActor))
	{
		if (P->IsPlayerControlled())
		{
			bActivated = true;
			// Checkpoints never told the game mode where to respawn, so a death after a checkpoint still sent the
			// player back to the start (or nowhere at all).
			if (AGameForgeGameMode* GM = GetWorld()->GetAuthGameMode<AGameForgeGameMode>())
			{
				GM->SetRespawnTransform(FTransform(P->GetActorRotation(), GetActorLocation() + FVector(0.f, 0.f, 100.f)));
			}
			GameForgeVisuals::Tint(Mesh, FLinearColor(0.2f, 1.f, 0.35f));
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				Bus->Emit(GFEvent::CheckpointReached, GetName(), TEXT("{}"), EntityId);
				Bus->Emit(FName(TEXT("ui.message")), GetName(), TEXT("{\"text\":\"Checkpoint reached\",\"seconds\":2}"), EntityId);
			}
		}
	}
}

// ── Goal ──────────────────────────────────────────────────────────────────────

AGameForgeGoal::AGameForgeGoal()
{
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->SetSphereRadius(150.f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cone.Cone")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(0.8f, 0.8f, 1.2f));
	}
}

void AGameForgeGoal::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	GameForgeVisuals::Tint(Mesh, FLinearColor(1.f, 0.82f, 0.1f));
	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AGameForgeGoal::OnOverlapBegin);
}

void AGameForgeGoal::OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (bReached)
	{
		return;
	}

	if (APawn* P = Cast<APawn>(OtherActor))
	{
		if (P->IsPlayerControlled())
		{
			bool bReqMet = true;
			if (!RequiredStat.IsNone())
			{
				if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
				{
					bReqMet = (GS->GetStat(RequiredStat) >= RequiredValue - 1e-4f);
				}
			}

			if (bReqMet)
			{
				bReached = true;
				if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
				{
					Bus->Emit(GFEvent::GoalReached, GetName(), TEXT("{}"), EntityId);
				}
			}
			else if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				// A locked goal used to do nothing at all; tell the player why.
				Bus->Emit(FName(TEXT("ui.message")), GetName(), TEXT("{\"text\":\"Not yet - finish your objective first\",\"seconds\":2.5}"), EntityId);
			}
		}
	}
}

// ── Landmark ──────────────────────────────────────────────────────────────────

AGameForgeLandmark::AGameForgeLandmark()
{
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->SetSphereRadius(DiscoverRadius);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(0.5f, 0.5f, 3.0f));
	}
}

void AGameForgeLandmark::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	// DiscoverRadius is assigned after construction (gfdef / set_actor_property), so apply it here.
	Trigger->SetSphereRadius(DiscoverRadius);
	GameForgeVisuals::Tint(Mesh, FLinearColor(0.6f, 0.45f, 1.f));
	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AGameForgeLandmark::OnOverlapBegin);
}

void AGameForgeLandmark::OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (bDiscovered)
	{
		return;
	}

	if (APawn* P = Cast<APawn>(OtherActor))
	{
		if (P->IsPlayerControlled())
		{
			bDiscovered = true;
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				Bus->Emit(GFEvent::LandmarkDiscovered, GetName(), TEXT("{}"), EntityId);
			}
		}
	}
}

// ── Moving Platform ───────────────────────────────────────────────────────────

AGameForgeMovingPlatform::AGameForgeMovingPlatform()
{
	PrimaryActorTick.bCanEverTick = true;
	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	RootComponent = Mesh;
	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetCollisionProfileName(TEXT("BlockAll"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(2.0f, 2.0f, 0.25f));
	}
}

void AGameForgeMovingPlatform::BeginPlay()
{
	Super::BeginPlay();
	GameForgeVisuals::Tint(Mesh, FLinearColor(0.25f, 0.8f, 0.75f));
	StartLoc = GetActorLocation();
}

void AGameForgeMovingPlatform::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (Seconds <= 0.01f)
	{
		return;
	}

	Timer += DeltaSeconds;
	const float HalfPeriod = Seconds;
	const float FullPeriod = 2.f * (HalfPeriod + PauseSeconds);
	float ModTime = FMath::Fmod(Timer, FullPeriod);

	float Alpha = 0.f;
	if (ModTime < HalfPeriod)
	{
		Alpha = ModTime / HalfPeriod;
	}
	else if (ModTime < HalfPeriod + PauseSeconds)
	{
		Alpha = 1.0f;
	}
	else if (ModTime < 2.f * HalfPeriod + PauseSeconds)
	{
		Alpha = 1.0f - ((ModTime - (HalfPeriod + PauseSeconds)) / HalfPeriod);
	}
	else
	{
		Alpha = 0.0f;
	}

	Alpha = FMath::SmoothStep(0.f, 1.f, Alpha);
	SetActorLocation(StartLoc + EndOffset * Alpha);
}

// ── Door ──────────────────────────────────────────────────────────────────────

AGameForgeDoor::AGameForgeDoor()
{
	PrimaryActorTick.bCanEverTick = true;
	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	RootComponent = Mesh;
	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetCollisionProfileName(TEXT("BlockAll"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(0.2f, 1.2f, 2.4f));
	}
}

void AGameForgeDoor::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	GameForgeVisuals::Tint(Mesh, FLinearColor(0.45f, 0.3f, 0.18f));
	ClosedLoc = GetActorLocation();
}

bool AGameForgeDoor::CanInteract(AController* InController) const
{
	if (bOpen)
	{
		return false;
	}
	if (!RequiredStat.IsNone())
	{
		if (UWorld* W = GetWorld())
		{
			if (AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>())
			{
				return GS->GetStat(RequiredStat) >= RequiredValue - 1e-4f;
			}
		}
		return false;
	}
	return true;
}

void AGameForgeDoor::Interact(AController* InController)
{
	if (CanInteract(InController))
	{
		bOpen = true;
		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
		{
			Bus->Emit(GFEvent::DoorOpened, GetName(), TEXT("{}"), EntityId);
		}
	}
}

void AGameForgeDoor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bOpen && OpenProgress < 1.0f)
	{
		OpenProgress = FMath::Min(OpenProgress + DeltaSeconds / FMath::Max(Seconds, 0.01f), 1.0f);
		SetActorLocation(ClosedLoc + OpenOffset * FMath::SmoothStep(0.f, 1.f, OpenProgress));
	}
}

// ── Switch ────────────────────────────────────────────────────────────────────

AGameForgeSwitch::AGameForgeSwitch()
{
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->InitSphereRadius(120.f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(0.3f, 0.3f, 0.8f));
	}
}

void AGameForgeSwitch::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	GameForgeVisuals::Tint(Mesh, FLinearColor(0.95f, 0.75f, 0.1f));
	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AGameForgeSwitch::OnOverlapBegin);
}

void AGameForgeSwitch::OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (APawn* P = Cast<APawn>(OtherActor))
	{
		if (P->IsPlayerControlled())
		{
			Interact(P->GetController());
		}
	}
}

void AGameForgeSwitch::Interact(AController* InController)
{
	bActive = bToggle ? !bActive : true;
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		FString Data = FString::Printf(TEXT("{\"active\":%s}"), bActive ? TEXT("true") : TEXT("false"));
		Bus->Emit(GFEvent::SwitchToggled, GetName(), Data, EntityId);
	}
}

// ── Projectile ────────────────────────────────────────────────────────────────

AGameForgeProjectile::AGameForgeProjectile()
{
	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	RootComponent = Collision;
	Collision->SetSphereRadius(15.f);
	Collision->SetCollisionProfileName(TEXT("BlockAllDynamic"));
	Collision->OnComponentHit.AddDynamic(this, &AGameForgeProjectile::OnHit);

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));
	Mesh->SetCastShadow(false);

	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	Movement->InitialSpeed = 1500.f;
	Movement->MaxSpeed = 1500.f;
	Movement->bRotationFollowsVelocity = true;
	Movement->ProjectileGravityScale = 0.f;

	InitialLifeSpan = 5.0f;
}

void AGameForgeProjectile::BeginPlay()
{
	Super::BeginPlay();
	// Never collide with whoever fired it (projectiles spawned inside the shooter's capsule used to explode instantly).
	if (AActor* Shooter = GetInstigator())
	{
		Collision->IgnoreActorWhenMoving(Shooter, true);
	}
	if (Mesh && Mesh->GetStaticMesh() == nullptr)
	{
		if (GameForgeVisuals::SetBasicShape(Mesh, TEXT("Sphere")))
		{
			Mesh->SetWorldScale3D(FVector(0.18f, 0.18f, 0.18f));
			const AGameForgeEnemy* ShooterEnemy = Cast<AGameForgeEnemy>(GetInstigator());
			const bool bHostileShot = ShooterEnemy && ShooterEnemy->TeamId != 0;
			GameForgeVisuals::Tint(Mesh, bHostileShot ? FLinearColor(1.f, 0.25f, 0.1f) : FLinearColor(0.3f, 0.9f, 1.f));
		}
	}
}

void AGameForgeProjectile::OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	AActor* Shooter = GetInstigator();
	if (OtherActor && OtherActor != Shooter)
	{
		// Avoid same-team friendly fire between enemies, while allowing allied turrets (TeamId == 0) to damage
		// hostile enemies (TeamId != 0).
		const AGameForgeEnemy* ShooterEnemy = Cast<AGameForgeEnemy>(Shooter);
		const AGameForgeEnemy* TargetEnemy = Cast<AGameForgeEnemy>(OtherActor);
		const bool bSameEnemyTeam = ShooterEnemy && TargetEnemy && (ShooterEnemy->TeamId == TargetEnemy->TeamId);
		const bool bAlliedHittingPlayer = ShooterEnemy && ShooterEnemy->TeamId == 0 && Cast<APawn>(OtherActor) && Cast<APawn>(OtherActor)->IsPlayerControlled();
		if (!bSameEnemyTeam && !bAlliedHittingPlayer)
		{
			UGameForgeDamageLibrary::ApplyDamage(OtherActor, Shooter, Damage);
		}
	}
	Destroy();
}

// ── Enemy Character ───────────────────────────────────────────────────────────

AGameForgeEnemy::AGameForgeEnemy()
{
	AbilitySystemComponent = CreateDefaultSubobject<UAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet = CreateDefaultSubobject<UGameForgeAttributeSet>(TEXT("AttributeSet"));

	WeaponMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WeaponMesh"));
	WeaponMesh->SetupAttachment(GetMesh(), FName(TEXT("hand_rSocket")));
	WeaponMesh->SetCollisionProfileName(TEXT("NoCollision"));

	ProxyBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProxyBody"));
	ProxyBody->SetupAttachment(RootComponent);
	ProxyBody->SetCollisionProfileName(TEXT("NoCollision"));
	ProxyBody->SetRelativeLocation(FVector(0.f, 0.f, -20.f));
	ProxyBody->SetRelativeScale3D(FVector(0.7f, 0.7f, 1.3f));
	ProxyBody->SetVisibility(false);

	ProxyHead = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ProxyHead"));
	ProxyHead->SetupAttachment(RootComponent);
	ProxyHead->SetCollisionProfileName(TEXT("NoCollision"));
	ProxyHead->SetRelativeLocation(FVector(0.f, 0.f, 70.f));
	ProxyHead->SetRelativeScale3D(FVector(0.45f, 0.45f, 0.45f));
	ProxyHead->SetVisibility(false);

	AIControllerClass = AGameForgeEnemyAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;

	bUseControllerRotationYaw = false;
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->bOrientRotationToMovement = true;
		Move->RotationRate = FRotator(0.f, 480.f, 0.f);
	}
}

void AGameForgeEnemy::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	HomeLocation = GetActorLocation();

	if (!FMath::IsNearlyEqual(PatrolRadius, 600.f) && FMath::IsNearlyEqual(WanderRadius, 600.f))
	{
		WanderRadius = PatrolRadius;
	}
	if (MoveSpeed <= 0.f)
	{
		bStationaryTurret = true;
	}

	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->InitAbilityActorInfo(this, this);
		AttributeSet->SetMaxHealth(MaxHealth);
		AttributeSet->SetHealth(MaxHealth);
	}
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->MaxWalkSpeed = FMath::Max(0.f, MoveSpeed);
	}

	ApplyVisuals();

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::EnemySpawned, GetName(), TEXT("{}"), EntityId);
	}
}

void AGameForgeEnemy::ApplyVisuals()
{
	if (TeamId == 0 && BodyColor.Equals(FLinearColor(0.85f, 0.15f, 0.12f, 1.f)))
	{
		BodyColor = FLinearColor(0.2f, 0.75f, 0.95f, 1.f);
	}
	else if (bRanged && BodyColor.Equals(FLinearColor(0.85f, 0.15f, 0.12f, 1.f)))
	{
		BodyColor = FLinearColor(0.75f, 0.2f, 0.85f, 1.f);   // ranged enemies read differently from melee ones
	}

	bool bHasSkeletal = GetMesh() && GetMesh()->GetSkeletalMeshAsset() != nullptr;
	if (GetMesh() && !bHasSkeletal)
	{
		USkeletalMesh* SKM = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple"));
		if (!SKM)
		{
			SKM = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"));
		}
		if (SKM)
		{
			GetMesh()->SetSkeletalMeshAsset(SKM);
			GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -90.f));
			GetMesh()->SetRelativeRotation(FRotator(0.f, -90.f, 0.f));
			if (UClass* AnimClass = LoadClass<UAnimInstance>(nullptr,
				TEXT("/Game/Characters/Mannequins/Anims/Unarmed/ABP_Unarmed.ABP_Unarmed_C")))
			{
				GetMesh()->SetAnimInstanceClass(AnimClass);
			}
			bHasSkeletal = true;
		}
	}

	BodyMaterials.Reset();
	if (bHasSkeletal)
	{
		for (int32 Slot = 0; Slot < GetMesh()->GetNumMaterials(); ++Slot)
		{
			if (UMaterialInstanceDynamic* MID = GetMesh()->CreateAndSetMaterialInstanceDynamic(Slot))
			{
				// Mannequin materials expose "Tint"; basic materials expose "Color". Setting both is harmless.
				MID->SetVectorParameterValue(TEXT("Tint"), BodyColor);
				MID->SetVectorParameterValue(TEXT("Color"), BodyColor);
				BodyMaterials.Add(MID);
			}
		}
	}
	else
	{
		// No character content in the project: build a readable primitive body instead of an invisible capsule.
		GameForgeVisuals::SetBasicShape(ProxyBody, TEXT("Cylinder"));
		GameForgeVisuals::SetBasicShape(ProxyHead, TEXT("Sphere"));
		ProxyBody->SetVisibility(true);
		ProxyHead->SetVisibility(true);
		for (UMaterialInstanceDynamic* MID : GameForgeVisuals::Tint(ProxyBody, BodyColor))
		{
			BodyMaterials.Add(MID);
		}
		for (UMaterialInstanceDynamic* MID : GameForgeVisuals::Tint(ProxyHead, BodyColor * 0.7f))
		{
			BodyMaterials.Add(MID);
		}
	}

	if (WeaponMesh && WeaponMesh->GetStaticMesh() == nullptr)
	{
		const bool bSocket = bHasSkeletal && GetMesh()->DoesSocketExist(FName(TEXT("hand_rSocket")));
		if (bSocket && GameForgeVisuals::SetBasicShape(WeaponMesh, TEXT("Cube")))
		{
			WeaponMesh->SetRelativeScale3D(FVector(0.10f, 0.35f, 0.12f));
			GameForgeVisuals::Tint(WeaponMesh, FLinearColor(0.1f, 0.1f, 0.12f));
		}
		else
		{
			WeaponMesh->SetVisibility(false);
		}
	}
}

void AGameForgeEnemy::FlashColor(const FLinearColor& Color, float Seconds)
{
	for (UMaterialInstanceDynamic* MID : BodyMaterials)
	{
		if (MID)
		{
			MID->SetVectorParameterValue(TEXT("Tint"), Color);
			MID->SetVectorParameterValue(TEXT("Color"), Color);
		}
	}
	if (UWorld* W = GetWorld())
	{
		TWeakObjectPtr<AGameForgeEnemy> WeakThis(this);
		W->GetTimerManager().SetTimer(FlashTimer, [WeakThis]()
		{
			if (AGameForgeEnemy* Self = WeakThis.Get())
			{
				const FLinearColor Restore = Self->bDead ? Self->BodyColor * 0.3f : Self->BodyColor;
				for (UMaterialInstanceDynamic* MID : Self->BodyMaterials)
				{
					if (MID)
					{
						MID->SetVectorParameterValue(TEXT("Tint"), Restore);
						MID->SetVectorParameterValue(TEXT("Color"), Restore);
					}
				}
			}
		}, Seconds, false);
	}
}

void AGameForgeEnemy::OnDamaged(AActor* DamageInstigator)
{
	if (bDead)
	{
		return;
	}
	FlashColor(FLinearColor::White, 0.12f);
	// Small knock-back so hits are felt (unless stationary turret).
	if (DamageInstigator && !bStationaryTurret && MoveSpeed > 0.f)
	{
		FVector Away = GetActorLocation() - DamageInstigator->GetActorLocation();
		Away.Z = 0.f;
		LaunchCharacter(Away.GetSafeNormal() * 350.f + FVector(0.f, 0.f, 120.f), true, false);
	}
	// Being shot from outside the aggro range still makes the enemy react.
	if (DamageInstigator)
	{
		AggroRange = FMath::Max(AggroRange, FVector::Dist(GetActorLocation(), DamageInstigator->GetActorLocation()) + 200.f);
	}
}

void AGameForgeEnemy::HandleDeath()
{
	if (bDead)
	{
		return;
	}
	bDead = true;

	if (AController* C = GetController())
	{
		C->StopMovement();
	}
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->DisableMovement();
		Move->StopMovementImmediately();
	}
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	FlashColor(BodyColor * 0.3f, 0.01f);

	if (GetMesh() && GetMesh()->GetSkeletalMeshAsset() && GetMesh()->GetPhysicsAsset())
	{
		GetMesh()->SetCollisionProfileName(TEXT("Ragdoll"));
		GetMesh()->SetSimulatePhysics(true);
	}
	else
	{
		// Primitive body: tip over.
		SetActorRotation(GetActorRotation() + FRotator(0.f, 0.f, 80.f));
	}

	// A positive life span removes the enemy from entity.<id>.remaining immediately and destroys it shortly after.
	SetLifeSpan(FMath::Max(0.5f, CorpseSeconds));
}

void AGameForgeEnemy::PerformAttack(AActor* Target)
{
	if (!Target || bDead)
	{
		return;
	}

	float CurrentTime = GetWorld()->GetTimeSeconds();
	if (CurrentTime - LastAttackTime < AttackCooldown)
	{
		return;
	}
	LastAttackTime = CurrentTime;

	FVector ToTarget = Target->GetActorLocation() - GetActorLocation();
	ToTarget.Z = 0.f;
	if (!ToTarget.IsNearlyZero())
	{
		SetActorRotation(ToTarget.Rotation());
	}

	if (bRanged)
	{
		FVector SpawnLoc = GetActorLocation() + GetActorForwardVector() * 80.f + FVector(0.f, 0.f, 30.f);
		FRotator SpawnRot = (Target->GetActorLocation() - SpawnLoc).Rotation();
		FActorSpawnParameters Params;
		Params.Instigator = this;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AGameForgeProjectile* Proj = GetWorld()->SpawnActor<AGameForgeProjectile>(AGameForgeProjectile::StaticClass(), SpawnLoc, SpawnRot, Params);
		if (Proj)
		{
			Proj->Damage = AttackDamage;
			Proj->Movement->InitialSpeed = ProjectileSpeed;
			Proj->Movement->MaxSpeed = ProjectileSpeed;
			Proj->Movement->Velocity = SpawnRot.Vector() * ProjectileSpeed;
		}
	}
	else
	{
		FlashColor(FLinearColor(1.f, 0.85f, 0.2f), 0.15f);   // wind-up flash telegraphs the hit
		UGameForgeDamageLibrary::ApplyDamage(Target, this, AttackDamage);
	}
}

// ── Enemy AIController ────────────────────────────────────────────────────────

AGameForgeEnemyAIController::AGameForgeEnemyAIController()
{
	PrimaryActorTick.bCanEverTick = true;
}

AActor* AGameForgeEnemyAIController::ResolveHostileOrGoalTarget(AGameForgeEnemy* EnemyPawn, bool& bOutIsGoal) const
{
	bOutIsGoal = false;
	if (!EnemyPawn || !GetWorld())
	{
		return nullptr;
	}

	// Allied unit / friendly turret (TeamId == 0): target nearest living hostile AGameForgeEnemy (TeamId != 0)
	if (EnemyPawn->TeamId == 0)
	{
		AGameForgeEnemy* BestHostile = nullptr;
		float BestDistSq = TNumericLimits<float>::Max();
		for (TActorIterator<AGameForgeEnemy> It(GetWorld()); It; ++It)
		{
			AGameForgeEnemy* Other = *It;
			if (!Other || Other == EnemyPawn || Other->IsDead() || Other->TeamId == 0)
			{
				continue;
			}
			const float D = FVector::DistSquared(EnemyPawn->GetActorLocation(), Other->GetActorLocation());
			if (D < BestDistSq)
			{
				BestDistSq = D;
				BestHostile = Other;
			}
		}
		return BestHostile;
	}

	// Hostile enemy (TeamId != 0): check lane goal target if TargetGoalEntityId is specified
	if (!EnemyPawn->TargetGoalEntityId.IsNone())
	{
		const FName GoalTag(*(FString(TEXT("GF_E_")) + EnemyPawn->TargetGoalEntityId.ToString()));
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			AActor* Act = *It;
			if (!IsValid(Act) || Act == EnemyPawn)
			{
				continue;
			}
			if (Act->Tags.Contains(GoalTag) || Act->Tags.Contains(EnemyPawn->TargetGoalEntityId))
			{
				bOutIsGoal = true;
				return Act;
			}
			if (const AGameForgeGoal* GoalActor = Cast<AGameForgeGoal>(Act))
			{
				if (GoalActor->EntityId == EnemyPawn->TargetGoalEntityId)
				{
					bOutIsGoal = true;
					return Act;
				}
			}
		}
	}

	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	return PC ? PC->GetPawn() : nullptr;
}

void AGameForgeEnemyAIController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	AGameForgeEnemy* EnemyPawn = Cast<AGameForgeEnemy>(GetPawn());
	if (!EnemyPawn || EnemyPawn->IsDead() || (EnemyPawn->AttributeSet && EnemyPawn->AttributeSet->GetHealth() <= 0.f))
	{
		return;
	}

	bool bIsGoalTarget = false;
	AActor* Target = ResolveHostileOrGoalTarget(EnemyPawn, bIsGoalTarget);
	CurrentTarget = Target;

	const bool bStationary = EnemyPawn->bStationaryTurret || EnemyPawn->MoveSpeed <= 0.f;
	const float DistSq = Target ? FVector::DistSquared(EnemyPawn->GetActorLocation(), Target->GetActorLocation()) : TNumericLimits<float>::Max();
	const float AggroSq = FMath::Square(EnemyPawn->AggroRange);
	// Keep chasing until the target is well outside the aggro radius (hysteresis avoids stutter at the edge).
	const float LeashSq = FMath::Square(EnemyPawn->AggroRange * 1.5f);
	const float AttackSq = FMath::Square(EnemyPawn->AttackRange);

	if (Target && DistSq <= AttackSq)
	{
		bAggro = true;
		StopMovement();
		SetFocus(Target);
		EnemyPawn->PerformAttack(Target);
		return;
	}

	if (bStationary)
	{
		StopMovement();
		if (Target && DistSq <= FMath::Max(AggroSq, AttackSq))
		{
			SetFocus(Target);
			FVector ToTarget = Target->GetActorLocation() - EnemyPawn->GetActorLocation();
			ToTarget.Z = 0.f;
			if (!ToTarget.IsNearlyZero())
			{
				EnemyPawn->SetActorRotation(ToTarget.Rotation());
			}
			if (DistSq <= AttackSq)
			{
				EnemyPawn->PerformAttack(Target);
			}
		}
		return;
	}

	if (Target && (bIsGoalTarget || DistSq <= AggroSq || (bAggro && DistSq <= LeashSq)))
	{
		bAggro = true;
		SetFocus(Target);
		MoveCooldown -= DeltaSeconds;
		if (MoveCooldown <= 0.f)
		{
			MoveCooldown = 0.35f;
			const EPathFollowingRequestResult::Type Res = MoveToActor(Target, EnemyPawn->AttackRange * 0.7f, true, true, true);
			if (Res == EPathFollowingRequestResult::Failed)
			{
				// No navmesh path (e.g. navmesh still building): steer straight at the target.
				FVector Dir = Target->GetActorLocation() - EnemyPawn->GetActorLocation();
				Dir.Z = 0.f;
				EnemyPawn->AddMovementInput(Dir.GetSafeNormal(), 1.f);
			}
		}
		return;
	}

	// Idle: wander around the spawn point so the level feels alive instead of full of statues.
	if (bAggro)
	{
		bAggro = false;
		ClearFocus(EAIFocusPriority::Gameplay);
	}
	if (EnemyPawn->WanderRadius > 50.f)
	{
		WanderCooldown -= DeltaSeconds;
		if (WanderCooldown <= 0.f)
		{
			WanderCooldown = FMath::FRandRange(2.5f, 5.0f);
			const FVector2D Offset = FMath::RandPointInCircle(EnemyPawn->WanderRadius);
			const FVector Dest = EnemyPawn->GetHomeLocation() + FVector(Offset.X, Offset.Y, 0.f);
			MoveToLocation(Dest, 50.f, true, true, true, true);
		}
	}
}

// ── Spawner ───────────────────────────────────────────────────────────────────

AGameForgeSpawner::AGameForgeSpawner()
{
	PrimaryActorTick.bCanEverTick = false;
}

void AGameForgeSpawner::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);

	if (MaxWaves != 3 && WaveCount == 3)
	{
		WaveCount = MaxWaves;
	}
	if (!FMath::IsNearlyEqual(WaveIntervalSeconds, 5.f) && FMath::IsNearlyEqual(SecondsBetweenWaves, 5.f))
	{
		SecondsBetweenWaves = WaveIntervalSeconds;
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.AddUObject(this, &AGameForgeSpawner::HandleEvent);
	}

	if (bAutoStart)
	{
		// Short grace period so the player can orient before the first wave arrives.
		GetWorld()->GetTimerManager().SetTimer(WaveTimerHandle, this, &AGameForgeSpawner::StartWave,
			FMath::Clamp(SecondsBetweenWaves * 0.5f, 1.5f, 4.f), false);
	}
}

void AGameForgeSpawner::ConfigureSpawnedEnemy(AActor* Spawned) const
{
	AGameForgeEnemy* Enemy = Cast<AGameForgeEnemy>(Spawned);
	if (!Enemy)
	{
		return;
	}
	Enemy->EntityId = EnemyEntityId;
	Enemy->Tags.AddUnique(FName(*(FString(TEXT("GF_E_")) + EnemyEntityId.ToString())));
	Enemy->Tags.AddUnique(FName(TEXT("GF_Owned")));
	Enemy->Tags.AddUnique(FName(TEXT("enemy")));

	// 1. Apply spawner-level enemy overrides first if set (> 0)
	if (EnemyMaxHealth > 0.f) { Enemy->MaxHealth = EnemyMaxHealth; }
	if (EnemyAttackDamage > 0.f) { Enemy->AttackDamage = EnemyAttackDamage; }
	if (EnemyAttackRange > 0.f) { Enemy->AttackRange = EnemyAttackRange; }
	if (EnemyAttackCooldown > 0.f) { Enemy->AttackCooldown = EnemyAttackCooldown; }
	if (EnemySpeed > 0.f) { Enemy->MoveSpeed = EnemySpeed; }
	if (!VisualStyle.IsEmpty()) { Enemy->VisualStyle = VisualStyle; }
	if (!BodyColor.Equals(FLinearColor(0.85f, 0.15f, 0.12f, 1.f))) { Enemy->BodyColor = BodyColor; }

	// 2. Also check game definition for entity-specific properties
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
	TSharedPtr<FJsonObject> Def;
	if (DefAsset)
	{
		Def = DefAsset->GetParsed();
	}
	bool bExplicitAggroRange = false;
	const TSharedPtr<FJsonObject>* Entities = nullptr;
	const TSharedPtr<FJsonObject>* EntSpec = nullptr;
	const TSharedPtr<FJsonObject>* Props = nullptr;
	if (Def.IsValid() && Def->TryGetObjectField(TEXT("entities"), Entities) && Entities &&
		(*Entities)->TryGetObjectField(EnemyEntityId.ToString(), EntSpec) && EntSpec &&
		(*EntSpec)->TryGetObjectField(TEXT("properties"), Props) && Props)
	{
		double V = 0.0;
		if (EnemyAttackDamage <= 0.f && (*Props)->TryGetNumberField(TEXT("attack_damage"), V)) { Enemy->AttackDamage = static_cast<float>(V); }
		if (EnemyAttackRange <= 0.f && (*Props)->TryGetNumberField(TEXT("attack_range"), V)) { Enemy->AttackRange = static_cast<float>(V); }
		if (EnemyAttackCooldown <= 0.f && (*Props)->TryGetNumberField(TEXT("attack_cooldown"), V)) { Enemy->AttackCooldown = static_cast<float>(V); }
		if (EnemySpeed <= 0.f && (*Props)->TryGetNumberField(TEXT("move_speed"), V)) { Enemy->MoveSpeed = static_cast<float>(V); }
		if ((*Props)->TryGetNumberField(TEXT("aggro_range"), V) && V > 0.0)
		{
			Enemy->AggroRange = static_cast<float>(V);
			bExplicitAggroRange = true;
		}
		if (EnemyMaxHealth <= 0.f && (*Props)->TryGetNumberField(TEXT("max_health"), V)) { Enemy->MaxHealth = static_cast<float>(V); }
		if ((*Props)->TryGetNumberField(TEXT("projectile_speed"), V)) { Enemy->ProjectileSpeed = static_cast<float>(V); Enemy->bRanged = true; }
		const TArray<TSharedPtr<FJsonValue>>* ColorArr = nullptr;
		if ((*Props)->TryGetArrayField(TEXT("body_color"), ColorArr) && ColorArr && ColorArr->Num() >= 3)
		{
			TArray<double> Values;
			for (const TSharedPtr<FJsonValue>& C : *ColorArr) { Values.Add(C->AsNumber()); }
			Enemy->BodyColor = GameForgeVisuals::ColorFromArray(Values, Enemy->BodyColor);
		}
	}

	// Wave enemies come to the player when no explicit aggro_range override was specified.
	if (!bExplicitAggroRange)
	{
		Enemy->AggroRange = FMath::Max(Enemy->AggroRange, 6000.f);
	}
}

void AGameForgeSpawner::SpawnWave()
{
	StartWave();
}

void AGameForgeSpawner::StartWave()
{
	CurrentWave++;
	if (CurrentWave > WaveCount)
	{
		return;
	}

	UWorld* W = GetWorld();
	if (!W)
	{
		return;
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::WaveStarted, GetName(), FString::Printf(TEXT("{\"wave\":%d,\"of\":%d}"), CurrentWave, WaveCount), EntityId);
		TSharedRef<FJsonObject> Msg = MakeShared<FJsonObject>();
		Msg->SetStringField(TEXT("text"), FString::Printf(TEXT("Wave %d of %d"), CurrentWave, WaveCount));
		Msg->SetNumberField(TEXT("seconds"), 2.5);
		FString MsgStr;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&MsgStr);
		FJsonSerializer::Serialize(Msg, Writer);
		Bus->Emit(FName(TEXT("ui.message")), GetName(), MsgStr, EntityId);
	}

	UClass* Cls = EnemyClass ? EnemyClass.Get() : AGameForgeEnemy::StaticClass();
	// Later waves are a little bigger so the fight escalates, capped by MaxAlive.
	const int32 DesiredCount = EnemiesPerWave + (CurrentWave - 1) / 2;
	const int32 ThisWave = (MaxAlive > 0) ? FMath::Min(DesiredCount, MaxAlive) : DesiredCount;
	int32 Spawned = 0;

	UNavigationSystemV1* NavSys = FNavigationSystem::GetCurrent<UNavigationSystemV1>(W);

	for (int32 i = 0; i < ThisWave; i++)
	{
		const float Angle = (static_cast<float>(i) / FMath::Max(1, ThisWave)) * 2.f * PI + FMath::FRandRange(-0.2f, 0.2f);
		FVector Offset(FMath::Cos(Angle) * SpawnRadius, FMath::Sin(Angle) * SpawnRadius, 90.f);
		FVector SpawnLocation = GetActorLocation() + Offset;

		// Project candidate spawn point onto NavMesh so enemies never spawn outside walls/bounds
		FNavLocation ProjectedLoc;
		if (NavSys && NavSys->ProjectPointToNavigation(SpawnLocation, ProjectedLoc, FVector(400.f, 400.f, 500.f)))
		{
			SpawnLocation = ProjectedLoc.Location + FVector(0.f, 0.f, 90.f);
		}

		FTransform SpawnTransform(GetActorRotation(), SpawnLocation);

		AActor* NewActor = W->SpawnActorDeferred<AActor>(Cls, SpawnTransform, nullptr, nullptr,
			ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
		if (NewActor)
		{
			ConfigureSpawnedEnemy(NewActor);
			UGameplayStatics::FinishSpawningActor(NewActor, SpawnTransform);
			WaveActorNames.Add(NewActor->GetName());
			Spawned++;
		}
	}
	// Count what actually spawned; a failed spawn used to leave the wave un-clearable forever.
	AliveEnemiesInWave = Spawned;
	if (Spawned == 0)
	{
		W->GetTimerManager().SetTimer(WaveTimerHandle, this, &AGameForgeSpawner::StartWave, SecondsBetweenWaves, false);
	}
}

void AGameForgeSpawner::OnEnemyDied(const FString& DeadActorName)
{
	if (AliveEnemiesInWave > 0 && WaveActorNames.Remove(DeadActorName) > 0)
	{
		AliveEnemiesInWave--;
		if (AliveEnemiesInWave <= 0)
		{
			if (UWorld* W = GetWorld())
			{
				if (AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>())
				{
					GS->IncrementCounter(FName(TEXT("game.counter.waves_cleared")), 1);
				}
			}
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				Bus->Emit(GFEvent::WaveCleared, GetName(), FString::Printf(TEXT("{\"wave\":%d}"), CurrentWave), EntityId);
			}

			if (CurrentWave < WaveCount && GetWorld())
			{
				GetWorld()->GetTimerManager().SetTimer(WaveTimerHandle, this, &AGameForgeSpawner::StartWave, SecondsBetweenWaves, false);
			}
		}
	}
}

void AGameForgeSpawner::HandleEvent(const FGameForgeEvent& Event)
{
	// Only this spawner's own wave members count: pre-placed enemies of the same entity, or another spawner's
	// wave, used to clear this wave early while its enemies were still alive.
	if (Event.Name == GFEvent::EnemyKilled)
	{
		OnEnemyDied(Event.Source);
	}
}

// ── Bomb Site & Bomb ─────────────────────────────────────────────────────────

AGameForgeBombSite::AGameForgeBombSite()
{
	PrimaryActorTick.bCanEverTick = false;
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->SetSphereRadius(300.f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionProfileName(TEXT("NoCollision"));
	if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")))
	{
		Mesh->SetStaticMesh(SM);
		Mesh->SetRelativeScale3D(FVector(2.0f, 2.0f, 0.05f));
	}
}

bool AGameForgeBombSite::CanInteract(AController* InController) const
{
	return !bBombPlanted;
}

void AGameForgeBombSite::Interact(AController* InController)
{
	if (bBombPlanted) return;
	bBombPlanted = true;

	FActorSpawnParameters SpawnParams;
	SpawnParams.Owner = this;
	SpawnParams.Instigator = InController ? InController->GetPawn() : nullptr;
	FVector BombLoc = GetActorLocation() + FVector(0.f, 0.f, 20.f);
	GetWorld()->SpawnActor<AGameForgeBomb>(AGameForgeBomb::StaticClass(), BombLoc, FRotator::ZeroRotator, SpawnParams);

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(FName(TEXT("bomb.planted")), GetName(), FString::Printf(TEXT("{\"site\":\"%s\"}"), *SiteName.ToString()), EntityId);
	}
}

AGameForgeBomb::AGameForgeBomb()
{
	PrimaryActorTick.bCanEverTick = true;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	RootComponent = Mesh;
	Mesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));
	if (UStaticMesh* BoxMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		Mesh->SetStaticMesh(BoxMesh);
		Mesh->SetWorldScale3D(FVector(0.4f, 0.3f, 0.2f));
	}

	DefuseTrigger = CreateDefaultSubobject<USphereComponent>(TEXT("DefuseTrigger"));
	DefuseTrigger->SetupAttachment(RootComponent);
	DefuseTrigger->SetSphereRadius(180.f);
	DefuseTrigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
}

bool AGameForgeBomb::CanInteract(AController* InController) const
{
	return !bDefused && !bExploded;
}

void AGameForgeBomb::Interact(AController* InController)
{
	if (bDefused || bExploded) return;
	CurrentDefuseProgress += 2.5f;
	if (CurrentDefuseProgress >= DefuseTimeRequired)
	{
		Defused();
	}
}

void AGameForgeBomb::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bDefused || bExploded) return;

	FuseTimeRemaining -= DeltaSeconds;
	if (FuseTimeRemaining <= 0.f)
	{
		Explode();
	}
}

void AGameForgeBomb::Explode()
{
	if (bExploded || bDefused) return;
	bExploded = true;

	TArray<AActor*> OverlappingActors;
	UGameplayStatics::GetAllActorsOfClass(this, ACharacter::StaticClass(), OverlappingActors);
	for (AActor* Act : OverlappingActors)
	{
		if (FVector::Dist(Act->GetActorLocation(), GetActorLocation()) <= ExplosionRadius)
		{
			UGameForgeDamageLibrary::ApplyDamage(Act, this, 5000.f);
		}
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(FName(TEXT("bomb.exploded")), GetName(), TEXT("{}"), FName(TEXT("bomb")));
	}
}

void AGameForgeBomb::Defused()
{
	if (bDefused || bExploded) return;
	bDefused = true;

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(FName(TEXT("bomb.defused")), GetName(), TEXT("{}"), FName(TEXT("bomb")));
	}
}
