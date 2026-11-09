// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "GameFramework/Character.h"
#include "Perception/AIPerceptionTypes.h"
#include "GameForgeGuard.generated.h"

class UAIPerceptionComponent;
class UAISenseConfig_Sight;
class UStaticMeshComponent;

UENUM(BlueprintType)
enum class EGameForgeGuardState : uint8
{
	Patrol,
	Chase,
	Search,
	Return
};

/**
 * Gameplay kit NPC guard: patrols its points, chases a player-controlled pawn it SEES (engine AI Perception, sight
 * sense), searches the last known location when sight is lost, then returns to its route. Movement uses the
 * NavMesh through AAIController::MoveTo*. Every state change is logged as "GF_EVENT guard_state" and kept in
 * StateLog for read-back.
 */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGuard : public ACharacter
{
	GENERATED_BODY()

public:
	AGameForgeGuard();

	/** World-space patrol route, visited in order and looped. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	TArray<FVector> PatrolPoints;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	float PatrolRadius = 600.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	float AggroRadius = 900.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	float MoveSpeed = 240.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	float PatrolSpeed = 200.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	float ChaseSpeed = 420.0f;

	/** Seconds spent at the last known location before giving up. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	float SearchTime = 3.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Guard")
	FLinearColor BodyColor = FLinearColor(0.95f, 0.55f, 0.1f, 1.f);

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Guard")
	TObjectPtr<UStaticMeshComponent> ProxyBody;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Guard")
	TObjectPtr<UStaticMeshComponent> ProxyHead;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	EGameForgeGuardState CurrentState = EGameForgeGuardState::Patrol;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	FString CurrentStateName = TEXT("Patrol");

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	FString TargetName;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	int32 PatrolIndex = 0;

	/** "From->To t=.. target=.." for every state change, in order. */
	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	TArray<FString> StateLog;

	/** Last patrol move request result and last move completion code, for diagnosing stuck routes. */
	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	FString LastMoveRequest;

	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	FString LastMoveResult;

	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	int32 MoveRequests = 0;

	/** "Arrived #i" each time a patrol point is reached. */
	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Guard|State")
	TArray<FString> PatrolLog;

	virtual void BeginPlay() override;
	void EnterState(EGameForgeGuardState NewState, const AActor* Target = nullptr);
};

UCLASS()
class GAMEFORGERUNTIME_API AGameForgeGuardAIController : public AAIController
{
	GENERATED_BODY()

public:
	AGameForgeGuardAIController();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Guard")
	TObjectPtr<UAIPerceptionComponent> Perception;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Guard")
	TObjectPtr<UAISenseConfig_Sight> SightConfig;

	virtual void OnPossess(APawn* InPawn) override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void OnMoveCompleted(FAIRequestID RequestID, const FPathFollowingResult& Result) override;
	void ApplyGuardSightRadius(float NewAggroRadius);

protected:
	UFUNCTION()
	void HandlePerception(AActor* Actor, FAIStimulus Stimulus);

private:
	AGameForgeGuard* Guard() const;
	void MoveToPatrolPoint();
	void SetSpeed(float Speed) const;

	/** Moves are issued from Tick, never from OnMoveCompleted: a request that fails at once (e.g. NavMesh not built
	 *  yet) completes synchronously, so re-requesting inside the callback recursed until the stack overflowed. */
	void RequestPatrolMove(float Delay);

	TWeakObjectPtr<AActor> ChaseTarget;
	FVector LastKnownLocation = FVector::ZeroVector;
	float SearchRemaining = 0.0f;
	bool bArrivedAtSearchPoint = false;
	bool bPatrolMovePending = false;
	float PatrolMoveDelay = 0.0f;
};
