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
	UFUNCTION()
	void HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp,
		int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);
};
