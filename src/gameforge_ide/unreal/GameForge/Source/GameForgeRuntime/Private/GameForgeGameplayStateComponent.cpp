// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeGameplayStateComponent.h"
#include "Blueprint/UserWidget.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "UObject/UObjectIterator.h"

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
		RefreshViewportHUD();
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
		RefreshViewportHUD();
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
	RefreshViewportHUD();
}

UGameForgeGameplayStateComponent* UGameForgeGameplayStateComponent::FindOrCreateInWorld(UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (UGameForgeGameplayStateComponent* C = It->FindComponentByClass<UGameForgeGameplayStateComponent>())
		{
			return C;
		}
	}
	FActorSpawnParameters SpawnParams;
	SpawnParams.Name = FName(TEXT("GF_GameplayStateActor"));
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* Holder = World->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
	if (!Holder)
	{
		return nullptr;
	}
	UGameForgeGameplayStateComponent* Comp = NewObject<UGameForgeGameplayStateComponent>(Holder, TEXT("GFGameplayStateComponent"));
	Comp->RegisterComponent();
	Holder->AddInstanceComponent(Comp);
	return Comp;
}

void UGameForgeGameplayStateComponent::ExecuteMenuActionInWorld(UObject* WorldContextObject, const FString& ActionName)
{
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	UGameForgeGameplayStateComponent* Comp = FindOrCreateInWorld(World);
	if (!Comp)
	{
		UE_LOG(LogTemp, Warning, TEXT("[GameForgeGameplayState] ExecuteMenuActionInWorld('%s'): no world"), *ActionName);
		return;
	}
	UE_LOG(LogTemp, Log, TEXT("[GameForgeGameplayState] Widget event -> ExecuteMenuActionInWorld('%s') from %s"),
		*ActionName, WorldContextObject ? *WorldContextObject->GetName() : TEXT("None"));
	Comp->ExecuteMenuAction(ActionName);

	if (UUserWidget* Menu = Cast<UUserWidget>(WorldContextObject))
	{
		if (ActionName.Equals(TEXT("CloseMenu"), ESearchCase::IgnoreCase))
		{
			Menu->SetVisibility(ESlateVisibility::Collapsed);
		}
		else if (ActionName.Equals(TEXT("ToggleHUD"), ESearchCase::IgnoreCase))
		{
			const bool bCompact = Comp->ActiveMenuState.Equals(TEXT("Compact"), ESearchCase::IgnoreCase);
			if (UTextBlock* Title = Cast<UTextBlock>(Menu->GetWidgetFromName(TEXT("MenuTitle"))))
			{
				Title->SetText(FText::FromString(bCompact ? TEXT("GAMEFORGE (COMPACT)") : TEXT("GAMEFORGE MENU")));
			}
			if (UTextBlock* Label = Cast<UTextBlock>(Menu->GetWidgetFromName(TEXT("SecondaryButtonText"))))
			{
				Label->SetText(FText::FromString(bCompact ? TEXT("EXPAND MENU") : TEXT("TOGGLE COMPACT MODE")));
			}
		}
	}
}

int32 UGameForgeGameplayStateComponent::RefreshViewportHUD() const
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return 0;
	}
	int32 Updated = 0;
	for (TObjectIterator<UUserWidget> It; It; ++It)
	{
		UUserWidget* W = *It;
		if (W->GetWorld() != World || !W->IsInViewport())
		{
			continue;
		}
		if (UProgressBar* Bar = Cast<UProgressBar>(W->GetWidgetFromName(TEXT("HealthBar"))))
		{
			Bar->SetPercent(MaxHealth > 0.f ? Health / MaxHealth : 0.f);
			++Updated;
		}
		if (UTextBlock* Label = Cast<UTextBlock>(W->GetWidgetFromName(TEXT("HealthLabel"))))
		{
			Label->SetText(FText::FromString(FString::Printf(TEXT("HEALTH: %d / %d"), (int32)Health, (int32)MaxHealth)));
			++Updated;
		}
		if (UProgressBar* Bar = Cast<UProgressBar>(W->GetWidgetFromName(TEXT("StaminaBar"))))
		{
			Bar->SetPercent(MaxStamina > 0.f ? Stamina / MaxStamina : 0.f);
			++Updated;
		}
		if (UTextBlock* Label = Cast<UTextBlock>(W->GetWidgetFromName(TEXT("StaminaLabel"))))
		{
			Label->SetText(FText::FromString(FString::Printf(TEXT("STAMINA: %d / %d"), (int32)Stamina, (int32)MaxStamina)));
			++Updated;
		}
	}
	return Updated;
}
