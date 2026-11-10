#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "AIController.h"
#include "AbilitySystemInterface.h"
#include "AbilitySystemComponent.h"
#include "Components/BoxComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameForgeAttributes.h"
#include "GameForgeEvents.h"
#include "GameForgeKitActors.generated.h"

class UMaterialInstanceDynamic;

// ── Interface ─────────────────────────────────────────────────────────────────

UINTERFACE(MinimalAPI, Blueprintable)
class UGameForgeInteractable : public UInterface
{
	GENERATED_BODY()
};

class GAMEFORGERUNTIME_API IGameForgeInteractable
{
	GENERATED_BODY()
public:
	virtual bool CanInteract(AController* InController) const = 0;
	virtual void Interact(AController* InController) = 0;
};

// ── Hazard ────────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeHazard : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeHazard();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UBoxComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float DamagePerSecond = 20.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bInstantKill = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float ShapeExtent = 100.f;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

protected:
	UFUNCTION()
	void OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	UFUNCTION()
	void OnOverlapEnd(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex);

	TSet<TWeakObjectPtr<AActor>> OverlappingPawns;
	float TickTimer = 0.f;
};

// ── Checkpoint ────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeCheckpoint : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeCheckpoint();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bActivateOnce = true;

	virtual void BeginPlay() override;

protected:
	UFUNCTION()
	void OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	bool bActivated = false;
};

// ── Goal ──────────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGoal : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeGoal();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName RequiredStat;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float RequiredValue = 0.f;

	virtual void BeginPlay() override;

protected:
	UFUNCTION()
	void OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	bool bReached = false;
};

// ── Landmark ──────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeLandmark : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeLandmark();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float DiscoverRadius = 500.f;

	virtual void BeginPlay() override;

protected:
	UFUNCTION()
	void OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	bool bDiscovered = false;
};

// ── Moving Platform ───────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeMovingPlatform : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeMovingPlatform();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FVector EndOffset = FVector(0.f, 0.f, 200.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float Seconds = 3.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float PauseSeconds = 1.f;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	FVector StartLoc;
	float Timer = 0.f;
	bool bForward = true;
};

