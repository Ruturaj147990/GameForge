// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeBlueprintGraphLibrary.h"
#include "Engine/Blueprint.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Engine/SimpleConstructionScript.h"
#include "Engine/SCS_Node.h"
#include "FileHelpers.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Dom/JsonObject.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"

namespace GameForgeJsonHelpers
{
	static FString MakeEnvelope(bool bOk, const FString& Op, TSharedPtr<FJsonObject> Data, const TArray<FString>& Errors = {}, const TArray<FString>& Warnings = {})
	{
		TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
		Root->SetBoolField(TEXT("ok"), bOk);
		Root->SetStringField(TEXT("op"), Op);
		Root->SetObjectField(TEXT("data"), Data.IsValid() ? Data : MakeShared<FJsonObject>());

		TArray<TSharedPtr<FJsonValue>> ErrArr;
		for (const FString& E : Errors) { ErrArr.Add(MakeShared<FJsonValueString>(E)); }
		Root->SetArrayField(TEXT("errors"), ErrArr);

		TArray<TSharedPtr<FJsonValue>> WarnArr;
		for (const FString& W : Warnings) { WarnArr.Add(MakeShared<FJsonValueString>(W)); }
		Root->SetArrayField(TEXT("warnings"), WarnArr);

		FString OutputString;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
		FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
		return OutputString;
	}
}

UBlueprint* UGameForgeBlueprintGraphLibrary::ResolveBlueprint(const FString& BlueprintPath, FString& OutError)
{
	if (BlueprintPath.IsEmpty())
	{
		OutError = TEXT("Blueprint path is empty");
		return nullptr;
	}

	FString CleanPath = BlueprintPath;
	if (CleanPath.EndsWith(TEXT(".")))
	{
		CleanPath.LeftChopInline(1);
	}

	UBlueprint* BP = LoadObject<UBlueprint>(nullptr, *CleanPath);
	if (!BP)
	{
		// Attempt to load package directly
		UPackage* Pkg = LoadPackage(nullptr, *CleanPath, LOAD_None);
		if (Pkg)
		{
			FString AssetName = FPackageName::GetLongPackageAssetName(CleanPath);
			BP = FindObject<UBlueprint>(Pkg, *AssetName);
		}
	}

	if (!BP)
	{
		OutError = FString::Printf(TEXT("Blueprint asset not found at path: %s"), *BlueprintPath);
		return nullptr;
	}
	return BP;
}

UEdGraph* UGameForgeBlueprintGraphLibrary::ResolveGraph(UBlueprint* BP, const FString& GraphName, FString& OutError)
{
	if (!BP)
	{
		OutError = TEXT("Blueprint is null");
		return nullptr;
	}

	FString TargetName = GraphName.IsEmpty() ? TEXT("EventGraph") : GraphName;

	// Check UbergraphPages (Event Graphs)
	for (UEdGraph* Graph : BP->UbergraphPages)
	{
		if (Graph && (Graph->GetName().Equals(TargetName, ESearchCase::IgnoreCase) ||
		              Graph->GetFName().ToString().Equals(TargetName, ESearchCase::IgnoreCase)))
		{
			return Graph;
		}
	}

	// Check FunctionGraphs
	for (UEdGraph* Graph : BP->FunctionGraphs)
	{
		if (Graph && (Graph->GetName().Equals(TargetName, ESearchCase::IgnoreCase) ||
		              Graph->GetFName().ToString().Equals(TargetName, ESearchCase::IgnoreCase)))
		{
			return Graph;
		}
	}

	// Check MacroGraphs
	for (UEdGraph* Graph : BP->MacroGraphs)
	{
		if (Graph && (Graph->GetName().Equals(TargetName, ESearchCase::IgnoreCase) ||
		              Graph->GetFName().ToString().Equals(TargetName, ESearchCase::IgnoreCase)))
		{
			return Graph;
		}
	}

	// Fallback to FBlueprintEditorUtils helper
	if (TargetName.Equals(TEXT("EventGraph"), ESearchCase::IgnoreCase))
	{
		UEdGraph* EventGraph = FBlueprintEditorUtils::FindEventGraph(BP);
		if (EventGraph) return EventGraph;
	}

	OutError = FString::Printf(TEXT("Graph '%s' not found in Blueprint '%s'"), *TargetName, *BP->GetName());
	return nullptr;
}

