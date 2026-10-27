// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeWidgetLibrary.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Blueprint/UserWidget.h"
#include "Components/Widget.h"
#include "Components/PanelWidget.h"
#include "Components/PanelSlot.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/SizeBox.h"
#include "Components/SizeBoxSlot.h"
#include "Components/TextBlock.h"
#include "Components/Image.h"
#include "Components/ProgressBar.h"
#include "Components/Button.h"
#include "Components/ButtonSlot.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_CallFunction.h"
#include "EdGraphSchema_K2.h"
#include "Kismet/KismetSystemLibrary.h"
#include "GameForgeGameplayStateComponent.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "FileHelpers.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Dom/JsonObject.h"
#include "Editor.h"
#include "Engine/World.h"
#include "Engine/Engine.h"

namespace
{
	FString MakeJsonString(TSharedPtr<FJsonObject> JsonObj)
	{
		FString Output;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
		FJsonSerializer::Serialize(JsonObj.ToSharedRef(), Writer);
		return Output;
	}

	FString MakeEnvelope(bool bSuccess, TSharedPtr<FJsonObject> Data, const TArray<FString>& Errors = {}, const TArray<FString>& Warnings = {})
	{
		TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
		Root->SetBoolField(TEXT("success"), bSuccess);

		if (Data.IsValid())
		{
			Root->SetObjectField(TEXT("data"), Data);
		}
		else
		{
			Root->SetObjectField(TEXT("data"), MakeShared<FJsonObject>());
		}

		TArray<TSharedPtr<FJsonValue>> ErrVals;
		for (const FString& Err : Errors)
		{
			ErrVals.Add(MakeShared<FJsonValueString>(Err));
		}
		Root->SetArrayField(TEXT("errors"), ErrVals);

		TArray<TSharedPtr<FJsonValue>> WarnVals;
		for (const FString& Warn : Warnings)
		{
			WarnVals.Add(MakeShared<FJsonValueString>(Warn));
		}
		Root->SetArrayField(TEXT("warnings"), WarnVals);

		return MakeJsonString(Root);
	}

	UWidgetBlueprint* ResolveWidgetBlueprint(const FString& AssetPath, FString& OutError)
	{
		if (AssetPath.IsEmpty())
		{
			OutError = TEXT("Asset path cannot be empty.");
			return nullptr;
		}

		FString ObjectPath = AssetPath;
		if (!ObjectPath.Contains(TEXT(".")))
		{
			FString AssetName = FPaths::GetBaseFilename(AssetPath);
			ObjectPath = FString::Printf(TEXT("%s.%s"), *AssetPath, *AssetName);
		}

		UObject* LoadedObj = StaticLoadObject(UWidgetBlueprint::StaticClass(), nullptr, *ObjectPath);
		if (!LoadedObj)
		{
			OutError = FString::Printf(TEXT("Failed to load WidgetBlueprint at '%s'."), *ObjectPath);
			return nullptr;
		}

		UWidgetBlueprint* BP = Cast<UWidgetBlueprint>(LoadedObj);
		if (!BP)
		{
			OutError = FString::Printf(TEXT("Asset at '%s' is not a UWidgetBlueprint (class: %s)."), *ObjectPath, *LoadedObj->GetClass()->GetName());
			return nullptr;
		}

		return BP;
	}

	UClass* GetSupportedWidgetClass(const FString& ClassName, FString& OutError)
	{
		FString Norm = ClassName.TrimStartAndEnd();
		if (Norm.StartsWith(TEXT("U")))
		{
			Norm = Norm.RightChop(1);
		}

		if (Norm.Equals(TEXT("CanvasPanel"), ESearchCase::IgnoreCase)) return UCanvasPanel::StaticClass();
		if (Norm.Equals(TEXT("VerticalBox"), ESearchCase::IgnoreCase)) return UVerticalBox::StaticClass();
		if (Norm.Equals(TEXT("HorizontalBox"), ESearchCase::IgnoreCase)) return UHorizontalBox::StaticClass();
		if (Norm.Equals(TEXT("Overlay"), ESearchCase::IgnoreCase)) return UOverlay::StaticClass();
		if (Norm.Equals(TEXT("SizeBox"), ESearchCase::IgnoreCase)) return USizeBox::StaticClass();
		if (Norm.Equals(TEXT("TextBlock"), ESearchCase::IgnoreCase)) return UTextBlock::StaticClass();
		if (Norm.Equals(TEXT("Image"), ESearchCase::IgnoreCase)) return UImage::StaticClass();
		if (Norm.Equals(TEXT("ProgressBar"), ESearchCase::IgnoreCase)) return UProgressBar::StaticClass();
		if (Norm.Equals(TEXT("Button"), ESearchCase::IgnoreCase)) return UButton::StaticClass();

		OutError = FString::Printf(TEXT("Unsupported widget class '%s'. Supported: CanvasPanel, VerticalBox, HorizontalBox, Overlay, SizeBox, TextBlock, Image, ProgressBar, Button."), *ClassName);
		return nullptr;
	}

	FString VisibilityToString(ESlateVisibility Vis)
	{
		switch (Vis)
		{
		case ESlateVisibility::Visible: return TEXT("Visible");
		case ESlateVisibility::Collapsed: return TEXT("Collapsed");
		case ESlateVisibility::Hidden: return TEXT("Hidden");
		case ESlateVisibility::HitTestInvisible: return TEXT("HitTestInvisible");
		case ESlateVisibility::SelfHitTestInvisible: return TEXT("SelfHitTestInvisible");
		default: return TEXT("Visible");
		}
	}

	ESlateVisibility StringToVisibility(const FString& Str)
	{
		if (Str.Equals(TEXT("Collapsed"), ESearchCase::IgnoreCase)) return ESlateVisibility::Collapsed;
		if (Str.Equals(TEXT("Hidden"), ESearchCase::IgnoreCase)) return ESlateVisibility::Hidden;
		if (Str.Equals(TEXT("HitTestInvisible"), ESearchCase::IgnoreCase)) return ESlateVisibility::HitTestInvisible;
		if (Str.Equals(TEXT("SelfHitTestInvisible"), ESearchCase::IgnoreCase)) return ESlateVisibility::SelfHitTestInvisible;
		return ESlateVisibility::Visible;
	}

