// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeKitSelfTest.h"

#include "Blueprint/AIBlueprintHelperLibrary.h"
#include "EngineUtils.h"
#include "GameForgeGuard.h"
#include "GameForgeObjectives.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

AGameForgeKitSelfTest::AGameForgeKitSelfTest()
{
	PrimaryActorTick.bCanEverTick = true;
}

void AGameForgeKitSelfTest::BeginPlay()
{
	Super::BeginPlay();
	if (FParse::Param(FCommandLine::Get(), TEXT("GFKitSelfTestRestore")))
	{
		Mode = EMode::Restore;
	}
	else if (FParse::Param(FCommandLine::Get(), TEXT("GFKitSelfTest")))
	{
		Mode = EMode::Fresh;
	}
	SetActorTickEnabled(Mode != EMode::Off);
	if (Mode != EMode::Off)
	{
		UE_LOG(LogTemp, Display, TEXT("GF_KIT_SELFTEST start mode=%s waypoints=%d"),
			Mode == EMode::Fresh ? TEXT("fresh") : TEXT("restore"), Waypoints.Num());
	}
}

void AGameForgeKitSelfTest::Finish(bool bPass, const FString& Details)
{
	bFinished = true;
	UE_LOG(LogTemp, Display, TEXT("GF_KIT_SELFTEST %s %s"), bPass ? TEXT("PASS") : TEXT("FAIL"), *Details);
	UKismetSystemLibrary::QuitGame(this, UGameplayStatics::GetPlayerController(this, 0), EQuitPreference::Quit, false);
}

void AGameForgeKitSelfTest::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bFinished)
	{
		return;
	}
	Elapsed += DeltaSeconds;
	StepElapsed += DeltaSeconds;
	UGameForgeObjectiveSubsystem* Objectives = UGameForgeObjectiveSubsystem::GetForWorld(this);
	APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (!Objectives || !Pawn)
	{
		if (Elapsed > 10.0f)
		{
			Finish(false, TEXT("no objective subsystem or player pawn"));
		}
		return;
	}

	if (Mode == EMode::Restore)
	{
		if (Elapsed > 2.0f)
		{
			const FString Json = Objectives->GetObjectivesJson();
			// Run 1 string-matched the (pretty-printed) JSON and failed although the slot had loaded.
			const bool bOk = Objectives->WasLoadedFromSlot() && Objectives->GetState(ObjectiveId) == EGameForgeObjectiveState::Completed;
			Finish(bOk, FString::Printf(TEXT("restore objectives=%s"), *Json));
		}
		return;
	}

	// Fresh: walk the waypoints (wait 2 s at start for the NavMesh/possession).
	if (Elapsed < 2.0f)
	{
		return;
	}
	const bool bWalking = WaypointIndex >= 0 && WaypointIndex < Waypoints.Num();
	const bool bAtWaypoint = bWalking && FVector::Dist2D(Pawn->GetActorLocation(), Waypoints[WaypointIndex]) < 150.0f;
	if (WaypointIndex < 0 || bAtWaypoint || (bWalking && StepElapsed > WaypointTimeout))
	{
		if (bWalking)
		{
			// World time + pawn position per waypoint let the host check the legs are physically plausible.
			const FVector L = Pawn->GetActorLocation();
			UE_LOG(LogTemp, Display, TEXT("GF_KIT_SELFTEST waypoint=%d reached=%d leg_s=%.2f world_t=%.2f pawn=%.0f,%.0f,%.0f"),
				WaypointIndex, bAtWaypoint ? 1 : 0, StepElapsed, GetWorld()->GetTimeSeconds(), L.X, L.Y, L.Z);
		}
		++WaypointIndex;
		StepElapsed = 0.0f;
		if (WaypointIndex < Waypoints.Num())
		{
			UAIBlueprintHelperLibrary::SimpleMoveToLocation(PC, Waypoints[WaypointIndex]);
			return;
		}
	}
	if (WaypointIndex >= Waypoints.Num() && StepElapsed > 3.0f)
	{
		int32 Spoken = 0;
		for (TActorIterator<AGameForgeQuestGiver> It(GetWorld()); It; ++It)
		{
			Spoken = It->SpokenLines.Num();
		}
		int32 Patrols = 0;
		bool bChased = false;
		for (TActorIterator<AGameForgeGuard> It(GetWorld()); It; ++It)
		{
			Patrols = It->PatrolLog.Num();
			bChased = It->StateLog.ContainsByPredicate([](const FString& E) { return E.StartsWith(TEXT("Patrol->Chase")); });
		}
		const bool bQuest = Objectives->GetState(ObjectiveId) == EGameForgeObjectiveState::Completed && Spoken == 3;
		const bool bPass = bQuest && Patrols >= 1 && bChased;
		Finish(bPass, FString::Printf(TEXT("objective=%d spoken=%d guard_patrols=%d guard_chased=%d objectives=%s"),
			static_cast<int32>(Objectives->GetState(ObjectiveId)), Spoken, Patrols, bChased ? 1 : 0, *Objectives->GetObjectivesJson()));
	}
}
