// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "GameForgeLocomotionAnimInstance.generated.h"

class UAnimSequence;

UENUM(BlueprintType)
enum class EGameForgeLocomotionState : uint8
{
	Idle,
	Walk,
	Run,
	Jump,
	Fall,
	Land
};

/** Worker-thread side of the locomotion instance: advances clip time and evaluates/blends poses. */
USTRUCT()
struct GAMEFORGERUNTIME_API FGameForgeLocomotionProxy : public FAnimInstanceProxy
{
	GENERATED_BODY()

	FGameForgeLocomotionProxy() = default;
	explicit FGameForgeLocomotionProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance) {}

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual void Update(float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

private:
	UAnimSequence* ClipFor(EGameForgeLocomotionState State) const;
	void SampleClip(UAnimSequence* Clip, double Time, bool bLoop, FPoseContext& Out) const;

	TObjectPtr<UAnimSequence> Clips[6] = {};
	EGameForgeLocomotionState State = EGameForgeLocomotionState::Idle;
	EGameForgeLocomotionState PrevState = EGameForgeLocomotionState::Idle;
	double StateTime = 0.0;
	double PrevStateTime = 0.0;
	float BlendElapsed = 1.0f;
	float BlendTime = 0.15f;
	bool bHasPrev = false;
};

/**
 * Native locomotion Anim Instance: a movement-driven state machine (Idle, Walk, Run, Jump, Fall,
 * Land) that reads the owning character's real CharacterMovement velocity and falling state and
 * evaluates the assigned AnimSequences with cross-fades. Use as the parent class of an AnimBP.
 */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API UGameForgeLocomotionAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion|Clips")
	TObjectPtr<UAnimSequence> IdleClip;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion|Clips")
	TObjectPtr<UAnimSequence> WalkClip;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion|Clips")
	TObjectPtr<UAnimSequence> RunClip;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion|Clips")
	TObjectPtr<UAnimSequence> JumpClip;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion|Clips")
	TObjectPtr<UAnimSequence> FallClip;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion|Clips")
	TObjectPtr<UAnimSequence> LandClip;

	/** Ground speed (cm/s) at or above which the character walks / runs. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion")
	float WalkSpeedThreshold = 10.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion")
	float RunSpeedThreshold = 350.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Locomotion")
	float BlendTime = 0.15f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion|State")
	EGameForgeLocomotionState CurrentState = EGameForgeLocomotionState::Idle;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion|State")
	float GroundSpeed = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion|State")
	float VerticalSpeed = 0.0f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion|State")
	bool bIsFalling = false;

	/** "From->To t=.. speed=.. vz=.." for every state change, in order. */
	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Locomotion|State")
	TArray<FString> TransitionLog;

	UFUNCTION(BlueprintCallable, Category = "Locomotion")
	static FString StateName(EGameForgeLocomotionState State);

protected:
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;

private:
	void EnterState(EGameForgeLocomotionState NewState);

	bool bWasFalling = false;
	float LandTimeRemaining = 0.0f;

	friend struct FGameForgeLocomotionProxy;
};
