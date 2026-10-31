// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeGuard.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"

#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Navigation/PathFollowingComponent.h"
#include "Perception/AIPerceptionComponent.h"
#include "Perception/AISenseConfig_Sight.h"
#include "Perception/AISense_Sight.h"

static FString GuardStateName(EGameForgeGuardState State)
{
	switch (State)
	{
		case EGameForgeGuardState::Patrol: return TEXT("Patrol");
		case EGameForgeGuardState::Chase: return TEXT("Chase");
		case EGameForgeGuardState::Search: return TEXT("Search");
		case EGameForgeGuardState::Return: return TEXT("Return");
	}
	return TEXT("Unknown");
}

AGameForgeGuard::AGameForgeGuard()
{
	AIControllerClass = AGameForgeGuardAIController::StaticClass();
	AutoPossessAI = EAutoPossessAI::PlacedInWorldOrSpawned;
	bUseControllerRotationYaw = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->MaxWalkSpeed = PatrolSpeed;
}

void AGameForgeGuard::EnterState(EGameForgeGuardState NewState, const AActor* Target)
{
	if (NewState == CurrentState)
	{
		return;
	}
	const UWorld* World = GetWorld();
	const FString Entry = FString::Printf(TEXT("%s->%s t=%.2f target=%s"), *GuardStateName(CurrentState),
		*GuardStateName(NewState), World ? World->GetTimeSeconds() : 0.0, Target ? *Target->GetName() : TEXT("None"));
	StateLog.Add(Entry);
	UE_LOG(LogTemp, Display, TEXT("GF_EVENT guard_state guard=%s %s"), *GetName(), *Entry);
	const FString PrevStateName = GuardStateName(CurrentState);
	const FString NextStateName = GuardStateName(NewState);
	const FString StateDataJson = FString::Printf(TEXT("{\"state\":\"%s\",\"prev\":\"%s\"}"), *NextStateName, *PrevStateName);
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GuardState, GetName(), StateDataJson, EntityId);
	if (NewState == EGameForgeGuardState::Chase)
	{
		UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GuardSpottedPlayer, GetName(), StateDataJson, EntityId);
	}
	else if (NewState == EGameForgeGuardState::Search)
	{
		UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::GuardLostPlayer, GetName(), StateDataJson, EntityId);
	}
	CurrentState = NewState;
	CurrentStateName = GuardStateName(NewState);
	TargetName = Target ? Target->GetName() : FString();
}

AGameForgeGuardAIController::AGameForgeGuardAIController()
{
	PrimaryActorTick.bCanEverTick = true;
	Perception = CreateDefaultSubobject<UAIPerceptionComponent>(TEXT("Perception"));
	SightConfig = CreateDefaultSubobject<UAISenseConfig_Sight>(TEXT("SightConfig"));
	SightConfig->SightRadius = 1500.0f;
	SightConfig->LoseSightRadius = 1900.0f;
	SightConfig->PeripheralVisionAngleDegrees = 70.0f;
	SightConfig->DetectionByAffiliation.bDetectEnemies = true;
	SightConfig->DetectionByAffiliation.bDetectNeutrals = true;
	SightConfig->DetectionByAffiliation.bDetectFriendlies = true;
	SightConfig->SetMaxAge(1.0f);
	Perception->ConfigureSense(*SightConfig);
	Perception->SetDominantSense(UAISense_Sight::StaticClass());
	SetPerceptionComponent(*Perception);
}

AGameForgeGuard* AGameForgeGuardAIController::Guard() const
{
	return Cast<AGameForgeGuard>(GetPawn());
}

void AGameForgeGuardAIController::SetSpeed(float Speed) const
{
	if (AGameForgeGuard* G = Guard())
	{
		G->GetCharacterMovement()->MaxWalkSpeed = Speed;
	}
}

void AGameForgeGuardAIController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);
	Perception->OnTargetPerceptionUpdated.AddUniqueDynamic(this, &AGameForgeGuardAIController::HandlePerception);
	RequestPatrolMove(0.5f);  // give the NavMesh a moment at world start
}

void AGameForgeGuardAIController::RequestPatrolMove(float Delay)
{
	bPatrolMovePending = true;
	PatrolMoveDelay = Delay;
}

