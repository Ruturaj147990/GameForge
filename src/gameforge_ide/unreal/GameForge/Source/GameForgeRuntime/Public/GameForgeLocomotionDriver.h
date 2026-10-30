// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameForgeLocomotionDriver.generated.h"

class ACharacter;

/**
 * Drives an AI-possessed ACharacter through a fixed movement script (stand, walk, run, jump,
 * land, stand) using real CharacterMovement input and Jump(). Used to verify that a locomotion
 * Anim Instance changes state because of actual movement, not because a test sets the state.
 */
UCLASS()
class GAMEFORGERUNTIME_API AGameForgeLocomotionDriver : public AActor
{
	GENERATED_BODY()

public:
	AGameForgeLocomotionDriver();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion")
	TObjectPtr<ACharacter> Target;

	/** Seconds since the script started; the script ends at ScriptLength. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion")
	float Elapsed = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion")
	float ScriptLength = 10.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion")
	bool bFinished = false;

	/** Phase names as they start, e.g. "walk@1.50". */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion")
	TArray<FString> PhaseLog;

	virtual void Tick(float DeltaSeconds) override;

private:
	FString CurrentPhase;
	bool bJumped = false;
};
