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
	bool bRanged = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float ProjectileSpeed = 1500.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	uint8 TeamId = 1; // 0 = CT / Friendly, 1 = Terrorist / Enemy

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> WeaponMesh;

	virtual void BeginPlay() override;
	void PerformAttack(AActor* Target);

private:
	float LastAttackTime = -100.f;
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
	TWeakObjectPtr<AActor> CurrentTarget;
	float MoveCooldown = 0.f;
};

// ── Spawner ───────────────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeSpawner : public AActor
{
	GENERATED_BODY()
public:
	AGameForgeSpawner();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	TSubclassOf<AActor> EnemyClass;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EnemyEntityId = FName(TEXT("enemy"));

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 WaveCount = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 EnemiesPerWave = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float SecondsBetweenWaves = 5.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float SpawnRadius = 400.f;

	virtual void BeginPlay() override;

private:
	void StartWave();
	void HandleEvent(const FGameForgeEvent& Event);

	int32 CurrentWave = 0;
	int32 AliveEnemiesInWave = 0;
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