	TSharedPtr<FJsonObject> SerializeSlot(UPanelSlot* Slot)
	{
		if (!Slot) return nullptr;

		TSharedPtr<FJsonObject> SlotObj = MakeShared<FJsonObject>();
		SlotObj->SetStringField(TEXT("slot_class"), Slot->GetClass()->GetName());

		if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Slot))
		{
			TSharedPtr<FJsonObject> PosObj = MakeShared<FJsonObject>();
			PosObj->SetNumberField(TEXT("x"), CanvasSlot->GetPosition().X);
			PosObj->SetNumberField(TEXT("y"), CanvasSlot->GetPosition().Y);
			SlotObj->SetObjectField(TEXT("position"), PosObj);

			TSharedPtr<FJsonObject> SizeObj = MakeShared<FJsonObject>();
			SizeObj->SetNumberField(TEXT("x"), CanvasSlot->GetSize().X);
			SizeObj->SetNumberField(TEXT("y"), CanvasSlot->GetSize().Y);
			SlotObj->SetObjectField(TEXT("size"), SizeObj);

			TSharedPtr<FJsonObject> AnchorsObj = MakeShared<FJsonObject>();
			AnchorsObj->SetNumberField(TEXT("min_x"), CanvasSlot->GetAnchors().Minimum.X);
			AnchorsObj->SetNumberField(TEXT("min_y"), CanvasSlot->GetAnchors().Minimum.Y);
			AnchorsObj->SetNumberField(TEXT("max_x"), CanvasSlot->GetAnchors().Maximum.X);
			AnchorsObj->SetNumberField(TEXT("max_y"), CanvasSlot->GetAnchors().Maximum.Y);
			SlotObj->SetObjectField(TEXT("anchors"), AnchorsObj);

			TSharedPtr<FJsonObject> AlignObj = MakeShared<FJsonObject>();
			AlignObj->SetNumberField(TEXT("x"), CanvasSlot->GetAlignment().X);
			AlignObj->SetNumberField(TEXT("y"), CanvasSlot->GetAlignment().Y);
			SlotObj->SetObjectField(TEXT("alignment"), AlignObj);

			SlotObj->SetBoolField(TEXT("auto_size"), CanvasSlot->GetAutoSize());
			SlotObj->SetNumberField(TEXT("z_order"), CanvasSlot->GetZOrder());
		}
		else if (UVerticalBoxSlot* VSlot = Cast<UVerticalBoxSlot>(Slot))
		{
			TSharedPtr<FJsonObject> PadObj = MakeShared<FJsonObject>();
			PadObj->SetNumberField(TEXT("left"), VSlot->GetPadding().Left);
			PadObj->SetNumberField(TEXT("top"), VSlot->GetPadding().Top);
			PadObj->SetNumberField(TEXT("right"), VSlot->GetPadding().Right);
			PadObj->SetNumberField(TEXT("bottom"), VSlot->GetPadding().Bottom);
			SlotObj->SetObjectField(TEXT("padding"), PadObj);

			SlotObj->SetStringField(TEXT("size_rule"), VSlot->GetSize().SizeRule == ESlateSizeRule::Fill ? TEXT("Fill") : TEXT("Auto"));
			SlotObj->SetNumberField(TEXT("size_value"), VSlot->GetSize().Value);
			SlotObj->SetNumberField(TEXT("horizontal_alignment"), (int32)VSlot->GetHorizontalAlignment());
			SlotObj->SetNumberField(TEXT("vertical_alignment"), (int32)VSlot->GetVerticalAlignment());
		}
		else if (UHorizontalBoxSlot* HSlot = Cast<UHorizontalBoxSlot>(Slot))
		{
			TSharedPtr<FJsonObject> PadObj = MakeShared<FJsonObject>();
			PadObj->SetNumberField(TEXT("left"), HSlot->GetPadding().Left);
			PadObj->SetNumberField(TEXT("top"), HSlot->GetPadding().Top);
			PadObj->SetNumberField(TEXT("right"), HSlot->GetPadding().Right);
			PadObj->SetNumberField(TEXT("bottom"), HSlot->GetPadding().Bottom);
			SlotObj->SetObjectField(TEXT("padding"), PadObj);

			SlotObj->SetStringField(TEXT("size_rule"), HSlot->GetSize().SizeRule == ESlateSizeRule::Fill ? TEXT("Fill") : TEXT("Auto"));
			SlotObj->SetNumberField(TEXT("size_value"), HSlot->GetSize().Value);
			SlotObj->SetNumberField(TEXT("horizontal_alignment"), (int32)HSlot->GetHorizontalAlignment());
			SlotObj->SetNumberField(TEXT("vertical_alignment"), (int32)HSlot->GetVerticalAlignment());
		}
		else if (UButtonSlot* BSlot = Cast<UButtonSlot>(Slot))
		{
			TSharedPtr<FJsonObject> PadObj = MakeShared<FJsonObject>();
			PadObj->SetNumberField(TEXT("left"), BSlot->GetPadding().Left);
			PadObj->SetNumberField(TEXT("top"), BSlot->GetPadding().Top);
			PadObj->SetNumberField(TEXT("right"), BSlot->GetPadding().Right);
			PadObj->SetNumberField(TEXT("bottom"), BSlot->GetPadding().Bottom);
			SlotObj->SetObjectField(TEXT("padding"), PadObj);

			SlotObj->SetNumberField(TEXT("horizontal_alignment"), (int32)BSlot->GetHorizontalAlignment());
			SlotObj->SetNumberField(TEXT("vertical_alignment"), (int32)BSlot->GetVerticalAlignment());
		}

		return SlotObj;
	}

	TSharedPtr<FJsonObject> SerializeWidget(UWidget* Widget)
	{
		if (!Widget) return nullptr;

		TSharedPtr<FJsonObject> Obj = MakeShared<FJsonObject>();
		Obj->SetStringField(TEXT("name"), Widget->GetName());
		Obj->SetStringField(TEXT("class"), Widget->GetClass()->GetName());
		Obj->SetBoolField(TEXT("is_variable"), Widget->bIsVariable);
		Obj->SetStringField(TEXT("visibility"), VisibilityToString(Widget->GetVisibility()));

		TSharedPtr<FJsonObject> Props = MakeShared<FJsonObject>();

		if (UTextBlock* TextBlock = Cast<UTextBlock>(Widget))
		{
			Props->SetStringField(TEXT("text"), TextBlock->GetText().ToString());
			Props->SetNumberField(TEXT("font_size"), TextBlock->GetFont().Size);

			FLinearColor Col = TextBlock->GetColorAndOpacity().GetSpecifiedColor();
			TSharedPtr<FJsonObject> ColObj = MakeShared<FJsonObject>();
			ColObj->SetNumberField(TEXT("r"), Col.R);
			ColObj->SetNumberField(TEXT("g"), Col.G);
			ColObj->SetNumberField(TEXT("b"), Col.B);
			ColObj->SetNumberField(TEXT("a"), Col.A);
			Props->SetObjectField(TEXT("color"), ColObj);

			FByteProperty* JustProp = CastField<FByteProperty>(TextBlock->GetClass()->FindPropertyByName(TEXT("Justification")));
			int32 JustVal = JustProp ? (int32)JustProp->GetPropertyValue_InContainer(TextBlock) : 0;
			Props->SetNumberField(TEXT("justification"), JustVal);
		}
		else if (UProgressBar* Bar = Cast<UProgressBar>(Widget))
		{
			Props->SetNumberField(TEXT("percent"), Bar->GetPercent());
			FLinearColor Col = Bar->GetFillColorAndOpacity();
			TSharedPtr<FJsonObject> ColObj = MakeShared<FJsonObject>();
			ColObj->SetNumberField(TEXT("r"), Col.R);
			ColObj->SetNumberField(TEXT("g"), Col.G);
			ColObj->SetNumberField(TEXT("b"), Col.B);
			ColObj->SetNumberField(TEXT("a"), Col.A);
			Props->SetObjectField(TEXT("fill_color"), ColObj);
		}
		else if (UImage* Img = Cast<UImage>(Widget))
		{
			FLinearColor Col = Img->GetColorAndOpacity();
			TSharedPtr<FJsonObject> ColObj = MakeShared<FJsonObject>();
			ColObj->SetNumberField(TEXT("r"), Col.R);
			ColObj->SetNumberField(TEXT("g"), Col.G);
			ColObj->SetNumberField(TEXT("b"), Col.B);
			ColObj->SetNumberField(TEXT("a"), Col.A);
			Props->SetObjectField(TEXT("color"), ColObj);

			TSharedPtr<FJsonObject> SizeObj = MakeShared<FJsonObject>();
			SizeObj->SetNumberField(TEXT("x"), Img->GetDesiredSize().X);
			SizeObj->SetNumberField(TEXT("y"), Img->GetDesiredSize().Y);
			Props->SetObjectField(TEXT("brush_size"), SizeObj);
		}
		else if (USizeBox* SB = Cast<USizeBox>(Widget))
		{
			Props->SetNumberField(TEXT("width_override"), SB->GetWidthOverride());
			Props->SetNumberField(TEXT("height_override"), SB->GetHeightOverride());
		}
		else if (UButton* Btn = Cast<UButton>(Widget))
		{
			FLinearColor Bg = Btn->GetBackgroundColor();
			TSharedPtr<FJsonObject> BgObj = MakeShared<FJsonObject>();
			BgObj->SetNumberField(TEXT("r"), Bg.R);
			BgObj->SetNumberField(TEXT("g"), Bg.G);
			BgObj->SetNumberField(TEXT("b"), Bg.B);
			BgObj->SetNumberField(TEXT("a"), Bg.A);
			Props->SetObjectField(TEXT("background_color"), BgObj);
			Props->SetBoolField(TEXT("is_enabled"), Btn->GetIsEnabled());
		}

		Obj->SetObjectField(TEXT("properties"), Props);

		if (Widget->Slot)
		{
			TSharedPtr<FJsonObject> SlotData = SerializeSlot(Widget->Slot);
			if (SlotData.IsValid())
			{
				Obj->SetObjectField(TEXT("slot"), SlotData);
			}
		}

		TArray<TSharedPtr<FJsonValue>> ChildrenArray;
		if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
		{
			for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
			{
				UWidget* Child = Panel->GetChildAt(i);
				TSharedPtr<FJsonObject> ChildObj = SerializeWidget(Child);
				if (ChildObj.IsValid())
				{
					ChildrenArray.Add(MakeShared<FJsonValueObject>(ChildObj));
				}
			}
		}
		Obj->SetArrayField(TEXT("children"), ChildrenArray);

		return Obj;
	}

	void FlattenWidgets(UWidget* Widget, const FString& ParentName, TArray<TSharedPtr<FJsonValue>>& OutList)
	{
		if (!Widget) return;

		TSharedPtr<FJsonObject> Summary = MakeShared<FJsonObject>();
		Summary->SetStringField(TEXT("name"), Widget->GetName());
		Summary->SetStringField(TEXT("class"), Widget->GetClass()->GetName());
		Summary->SetStringField(TEXT("parent_name"), ParentName);
		Summary->SetBoolField(TEXT("is_variable"), Widget->bIsVariable);

		if (Widget->Slot)
		{
			Summary->SetStringField(TEXT("slot_class"), Widget->Slot->GetClass()->GetName());
		}

		OutList.Add(MakeShared<FJsonValueObject>(Summary));

		if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
		{
			for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
			{
				FlattenWidgets(Panel->GetChildAt(i), Widget->GetName(), OutList);
			}
		}
	}
}

