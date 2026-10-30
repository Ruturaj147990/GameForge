// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeWidgetLibrary.generated.h"

/** Counts real UButton::OnClicked broadcasts while a routed click is verified. */
UCLASS(Transient)
class GAMEFORGEEDITOR_API UGameForgeClickProbe : public UObject
{
	GENERATED_BODY()

public:
	int32 ClickCount = 0;

	UFUNCTION()
	void HandleClicked() { ++ClickCount; }
};

/**
 * Native C++ editor library providing genuine Unreal Engine 5.7.4 UMG Widget Blueprint authoring.
 * Manipulates real UWidgetBlueprint, UWidgetTree, UWidget, and UPanelSlot objects.
 * All operations return structured JSON strings.
 */
UCLASS()
class GAMEFORGEEDITOR_API UGameForgeWidgetLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Inspects an existing Widget Blueprint.
	 * Returns asset identity, parent class, generated class, compilation status, whether dirty, root widget, and widget count.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString InspectWidgetBlueprint(const FString& AssetPath);

	/**
	 * Reads back the entire widget hierarchy and property tree as JSON.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString ReadbackWidgetTree(const FString& AssetPath);

	/**
	 * Creates a new Widget Blueprint asset at AssetPath.
	 * Default ParentClass is "UserWidget", default RootWidgetClass is "CanvasPanel".
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString CreateWidgetBlueprint(const FString& AssetPath, const FString& ParentClassName = TEXT("UserWidget"), const FString& RootWidgetClassName = TEXT("CanvasPanel"));

	/**
	 * Creates a widget of the specified class (allowlisted) in the WidgetTree.
	 * If ParentName is specified, adds the widget as a child to that parent panel.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString CreateWidget(const FString& AssetPath, const FString& WidgetClassName, const FString& WidgetName, const FString& ParentName = TEXT(""));

	/**
	 * Sets visual or layout property on a widget (Text, Color, FontSize, Percent, FillColor, Visibility, WidthOverride, etc.).
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString SetWidgetProperty(const FString& AssetPath, const FString& WidgetName, const FString& PropertyName, const FString& ValueJson);

	/**
	 * Configures panel-specific slot properties (Position, Size, Anchors, Alignment, AutoSize, Padding, SizeRule, Alignment).
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString SetWidgetSlotProperty(const FString& AssetPath, const FString& WidgetName, const FString& SlotPropertiesJson);

	/**
	 * Safely removes a widget from its parent panel and from the widget tree.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString RemoveWidget(const FString& AssetPath, const FString& WidgetName);

	/**
	 * Compiles the Widget Blueprint using real engine compiler and returns diagnostics.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString CompileWidgetBlueprint(const FString& AssetPath);

	/**
	 * Saves the Widget Blueprint package to disk and verifies dirty state is cleared.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString SaveWidgetBlueprint(const FString& AssetPath);

	/**
	 * Instantiates the compiled Widget Blueprint in active PIE game world and adds to viewport.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString DisplayWidgetInGame(const FString& AssetPath, int32 ZOrder = 0);

	/**
	 * Binds an event on a widget (e.g. OnClicked on a Button) to an event handler in the Widget Blueprint event graph.
	 * Can optionally connect to a target action (e.g. CallFunction or PrintString).
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString BindWidgetEvent(const FString& AssetPath, const FString& WidgetName, const FString& DelegateName, const FString& ActionTypeJson = TEXT("{}"));

	/**
	 * Inspects event bindings and event graphs on a Widget Blueprint.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString InspectWidgetEvents(const FString& AssetPath);

	/**
	 * Triggers a button click in the active PIE game world on the specified button widget
	 * through real Slate input routing (calculates absolute screen geometry, checks hit-test eligibility,
	 * routes pointer move, pointer down, and pointer up events).
	 */
	/**
	 * Requests a capture of the active game viewport INCLUDING UMG/Slate UI (what the player sees).
	 * HighResShot / take_high_res_screenshot renders the camera only and never shows widgets.
	 * The file is written on the next rendered frame.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString CaptureViewportWithUI(const FString& OutputPath);

	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString TriggerButtonClick(const FString& AssetPath, const FString& ButtonName);

	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString TriggerButtonClickRealInput(const FString& AssetPath, const FString& ButtonName);

	/**
	 * Diagnostic tool: directly invokes target button's OnClicked delegate.
	 * Explicitly labeled as event-delegate diagnostic only; never proof of real UI hit-testing.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString TriggerButtonDelegateDiagnostic(const FString& AssetPath, const FString& ButtonName);

	/**
	 * Reads real runtime state of a displayed widget instance in the active PIE world.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|UMG")
	static FString GetWidgetRuntimeState(const FString& AssetPath);

	/**
	 * Reads real runtime gameplay state (health, max_health, stamina, max_stamina, menu_state) from active PIE world.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|Gameplay")
	static FString GetGameplayState();

	/**
	 * Modifies real runtime gameplay state in active PIE world (delta health, delta stamina, menu action) and broadcasts delegates.
	 */
	UFUNCTION(BlueprintCallable, Category="GameForge|Gameplay")
	static FString ModifyGameplayState(float DeltaHealth, float DeltaStamina, const FString& MenuAction = TEXT(""));
};