UEdGraphNode* UGameForgeBlueprintGraphLibrary::ResolveNode(UEdGraph* Graph, const FString& NodeIdentifier, FString& OutError)
{
	if (!Graph)
	{
		OutError = TEXT("Graph is null");
		return nullptr;
	}
	if (NodeIdentifier.IsEmpty())
	{
		OutError = TEXT("Node identifier is empty");
		return nullptr;
	}

	FGuid SearchGuid;
	bool bIsGuid = FGuid::Parse(NodeIdentifier, SearchGuid);

	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (!Node) continue;

		if (bIsGuid && Node->NodeGuid == SearchGuid)
		{
			return Node;
		}
		if (Node->NodeGuid.ToString(EGuidFormats::DigitsWithHyphens).Equals(NodeIdentifier, ESearchCase::IgnoreCase) ||
		    Node->NodeGuid.ToString(EGuidFormats::Digits).Equals(NodeIdentifier, ESearchCase::IgnoreCase))
		{
			return Node;
		}
		if (Node->GetName().Equals(NodeIdentifier, ESearchCase::IgnoreCase))
		{
			return Node;
		}
		if (Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString().Equals(NodeIdentifier, ESearchCase::IgnoreCase))
		{
			return Node;
		}
		if (UK2Node_CallFunction* CallNode = Cast<UK2Node_CallFunction>(Node))
		{
			if (CallNode->FunctionReference.GetMemberName().ToString().Equals(NodeIdentifier, ESearchCase::IgnoreCase))
			{
				return Node;
			}
		}
		if (UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node))
		{
			if (EventNode->CustomFunctionName.ToString().Equals(NodeIdentifier, ESearchCase::IgnoreCase) ||
			    EventNode->EventReference.GetMemberName().ToString().Equals(NodeIdentifier, ESearchCase::IgnoreCase))
			{
				return Node;
			}
		}
	}

	OutError = FString::Printf(TEXT("Node '%s' not found in graph '%s'"), *NodeIdentifier, *Graph->GetName());
	return nullptr;
}

