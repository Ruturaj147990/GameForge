#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameForgeAutopilot.generated.h"

USTRUCT(BlueprintType)
struct GAMEFORGERUNTIME_API FGameForgeLeg
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString Target;
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float DistanceCm = 0.f;   // path length actually travelled
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float Seconds = 0.f;
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float MaxStepCm = 0.f;    // largest single-frame displacement
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString Result;            // ARRIVED | TELEPORT_SUSPECTED | STUCK | NO_PATH | TIMEOUT
};

UCLASS(ClassGroup = (GameForge), meta = (BlueprintSpawnableComponent))
class GAMEFORGERUNTIME_API UGameForgeAutopilotComponent : public UActorComponent
{
	GENERATED_BODY()
public:
	UGameForgeAutopilotComponent();
	/** Starts walking to Target via NavMesh using injected IA_Move input. Returns false if no path. */
	bool MoveTo(const FVector& Target, const FString& Label, float AcceptRadiusCm = 120.f, float TimeoutS = 60.f);
	bool IsActive() const { return bActive; }
	const TArray<FGameForgeLeg>& Legs() const { return CompletedLegs; }
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
private:
	void Finish(const FString& Result);
	TArray<FVector> Path;
	int32 PathIndex = 0;
	bool bActive = false;
	FGameForgeLeg Current;
	FVector LastPos = FVector::ZeroVector;
	float Accept = 120.f;
	float Timeout = 60.f;
	float StuckTimer = 0.f;
	FVector StuckAnchor = FVector::ZeroVector;
	TArray<FGameForgeLeg> CompletedLegs;
};