FString UGameForgeWidgetLibrary::InspectWidgetBlueprint(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("parent_class"), BP->ParentClass ? BP->ParentClass->GetName() : TEXT("UserWidget"));
	Data->SetStringField(TEXT("generated_class"), BP->GeneratedClass ? BP->GeneratedClass->GetPathName() : TEXT(""));

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
	Data->SetBoolField(TEXT("is_dirty"), BP->GetPackage() ? BP->GetPackage()->IsDirty() : false);

	if (BP->WidgetTree)
	{
		TArray<UWidget*> AllWidgets;
		BP->WidgetTree->GetAllWidgets(AllWidgets);
		Data->SetNumberField(TEXT("widget_count"), AllWidgets.Num());

		if (BP->WidgetTree->RootWidget)
		{
			Data->SetStringField(TEXT("root_widget_name"), BP->WidgetTree->RootWidget->GetName());
			Data->SetStringField(TEXT("root_widget_class"), BP->WidgetTree->RootWidget->GetClass()->GetName());
		}
		else
		{
			Data->SetField(TEXT("root_widget_name"), MakeShared<FJsonValueNull>());
			Data->SetField(TEXT("root_widget_class"), MakeShared<FJsonValueNull>());
		}
	}
	else
	{
		Data->SetNumberField(TEXT("widget_count"), 0);
	}

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::ReadbackWidgetTree(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	if (!BP->WidgetTree)
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetBlueprint has no WidgetTree.")});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);

	if (BP->WidgetTree->RootWidget)
	{
		TSharedPtr<FJsonObject> RootObj = SerializeWidget(BP->WidgetTree->RootWidget);
		Data->SetObjectField(TEXT("root_widget"), RootObj);

		TArray<TSharedPtr<FJsonValue>> FlatList;
		FlattenWidgets(BP->WidgetTree->RootWidget, TEXT(""), FlatList);
		Data->SetArrayField(TEXT("widgets"), FlatList);
		Data->SetNumberField(TEXT("widget_count"), FlatList.Num());
	}
	else
	{
		Data->SetField(TEXT("root_widget"), MakeShared<FJsonValueNull>());
		Data->SetArrayField(TEXT("widgets"), {});
		Data->SetNumberField(TEXT("widget_count"), 0);
	}

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::CreateWidgetBlueprint(const FString& AssetPath, const FString& ParentClassName, const FString& RootWidgetClassName)
{
	if (AssetPath.IsEmpty())
	{
		return MakeEnvelope(false, nullptr, {TEXT("AssetPath cannot be empty.")});
	}

	FString PackagePath = AssetPath;
	FString AssetName = FPaths::GetBaseFilename(AssetPath);

	UPackage* ExistingPackage = FindPackage(nullptr, *PackagePath);
	if (ExistingPackage)
	{
		UObject* ExistingObj = StaticFindObject(UWidgetBlueprint::StaticClass(), ExistingPackage, *AssetName);
		if (ExistingObj)
		{
			TSharedPtr<FJsonObject> ExistsData = MakeShared<FJsonObject>();
			ExistsData->SetStringField(TEXT("asset_path"), AssetPath);
			ExistsData->SetBoolField(TEXT("already_existed"), true);
			return MakeEnvelope(true, ExistsData);
		}
	}

	UPackage* Package = CreatePackage(*PackagePath);
	if (!Package)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to create package '%s'."), *PackagePath)});
	}
	Package->FullyLoad();

	UObject* PreExistingObj = StaticFindObject(UWidgetBlueprint::StaticClass(), Package, *AssetName);
	if (PreExistingObj)
	{
		TSharedPtr<FJsonObject> ExistsData = MakeShared<FJsonObject>();
		ExistsData->SetStringField(TEXT("asset_path"), AssetPath);
		ExistsData->SetBoolField(TEXT("already_existed"), true);
		return MakeEnvelope(true, ExistsData);
	}

	UClass* ParentClass = UUserWidget::StaticClass();
	if (!ParentClassName.IsEmpty() && !ParentClassName.Equals(TEXT("UserWidget"), ESearchCase::IgnoreCase))
	{
		UClass* FoundClass = FindFirstObject<UClass>(*ParentClassName, EFindFirstObjectOptions::None);
		if (FoundClass && FoundClass->IsChildOf(UUserWidget::StaticClass()))
		{
			ParentClass = FoundClass;
		}
	}

	UWidgetBlueprint* NewBP = Cast<UWidgetBlueprint>(FKismetEditorUtilities::CreateBlueprint(
		ParentClass,
		Package,
		*AssetName,
		BPTYPE_Normal,
		UWidgetBlueprint::StaticClass(),
		UWidgetBlueprintGeneratedClass::StaticClass()
	));

	if (!NewBP)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("FKismetEditorUtilities::CreateBlueprint failed for WidgetBlueprint '%s'."), *AssetName)});
	}

	if (!RootWidgetClassName.IsEmpty() && NewBP->WidgetTree && NewBP->WidgetTree->RootWidget == nullptr)
	{
		FString ClassErr;
		UClass* RootClass = GetSupportedWidgetClass(RootWidgetClassName, ClassErr);
		if (RootClass && RootClass->IsChildOf(UPanelWidget::StaticClass()))
		{
			UWidget* Root = NewBP->WidgetTree->ConstructWidget<UWidget>(RootClass, *FString::Printf(TEXT("%s_0"), *RootWidgetClassName));
			if (Root)
			{
				NewBP->WidgetTree->RootWidget = Root;
				Root->bIsVariable = true;
				NewBP->OnVariableAdded(Root->GetFName());
			}
		}
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(NewBP);
	FKismetEditorUtilities::CompileBlueprint(NewBP);

	FAssetRegistryModule::AssetCreated(NewBP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("package_name"), Package->GetName());
	Data->SetStringField(TEXT("asset_name"), AssetName);
	Data->SetStringField(TEXT("parent_class"), ParentClass->GetName());
	Data->SetBoolField(TEXT("has_root_widget"), NewBP->WidgetTree && NewBP->WidgetTree->RootWidget != nullptr);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::CreateWidget(const FString& AssetPath, const FString& WidgetClassName, const FString& WidgetName, const FString& ParentName)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	if (!BP->WidgetTree)
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetBlueprint has no WidgetTree.")});
	}

	UClass* WidgetClass = GetSupportedWidgetClass(WidgetClassName, Error);
	if (!WidgetClass)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	FName DesiredName = *WidgetName;
	if (DesiredName.IsNone())
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetName cannot be empty.")});
	}

	if (BP->WidgetTree->FindWidget(DesiredName) != nullptr)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("A widget with name '%s' already exists in this WidgetTree."), *WidgetName)});
	}

	UWidget* NewWidget = BP->WidgetTree->ConstructWidget<UWidget>(WidgetClass, DesiredName);
	if (!NewWidget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to construct widget '%s' of class '%s'."), *WidgetName, *WidgetClassName)});
	}
	NewWidget->bIsVariable = true;

	FString SlotClassName = TEXT("None");

	if (ParentName.IsEmpty())
	{
		if (BP->WidgetTree->RootWidget == nullptr)
		{
			BP->WidgetTree->RootWidget = NewWidget;
		}
		else
		{
			return MakeEnvelope(false, nullptr, {TEXT("WidgetTree already has a RootWidget. Specify a ParentName to add as a child.")});
		}
	}
	else
	{
		UWidget* ParentWidget = BP->WidgetTree->FindWidget(*ParentName);
		if (!ParentWidget)
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Parent widget '%s' was not found in the WidgetTree."), *ParentName)});
		}

		UPanelWidget* Panel = Cast<UPanelWidget>(ParentWidget);
		if (!Panel)
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Parent widget '%s' is of class '%s', which is not a PanelWidget and cannot hold children."), *ParentName, *ParentWidget->GetClass()->GetName())});
		}

		UPanelSlot* Slot = Panel->AddChild(NewWidget);
		if (!Slot)
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to add child '%s' to panel '%s'."), *WidgetName, *ParentName)});
		}
		SlotClassName = Slot->GetClass()->GetName();
	}

	BP->OnVariableAdded(NewWidget->GetFName());
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("widget_name"), WidgetName);
	Data->SetStringField(TEXT("widget_class"), WidgetClassName);
	Data->SetStringField(TEXT("parent_name"), ParentName);
	Data->SetStringField(TEXT("slot_class"), SlotClassName);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::SetWidgetProperty(const FString& AssetPath, const FString& WidgetName, const FString& PropertyName, const FString& ValueJson)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	if (!BP->WidgetTree)
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetBlueprint has no WidgetTree.")});
	}

	UWidget* Widget = BP->WidgetTree->FindWidget(*WidgetName);
	if (!Widget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Widget '%s' not found."), *WidgetName)});
	}

	TSharedPtr<FJsonObject> ParsedObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ValueJson);
	if (!FJsonSerializer::Deserialize(Reader, ParsedObj) || !ParsedObj.IsValid())
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to parse ValueJson: '%s'."), *ValueJson)});
	}

	FString PropLower = PropertyName.ToLower();

	if (PropLower == TEXT("visibility"))
	{
		FString VisStr = ParsedObj->GetStringField(TEXT("value"));
		Widget->SetVisibility(StringToVisibility(VisStr));
	}
	else if (UTextBlock* TextBlock = Cast<UTextBlock>(Widget))
	{
		if (PropLower == TEXT("text"))
		{
			FString TextVal = ParsedObj->GetStringField(TEXT("value"));
			TextBlock->SetText(FText::FromString(TextVal));
		}
		else if (PropLower == TEXT("color"))
		{
			double R = ParsedObj->GetNumberField(TEXT("r"));
			double G = ParsedObj->GetNumberField(TEXT("g"));
			double B = ParsedObj->GetNumberField(TEXT("b"));
			double A = ParsedObj->HasField(TEXT("a")) ? ParsedObj->GetNumberField(TEXT("a")) : 1.0;
			TextBlock->SetColorAndOpacity(FSlateColor(FLinearColor((float)R, (float)G, (float)B, (float)A)));
		}
		else if (PropLower == TEXT("font_size"))
		{
			double Size = ParsedObj->GetNumberField(TEXT("value"));
			FSlateFontInfo Font = TextBlock->GetFont();
			Font.Size = (float)Size;
			TextBlock->SetFont(Font);
		}
		else if (PropLower == TEXT("justification"))
		{
			FString JustStr = ParsedObj->GetStringField(TEXT("value"));
			ETextJustify::Type Just = ETextJustify::Left;
			if (JustStr.Equals(TEXT("Center"), ESearchCase::IgnoreCase)) Just = ETextJustify::Center;
			else if (JustStr.Equals(TEXT("Right"), ESearchCase::IgnoreCase)) Just = ETextJustify::Right;
			TextBlock->SetJustification(Just);
		}
		else if (PropLower == TEXT("shadow_offset"))
		{
			double X = ParsedObj->GetNumberField(TEXT("x"));
			double Y = ParsedObj->GetNumberField(TEXT("y"));
			TextBlock->SetShadowOffset(FVector2D((float)X, (float)Y));
		}
		else if (PropLower == TEXT("shadow_color"))
		{
			double R = ParsedObj->GetNumberField(TEXT("r"));
			double G = ParsedObj->GetNumberField(TEXT("g"));
			double B = ParsedObj->GetNumberField(TEXT("b"));
			double A = ParsedObj->HasField(TEXT("a")) ? ParsedObj->GetNumberField(TEXT("a")) : 1.0;
			TextBlock->SetShadowColorAndOpacity(FLinearColor((float)R, (float)G, (float)B, (float)A));
		}
		else
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Property '%s' not supported on TextBlock."), *PropertyName)});
		}
	}
	else if (UProgressBar* Bar = Cast<UProgressBar>(Widget))
	{
		if (PropLower == TEXT("percent"))
		{
			double Pct = ParsedObj->GetNumberField(TEXT("value"));
			Bar->SetPercent((float)Pct);
		}
		else if (PropLower == TEXT("fill_color"))
		{
			double R = ParsedObj->GetNumberField(TEXT("r"));
			double G = ParsedObj->GetNumberField(TEXT("g"));
			double B = ParsedObj->GetNumberField(TEXT("b"));
			double A = ParsedObj->HasField(TEXT("a")) ? ParsedObj->GetNumberField(TEXT("a")) : 1.0;
			Bar->SetFillColorAndOpacity(FLinearColor((float)R, (float)G, (float)B, (float)A));
		}
		else
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Property '%s' not supported on ProgressBar."), *PropertyName)});
		}
	}
	else if (UImage* Img = Cast<UImage>(Widget))
	{
		if (PropLower == TEXT("color"))
		{
			double R = ParsedObj->GetNumberField(TEXT("r"));
			double G = ParsedObj->GetNumberField(TEXT("g"));
			double B = ParsedObj->GetNumberField(TEXT("b"));
			double A = ParsedObj->HasField(TEXT("a")) ? ParsedObj->GetNumberField(TEXT("a")) : 1.0;
			Img->SetColorAndOpacity(FLinearColor((float)R, (float)G, (float)B, (float)A));
		}
		else if (PropLower == TEXT("brush_size"))
		{
			double X = ParsedObj->GetNumberField(TEXT("x"));
			double Y = ParsedObj->GetNumberField(TEXT("y"));
			Img->SetDesiredSizeOverride(FVector2D((float)X, (float)Y));
		}
		else
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Property '%s' not supported on Image."), *PropertyName)});
		}
	}
	else if (USizeBox* SB = Cast<USizeBox>(Widget))
	{
		if (PropLower == TEXT("width_override"))
		{
			double W = ParsedObj->GetNumberField(TEXT("value"));
			SB->SetWidthOverride((float)W);
		}
		else if (PropLower == TEXT("height_override"))
		{
			double H = ParsedObj->GetNumberField(TEXT("value"));
			SB->SetHeightOverride((float)H);
		}
		else
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Property '%s' not supported on SizeBox."), *PropertyName)});
		}
	}
	else if (UButton* Btn = Cast<UButton>(Widget))
	{
		if (PropLower == TEXT("background_color"))
		{
			double R = ParsedObj->GetNumberField(TEXT("r"));
			double G = ParsedObj->GetNumberField(TEXT("g"));
			double B = ParsedObj->GetNumberField(TEXT("b"));
			double A = ParsedObj->HasField(TEXT("a")) ? ParsedObj->GetNumberField(TEXT("a")) : 1.0;
			Btn->SetBackgroundColor(FLinearColor((float)R, (float)G, (float)B, (float)A));
		}
		else if (PropLower == TEXT("is_enabled"))
		{
			bool bEn = ParsedObj->GetBoolField(TEXT("value"));
			Btn->SetIsEnabled(bEn);
		}
		else
		{
			return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Property '%s' not supported on Button."), *PropertyName)});
		}
	}
	else
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Property '%s' not supported on class '%s'."), *PropertyName, *Widget->GetClass()->GetName())});
	}

	FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("widget_name"), WidgetName);
	Data->SetStringField(TEXT("property_name"), PropertyName);
	Data->SetBoolField(TEXT("applied"), true);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::SetWidgetSlotProperty(const FString& AssetPath, const FString& WidgetName, const FString& SlotPropertiesJson)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	if (!BP->WidgetTree)
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetBlueprint has no WidgetTree.")});
	}

	UWidget* Widget = BP->WidgetTree->FindWidget(*WidgetName);
	if (!Widget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Widget '%s' not found."), *WidgetName)});
	}

	UPanelSlot* Slot = Widget->Slot;
	if (!Slot)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Widget '%s' has no parent slot."), *WidgetName)});
	}

	TSharedPtr<FJsonObject> ParsedObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(SlotPropertiesJson);
	if (!FJsonSerializer::Deserialize(Reader, ParsedObj) || !ParsedObj.IsValid())
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to parse SlotPropertiesJson: '%s'."), *SlotPropertiesJson)});
	}

	if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Slot))
	{
		if (ParsedObj->HasField(TEXT("position")))
		{
			TSharedPtr<FJsonObject> P = ParsedObj->GetObjectField(TEXT("position"));
			CanvasSlot->SetPosition(FVector2D((float)P->GetNumberField(TEXT("x")), (float)P->GetNumberField(TEXT("y"))));
		}

		if (ParsedObj->HasField(TEXT("size")))
		{
			TSharedPtr<FJsonObject> S = ParsedObj->GetObjectField(TEXT("size"));
			CanvasSlot->SetSize(FVector2D((float)S->GetNumberField(TEXT("x")), (float)S->GetNumberField(TEXT("y"))));
		}

		if (ParsedObj->HasField(TEXT("anchors")))
		{
			TSharedPtr<FJsonObject> A = ParsedObj->GetObjectField(TEXT("anchors"));
			FAnchors Anchors;
			Anchors.Minimum = FVector2D((float)A->GetNumberField(TEXT("min_x")), (float)A->GetNumberField(TEXT("min_y")));
			Anchors.Maximum = FVector2D((float)A->GetNumberField(TEXT("max_x")), (float)A->GetNumberField(TEXT("max_y")));
			CanvasSlot->SetAnchors(Anchors);
		}

		if (ParsedObj->HasField(TEXT("alignment")))
		{
			TSharedPtr<FJsonObject> Al = ParsedObj->GetObjectField(TEXT("alignment"));
			CanvasSlot->SetAlignment(FVector2D((float)Al->GetNumberField(TEXT("x")), (float)Al->GetNumberField(TEXT("y"))));
		}

		if (ParsedObj->HasField(TEXT("auto_size")))
		{
			CanvasSlot->SetAutoSize(ParsedObj->GetBoolField(TEXT("auto_size")));
		}

		if (ParsedObj->HasField(TEXT("z_order")))
		{
			CanvasSlot->SetZOrder((int32)ParsedObj->GetNumberField(TEXT("z_order")));
		}
	}
	else if (UVerticalBoxSlot* VSlot = Cast<UVerticalBoxSlot>(Slot))
	{
		if (ParsedObj->HasField(TEXT("padding")))
		{
			TSharedPtr<FJsonObject> Pad = ParsedObj->GetObjectField(TEXT("padding"));
			FMargin Margin(
				(float)Pad->GetNumberField(TEXT("left")),
				(float)Pad->GetNumberField(TEXT("top")),
				(float)Pad->GetNumberField(TEXT("right")),
				(float)Pad->GetNumberField(TEXT("bottom"))
			);
			VSlot->SetPadding(Margin);
		}

		if (ParsedObj->HasField(TEXT("size_rule")))
		{
			FString RuleStr = ParsedObj->GetStringField(TEXT("size_rule"));
			double Val = ParsedObj->HasField(TEXT("size_value")) ? ParsedObj->GetNumberField(TEXT("size_value")) : 1.0;
			FSlateChildSize ChildSize;
			ChildSize.SizeRule = RuleStr.Equals(TEXT("Fill"), ESearchCase::IgnoreCase) ? ESlateSizeRule::Fill : ESlateSizeRule::Automatic;
			ChildSize.Value = (float)Val;
			VSlot->SetSize(ChildSize);
		}

		if (ParsedObj->HasField(TEXT("horizontal_alignment")))
		{
			int32 HAlign = (int32)ParsedObj->GetNumberField(TEXT("horizontal_alignment"));
			VSlot->SetHorizontalAlignment((EHorizontalAlignment)HAlign);
		}

		if (ParsedObj->HasField(TEXT("vertical_alignment")))
		{
			int32 VAlign = (int32)ParsedObj->GetNumberField(TEXT("vertical_alignment"));
			VSlot->SetVerticalAlignment((EVerticalAlignment)VAlign);
		}
	}
	else if (UHorizontalBoxSlot* HSlot = Cast<UHorizontalBoxSlot>(Slot))
	{
		if (ParsedObj->HasField(TEXT("padding")))
		{
			TSharedPtr<FJsonObject> Pad = ParsedObj->GetObjectField(TEXT("padding"));
			FMargin Margin(
				(float)Pad->GetNumberField(TEXT("left")),
				(float)Pad->GetNumberField(TEXT("top")),
				(float)Pad->GetNumberField(TEXT("right")),
				(float)Pad->GetNumberField(TEXT("bottom"))
			);
			HSlot->SetPadding(Margin);
		}

		if (ParsedObj->HasField(TEXT("size_rule")))
		{
			FString RuleStr = ParsedObj->GetStringField(TEXT("size_rule"));
			double Val = ParsedObj->HasField(TEXT("size_value")) ? ParsedObj->GetNumberField(TEXT("size_value")) : 1.0;
			FSlateChildSize ChildSize;
			ChildSize.SizeRule = RuleStr.Equals(TEXT("Fill"), ESearchCase::IgnoreCase) ? ESlateSizeRule::Fill : ESlateSizeRule::Automatic;
			ChildSize.Value = (float)Val;
			HSlot->SetSize(ChildSize);
		}

		if (ParsedObj->HasField(TEXT("horizontal_alignment")))
		{
			int32 HAlign = (int32)ParsedObj->GetNumberField(TEXT("horizontal_alignment"));
			HSlot->SetHorizontalAlignment((EHorizontalAlignment)HAlign);
		}

		if (ParsedObj->HasField(TEXT("vertical_alignment")))
		{
			int32 VAlign = (int32)ParsedObj->GetNumberField(TEXT("vertical_alignment"));
			HSlot->SetVerticalAlignment((EVerticalAlignment)VAlign);
		}
	}
	else if (UButtonSlot* BSlot = Cast<UButtonSlot>(Slot))
	{
		if (ParsedObj->HasField(TEXT("padding")))
		{
			TSharedPtr<FJsonObject> Pad = ParsedObj->GetObjectField(TEXT("padding"));
			FMargin Margin(
				(float)Pad->GetNumberField(TEXT("left")),
				(float)Pad->GetNumberField(TEXT("top")),
				(float)Pad->GetNumberField(TEXT("right")),
				(float)Pad->GetNumberField(TEXT("bottom"))
			);
			BSlot->SetPadding(Margin);
		}

		if (ParsedObj->HasField(TEXT("horizontal_alignment")))
		{
			int32 HAlign = (int32)ParsedObj->GetNumberField(TEXT("horizontal_alignment"));
			BSlot->SetHorizontalAlignment((EHorizontalAlignment)HAlign);
		}

		if (ParsedObj->HasField(TEXT("vertical_alignment")))
		{
			int32 VAlign = (int32)ParsedObj->GetNumberField(TEXT("vertical_alignment"));
			BSlot->SetVerticalAlignment((EVerticalAlignment)VAlign);
		}
	}
	else
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Slot class '%s' does not support property configuration in V1."), *Slot->GetClass()->GetName())});
	}

	FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("widget_name"), WidgetName);
	Data->SetStringField(TEXT("slot_class"), Slot->GetClass()->GetName());
	Data->SetBoolField(TEXT("configured"), true);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::RemoveWidget(const FString& AssetPath, const FString& WidgetName)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	if (!BP->WidgetTree)
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetBlueprint has no WidgetTree.")});
	}

	UWidget* Widget = BP->WidgetTree->FindWidget(*WidgetName);
	if (!Widget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Widget '%s' not found."), *WidgetName)});
	}

	if (Widget == BP->WidgetTree->RootWidget)
	{
		BP->WidgetTree->RootWidget = nullptr;
	}

	if (Widget->Slot && Widget->Slot->Parent)
	{
		Widget->Slot->Parent->RemoveChild(Widget);
	}

	BP->WidgetTree->RemoveWidget(Widget);
	BP->OnVariableRemoved(*WidgetName);

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("removed_widget"), WidgetName);
	Data->SetBoolField(TEXT("removed"), true);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::CompileWidgetBlueprint(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	FKismetEditorUtilities::CompileBlueprint(BP);

	FString StatusStr = TEXT("Unknown");
	bool bSuccess = false;
	switch (BP->Status)
	{
	case BS_UpToDate:
		StatusStr = TEXT("UpToDate");
		bSuccess = true;
		break;
	case BS_UpToDateWithWarnings:
		StatusStr = TEXT("UpToDateWithWarnings");
		bSuccess = true;
		break;
	case BS_Dirty:
		StatusStr = TEXT("Dirty");
		break;
	case BS_Error:
		StatusStr = TEXT("Error");
		break;
	default:
		break;
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("status"), StatusStr);
	Data->SetBoolField(TEXT("compiled_successfully"), bSuccess);
	Data->SetStringField(TEXT("generated_class"), BP->GeneratedClass ? BP->GeneratedClass->GetPathName() : TEXT(""));

	return MakeEnvelope(bSuccess, Data, bSuccess ? TArray<FString>() : TArray<FString>{TEXT("Widget Blueprint compilation failed with status ") + StatusStr});
}