UEdGraphPin* UGameForgeBlueprintGraphLibrary::ResolvePin(UEdGraphNode* Node, const FString& PinName, FString& OutError)
{
	if (!Node)
	{
		OutError = TEXT("Node is null");
		return nullptr;
	}
	if (PinName.IsEmpty())
	{
		OutError = TEXT("Pin name is empty");
		return nullptr;
	}

	for (UEdGraphPin* Pin : Node->Pins)
	{
		if (!Pin) continue;
		if (Pin->PinName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
		{
			return Pin;
		}
		if (Pin->PinFriendlyName.ToString().Equals(PinName, ESearchCase::IgnoreCase))
		{
			return Pin;
		}
	}

	OutError = FString::Printf(TEXT("Pin '%s' not found on node '%s'"), *PinName, *Node->GetName());
	return nullptr;
}

// 1. blueprint_inspect
FString UGameForgeBlueprintGraphLibrary::InspectBlueprint(const FString& BlueprintPath)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_inspect"), nullptr, {Err});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("name"), BP->GetName());
	Data->SetStringField(TEXT("parent_class"), BP->ParentClass ? BP->ParentClass->GetName() : TEXT("None"));
	Data->SetStringField(TEXT("parent_class_path"), BP->ParentClass ? BP->ParentClass->GetPathName() : TEXT(""));

	// Graphs
	TArray<TSharedPtr<FJsonValue>> GraphsArr;
	for (UEdGraph* G : BP->UbergraphPages)
	{
		if (!G) continue;
		TSharedPtr<FJsonObject> GObj = MakeShared<FJsonObject>();
		GObj->SetStringField(TEXT("name"), G->GetName());
		GObj->SetStringField(TEXT("type"), TEXT("Ubergraph"));
		GObj->SetNumberField(TEXT("node_count"), G->Nodes.Num());
		GraphsArr.Add(MakeShared<FJsonValueObject>(GObj));
	}
	for (UEdGraph* G : BP->FunctionGraphs)
	{
		if (!G) continue;
		TSharedPtr<FJsonObject> GObj = MakeShared<FJsonObject>();
		GObj->SetStringField(TEXT("name"), G->GetName());
		GObj->SetStringField(TEXT("type"), TEXT("Function"));
		GObj->SetNumberField(TEXT("node_count"), G->Nodes.Num());
		GraphsArr.Add(MakeShared<FJsonValueObject>(GObj));
	}
	Data->SetArrayField(TEXT("graphs"), GraphsArr);

	// Variables
	TArray<TSharedPtr<FJsonValue>> VarsArr;
	for (const FBPVariableDescription& Var : BP->NewVariables)
	{
		TSharedPtr<FJsonObject> VObj = MakeShared<FJsonObject>();
		VObj->SetStringField(TEXT("name"), Var.VarName.ToString());
		VObj->SetStringField(TEXT("category"), Var.VarType.PinCategory.ToString());
		VObj->SetStringField(TEXT("sub_category"), Var.VarType.PinSubCategory.ToString());
		VarsArr.Add(MakeShared<FJsonValueObject>(VObj));
	}
	Data->SetArrayField(TEXT("variables"), VarsArr);

	// Components
	TArray<TSharedPtr<FJsonValue>> CompsArr;
	if (BP->SimpleConstructionScript)
	{
		for (USCS_Node* ScsNode : BP->SimpleConstructionScript->GetAllNodes())
		{
			if (!ScsNode) continue;
			TSharedPtr<FJsonObject> CObj = MakeShared<FJsonObject>();
			CObj->SetStringField(TEXT("name"), ScsNode->GetVariableName().ToString());
			CObj->SetStringField(TEXT("class"), ScsNode->ComponentClass ? ScsNode->ComponentClass->GetName() : TEXT("None"));
			CompsArr.Add(MakeShared<FJsonValueObject>(CObj));
		}
	}
	Data->SetArrayField(TEXT("components"), CompsArr);

	// Status
	FString StatusStr = TEXT("Unknown");
	switch (BP->Status)
	{
		case BS_UpToDate: StatusStr = TEXT("UpToDate"); break;
		case BS_Dirty: StatusStr = TEXT("Dirty"); break;
		case BS_Error: StatusStr = TEXT("Error"); break;
		case BS_UpToDateWithWarnings: StatusStr = TEXT("UpToDateWithWarnings"); break;
		case BS_BeingCreated: StatusStr = TEXT("BeingCreated"); break;
		default: break;
	}
	Data->SetStringField(TEXT("status"), StatusStr);
	Data->SetBoolField(TEXT("is_up_to_date"), BP->Status == BS_UpToDate || BP->Status == BS_UpToDateWithWarnings);
	Data->SetBoolField(TEXT("has_errors"), BP->Status == BS_Error);

	return GameForgeJsonHelpers::MakeEnvelope(true, TEXT("blueprint_inspect"), Data);
}

