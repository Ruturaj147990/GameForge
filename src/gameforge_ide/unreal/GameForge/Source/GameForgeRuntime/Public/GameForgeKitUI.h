#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/VerticalBox.h"
#include "Components/TextBlock.h"
#include "Components/ProgressBar.h"
#include "Components/Button.h"
#include "Camera/CameraShakeBase.h"
#include "GameFramework/SaveGame.h"
#include "Subsystems/WorldSubsystem.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "GameForgeEvents.h"
#include "Dom/JsonObject.h"
#include "GameForgeKitUI.generated.h"

class AGameForgeGameState;

/**
 * SaveGame object serializing AGameForgeGameState stats and counters (WI-5.11).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeRuntimeSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	UPROPERTY(SaveGame)
	TMap<FName, float> SavedStats;

	UPROPERTY(SaveGame)
	TMap<FName, int32> SavedCounters;
};

/**
 * Native HUD widget created dynamically from gfdef/1 hud specification (WI-5.10).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeHUDWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual TSharedRef<SWidget> RebuildWidget() override;

	void ShowMessage(const FString& Message, float DurationSeconds = 3.f);

	UFUNCTION()
	void OnStatChanged(FName StatName, float NewValue);

private:
	void BuildRows(UCanvasPanel* Root);
	/** Re-reads every bound stat (derived stats such as entity.<id>.collected never broadcast OnStatChanged, so
	 *  pickup counters used to stay at "--" for the whole game). */
	void RefreshRows();
	void RefreshObjectives();
	void HandleBusEvent(const FGameForgeEvent& Event);
	void ShowEndScreen(bool bWon);
	UTextBlock* MakeText(const FName& Name, int32 Size, const FLinearColor& Color);

	UPROPERTY()
	TObjectPtr<UVerticalBox> RowBox;

	UPROPERTY()
	TObjectPtr<UTextBlock> MessageText;

	UPROPERTY()
	TObjectPtr<UTextBlock> QuestTrackerText;

	UPROPERTY()
	TObjectPtr<UTextBlock> DialogueText;

	/** Game title + objective shown for a few seconds at start. */
	UPROPERTY()
	TObjectPtr<UTextBlock> TitleCardText;

	UPROPERTY()
	TObjectPtr<UTextBlock> ObjectiveText;

	/** Persistent one-line objective / controls reminder (bottom of screen). */
	UPROPERTY()
	TObjectPtr<UTextBlock> HintText;

	UPROPERTY()
	TObjectPtr<UTextBlock> EndTitleText;

	UPROPERTY()
	TObjectPtr<UTextBlock> EndSubtitleText;

	UPROPERTY()
	TObjectPtr<UTextBlock> CrosshairText;

	TSharedPtr<FJsonObject> Def;
	FDelegateHandle BusHandle;
	FTimerHandle TitleCardHandle;
	FTimerHandle DialogueFadeHandle;
	bool bEndShown = false;

	struct FHudRow
	{
		FString Id;
		FString Kind;
		FName StatName;
		FString Label;
		float MaxValue = 100.f;
		TObjectPtr<UTextBlock> TextWidget;
		TObjectPtr<UProgressBar> BarWidget;
	};

	TArray<FHudRow> Rows;
	FTimerHandle TimerRefreshHandle;
	FTimerHandle MessageFadeHandle;
};

/**
 * Native Menu widget for Main Menu, Pause, and Game End screen (WI-5.10).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeMenuWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual TSharedRef<SWidget> RebuildWidget() override;

	void ShowMainMenu();
	void ShowPauseMenu();
	void ShowGameOver(bool bWon, const FString& Reason, float Score = 0.f);
	void ShowEndScreen(bool bWon, const FString& Reason, float Score = 0.f);

	/** Automation helper so scenarios bypass the main menu. */
	UFUNCTION(BlueprintCallable, Category = "GameForge")
	static void StartGameForScenario(UWorld* World);

private:
	UPROPERTY()
	TObjectPtr<UCanvasPanel> MenuRoot;

	UPROPERTY()
	TObjectPtr<UTextBlock> TitleText;

	UPROPERTY()
	TObjectPtr<UButton> PrimaryButton;

	UPROPERTY()
	TObjectPtr<UButton> SecondaryButton;
};

/**
 * Simple camera shake pattern for kit feedback (WI-5.10).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeCameraShake : public UCameraShakeBase
{
	GENERATED_BODY()
public:
	UGameForgeCameraShake(const FObjectInitializer& ObjectInitializer);
};

/**
 * World subsystem executing presentation feedback (VFX, SFX, shake, HUD message) (WI-5.10).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeFeedbackSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	void HandleEvent(const FGameForgeEvent& Event);

private:
	TSharedPtr<FJsonObject> Def;
};

/**
 * GameInstance subsystem handling persistent stats saving and loading (WI-5.11).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeSaveSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	void SaveGame();
	void LoadGame();

private:
	void HandleEvent(const FGameForgeEvent& Event);
	FString SaveSlotName;
};
