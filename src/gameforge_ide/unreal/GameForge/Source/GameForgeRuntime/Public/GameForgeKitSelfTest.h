// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameForgeKitSelfTest.generated.h"

class AGameForgeGuard;
class AGameForgeQuestGiver;

/**
 * Packaged-build self-test for the gameplay kit. Inert unless the game runs with -GFKitSelfTest (walk the player's
 * pawn along Waypoints with NavMesh moves, then check quest/objective, dialogue and guard state) or
 * -GFKitSelfTestRestore (check that the objective was restored from the save slot). Logs one
 * "GF_KIT_SELFTEST PASS|FAIL ..." line and quits.
 */
UCLASS()
class GAMEFORGERUNTIME_API AGameForgeKitSelfTest : public AActor
{
	GENERATED_BODY()

public:
	AGameForgeKitSelfTest();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "SelfTest")
	TArray<FVector> Waypoints;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "SelfTest")
	FName ObjectiveId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "SelfTest")
	float WaypointTimeout = 20.0f;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void Finish(bool bPass, const FString& Details);

	enum class EMode : uint8 { Off, Fresh, Restore };
	EMode Mode = EMode::Off;
	int32 WaypointIndex = -1;
	float Elapsed = 0.0f;
	float StepElapsed = 0.0f;
	bool bFinished = false;
};