// 2. blueprint_readback_graph
FString UGameForgeBlueprintGraphLibrary::ReadbackGraph(const FString& BlueprintPath, const FString& GraphName)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_readback_graph"), nullptr, {Err});
	}

	UEdGraph* Graph = ResolveGraph(BP, GraphName, Err);
	if (!Graph)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_readback_graph"), nullptr, {Err});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("graph_name"), Graph->GetName());
	Data->SetNumberField(TEXT("node_count"), Graph->Nodes.Num());

	TArray<TSharedPtr<FJsonValue>> NodesArr;
	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (!Node) continue;

		TSharedPtr<FJsonObject> NObj = MakeShared<FJsonObject>();
		NObj->SetStringField(TEXT("node_id"), Node->NodeGuid.ToString(EGuidFormats::DigitsWithHyphens));
		NObj->SetStringField(TEXT("node_name"), Node->GetName());
		NObj->SetStringField(TEXT("node_class"), Node->GetClass()->GetName());
		NObj->SetStringField(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
		NObj->SetNumberField(TEXT("pos_x"), Node->NodePosX);
		NObj->SetNumberField(TEXT("pos_y"), Node->NodePosY);

		if (UK2Node_CallFunction* CallNode = Cast<UK2Node_CallFunction>(Node))
		{
			NObj->SetStringField(TEXT("function_name"), CallNode->FunctionReference.GetMemberName().ToString());
			if (UClass* MemberClass = CallNode->FunctionReference.GetMemberParentClass())
			{
				NObj->SetStringField(TEXT("function_class"), MemberClass->GetName());
			}
		}
		else if (UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node))
		{
			NObj->SetStringField(TEXT("event_name"), EventNode->CustomFunctionName.IsNone() ?
				EventNode->EventReference.GetMemberName().ToString() : EventNode->CustomFunctionName.ToString());
		}

		// Pins
		TArray<TSharedPtr<FJsonValue>> PinsArr;
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (!Pin) continue;

			TSharedPtr<FJsonObject> PObj = MakeShared<FJsonObject>();
			PObj->SetStringField(TEXT("pin_name"), Pin->PinName.ToString());
			PObj->SetStringField(TEXT("direction"), Pin->Direction == EGPD_Input ? TEXT("EGPD_Input") : TEXT("EGPD_Output"));
			PObj->SetStringField(TEXT("category"), Pin->PinType.PinCategory.ToString());
			PObj->SetStringField(TEXT("sub_category"), Pin->PinType.PinSubCategory.ToString());
			PObj->SetStringField(TEXT("default_value"), Pin->GetDefaultAsString());
			PObj->SetBoolField(TEXT("is_linked"), Pin->LinkedTo.Num() > 0);

			TArray<TSharedPtr<FJsonValue>> LinkedArr;
			for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
			{
				if (!LinkedPin || !LinkedPin->GetOwningNode()) continue;
				TSharedPtr<FJsonObject> LObj = MakeShared<FJsonObject>();
				LObj->SetStringField(TEXT("target_node_id"), LinkedPin->GetOwningNode()->NodeGuid.ToString(EGuidFormats::DigitsWithHyphens));
				LObj->SetStringField(TEXT("target_node_title"), LinkedPin->GetOwningNode()->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
				LObj->SetStringField(TEXT("target_pin_name"), LinkedPin->PinName.ToString());
				LinkedArr.Add(MakeShared<FJsonValueObject>(LObj));
			}
			PObj->SetArrayField(TEXT("linked_to"), LinkedArr);

			PinsArr.Add(MakeShared<FJsonValueObject>(PObj));
		}
		NObj->SetArrayField(TEXT("pins"), PinsArr);

		NodesArr.Add(MakeShared<FJsonValueObject>(NObj));
	}
	Data->SetArrayField(TEXT("nodes"), NodesArr);

	return GameForgeJsonHelpers::MakeEnvelope(true, TEXT("blueprint_readback_graph"), Data);
}