// ── Door ──────────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeDoor : public AActor, public IGameForgeInteractable
{
	GENERATED_BODY()
public:
	AGameForgeDoor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName RequiredStat;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float RequiredValue = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FVector OpenOffset = FVector(0.f, 0.f, 300.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float Seconds = 1.f;

	virtual bool CanInteract(AController* InController) const override;
	virtual void Interact(AController* InController) override;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	FVector ClosedLoc;
	bool bOpen = false;
	float OpenProgress = 0.f;
};

// ── Switch ────────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeSwitch : public AActor, public IGameForgeInteractable
{
	GENERATED_BODY()
public:
	AGameForgeSwitch();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName TargetTag;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bToggle = false;

	virtual bool CanInteract(AController* InController) const override { return true; }
	virtual void Interact(AController* InController) override;

	virtual void BeginPlay() override;

protected:
	UFUNCTION()
	void OnOverlapBegin(UPrimitiveComponent* OverlappedComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

private:
	bool bActive = false;
};

// ── Projectile ────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeProjectile : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeProjectile();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> Collision;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UProjectileMovementComponent> Movement;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float Damage = 10.f;

	virtual void BeginPlay() override;

protected:
	UFUNCTION()
	void OnHit(UPrimitiveComponent* HitComp, AActor* OtherActor,
		UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);
};

// ── Enemy Character ───────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeEnemy : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()
public:
	AGameForgeEnemy();

	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override { return AbilitySystemComponent; }

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UGameForgeAttributeSet> AttributeSet;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName TargetGoalEntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bStationaryTurret = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AttackDamage = 15.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AttackRange = 180.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AttackCooldown = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float MoveSpeed = 350.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AggroRange = 800.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float MaxHealth = 50.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float ScoreValue = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float PatrolRadius = 600.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bRanged = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bIsBoss = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FString BossName = TEXT("Boss");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 BossPhase = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bEnraged = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float ProjectileSpeed = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	uint8 TeamId = 1; // 0 = CT / Friendly / Allied Turret, 1 = Terrorist / Hostile Enemy

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FString VisualStyle = TEXT("humanoid");

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> WeaponMesh;

	/** Primitive body shown when no skeletal mesh is available (blank projects have no Mannequin content), so
	 *  enemies are never invisible capsules. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> ProxyBody;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> ProxyHead;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FLinearColor BodyColor = FLinearColor(0.85f, 0.15f, 0.12f, 1.f);

	/** Idle wander radius around the spawn point (0 = stand still until the player comes into range). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float WanderRadius = 600.f;

	/** Seconds the corpse stays before it is removed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float CorpseSeconds = 2.5f;

	virtual void BeginPlay() override;
	void PerformAttack(AActor* Target);
	void HandleDeath();
	void OnDamaged(AActor* DamageInstigator);
	bool IsDead() const { return bDead; }
	FVector GetHomeLocation() const { return HomeLocation; }

private:
	void ApplyVisuals();
	void FlashColor(const FLinearColor& Color, float Seconds);

	float LastAttackTime = -100.f;
	bool bDead = false;
	FVector HomeLocation = FVector::ZeroVector;
	FTimerHandle FlashTimer;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UMaterialInstanceDynamic>> BodyMaterials;
};

// ── Enemy AIController ────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeEnemyAIController : public AAIController
{
	GENERATED_BODY()
public:
	AGameForgeEnemyAIController();
	virtual void Tick(float DeltaSeconds) override;

private:
	AActor* ResolveHostileOrGoalTarget(AGameForgeEnemy* EnemyPawn, bool& bOutIsGoal) const;

	TWeakObjectPtr<AActor> CurrentTarget;
	float MoveCooldown = 0.f;
	float WanderCooldown = 0.f;
	bool bAggro = false;
};

// ── Spawner ───────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeSpawner : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeSpawner();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	TSubclassOf<AActor> EnemyClass;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	FName EnemyEntityId = FName(TEXT("enemy"));

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	int32 WaveCount = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	int32 MaxWaves = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	int32 EnemiesPerWave = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	int32 MaxAlive = 12;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float SecondsBetweenWaves = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float WaveIntervalSeconds = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float SpawnRadius = 400.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	bool bAutoStart = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	FString VisualStyle = TEXT("humanoid");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	FLinearColor BodyColor = FLinearColor(0.85f, 0.15f, 0.12f, 1.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float EnemyMaxHealth = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float EnemyAttackDamage = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float EnemyAttackRange = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float EnemyAttackCooldown = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Spawner")
	float EnemySpeed = -1.f;

	virtual void BeginPlay() override;

	UFUNCTION(BlueprintCallable, Category = "GameForge|Spawner")
	void SpawnWave();

	void OnEnemyDied(const FString& DeadActorName);

private:
	void StartWave();
	void HandleEvent(const FGameForgeEvent& Event);
	/** Copies the enemy entity's GDS properties (attack_damage, max_health, ...) from the game definition onto a
	 *  deferred-spawned enemy. Spawned wave enemies used to run with hard-coded defaults and no EntityId. */
	void ConfigureSpawnedEnemy(AActor* Spawned) const;

	int32 CurrentWave = 0;
	int32 AliveEnemiesInWave = 0;
	TSet<FString> WaveActorNames;
	FTimerHandle WaveTimerHandle;
};

// ── Bomb Site & Bomb (Tactical Bomb Defusal) ──────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeBombSite : public AActor, public IGameForgeInteractable
{
	GENERATED_BODY()
public:
	AGameForgeBombSite();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName SiteName = FName(TEXT("A"));

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId = FName(TEXT("bombsite_a"));

	virtual bool CanInteract(AController* InController) const override;
	virtual void Interact(AController* InController) override;

protected:
	bool bBombPlanted = false;
};

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeBomb : public AActor, public IGameForgeInteractable
{
	GENERATED_BODY()
public:
	AGameForgeBomb();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USphereComponent> DefuseTrigger;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float FuseTimeRemaining = 45.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float DefuseTimeRequired = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float ExplosionRadius = 1500.f;

	virtual bool CanInteract(AController* InController) const override;
	virtual void Interact(AController* InController) override;

	virtual void Tick(float DeltaSeconds) override;

protected:
	void Explode();
	void Defused();

	bool bDefused = false;
	bool bExploded = false;
	float CurrentDefuseProgress = 0.f;
};
