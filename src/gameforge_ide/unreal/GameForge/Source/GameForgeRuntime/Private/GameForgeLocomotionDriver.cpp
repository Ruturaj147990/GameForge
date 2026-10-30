// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeLocomotionDriver.h"

#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

AGameForgeLocomotionDriver::AGameForgeLocomotionDriver()
{
	PrimaryActorTick.bCanEverTick = true;
}

void AGameForgeLocomotionDriver::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bFinished || !Target)
	{
		return;
	}
	Elapsed += DeltaSeconds;

	// 0-1.5 s stand, 1.5-4 s walk (35% input), 4-6.5 s run (full input), 6.5 s jump, then stand.
	FString Phase;
	float Input = 0.0f;
	if (Elapsed < 1.5f)
	{
		Phase = TEXT("stand");
	}
	else if (Elapsed < 4.0f)
	{
		Phase = TEXT("walk");
		Input = 0.35f;
	}
	else if (Elapsed < 6.5f)
	{
		Phase = TEXT("run");
		Input = 1.0f;
	}
	else
	{
		Phase = bJumped ? TEXT("stand_after_jump") : TEXT("jump");
		if (!bJumped)
		{
			Target->Jump();
			bJumped = true;
		}
		else
		{
			Target->StopJumping();
		}
	}
	if (Phase != CurrentPhase)
	{
		PhaseLog.Add(FString::Printf(TEXT("%s@%.2f"), *Phase, Elapsed));
		UE_LOG(LogTemp, Display, TEXT("GF_LOCOMOTION_PHASE %s t=%.2f"), *Phase, Elapsed);
		CurrentPhase = Phase;
	}
	if (Input > 0.0f)
	{
		Target->AddMovementInput(FVector::ForwardVector, Input);
	}
	if (Elapsed >= ScriptLength)
	{
		bFinished = true;
	}
}