// 3. blueprint_create_node
FString UGameForgeBlueprintGraphLibrary::CreateNode(const FString& BlueprintPath, const FString& GraphName, const FString& NodeType, int32 PosX, int32 PosY, const FString& ExtraParamsJson)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_create_node"), nullptr, {Err});
	}

	UEdGraph* Graph = ResolveGraph(BP, GraphName, Err);
	if (!Graph)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_create_node"), nullptr, {Err});
	}

	TSharedPtr<FJsonObject> ExtraParams;
	if (!ExtraParamsJson.IsEmpty())
	{
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ExtraParamsJson);
		FJsonSerializer::Deserialize(Reader, ExtraParams);
	}
	if (!ExtraParams.IsValid())
	{
		ExtraParams = MakeShared<FJsonObject>();
	}

	FScopedTransaction Transaction(NSLOCTEXT("GameForge", "CreateNode", "GameForge: Create Blueprint Node"));
	BP->Modify();
	Graph->Modify();

	UEdGraphNode* NewNode = nullptr;

	if (NodeType.Equals(TEXT("CallFunction"), ESearchCase::IgnoreCase) || NodeType.Equals(TEXT("K2Node_CallFunction"), ESearchCase::IgnoreCase))
	{
		FString FunctionName = ExtraParams->GetStringField(TEXT("function_name"));
		if (FunctionName.IsEmpty())
		{
			return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_create_node"), nullptr, {TEXT("ExtraParams 'function_name' is required for CallFunction node")});
		}

		FString FunctionClassStr = ExtraParams->GetStringField(TEXT("function_class"));
		UClass* TargetFunctionClass = UKismetSystemLibrary::StaticClass();
		if (!FunctionClassStr.IsEmpty())
		{
			UClass* FoundClass = LoadClass<UObject>(nullptr, *FunctionClassStr);
			if (FoundClass)
			{
				TargetFunctionClass = FoundClass;
			}
		}

		UK2Node_CallFunction* CallNode = NewObject<UK2Node_CallFunction>(Graph);
		CallNode->FunctionReference.SetExternalMember(FName(*FunctionName), TargetFunctionClass);
		CallNode->NodePosX = PosX;
		CallNode->NodePosY = PosY;
		CallNode->CreateNewGuid();
		CallNode->PostPlacedNewNode();
		CallNode->AllocateDefaultPins();
		Graph->AddNode(CallNode, true, true);
		NewNode = CallNode;
	}
	else if (NodeType.Equals(TEXT("Event"), ESearchCase::IgnoreCase) || NodeType.Equals(TEXT("K2Node_Event"), ESearchCase::IgnoreCase))
	{
		FString EventName = ExtraParams->GetStringField(TEXT("event_name"));
		if (EventName.IsEmpty())
		{
			EventName = TEXT("ReceiveBeginPlay");
		}

		// First check if this event node already exists in graph
		for (UEdGraphNode* ExistingNode : Graph->Nodes)
		{
			if (UK2Node_Event* Ev = Cast<UK2Node_Event>(ExistingNode))
			{
				if (Ev->EventReference.GetMemberName().ToString().Equals(EventName, ESearchCase::IgnoreCase) ||
				    Ev->CustomFunctionName.ToString().Equals(EventName, ESearchCase::IgnoreCase))
				{
					// Found existing event node; update pos and return it
					Ev->NodePosX = PosX;
					Ev->NodePosY = PosY;
					NewNode = Ev;
					break;
				}
			}
		}

		if (!NewNode)
		{
			UK2Node_Event* EventNode = NewObject<UK2Node_Event>(Graph);
			UClass* ParentCls = BP->ParentClass ? BP->ParentClass.Get() : AActor::StaticClass();
			EventNode->EventReference.SetExternalMember(FName(*EventName), ParentCls);
			EventNode->bOverrideFunction = true;
			EventNode->NodePosX = PosX;
			EventNode->NodePosY = PosY;
			EventNode->CreateNewGuid();
			EventNode->PostPlacedNewNode();
			EventNode->AllocateDefaultPins();
			Graph->AddNode(EventNode, true, true);
			NewNode = EventNode;
		}
	}
	else if (NodeType.Equals(TEXT("VariableGet"), ESearchCase::IgnoreCase))
	{
		FString VarName = ExtraParams->GetStringField(TEXT("variable_name"));
		UK2Node_VariableGet* GetNode = NewObject<UK2Node_VariableGet>(Graph);
		GetNode->VariableReference.SetSelfMember(FName(*VarName));
		GetNode->NodePosX = PosX;
		GetNode->NodePosY = PosY;
		GetNode->CreateNewGuid();
		GetNode->PostPlacedNewNode();
		GetNode->AllocateDefaultPins();
		Graph->AddNode(GetNode, true, true);
		NewNode = GetNode;
	}
	else
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_create_node"), nullptr,
			{FString::Printf(TEXT("Unsupported node type: %s. Supported: CallFunction, Event, VariableGet"), *NodeType)});
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("graph_name"), Graph->GetName());
	Data->SetStringField(TEXT("node_id"), NewNode->NodeGuid.ToString(EGuidFormats::DigitsWithHyphens));
	Data->SetStringField(TEXT("node_name"), NewNode->GetName());
	Data->SetStringField(TEXT("node_class"), NewNode->GetClass()->GetName());
	Data->SetStringField(TEXT("title"), NewNode->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
	Data->SetNumberField(TEXT("pos_x"), NewNode->NodePosX);
	Data->SetNumberField(TEXT("pos_y"), NewNode->NodePosY);

	TArray<TSharedPtr<FJsonValue>> PinsArr;
	for (UEdGraphPin* P : NewNode->Pins)
	{
		if (!P) continue;
		TSharedPtr<FJsonObject> PObj = MakeShared<FJsonObject>();
		PObj->SetStringField(TEXT("pin_name"), P->PinName.ToString());
		PObj->SetStringField(TEXT("direction"), P->Direction == EGPD_Input ? TEXT("EGPD_Input") : TEXT("EGPD_Output"));
		PObj->SetStringField(TEXT("category"), P->PinType.PinCategory.ToString());
		PinsArr.Add(MakeShared<FJsonValueObject>(PObj));
	}
	Data->SetArrayField(TEXT("pins"), PinsArr);

	return GameForgeJsonHelpers::MakeEnvelope(true, TEXT("blueprint_create_node"), Data);
}

