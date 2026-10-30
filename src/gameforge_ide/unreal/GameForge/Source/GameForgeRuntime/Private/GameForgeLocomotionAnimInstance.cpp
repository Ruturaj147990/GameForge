// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeLocomotionAnimInstance.h"

#include "Animation/AnimNodeBase.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

FString UGameForgeLocomotionAnimInstance::StateName(EGameForgeLocomotionState State)
{
	switch (State)
	{
		case EGameForgeLocomotionState::Idle: return TEXT("Idle");
		case EGameForgeLocomotionState::Walk: return TEXT("Walk");
		case EGameForgeLocomotionState::Run: return TEXT("Run");
		case EGameForgeLocomotionState::Jump: return TEXT("Jump");
		case EGameForgeLocomotionState::Fall: return TEXT("Fall");
		case EGameForgeLocomotionState::Land: return TEXT("Land");
	}
	return TEXT("Unknown");
}

void UGameForgeLocomotionAnimInstance::EnterState(EGameForgeLocomotionState NewState)
{
	if (NewState == CurrentState)
	{
		return;
	}
	const UWorld* World = GetWorld();
	const FString Entry = FString::Printf(TEXT("%s->%s t=%.2f speed=%.0f vz=%.0f"),
		*StateName(CurrentState), *StateName(NewState), World ? World->GetTimeSeconds() : 0.0, GroundSpeed, VerticalSpeed);
	TransitionLog.Add(Entry);
	UE_LOG(LogTemp, Display, TEXT("GF_ANIM_STATE %s"), *Entry);
	CurrentState = NewState;
	if (NewState == EGameForgeLocomotionState::Land)
	{
		LandTimeRemaining = LandClip ? LandClip->GetPlayLength() : 0.25f;
	}
}

void UGameForgeLocomotionAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	const APawn* Pawn = TryGetPawnOwner();
	if (!Pawn)
	{
		return;
	}
	const FVector Velocity = Pawn->GetVelocity();
	GroundSpeed = Velocity.Size2D();
	VerticalSpeed = Velocity.Z;
	const ACharacter* Character = Cast<ACharacter>(Pawn);
	const UCharacterMovementComponent* Move = Character ? Character->GetCharacterMovement() : nullptr;
	bIsFalling = Move && Move->IsFalling();

	LandTimeRemaining = FMath::Max(0.0f, LandTimeRemaining - DeltaSeconds);

	EGameForgeLocomotionState Next;
	if (bIsFalling)
	{
		// Rising after leaving the ground is a jump; descending (or walking off a ledge) is a fall.
		Next = (VerticalSpeed > 0.0f && CurrentState != EGameForgeLocomotionState::Fall)
			? EGameForgeLocomotionState::Jump : EGameForgeLocomotionState::Fall;
	}
	else if (bWasFalling)
	{
		Next = EGameForgeLocomotionState::Land;
	}
	else if (CurrentState == EGameForgeLocomotionState::Land && LandTimeRemaining > 0.0f)
	{
		Next = EGameForgeLocomotionState::Land;
	}
	else if (GroundSpeed < WalkSpeedThreshold)
	{
		Next = EGameForgeLocomotionState::Idle;
	}
	else
	{
		Next = GroundSpeed < RunSpeedThreshold ? EGameForgeLocomotionState::Walk : EGameForgeLocomotionState::Run;
	}
	EnterState(Next);
	bWasFalling = bIsFalling;
}

FAnimInstanceProxy* UGameForgeLocomotionAnimInstance::CreateAnimInstanceProxy()
{
	return new FGameForgeLocomotionProxy(this);
}

void UGameForgeLocomotionAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy)
{
	delete InProxy;
}

void FGameForgeLocomotionProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	const UGameForgeLocomotionAnimInstance* Inst = CastChecked<UGameForgeLocomotionAnimInstance>(InAnimInstance);
	Clips[0] = Inst->IdleClip;
	Clips[1] = Inst->WalkClip;
	Clips[2] = Inst->RunClip;
	Clips[3] = Inst->JumpClip;
	Clips[4] = Inst->FallClip;
	Clips[5] = Inst->LandClip;
	BlendTime = FMath::Max(0.01f, Inst->BlendTime);
	if (Inst->CurrentState != State)
	{
		PrevState = State;
		PrevStateTime = StateTime;
		bHasPrev = true;
		State = Inst->CurrentState;
		StateTime = 0.0;
		BlendElapsed = 0.0f;
	}
}

void FGameForgeLocomotionProxy::Update(float DeltaSeconds)
{
	StateTime += DeltaSeconds;
	PrevStateTime += DeltaSeconds;
	BlendElapsed += DeltaSeconds;
}

UAnimSequence* FGameForgeLocomotionProxy::ClipFor(EGameForgeLocomotionState InState) const
{
	return Clips[static_cast<int32>(InState)].Get();
}

void FGameForgeLocomotionProxy::SampleClip(UAnimSequence* Clip, double Time, bool bLoop, FPoseContext& Out) const
{
	const double Length = FMath::Max(Clip->GetPlayLength(), UE_KINDA_SMALL_NUMBER);
	const double T = bLoop ? FMath::Fmod(Time, Length) : FMath::Min(Time, Length);
	FAnimationPoseData PoseData(Out);
	Clip->GetAnimationPose(PoseData, FAnimExtractContext(T, false));
}

static bool IsLoopingState(EGameForgeLocomotionState State)
{
	return State == EGameForgeLocomotionState::Idle || State == EGameForgeLocomotionState::Walk
		|| State == EGameForgeLocomotionState::Run || State == EGameForgeLocomotionState::Fall;
}

bool FGameForgeLocomotionProxy::Evaluate(FPoseContext& Output)
{
	UAnimSequence* Current = ClipFor(State);
	if (!Current)
	{
		Output.ResetToRefPose();
		return true;
	}
	UAnimSequence* Previous = bHasPrev ? ClipFor(PrevState) : nullptr;
	if (!Previous || BlendElapsed >= BlendTime)
	{
		SampleClip(Current, StateTime, IsLoopingState(State), Output);
		return true;
	}
	// Cross-fade from the previous state's pose into the current one.
	FPoseContext CurrentPose(this);
	FPoseContext PreviousPose(this);
	SampleClip(Current, StateTime, IsLoopingState(State), CurrentPose);
	SampleClip(Previous, PrevStateTime, IsLoopingState(PrevState), PreviousPose);
	const float Alpha = FMath::Clamp(BlendElapsed / BlendTime, 0.0f, 1.0f);
	FAnimationPoseData CurrentData(CurrentPose);
	FAnimationPoseData PreviousData(PreviousPose);
	FAnimationPoseData OutData(Output);
	FAnimationRuntime::BlendTwoPosesTogether(CurrentData, PreviousData, Alpha, OutData);
	return true;
}
