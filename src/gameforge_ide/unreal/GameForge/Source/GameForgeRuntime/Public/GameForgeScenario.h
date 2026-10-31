#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "GameForgeAutopilot.h"
#include "GameForgeEvents.h"
#include "GameForgeScenario.generated.h"

USTRUCT()
struct FScenarioStepRecord
{
	GENERATED_BODY()
	int32 Index = 0;
	FString Kind;
	FString Status = TEXT("PENDING");  // DONE | FAILED | SKIPPED
	float T0 = 0.f;
	float T1 = 0.f;
	FString Error;
};

USTRUCT()
struct FScenarioExpectRecord
{
	GENERATED_BODY()
	FString ExpectJson;
	bool bOk = false;
	int32 Observed = 0;
};

UCLASS()
class GAMEFORGERUNTIME_API UGameForgeScenarioSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	// FTickableGameObject interface
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickable() const override { return bLoaded && !bFinished; }
	virtual ETickableTickType GetTickableTickType() const override { return ETickableTickType::Conditional; }
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UGameForgeScenarioSubsystem, STATGROUP_Tickables); }

private:
	void HandleEvent(const FGameForgeEvent& Ev);
	void StartCurrentStep();
	void TickCurrentStep(float DeltaTime);
	void CompleteCurrentStep();
	void FailCurrentStep(const FString& ErrorReason);
	void FinishScenario();
	void WriteErrorResult(const FString& Error);

	bool bLoaded = false;
	bool bStarted = false;
	bool bFinished = false;

	FString ScenarioPath;
	FString ScenarioOutPath;
	FString ScenarioId;
	float TimeoutSeconds = 120.f;

	float StartDelayTimer = 0.f;
	float StartDelaySeconds = 0.f;
	double StartTime = 0.0;
	float TotalElapsed = 0.f;

	TArray<TSharedPtr<FJsonValue>> ParsedSteps;
	TArray<TSharedPtr<FJsonValue>> ParsedExpect;
	TArray<TSharedPtr<FJsonValue>> ParsedCaptures;

	int32 CurrentStepIndex = 0;
	FString CurrentStepKind;
	TSharedPtr<FJsonObject> CurrentStepObj;
	float CurrentStepTimer = 0.f;
	float CurrentStepHoldSeconds = 0.f;
	bool bHoldingInput = false;

	TArray<FScenarioStepRecord> StepRecords;
	TArray<FScenarioExpectRecord> ExpectRecords;
	TArray<FString> Failures;
	TSet<FString> CapturedEvents;
};
