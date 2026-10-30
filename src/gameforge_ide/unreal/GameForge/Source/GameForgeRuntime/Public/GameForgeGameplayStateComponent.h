// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "GameForgeGameplayStateComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnGFHealthChanged, float, NewHealth, float, MaxHealth);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnGFStaminaChanged, float, NewStamina, float, MaxStamina);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnGFMenuActionTriggered, const FString&, ActionName);

/**
 * Genuine gameplay state component for health, stamina, and menu action state.
 * Implements bounded values, dynamic multicasts, and event-driven updates.
 */
UCLASS(ClassGroup=(GameForge), meta=(BlueprintSpawnableComponent))
class GAMEFORGERUNTIME_API UGameForgeGameplayStateComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UGameForgeGameplayStateComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Gameplay")
	float Health;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Gameplay")
	float MaxHealth;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Gameplay")
	float Stamina;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Gameplay")
	float MaxStamina;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Gameplay")
	FString ActiveMenuState;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Gameplay")
	FString LastExecutedAction;

	UPROPERTY(BlueprintAssignable, Category="Gameplay|Events")
	FOnGFHealthChanged OnHealthChanged;

	UPROPERTY(BlueprintAssignable, Category="Gameplay|Events")
	FOnGFStaminaChanged OnStaminaChanged;

	UPROPERTY(BlueprintAssignable, Category="Gameplay|Events")
	FOnGFMenuActionTriggered OnMenuActionTriggered;

	UFUNCTION(BlueprintCallable, Category="Gameplay")
	void ModifyHealth(float Delta);

	UFUNCTION(BlueprintCallable, Category="Gameplay")
	void ModifyStamina(float Delta);

	UFUNCTION(BlueprintCallable, Category="Gameplay")
	void SetHealth(float NewVal);

	UFUNCTION(BlueprintCallable, Category="Gameplay")
	void SetStamina(float NewVal);

	UFUNCTION(BlueprintCallable, Category="Gameplay")
	void ExecuteMenuAction(const FString& ActionName);

	UFUNCTION(BlueprintCallable, Category="Gameplay")
	void ResetStats();

	/**
	 * Entry point for widget event graphs (e.g. a button's OnClicked): runs ActionName on the
	 * world's gameplay-state component. When called from a UUserWidget, menu actions also act
	 * on that widget (CloseMenu collapses it, ToggleHUD retitles it).
	 */
	UFUNCTION(BlueprintCallable, Category="Gameplay", meta=(WorldContext="WorldContextObject"))
	static void ExecuteMenuActionInWorld(UObject* WorldContextObject, const FString& ActionName);

	/** Returns the world's gameplay-state component, spawning a holder actor if none exists. */
	static UGameForgeGameplayStateComponent* FindOrCreateInWorld(UWorld* World);

	/**
	 * Pushes current state into viewport widgets that follow the HUD naming convention
	 * (HealthBar, HealthLabel, StaminaBar, StaminaLabel). Called on every state change.
	 * Returns the number of widgets updated.
	 */
	int32 RefreshViewportHUD() const;
};