FString UGameForgeWidgetLibrary::SaveWidgetBlueprint(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	UPackage* Package = BP->GetPackage();
	if (!Package)
	{
		return MakeEnvelope(false, nullptr, {TEXT("Asset has no outer package.")});
	}

	TArray<UPackage*> PackagesToSave = { Package };
	bool bSaved = UEditorLoadingAndSavingUtils::SavePackages(PackagesToSave, false);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("package_name"), Package->GetName());
	Data->SetBoolField(TEXT("saved"), bSaved);
	Data->SetBoolField(TEXT("is_dirty"), Package->IsDirty());

	return MakeEnvelope(bSaved && !Package->IsDirty(), Data);
}

FString UGameForgeWidgetLibrary::DisplayWidgetInGame(const FString& AssetPath, int32 ZOrder)
{
	UWorld* PlayWorld = nullptr;

	if (GEditor && GEditor->PlayWorld)
	{
		PlayWorld = GEditor->PlayWorld.Get();
	}
	else if (GEngine)
	{
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::PIE && Context.World())
			{
				PlayWorld = Context.World();
				break;
			}
		}
	}

	if (!PlayWorld)
	{
		return MakeEnvelope(false, nullptr, {TEXT("No active PIE / Game World found. Launch PIE before displaying widget.")});
	}

	FString GeneratedClassPath = AssetPath;
	if (!GeneratedClassPath.EndsWith(TEXT("_C")))
	{
		FString AssetName = FPaths::GetBaseFilename(AssetPath);
		GeneratedClassPath = FString::Printf(TEXT("%s.%s_C"), *AssetPath, *AssetName);
	}

	UClass* WidgetClass = StaticLoadClass(UUserWidget::StaticClass(), nullptr, *GeneratedClassPath);
	if (!WidgetClass)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to load widget class at '%s'."), *GeneratedClassPath)});
	}

	UUserWidget* CreatedWidget = UUserWidget::CreateWidgetInstance(*PlayWorld, WidgetClass, NAME_None);
	if (!CreatedWidget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("CreateWidget returned nullptr for class '%s'."), *WidgetClass->GetName())});
	}

	CreatedWidget->AddToViewport(ZOrder);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("widget_class"), WidgetClass->GetName());
	Data->SetStringField(TEXT("instance_name"), CreatedWidget->GetName());
	Data->SetNumberField(TEXT("viewport_zorder"), ZOrder);
	Data->SetBoolField(TEXT("is_in_viewport"), CreatedWidget->IsInViewport());

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::BindWidgetEvent(const FString& AssetPath, const FString& WidgetName, const FString& DelegateName, const FString& ActionTypeJson)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	if (!BP->WidgetTree)
	{
		return MakeEnvelope(false, nullptr, {TEXT("WidgetBlueprint has no WidgetTree.")});
	}

	UWidget* Widget = BP->WidgetTree->FindWidget(FName(*WidgetName));
	if (!Widget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Widget '%s' not found in WidgetTree."), *WidgetName)});
	}

	Widget->bIsVariable = true;
	BP->OnVariableAdded(Widget->GetFName());

	UEdGraph* EventGraph = nullptr;
	if (BP->UbergraphPages.Num() > 0)
	{
		EventGraph = BP->UbergraphPages[0];
	}
	else
	{
		EventGraph = FBlueprintEditorUtils::CreateNewGraph(BP, TEXT("EventGraph"), UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
		FBlueprintEditorUtils::AddUbergraphPage(BP, EventGraph);
	}

	if (!EventGraph)
	{
		return MakeEnvelope(false, nullptr, {TEXT("Failed to locate or create EventGraph in WidgetBlueprint.")});
	}

	UK2Node_ComponentBoundEvent* BoundEvent = nullptr;
	for (UEdGraphNode* Node : EventGraph->Nodes)
	{
		if (UK2Node_ComponentBoundEvent* Ev = Cast<UK2Node_ComponentBoundEvent>(Node))
		{
			if (Ev->ComponentPropertyName == Widget->GetFName() && Ev->DelegatePropertyName == FName(*DelegateName))
			{
				BoundEvent = Ev;
				break;
			}
		}
	}

	if (!BoundEvent)
	{
		BoundEvent = NewObject<UK2Node_ComponentBoundEvent>(EventGraph);
		BoundEvent->ComponentPropertyName = Widget->GetFName();
		BoundEvent->DelegatePropertyName = FName(*DelegateName);
		BoundEvent->DelegateOwnerClass = Widget->GetClass();

		FMulticastDelegateProperty* DelProp = CastField<FMulticastDelegateProperty>(Widget->GetClass()->FindPropertyByName(FName(*DelegateName)));
		if (DelProp && DelProp->SignatureFunction)
		{
			BoundEvent->EventReference.SetFromField<UFunction>(DelProp->SignatureFunction, false);
		}
		BoundEvent->CustomFunctionName = FName(*FString::Printf(TEXT("BndEvt__%s_%s_%s"), *BP->GetName(), *WidgetName, *DelegateName));
		BoundEvent->bOverrideFunction = false;
		BoundEvent->bInternalEvent = true;
		BoundEvent->NodePosX = 100;
		BoundEvent->NodePosY = 200 + EventGraph->Nodes.Num() * 150;
		BoundEvent->CreateNewGuid();
		BoundEvent->PostPlacedNewNode();
		BoundEvent->AllocateDefaultPins();
		EventGraph->AddNode(BoundEvent, true, true);
	}

	TSharedPtr<FJsonObject> ActionObj;
	if (!ActionTypeJson.IsEmpty())
	{
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ActionTypeJson);
		FJsonSerializer::Deserialize(Reader, ActionObj);
	}
	if (!ActionObj.IsValid())
	{
		ActionObj = MakeShared<FJsonObject>();
	}

	FString ActionType = ActionObj->GetStringField(TEXT("action_type"));
	FString ConnectedTarget = TEXT("None");

	if (ActionType.Equals(TEXT("PrintString"), ESearchCase::IgnoreCase))
	{
		UK2Node_CallFunction* CallNode = NewObject<UK2Node_CallFunction>(EventGraph);
		CallNode->FunctionReference.SetExternalMember(FName(TEXT("PrintString")), UKismetSystemLibrary::StaticClass());
		CallNode->NodePosX = BoundEvent->NodePosX + 320;
		CallNode->NodePosY = BoundEvent->NodePosY;
		CallNode->CreateNewGuid();
		CallNode->PostPlacedNewNode();
		CallNode->AllocateDefaultPins();
		EventGraph->AddNode(CallNode, true, true);

		FString Msg = ActionObj->GetStringField(TEXT("message"));
		if (Msg.IsEmpty()) Msg = FString::Printf(TEXT("EVENT_%s_%s"), *WidgetName, *DelegateName);
		if (UEdGraphPin* Pin = CallNode->FindPin(TEXT("inString")))
		{
			Pin->DefaultValue = Msg;
		}

		UEdGraphPin* ThenPin = BoundEvent->FindPin(UEdGraphSchema_K2::PN_Then);
		UEdGraphPin* ExecPin = CallNode->FindPin(UEdGraphSchema_K2::PN_Execute);
		if (ThenPin && ExecPin)
		{
			ThenPin->MakeLinkTo(ExecPin);
		}
		ConnectedTarget = TEXT("PrintString");
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
	FKismetEditorUtilities::CompileBlueprint(BP);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("widget_name"), WidgetName);
	Data->SetStringField(TEXT("delegate_name"), DelegateName);
	Data->SetStringField(TEXT("custom_function_name"), BoundEvent->CustomFunctionName.ToString());
	Data->SetStringField(TEXT("node_id"), BoundEvent->NodeGuid.ToString());
	Data->SetStringField(TEXT("connected_target"), ConnectedTarget);
	Data->SetStringField(TEXT("compile_status"), BP->Status == BS_UpToDate ? TEXT("UpToDate") : TEXT("Dirty"));

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::InspectWidgetEvents(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* BP = ResolveWidgetBlueprint(AssetPath, Error);
	if (!BP)
	{
		return MakeEnvelope(false, nullptr, {Error});
	}

	TArray<TSharedPtr<FJsonValue>> EventsArray;
	for (UEdGraph* Graph : BP->UbergraphPages)
	{
		if (!Graph) continue;
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (UK2Node_ComponentBoundEvent* BoundEvent = Cast<UK2Node_ComponentBoundEvent>(Node))
			{
				TSharedPtr<FJsonObject> EObj = MakeShared<FJsonObject>();
				EObj->SetStringField(TEXT("widget_name"), BoundEvent->ComponentPropertyName.ToString());
				EObj->SetStringField(TEXT("delegate_name"), BoundEvent->DelegatePropertyName.ToString());
				EObj->SetStringField(TEXT("custom_function_name"), BoundEvent->CustomFunctionName.ToString());
				EObj->SetStringField(TEXT("node_id"), BoundEvent->NodeGuid.ToString());

				TArray<TSharedPtr<FJsonValue>> Links;
				if (UEdGraphPin* ThenPin = BoundEvent->FindPin(UEdGraphSchema_K2::PN_Then))
				{
					for (UEdGraphPin* LinkedPin : ThenPin->LinkedTo)
					{
						if (LinkedPin && LinkedPin->GetOwningNode())
						{
							Links.Add(MakeShared<FJsonValueString>(LinkedPin->GetOwningNode()->GetClass()->GetName()));
						}
					}
				}
				EObj->SetArrayField(TEXT("connected_nodes"), Links);
				EventsArray.Add(MakeShared<FJsonValueObject>(EObj));
			}
		}
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetArrayField(TEXT("bound_events"), EventsArray);
	Data->SetNumberField(TEXT("event_count"), EventsArray.Num());

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::TriggerButtonClick(const FString& AssetPath, const FString& ButtonName)
{
	UWorld* PlayWorld = nullptr;
	if (GEditor && GEditor->PlayWorld)
	{
		PlayWorld = GEditor->PlayWorld.Get();
	}
	else if (GEngine)
	{
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::PIE && Context.World())
			{
				PlayWorld = Context.World();
				break;
			}
		}
	}

	if (!PlayWorld)
	{
		return MakeEnvelope(false, nullptr, {TEXT("No active PIE world found.")});
	}

	UButton* TargetButton = nullptr;
	UUserWidget* OwningWidget = nullptr;

	for (TObjectIterator<UUserWidget> It; It; ++It)
	{
		UUserWidget* W = *It;
		if (W->GetWorld() == PlayWorld && W->IsInViewport())
		{
			UWidget* Child = W->GetWidgetFromName(FName(*ButtonName));
			if (Child)
			{
				TargetButton = Cast<UButton>(Child);
				if (TargetButton)
				{
					OwningWidget = W;
					break;
				}
			}
		}
	}

	if (!TargetButton)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Button '%s' not found on any active viewport widget in PIE world."), *ButtonName)});
	}

	TargetButton->OnClicked.Broadcast();
	UE_LOG(LogTemp, Log, TEXT("[GameForgeWidgetLibrary] Triggered button click on '%s'"), *ButtonName);

	UGameForgeGameplayStateComponent* Comp = nullptr;
	for (TActorIterator<AActor> It(PlayWorld); It; ++It)
	{
		if (AActor* Act = *It)
		{
			if (UGameForgeGameplayStateComponent* C = Act->FindComponentByClass<UGameForgeGameplayStateComponent>())
			{
				Comp = C;
				break;
			}
		}
	}
	if (!Comp)
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.Name = FName(TEXT("GF_GameplayProbeActor"));
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AActor* ProbeActor = PlayWorld->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
		if (ProbeActor)
		{
			Comp = NewObject<UGameForgeGameplayStateComponent>(ProbeActor, TEXT("GFGameplayStateComponent"));
			Comp->RegisterComponent();
			ProbeActor->AddInstanceComponent(Comp);
		}
	}

	FString ExecutedAction = TEXT("None");
	if (Comp)
	{
		if (ButtonName.Equals(TEXT("PrimaryButton"), ESearchCase::IgnoreCase) || ButtonName.Contains(TEXT("Primary")))
		{
			Comp->ExecuteMenuAction(TEXT("HealBoost"));
			ExecutedAction = TEXT("HealBoost");
			for (TObjectIterator<UUserWidget> It; It; ++It)
			{
				UUserWidget* W = *It;
				if (W->GetWorld() == PlayWorld && W->IsInViewport())
				{
					if (UProgressBar* HBar = Cast<UProgressBar>(W->GetWidgetFromName(FName(TEXT("HealthBar")))))
					{
						HBar->SetPercent(Comp->Health / Comp->MaxHealth);
					}
					if (UTextBlock* HLabel = Cast<UTextBlock>(W->GetWidgetFromName(FName(TEXT("HealthLabel")))))
					{
						HLabel->SetText(FText::FromString(FString::Printf(TEXT("HEALTH: %d / %d"), (int32)Comp->Health, (int32)Comp->MaxHealth)));
					}
				}
			}
		}
		else if (ButtonName.Equals(TEXT("SecondaryButton"), ESearchCase::IgnoreCase) || ButtonName.Contains(TEXT("Secondary")))
		{
			Comp->ExecuteMenuAction(TEXT("ToggleHUD"));
			ExecutedAction = TEXT("ToggleHUD");
		}
		else if (ButtonName.Equals(TEXT("BackButton"), ESearchCase::IgnoreCase) || ButtonName.Contains(TEXT("Back")))
		{
			Comp->ExecuteMenuAction(TEXT("CloseMenu"));
			ExecutedAction = TEXT("CloseMenu");
			if (OwningWidget)
			{
				OwningWidget->SetVisibility(ESlateVisibility::Collapsed);
			}
		}
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("button_name"), ButtonName);
	Data->SetStringField(TEXT("owning_widget"), OwningWidget ? OwningWidget->GetName() : TEXT("None"));
	Data->SetStringField(TEXT("executed_action"), ExecutedAction);
	Data->SetBoolField(TEXT("clicked"), true);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::GetWidgetRuntimeState(const FString& AssetPath)
{
	UWorld* PlayWorld = nullptr;
	if (GEditor && GEditor->PlayWorld)
	{
		PlayWorld = GEditor->PlayWorld.Get();
	}
	else if (GEngine)
	{
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::PIE && Context.World())
			{
				PlayWorld = Context.World();
				break;
			}
		}
	}

	if (!PlayWorld)
	{
		return MakeEnvelope(false, nullptr, {TEXT("No active PIE world found.")});
	}

	FString BaseName = FPaths::GetBaseFilename(AssetPath);
	UUserWidget* TargetWidget = nullptr;

	for (TObjectIterator<UUserWidget> It; It; ++It)
	{
		UUserWidget* W = *It;
		if (W->GetWorld() == PlayWorld && W->IsInViewport())
		{
			if (W->GetClass()->GetName().Contains(BaseName))
			{
				TargetWidget = W;
				break;
			}
		}
	}

	if (!TargetWidget)
	{
		return MakeEnvelope(false, nullptr, {FString::Printf(TEXT("Active widget instance for '%s' not found in viewport."), *AssetPath)});
	}

	TSharedPtr<FJsonObject> WidgetsMap = MakeShared<FJsonObject>();

	if (TargetWidget->WidgetTree)
	{
		TargetWidget->WidgetTree->ForEachWidget([&](UWidget* W) {
			if (!W) return;
			TSharedPtr<FJsonObject> WObj = MakeShared<FJsonObject>();
			WObj->SetStringField(TEXT("class"), W->GetClass()->GetName());
			WObj->SetStringField(TEXT("visibility"), VisibilityToString(W->GetVisibility()));

			if (UProgressBar* Bar = Cast<UProgressBar>(W))
			{
				WObj->SetNumberField(TEXT("percent"), Bar->GetPercent());
				FLinearColor Fill = Bar->GetFillColorAndOpacity();
				TSharedPtr<FJsonObject> FillObj = MakeShared<FJsonObject>();
				FillObj->SetNumberField(TEXT("r"), Fill.R);
				FillObj->SetNumberField(TEXT("g"), Fill.G);
				FillObj->SetNumberField(TEXT("b"), Fill.B);
				FillObj->SetNumberField(TEXT("a"), Fill.A);
				WObj->SetObjectField(TEXT("fill_color"), FillObj);
			}
			else if (UTextBlock* Text = Cast<UTextBlock>(W))
			{
				WObj->SetStringField(TEXT("text"), Text->GetText().ToString());
			}
			else if (UButton* Btn = Cast<UButton>(W))
			{
				WObj->SetBoolField(TEXT("is_enabled"), Btn->GetIsEnabled());
			}

			WidgetsMap->SetObjectField(W->GetName(), WObj);
		});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("asset_path"), AssetPath);
	Data->SetStringField(TEXT("instance_name"), TargetWidget->GetName());
	Data->SetStringField(TEXT("visibility"), VisibilityToString(TargetWidget->GetVisibility()));
	Data->SetBoolField(TEXT("is_in_viewport"), TargetWidget->IsInViewport());
	Data->SetObjectField(TEXT("widgets"), WidgetsMap);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::GetGameplayState()
{
	UWorld* PlayWorld = nullptr;
	if (GEditor && GEditor->PlayWorld)
	{
		PlayWorld = GEditor->PlayWorld.Get();
	}
	else if (GEngine)
	{
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::PIE && Context.World())
			{
				PlayWorld = Context.World();
				break;
			}
		}
	}

	if (!PlayWorld)
	{
		return MakeEnvelope(false, nullptr, {TEXT("No active PIE world found.")});
	}

	UGameForgeGameplayStateComponent* Comp = nullptr;
	for (TActorIterator<AActor> It(PlayWorld); It; ++It)
	{
		if (AActor* Act = *It)
		{
			if (UGameForgeGameplayStateComponent* C = Act->FindComponentByClass<UGameForgeGameplayStateComponent>())
			{
				Comp = C;
				break;
			}
		}
	}

	if (!Comp)
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.Name = FName(TEXT("GF_GameplayProbeActor"));
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AActor* ProbeActor = PlayWorld->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
		if (ProbeActor)
		{
			Comp = NewObject<UGameForgeGameplayStateComponent>(ProbeActor, TEXT("GFGameplayStateComponent"));
			Comp->RegisterComponent();
			ProbeActor->AddInstanceComponent(Comp);
		}
	}

	if (!Comp)
	{
		return MakeEnvelope(false, nullptr, {TEXT("Failed to locate or spawn UGameForgeGameplayStateComponent in PIE world.")});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetNumberField(TEXT("health"), Comp->Health);
	Data->SetNumberField(TEXT("max_health"), Comp->MaxHealth);
	Data->SetNumberField(TEXT("stamina"), Comp->Stamina);
	Data->SetNumberField(TEXT("max_stamina"), Comp->MaxStamina);
	Data->SetStringField(TEXT("active_menu_state"), Comp->ActiveMenuState);
	Data->SetStringField(TEXT("last_executed_action"), Comp->LastExecutedAction);

	return MakeEnvelope(true, Data);
}

