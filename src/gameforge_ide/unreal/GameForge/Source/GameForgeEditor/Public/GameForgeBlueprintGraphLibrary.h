// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeBlueprintGraphLibrary.generated.h"

class UBlueprint;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;

/**
 * GameForge Native Blueprint Graph Authoring Library.
 * Directly interfaces with Unreal Engine 5.7 Kismet2, BlueprintGraph, and UEdGraphSchema_K2.
 */
UCLASS()
class GAMEFORGEEDITOR_API UGameForgeBlueprintGraphLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Inspects an existing Blueprint asset and returns its metadata, parent class, graphs, variables, and status.
	 * @param BlueprintPath Path to the Blueprint asset (e.g. "/Game/BP_Actor")
	 * @return JSON-encoded string with inspection details
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString InspectBlueprint(const FString& BlueprintPath);

	/**
	 * Reads back nodes and pins from an existing graph.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @param GraphName Name of the graph (defaults to "EventGraph")
	 * @return JSON-encoded string with nodes, pins, and connections
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString ReadbackGraph(const FString& BlueprintPath, const FString& GraphName = TEXT("EventGraph"));

	/**
	 * Creates a supported node in an existing graph.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @param GraphName Name of the graph to place node into
	 * @param NodeType Node type ("CallFunction", "Event", "VariableGet", "VariableSet")
	 * @param PosX Graph X position
	 * @param PosY Graph Y position
	 * @param ExtraParamsJson JSON string with node-specific parameters (e.g. function_name, function_class, event_name)
	 * @return JSON-encoded string with created node details
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString CreateNode(const FString& BlueprintPath, const FString& GraphName, const FString& NodeType, int32 PosX, int32 PosY, const FString& ExtraParamsJson);

	/**
	 * Sets a default literal value on a pin and reads back the resulting value.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @param NodeId Node GUID, name, or title
	 * @param PinName Pin identifier name
	 * @param DefaultValue String representation of the default value
	 * @return JSON-encoded string with operation outcome and readback value
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString SetPinDefault(const FString& BlueprintPath, const FString& NodeId, const FString& PinName, const FString& DefaultValue);

	/**
	 * Connects two pins in a graph using UEdGraphSchema_K2 validation.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @param FromNodeId Source node identifier
	 * @param FromPinName Source pin name
	 * @param ToNodeId Target node identifier
	 * @param ToPinName Target pin name
	 * @return JSON-encoded string with connection outcome
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString ConnectPins(const FString& BlueprintPath, const FString& FromNodeId, const FString& FromPinName, const FString& ToNodeId, const FString& ToPinName);

	/**
	 * Disconnects a pin or severs a specific link between two pins.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @param FromNodeId Source node identifier
	 * @param FromPinName Source pin name
	 * @param ToNodeId Optional target node identifier
	 * @param ToPinName Optional target pin name
	 * @return JSON-encoded string with outcome
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString DisconnectPins(const FString& BlueprintPath, const FString& FromNodeId, const FString& FromPinName, const FString& ToNodeId = TEXT(""), const FString& ToPinName = TEXT(""));

	/**
	 * Deletes a node from a graph using FBlueprintEditorUtils.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @param NodeId Node GUID, name, or title
	 * @return JSON-encoded string with outcome
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString DeleteNode(const FString& BlueprintPath, const FString& NodeId);

	/**
	 * Compiles the Blueprint and gathers compiler status and diagnostics.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @return JSON-encoded string with compilation diagnostics
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString CompileBlueprint(const FString& BlueprintPath);

	/**
	 * Saves the modified Blueprint package to disk.
	 * @param BlueprintPath Path to the Blueprint asset
	 * @return JSON-encoded string with save outcome
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Blueprint")
	static FString SaveBlueprint(const FString& BlueprintPath);

private:
	static UBlueprint* ResolveBlueprint(const FString& BlueprintPath, FString& OutError);
	static UEdGraph* ResolveGraph(UBlueprint* BP, const FString& GraphName, FString& OutError);
	static UEdGraphNode* ResolveNode(UEdGraph* Graph, const FString& NodeIdentifier, FString& OutError);
	static UEdGraphPin* ResolvePin(UEdGraphNode* Node, const FString& PinName, FString& OutError);
};
