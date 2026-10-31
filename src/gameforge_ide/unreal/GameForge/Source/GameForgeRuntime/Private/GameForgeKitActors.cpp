#include "GameForgeKitActors.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameState.h"
#include "GameForgePlayer.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "TimerManager.h"

// ── Hazard ────────────────────────────────────────────────────────────────────

AGameForgeHazard::AGameForgeHazard()
{
	PrimaryActorTick.bCanEverTick = true;
	Trigger = CreateDefaultSubobject<UBoxComponent>(TEXT("Trigger"));
	RootComponent = Trigger;
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Trigger->SetBoxExtent(FVector(100.f, 100.f, 50.f));
}

void AGameForgeHazard::BeginPlay()
{
	Super::BeginPlay();
	Trigger->SetBoxExtent(FVector(ShapeExtent, ShapeExtent, 50.f));
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
}

void AGameForgeCheckpoint::BeginPlay()
{
	Super::BeginPlay();
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
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				Bus->Emit(GFEvent::CheckpointReached, GetName(), TEXT("{}"), EntityId);
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
}

void AGameForgeGoal::BeginPlay()
{
	Super::BeginPlay();
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
}

void AGameForgeLandmark::BeginPlay()
{
	Super::BeginPlay();
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
}

void AGameForgeMovingPlatform::BeginPlay()
{
	Super::BeginPlay();
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
}

void AGameForgeDoor::BeginPlay()
{
	Super::BeginPlay();
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
}

void AGameForgeSwitch::BeginPlay()
{
	Super::BeginPlay();
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

	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	Movement->InitialSpeed = 1500.f;
	Movement->MaxSpeed = 1500.f;
	Movement->bRotationFollowsVelocity = true;
	Movement->ProjectileGravityScale = 0.f;

	InitialLifeSpan = 5.0f;
}

void AGameForgeProjectile::OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	if (OtherActor && OtherActor != GetInstigator())
	{
		UGameForgeDamageLibrary::ApplyDamage(OtherActor, GetInstigator(), Damage);
	}
	Destroy();
}

// ── Enemy Character ───────────────────────────────────────────────────────────

AGameForgeEnemy::AGameForgeEnemy()
{
	AbilitySystemComponent = CreateDefaultSubobject<UAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AttributeSet = CreateDefaultSubobject<UGameForgeAttributeSet>(TEXT("AttributeSet"));
	AIControllerClass = AGameForgeEnemyAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
}

void AGameForgeEnemy::BeginPlay()
{
	Super::BeginPlay();
	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->InitAbilityActorInfo(this, this);
		AttributeSet->SetMaxHealth(MaxHealth);
		AttributeSet->SetHealth(MaxHealth);
	}
	GetCharacterMovement()->MaxWalkSpeed = MoveSpeed;

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::EnemySpawned, GetName(), TEXT("{}"), EntityId);
	}
}

void AGameForgeEnemy::PerformAttack(AActor* Target)
{
	if (!Target)
	{
		return;
	}

	float CurrentTime = GetWorld()->GetTimeSeconds();
	if (CurrentTime - LastAttackTime < AttackCooldown)
	{
		return;
	}
	LastAttackTime = CurrentTime;

	if (bRanged)
	{
		FVector SpawnLoc = GetActorLocation() + GetActorForwardVector() * 80.f;
		FRotator SpawnRot = (Target->GetActorLocation() - SpawnLoc).Rotation();
		FActorSpawnParameters Params;
		Params.Instigator = this;
		AGameForgeProjectile* Proj = GetWorld()->SpawnActor<AGameForgeProjectile>(AGameForgeProjectile::StaticClass(), SpawnLoc, SpawnRot, Params);
		if (Proj)
		{
			Proj->Damage = AttackDamage;
			Proj->Movement->InitialSpeed = ProjectileSpeed;
			Proj->Movement->MaxSpeed = ProjectileSpeed;
		}
	}
	else
	{
		UGameForgeDamageLibrary::ApplyDamage(Target, this, AttackDamage);
	}
}

// ── Enemy AIController ────────────────────────────────────────────────────────

AGameForgeEnemyAIController::AGameForgeEnemyAIController()
{
	PrimaryActorTick.bCanEverTick = true;
}

void AGameForgeEnemyAIController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	AGameForgeEnemy* EnemyPawn = Cast<AGameForgeEnemy>(GetPawn());
	if (!EnemyPawn || EnemyPawn->AttributeSet->GetHealth() <= 0.f)
	{
		return;
	}

	if (!CurrentTarget.IsValid())
	{
		APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
		if (PC && PC->GetPawn())
		{
			CurrentTarget = PC->GetPawn();
		}
	}

	AActor* Target = CurrentTarget.Get();
	if (!Target)
	{
		return;
	}

	const float DistSq = FVector::DistSquared(EnemyPawn->GetActorLocation(), Target->GetActorLocation());
	const float AggroSq = FMath::Square(EnemyPawn->AggroRange);
	const float AttackSq = FMath::Square(EnemyPawn->AttackRange);

	if (DistSq <= AttackSq)
	{
		StopMovement();
		EnemyPawn->PerformAttack(Target);
	}
	else if (DistSq <= AggroSq)
	{
		MoveCooldown -= DeltaSeconds;
		if (MoveCooldown <= 0.f)
		{
			MoveCooldown = 0.5f;
			MoveToActor(Target, EnemyPawn->AttackRange * 0.8f);
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

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.AddUObject(this, &AGameForgeSpawner::HandleEvent);
	}

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
		Bus->Emit(GFEvent::WaveStarted, GetName(), FString::Printf(TEXT("{\"wave\":%d}"), CurrentWave), EntityId);
	}

	AliveEnemiesInWave = EnemiesPerWave;
	UClass* Cls = EnemyClass ? EnemyClass.Get() : AGameForgeEnemy::StaticClass();

	for (int32 i = 0; i < EnemiesPerWave; i++)
	{
		const float Angle = (static_cast<float>(i) / FMath::Max(1, EnemiesPerWave)) * 2.f * PI;
		FVector Offset(FMath::Cos(Angle) * SpawnRadius, FMath::Sin(Angle) * SpawnRadius, 50.f);
		FTransform SpawnTransform(GetActorRotation(), GetActorLocation() + Offset);

		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
		AActor* Spawned = W->SpawnActor<AActor>(Cls, SpawnTransform, Params);
		if (Spawned)
		{
			Spawned->Tags.AddUnique(FName(*(FString(TEXT("GF_E_")) + EnemyEntityId.ToString())));
		}
	}
}

void AGameForgeSpawner::HandleEvent(const FGameForgeEvent& Event)
{
	if (Event.Name == GFEvent::EnemyKilled && (Event.Entity == EnemyEntityId || Event.Entity == NAME_None))
	{
		AliveEnemiesInWave--;
		if (AliveEnemiesInWave <= 0)
		{
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				Bus->Emit(GFEvent::WaveCleared, GetName(), FString::Printf(TEXT("{\"wave\":%d}"), CurrentWave), EntityId);
			}

			if (CurrentWave < WaveCount)
			{
				GetWorld()->GetTimerManager().SetTimer(WaveTimerHandle, this, &AGameForgeSpawner::StartWave, SecondsBetweenWaves, false);
			}
		}
	}
}