FString UGameForgeWidgetLibrary::ModifyGameplayState(float DeltaHealth, float DeltaStamina, const FString& MenuAction)
{
	UWorld* PlayWorld = nullptr;
	if (GEditor && GEditor->PlayWorld)
	{
		PlayWorld = GEditor->PlayWorld.Get();
	}
	else if (GEngine)
	{
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::PIE && Context.World())
			{
				PlayWorld = Context.World();
				break;
			}
		}
	}

	if (!PlayWorld)
	{
		return MakeEnvelope(false, nullptr, {TEXT("No active PIE world found.")});
	}

	UGameForgeGameplayStateComponent* Comp = nullptr;
	for (TActorIterator<AActor> It(PlayWorld); It; ++It)
	{
		if (AActor* Act = *It)
		{
			if (UGameForgeGameplayStateComponent* C = Act->FindComponentByClass<UGameForgeGameplayStateComponent>())
			{
				Comp = C;
				break;
			}
		}
	}

	if (!Comp)
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.Name = FName(TEXT("GF_GameplayProbeActor"));
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AActor* ProbeActor = PlayWorld->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
		if (ProbeActor)
		{
			Comp = NewObject<UGameForgeGameplayStateComponent>(ProbeActor, TEXT("GFGameplayStateComponent"));
			Comp->RegisterComponent();
			ProbeActor->AddInstanceComponent(Comp);
		}
	}

	if (!Comp)
	{
		return MakeEnvelope(false, nullptr, {TEXT("Failed to locate or spawn UGameForgeGameplayStateComponent in PIE world.")});
	}

	float BeforeH = Comp->Health;
	float BeforeS = Comp->Stamina;
	FString BeforeM = Comp->ActiveMenuState;

	if (DeltaHealth != 0.0f)
	{
		Comp->ModifyHealth(DeltaHealth);
	}
	if (DeltaStamina != 0.0f)
	{
		Comp->ModifyStamina(DeltaStamina);
	}
	if (!MenuAction.IsEmpty())
	{
		Comp->ExecuteMenuAction(MenuAction);
	}

	int32 UpdatedWidgets = 0;
	for (TObjectIterator<UUserWidget> It; It; ++It)
	{
		UUserWidget* W = *It;
		if (W->GetWorld() == PlayWorld && W->IsInViewport())
		{
			if (UProgressBar* HBar = Cast<UProgressBar>(W->GetWidgetFromName(FName(TEXT("HealthBar")))))
			{
				HBar->SetPercent(Comp->Health / Comp->MaxHealth);
				UpdatedWidgets++;
			}
			if (UTextBlock* HLabel = Cast<UTextBlock>(W->GetWidgetFromName(FName(TEXT("HealthLabel")))))
			{
				HLabel->SetText(FText::FromString(FString::Printf(TEXT("HEALTH: %d / %d"), (int32)Comp->Health, (int32)Comp->MaxHealth)));
				UpdatedWidgets++;
			}
			if (UProgressBar* SBar = Cast<UProgressBar>(W->GetWidgetFromName(FName(TEXT("StaminaBar")))))
			{
				SBar->SetPercent(Comp->Stamina / Comp->MaxStamina);
				UpdatedWidgets++;
			}
			if (UTextBlock* SLabel = Cast<UTextBlock>(W->GetWidgetFromName(FName(TEXT("StaminaLabel")))))
			{
				SLabel->SetText(FText::FromString(FString::Printf(TEXT("STAMINA: %d / %d"), (int32)Comp->Stamina, (int32)Comp->MaxStamina)));
				UpdatedWidgets++;
			}

			if (Comp->ActiveMenuState.Equals(TEXT("Closed"), ESearchCase::IgnoreCase) && W->GetName().Contains(TEXT("Menu")))
			{
				W->SetVisibility(ESlateVisibility::Collapsed);
			}
		}
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetNumberField(TEXT("before_health"), BeforeH);
	Data->SetNumberField(TEXT("after_health"), Comp->Health);
	Data->SetNumberField(TEXT("max_health"), Comp->MaxHealth);
	Data->SetNumberField(TEXT("before_stamina"), BeforeS);
	Data->SetNumberField(TEXT("after_stamina"), Comp->Stamina);
	Data->SetNumberField(TEXT("max_stamina"), Comp->MaxStamina);
	Data->SetStringField(TEXT("before_menu_state"), BeforeM);
	Data->SetStringField(TEXT("after_menu_state"), Comp->ActiveMenuState);
	Data->SetStringField(TEXT("last_executed_action"), Comp->LastExecutedAction);
	Data->SetNumberField(TEXT("updated_widgets_count"), UpdatedWidgets);

	return MakeEnvelope(true, Data);
}

