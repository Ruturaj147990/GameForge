// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameForgePickup.generated.h"

class UAudioComponent;
class UNiagaraComponent;
class UNiagaraSystem;
class USoundAttenuation;
class USoundBase;
class USphereComponent;
class UStaticMeshComponent;

UENUM(BlueprintType)
enum class EGameForgePickupEffect : uint8
{
	AddScore UMETA(DisplayName = "Add Score"),
	Heal UMETA(DisplayName = "Heal"),
	GrantItem UMETA(DisplayName = "Grant Item"),
	SpeedBoost UMETA(DisplayName = "Speed Boost"),
	CustomEvent UMETA(DisplayName = "Custom Event")
};

/**
 * Gameplay kit pickup: when a player-controlled pawn overlaps it, it is collected once and plays its feedback
 * at its location: a Niagara effect (tagged "GF_VFX:<VFXLabel>" so tools can read live particle counts) and a
 * sound (optionally attenuated). It logs "GF_EVENT pickup". Gameplay state lives here; VFX and SFX are
 * presentation only.
 */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgePickup : public AActor
{
	GENERATED_BODY()

public:
	AGameForgePickup();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Pickup")
	TObjectPtr<USphereComponent> Trigger;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Pickup")
	TObjectPtr<UStaticMeshComponent> Visual;

	/** Effect spawned on collection (optional). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Feedback")
	TObjectPtr<UNiagaraSystem> CollectVFX;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Feedback")
	FString VFXLabel = TEXT("Pickup");

	/** Sound played at the pickup on collection (optional). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Feedback")
	TObjectPtr<USoundBase> CollectSound;

	/** Overrides the sound's own attenuation when set. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Feedback")
	TObjectPtr<USoundAttenuation> CollectAttenuation;

	/** Objective advanced by one when collected (GameForgeObjectiveSubsystem); none = not part of a quest. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	FName ObjectiveId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	EGameForgePickupEffect Effect = EGameForgePickupEffect::AddScore;

	/** String fallback for Effect when configured from JSON or string property overrides. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	FString EffectName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	FName CustomEvent;

	/** Points/amount carried by the pickup (reported in the event payload; score/heal rules read it). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	int32 Value = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	bool bRespawns = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup")
	float RespawnSeconds = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Visual")
	FString VisualStyle = TEXT("coin");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Visual")
	FLinearColor PickupColor = FLinearColor(1.f, 0.78f, 0.1f, 1.f);

	/** Degrees per second; pickups spin and bob so they read as collectibles. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Visual")
	float SpinSpeed = 90.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Pickup|Visual")
	float BobHeight = 18.f;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Pickup|State")
	bool bCollected = false;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Pickup|State")
	FString CollectedBy;

	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Pickup|State")
	TObjectPtr<UNiagaraComponent> SpawnedVFX;

	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Pickup|State")
	TObjectPtr<UAudioComponent> SpawnedSound;

	DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnCollected, APawn*, Collector);

	UPROPERTY(BlueprintAssignable, Category = "Pickup")
	FOnCollected OnCollected;

protected:
	void SyncEffectFromName();
	void Respawn();
	FVector BaseVisualLocation = FVector::ZeroVector;
	float Age = 0.f;
	FTimerHandle RespawnTimer;

	UFUNCTION()
	void HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp,
		int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);
};