void AGameForgeGuardAIController::MoveToPatrolPoint()
{
	AGameForgeGuard* G = Guard();
	if (!G || G->PatrolPoints.Num() == 0)
	{
		return;
	}
	SetSpeed(G->PatrolSpeed);
	G->PatrolIndex = G->PatrolIndex % G->PatrolPoints.Num();
	// Standing on the point (e.g. spawned there): the request is accepted but completes as "Invalid" (degenerate
	// path) and AlreadyAtGoal is not reported because the point's Z differs from the capsule centre. Decide in 2D.
	if (FVector::Dist2D(G->GetActorLocation(), G->PatrolPoints[G->PatrolIndex]) <= 100.0f)
	{
		if (G->CurrentState == EGameForgeGuardState::Return)
		{
			G->EnterState(EGameForgeGuardState::Patrol);
		}
		G->PatrolLog.Add(FString::Printf(TEXT("Arrived #%d"), G->PatrolIndex));
		UE_LOG(LogTemp, Display, TEXT("GF_EVENT guard_patrol guard=%s arrived=%d"), *G->GetName(), G->PatrolIndex);
		G->PatrolIndex = (G->PatrolIndex + 1) % G->PatrolPoints.Num();
		RequestPatrolMove(0.0f);
		return;
	}
	const EPathFollowingRequestResult::Type Res = MoveToLocation(G->PatrolPoints[G->PatrolIndex], /*AcceptanceRadius=*/60.0f);
	G->MoveRequests++;
	G->LastMoveRequest = Res == EPathFollowingRequestResult::AlreadyAtGoal ? TEXT("AlreadyAtGoal")
		: Res == EPathFollowingRequestResult::Failed ? TEXT("Failed") : TEXT("RequestSuccessful");
	if (Res == EPathFollowingRequestResult::AlreadyAtGoal)
	{
		// No OnMoveCompleted is sent for this result (e.g. the guard starts on point 0): count it as an arrival.
		if (G->CurrentState == EGameForgeGuardState::Return)
		{
			G->EnterState(EGameForgeGuardState::Patrol);
		}
		G->PatrolLog.Add(FString::Printf(TEXT("Arrived #%d"), G->PatrolIndex));
		UE_LOG(LogTemp, Display, TEXT("GF_EVENT guard_patrol guard=%s arrived=%d"), *G->GetName(), G->PatrolIndex);
		G->PatrolIndex = (G->PatrolIndex + 1) % G->PatrolPoints.Num();
		RequestPatrolMove(0.0f);
	}
	else if (Res == EPathFollowingRequestResult::Failed)
	{
		RequestPatrolMove(0.5f);
	}
}

void AGameForgeGuardAIController::HandlePerception(AActor* Actor, FAIStimulus Stimulus)
{
	AGameForgeGuard* G = Guard();
	const APawn* SeenPawn = Cast<APawn>(Actor);
	if (!G || !SeenPawn || !SeenPawn->IsPlayerControlled())
	{
		return;
	}
	if (Stimulus.WasSuccessfullySensed())
	{
		bPatrolMovePending = false;
		ChaseTarget = Actor;
		G->EnterState(EGameForgeGuardState::Chase, Actor);
		SetSpeed(G->ChaseSpeed);
		MoveToActor(Actor, /*AcceptanceRadius=*/120.0f);
	}
	else if (ChaseTarget.Get() == Actor && G->CurrentState == EGameForgeGuardState::Chase)
	{
		LastKnownLocation = Stimulus.StimulusLocation;
		SearchRemaining = G->SearchTime;
		bArrivedAtSearchPoint = false;
		G->EnterState(EGameForgeGuardState::Search, Actor);
		MoveToLocation(LastKnownLocation, /*AcceptanceRadius=*/80.0f);
	}
}

void AGameForgeGuardAIController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	AGameForgeGuard* G = Guard();
	if (!G)
	{
		return;
	}
	if (bPatrolMovePending)
	{
		PatrolMoveDelay -= DeltaSeconds;
		if (PatrolMoveDelay <= 0.0f)
		{
			bPatrolMovePending = false;
			MoveToPatrolPoint();
		}
	}
	if (G->CurrentState == EGameForgeGuardState::Chase && ChaseTarget.IsValid()
		&& GetMoveStatus() == EPathFollowingStatus::Idle)
	{
		MoveToActor(ChaseTarget.Get(), 120.0f);  // keep pursuing after reaching it
	}
	if (G->CurrentState == EGameForgeGuardState::Search && bArrivedAtSearchPoint)
	{
		SearchRemaining -= DeltaSeconds;
		if (SearchRemaining <= 0.0f)
		{
			ChaseTarget.Reset();
			G->EnterState(EGameForgeGuardState::Return);
			RequestPatrolMove(0.0f);
		}
	}
}

void AGameForgeGuardAIController::OnMoveCompleted(FAIRequestID RequestID, const FPathFollowingResult& Result)
{
	Super::OnMoveCompleted(RequestID, Result);
	AGameForgeGuard* G = Guard();
	if (!G)
	{
		return;
	}
	G->LastMoveResult = Result.ToString();
	switch (G->CurrentState)
	{
		case EGameForgeGuardState::Patrol:
			if (Result.IsSuccess())
			{
				G->PatrolLog.Add(FString::Printf(TEXT("Arrived #%d"), G->PatrolIndex));
				UE_LOG(LogTemp, Display, TEXT("GF_EVENT guard_patrol guard=%s arrived=%d"), *G->GetName(), G->PatrolIndex);
				G->PatrolIndex = (G->PatrolIndex + 1) % FMath::Max(1, G->PatrolPoints.Num());
			}
			RequestPatrolMove(Result.IsSuccess() ? 0.0f : 0.5f);
			break;
		case EGameForgeGuardState::Search:
			bArrivedAtSearchPoint = true;  // reached (or failed to reach) the last known location: look around
			break;
		case EGameForgeGuardState::Return:
			if (Result.IsSuccess())
			{
				G->EnterState(EGameForgeGuardState::Patrol);
			}
			RequestPatrolMove(Result.IsSuccess() ? 0.0f : 0.5f);
			break;
		default:
			break;
	}
}
