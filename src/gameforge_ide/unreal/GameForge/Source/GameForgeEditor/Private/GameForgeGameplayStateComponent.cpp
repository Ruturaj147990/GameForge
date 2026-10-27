// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeGameplayStateComponent.h"

UGameForgeGameplayStateComponent::UGameForgeGameplayStateComponent()
	: Health(100.0f)
	, MaxHealth(100.0f)
	, Stamina(85.0f)
	, MaxStamina(100.0f)
	, ActiveMenuState(TEXT("Main"))
	, LastExecutedAction(TEXT("None"))
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UGameForgeGameplayStateComponent::ModifyHealth(float Delta)
{
	float Old = Health;
	Health = FMath::Clamp(Health + Delta, 0.0f, MaxHealth);
	UE_LOG(LogTemp, Log, TEXT("[GameForgeGameplayState] ModifyHealth: %.1f -> %.1f (delta: %.1f)"), Old, Health, Delta);
	if (Health != Old || Delta == 0.0f)
	{
		OnHealthChanged.Broadcast(Health, MaxHealth);
	}
}

void UGameForgeGameplayStateComponent::ModifyStamina(float Delta)
{
	float Old = Stamina;
	Stamina = FMath::Clamp(Stamina + Delta, 0.0f, MaxStamina);
	UE_LOG(LogTemp, Log, TEXT("[GameForgeGameplayState] ModifyStamina: %.1f -> %.1f (delta: %.1f)"), Old, Stamina, Delta);
	if (Stamina != Old || Delta == 0.0f)
	{
		OnStaminaChanged.Broadcast(Stamina, MaxStamina);
	}
}

void UGameForgeGameplayStateComponent::SetHealth(float NewVal)
{
	ModifyHealth(NewVal - Health);
}

void UGameForgeGameplayStateComponent::SetStamina(float NewVal)
{
	ModifyStamina(NewVal - Stamina);
}

void UGameForgeGameplayStateComponent::ExecuteMenuAction(const FString& ActionName)
{
	LastExecutedAction = ActionName;
	UE_LOG(LogTemp, Log, TEXT("[GameForgeGameplayState] ExecuteMenuAction: '%s'"), *ActionName);

	if (ActionName.Equals(TEXT("HealBoost"), ESearchCase::IgnoreCase))
	{
		ModifyHealth(25.0f);
	}
	else if (ActionName.Equals(TEXT("ToggleHUD"), ESearchCase::IgnoreCase))
	{
		ActiveMenuState = ActiveMenuState.Equals(TEXT("Compact"), ESearchCase::IgnoreCase) ? TEXT("Full") : TEXT("Compact");
		UE_LOG(LogTemp, Log, TEXT("[GameForgeGameplayState] ActiveMenuState toggled to: '%s'"), *ActiveMenuState);
	}
	else if (ActionName.Equals(TEXT("CloseMenu"), ESearchCase::IgnoreCase))
	{
		ActiveMenuState = TEXT("Closed");
		UE_LOG(LogTemp, Log, TEXT("[GameForgeGameplayState] ActiveMenuState set to Closed"));
	}

	OnMenuActionTriggered.Broadcast(ActionName);
}

void UGameForgeGameplayStateComponent::ResetStats()
{
	Health = MaxHealth;
	Stamina = MaxStamina;
	ActiveMenuState = TEXT("Main");
	LastExecutedAction = TEXT("Reset");
	OnHealthChanged.Broadcast(Health, MaxHealth);
	OnStaminaChanged.Broadcast(Stamina, MaxStamina);
	OnMenuActionTriggered.Broadcast(TEXT("Reset"));
}
