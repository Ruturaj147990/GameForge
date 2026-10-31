#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "GameForgeGameState.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnGameForgeStatChanged, FName, StatName, float, NewValue);

USTRUCT(BlueprintType)
struct FGameForgeStatBounds
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") float MinValue = -1e9f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") float MaxValue = 1e9f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") bool bHasMin = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") bool bHasMax = false;
};

/**
 * GameState hosting gfdef stats with clamping, derived queries, and HUD change notification (WI-5.2).
 */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	AGameForgeGameState();

	virtual void BeginPlay() override;

	UFUNCTION(BlueprintCallable, Category = "GameForge|Stats")
	float GetStat(FName StatName) const;

	UFUNCTION(BlueprintCallable, Category = "GameForge|Stats")
	void SetStat(FName StatName, float Value);

	UFUNCTION(BlueprintCallable, Category = "GameForge|Stats")
	void AddStat(FName StatName, float Delta);

	void SetStatBounds(FName StatName, float MinVal, float MaxVal, bool bMin, bool bMax);

	UPROPERTY(BlueprintAssignable, Category = "GameForge|Stats")
	FOnGameForgeStatChanged OnStatChanged;

	const TMap<FName, float>& GetAllStats() const { return Stats; }

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Stats")
	TMap<FName, float> Stats;

	TMap<FName, FGameForgeStatBounds> StatBounds;

	double GameStartTime = 0.0;
};
