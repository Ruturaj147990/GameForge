#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "GameForgeEvents.h"
#include "GameForgeRules.generated.h"

class AGameForgeGameState;
class UGameForgeCustomRule;

/**
 * Pure C++ condition evaluator (WI-5.3). No UObject dependencies.
 */
class GAMEFORGERUNTIME_API FGameForgeConditionEvaluator
{
public:
	struct FContext
	{
		TFunction<float(FName Stat)> GetStat;
		TFunction<int32(FName Event, FName Entity)> CountEvents;
		TFunction<bool(FName Event, FName Entity)> HasEvent;
		TFunction<bool(FName Event, const FString& Key, FString& OutValue, FName Entity)> GetEventField;
		float ElapsedSeconds = 0.f;
	};

	/** false + Error set on malformed JSON (unknown kind, missing field, depth > 3). Never throws. */
	static bool Evaluate(const TSharedPtr<FJsonObject>& Condition, const FContext& Ctx, FString& Error, int32 Depth = 0);
};

/**
 * Base class for custom rule code (WI-5.4, WI-6.6).
 */
UCLASS(Abstract, Blueprintable)
class GAMEFORGERUNTIME_API UGameForgeCustomRule : public UObject
{
	GENERATED_BODY()

public:
	virtual void Initialize(UWorld* InWorld) { World = InWorld; }
	virtual void OnEvent(const FGameForgeEvent& Event) {}
	virtual void Tick(float DeltaSeconds) {}

protected:
	UPROPERTY()
	TObjectPtr<UWorld> World;

	AGameForgeGameState* GameState() const;
	void Emit(FName Name, const FString& DataJson = TEXT("{}"), FName Entity = NAME_None);
};

/**
 * Subsystem executing gfdef rules, win/lose checks, and custom rules (WI-5.4).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeRulesSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

	void HandleEvent(const FGameForgeEvent& Event);
	void CheckWinLose();

	bool IsGameEnded() const { return bGameEnded; }

private:
	void ApplyEffect(const TSharedPtr<FJsonObject>& Effect, const FGameForgeEvent& TriggerEvent);
	void SpawnEntity(const FString& EntityId, int32 Count);
	void SyncPlayerStatToAttributes(const FString& StatName, float NewVal) const;

	TSharedPtr<FJsonObject> Def;
	UPROPERTY()
	TArray<TObjectPtr<UGameForgeCustomRule>> CustomRules;

	FTimerHandle WinLoseTimerHandle;
	int32 ReentrancyDepth = 0;
	bool bGameEnded = false;
	double StartTime = 0.0;
};