// 4. blueprint_set_pin_default
FString UGameForgeBlueprintGraphLibrary::SetPinDefault(const FString& BlueprintPath, const FString& NodeId, const FString& PinName, const FString& DefaultValue)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_set_pin_default"), nullptr, {Err});
	}

	UEdGraph* Graph = FBlueprintEditorUtils::FindEventGraph(BP);
	if (!Graph && BP->UbergraphPages.Num() > 0) Graph = BP->UbergraphPages[0];
	if (!Graph)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_set_pin_default"), nullptr, {TEXT("No graph found in Blueprint")});
	}

	UEdGraphNode* Node = ResolveNode(Graph, NodeId, Err);
	if (!Node)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_set_pin_default"), nullptr, {Err});
	}

	UEdGraphPin* Pin = ResolvePin(Node, PinName, Err);
	if (!Pin)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_set_pin_default"), nullptr, {Err});
	}

	if (Pin->Direction != EGPD_Input)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_set_pin_default"), nullptr,
			{FString::Printf(TEXT("Pin '%s' is an output pin and cannot have a default value"), *PinName)});
	}

	if (Pin->LinkedTo.Num() > 0)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_set_pin_default"), nullptr,
			{FString::Printf(TEXT("Pin '%s' is connected to another pin and default value would be ignored"), *PinName)});
	}

	FScopedTransaction Transaction(NSLOCTEXT("GameForge", "SetPinDefault", "GameForge: Set Pin Default Value"));
	BP->Modify();
	Node->Modify();

	const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
	Schema->TrySetDefaultValue(*Pin, DefaultValue);

	FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

	FString ResultValue = Pin->GetDefaultAsString();

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("node_id"), Node->NodeGuid.ToString(EGuidFormats::DigitsWithHyphens));
	Data->SetStringField(TEXT("pin_name"), Pin->PinName.ToString());
	Data->SetStringField(TEXT("requested_value"), DefaultValue);
	Data->SetStringField(TEXT("readback_value"), ResultValue);
	Data->SetBoolField(TEXT("matches"), ResultValue.Equals(DefaultValue, ESearchCase::CaseSensitive) ||
	                                    ResultValue.Replace(TEXT("\""), TEXT("")).Equals(DefaultValue, ESearchCase::CaseSensitive));

	return GameForgeJsonHelpers::MakeEnvelope(true, TEXT("blueprint_set_pin_default"), Data);
}

// 5. blueprint_connect_pins
FString UGameForgeBlueprintGraphLibrary::ConnectPins(const FString& BlueprintPath, const FString& FromNodeId, const FString& FromPinName, const FString& ToNodeId, const FString& ToPinName)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr, {Err});
	}

	UEdGraph* Graph = FBlueprintEditorUtils::FindEventGraph(BP);
	if (!Graph && BP->UbergraphPages.Num() > 0) Graph = BP->UbergraphPages[0];
	if (!Graph)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr, {TEXT("No graph found in Blueprint")});
	}

	UEdGraphNode* FromNode = ResolveNode(Graph, FromNodeId, Err);
	if (!FromNode)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr, {FString::Printf(TEXT("FromNode: %s"), *Err)});
	}

	UEdGraphNode* ToNode = ResolveNode(Graph, ToNodeId, Err);
	if (!ToNode)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr, {FString::Printf(TEXT("ToNode: %s"), *Err)});
	}

	UEdGraphPin* FromPin = ResolvePin(FromNode, FromPinName, Err);
	if (!FromPin)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr, {FString::Printf(TEXT("FromPin: %s"), *Err)});
	}

	UEdGraphPin* ToPin = ResolvePin(ToNode, ToPinName, Err);
	if (!ToPin)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr, {FString::Printf(TEXT("ToPin: %s"), *Err)});
	}

	// Validation
	if (FromPin->Direction == ToPin->Direction)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr,
			{FString::Printf(TEXT("Cannot connect pins of same direction: both are %s"),
				FromPin->Direction == EGPD_Input ? TEXT("Input") : TEXT("Output"))});
	}

	// Schema connection
	FScopedTransaction Transaction(NSLOCTEXT("GameForge", "ConnectPins", "GameForge: Connect Blueprint Pins"));
	BP->Modify();
	FromNode->Modify();
	ToNode->Modify();

	const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();
	bool bConnected = Schema->TryCreateConnection(FromPin, ToPin);

	if (!bConnected)
	{
		// Attempt reverse if direction was backwards
		bConnected = Schema->TryCreateConnection(ToPin, FromPin);
	}

	if (!bConnected)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_connect_pins"), nullptr,
			{FString::Printf(TEXT("Schema rejected connection between '%s.%s' (%s) and '%s.%s' (%s)"),
				*FromNode->GetName(), *FromPinName, *FromPin->PinType.PinCategory.ToString(),
				*ToNode->GetName(), *ToPinName, *ToPin->PinType.PinCategory.ToString())});
	}

	Graph->NotifyGraphChanged();
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

	// Verify connection
	bool bVerified = FromPin->LinkedTo.Contains(ToPin) || ToPin->LinkedTo.Contains(FromPin);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("from_node"), FromNode->GetName());
	Data->SetStringField(TEXT("from_pin"), FromPin->PinName.ToString());
	Data->SetStringField(TEXT("to_node"), ToNode->GetName());
	Data->SetStringField(TEXT("to_pin"), ToPin->PinName.ToString());
	Data->SetBoolField(TEXT("verified_linked"), bVerified);

	return GameForgeJsonHelpers::MakeEnvelope(bVerified, TEXT("blueprint_connect_pins"), Data,
		bVerified ? TArray<FString>() : TArray<FString>{TEXT("Connection reported true by schema but readback link check failed")});
}

// 6. blueprint_disconnect_pins
FString UGameForgeBlueprintGraphLibrary::DisconnectPins(const FString& BlueprintPath, const FString& FromNodeId, const FString& FromPinName, const FString& ToNodeId, const FString& ToPinName)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_disconnect_pins"), nullptr, {Err});
	}

	UEdGraph* Graph = FBlueprintEditorUtils::FindEventGraph(BP);
	if (!Graph && BP->UbergraphPages.Num() > 0) Graph = BP->UbergraphPages[0];
	if (!Graph)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_disconnect_pins"), nullptr, {TEXT("No graph found in Blueprint")});
	}

	UEdGraphNode* FromNode = ResolveNode(Graph, FromNodeId, Err);
	if (!FromNode)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_disconnect_pins"), nullptr, {FString::Printf(TEXT("FromNode: %s"), *Err)});
	}

	UEdGraphPin* FromPin = ResolvePin(FromNode, FromPinName, Err);
	if (!FromPin)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_disconnect_pins"), nullptr, {FString::Printf(TEXT("FromPin: %s"), *Err)});
	}

	FScopedTransaction Transaction(NSLOCTEXT("GameForge", "DisconnectPins", "GameForge: Disconnect Blueprint Pins"));
	BP->Modify();
	FromNode->Modify();

	const UEdGraphSchema_K2* Schema = GetDefault<UEdGraphSchema_K2>();

	if (!ToNodeId.IsEmpty() && !ToPinName.IsEmpty())
	{
		UEdGraphNode* ToNode = ResolveNode(Graph, ToNodeId, Err);
		if (!ToNode)
		{
			return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_disconnect_pins"), nullptr, {FString::Printf(TEXT("ToNode: %s"), *Err)});
		}
		UEdGraphPin* ToPin = ResolvePin(ToNode, ToPinName, Err);
		if (!ToPin)
		{
			return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_disconnect_pins"), nullptr, {FString::Printf(TEXT("ToPin: %s"), *Err)});
		}
		ToNode->Modify();
		Schema->BreakSinglePinLink(FromPin, ToPin);
	}
	else
	{
		// Break all links on FromPin
		Schema->BreakPinLinks(*FromPin, true);
	}

	Graph->NotifyGraphChanged();
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("node"), FromNode->GetName());
	Data->SetStringField(TEXT("pin"), FromPin->PinName.ToString());
	Data->SetNumberField(TEXT("remaining_links"), FromPin->LinkedTo.Num());

	return GameForgeJsonHelpers::MakeEnvelope(true, TEXT("blueprint_disconnect_pins"), Data);
}

// 7. blueprint_delete_node
FString UGameForgeBlueprintGraphLibrary::DeleteNode(const FString& BlueprintPath, const FString& NodeId)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_delete_node"), nullptr, {Err});
	}

	UEdGraph* Graph = FBlueprintEditorUtils::FindEventGraph(BP);
	if (!Graph && BP->UbergraphPages.Num() > 0) Graph = BP->UbergraphPages[0];
	if (!Graph)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_delete_node"), nullptr, {TEXT("No graph found in Blueprint")});
	}

	UEdGraphNode* Node = ResolveNode(Graph, NodeId, Err);
	if (!Node)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_delete_node"), nullptr, {Err});
	}

	FString NodeTitle = Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString();
	FString NodeName = Node->GetName();

	FScopedTransaction Transaction(NSLOCTEXT("GameForge", "DeleteNode", "GameForge: Delete Blueprint Node"));
	BP->Modify();
	Graph->Modify();

	FBlueprintEditorUtils::RemoveNode(BP, Node, true);
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("deleted_node_id"), NodeId);
	Data->SetStringField(TEXT("deleted_node_name"), NodeName);
	Data->SetStringField(TEXT("deleted_node_title"), NodeTitle);

	return GameForgeJsonHelpers::MakeEnvelope(true, TEXT("blueprint_delete_node"), Data);
}

// 8. blueprint_compile
FString UGameForgeBlueprintGraphLibrary::CompileBlueprint(const FString& BlueprintPath)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_compile"), nullptr, {Err});
	}

	FKismetEditorUtilities::CompileBlueprint(BP);

	bool bSuccess = (BP->Status == BS_UpToDate || BP->Status == BS_UpToDateWithWarnings);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);

	FString StatusStr = TEXT("Unknown");
	switch (BP->Status)
	{
		case BS_UpToDate: StatusStr = TEXT("UpToDate"); break;
		case BS_Dirty: StatusStr = TEXT("Dirty"); break;
		case BS_Error: StatusStr = TEXT("Error"); break;
		case BS_UpToDateWithWarnings: StatusStr = TEXT("UpToDateWithWarnings"); break;
		case BS_BeingCreated: StatusStr = TEXT("BeingCreated"); break;
		default: break;
	}
	Data->SetStringField(TEXT("status"), StatusStr);
	Data->SetBoolField(TEXT("compiled_successfully"), bSuccess);
	Data->SetStringField(TEXT("generated_class"), BP->GeneratedClass ? BP->GeneratedClass->GetPathName() : TEXT("None"));

	TArray<FString> CompileErrors;
	if (BP->Status == BS_Error)
	{
		CompileErrors.Add(TEXT("Blueprint compilation failed with error state BS_Error"));
	}

	return GameForgeJsonHelpers::MakeEnvelope(bSuccess, TEXT("blueprint_compile"), Data, CompileErrors);
}

// 9. blueprint_save
FString UGameForgeBlueprintGraphLibrary::SaveBlueprint(const FString& BlueprintPath)
{
	FString Err;
	UBlueprint* BP = ResolveBlueprint(BlueprintPath, Err);
	if (!BP)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_save"), nullptr, {Err});
	}

	UPackage* Package = BP->GetOutermost();
	if (!Package)
	{
		return GameForgeJsonHelpers::MakeEnvelope(false, TEXT("blueprint_save"), nullptr, {TEXT("Blueprint outer package is null")});
	}

	TArray<UPackage*> PackagesToSave = { Package };
	bool bSaved = UEditorLoadingAndSavingUtils::SavePackages(PackagesToSave, true);

	bool bIsDirty = Package->IsDirty();

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BlueprintPath);
	Data->SetStringField(TEXT("package_name"), Package->GetName());
	Data->SetBoolField(TEXT("saved"), bSaved);
	Data->SetBoolField(TEXT("is_dirty"), bIsDirty);

	return GameForgeJsonHelpers::MakeEnvelope(bSaved && !bIsDirty, TEXT("blueprint_save"), Data,
		(!bSaved || bIsDirty) ? TArray<FString>{TEXT("SavePackages failed or package remains dirty")} : TArray<FString>());
}
