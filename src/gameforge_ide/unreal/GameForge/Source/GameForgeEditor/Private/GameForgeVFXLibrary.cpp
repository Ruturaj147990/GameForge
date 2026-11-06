// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeVFXLibrary.h"
#include "NiagaraComponent.h"
#include "NiagaraEmitterInstance.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "NiagaraSystemInstance.h"
#include "NiagaraSystemInstanceController.h"
#include "Editor.h"
#include "Engine/World.h"
#include "UObject/UObjectIterator.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	const TCHAR* VFXLabelTagPrefix = TEXT("GF_VFX:");

	FString VFXEnvelope(bool bSuccess, TSharedPtr<FJsonObject> Data, const TArray<FString>& Errors = {})
	{
		TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
		Root->SetBoolField(TEXT("success"), bSuccess);
		Root->SetObjectField(TEXT("data"), Data.IsValid() ? Data : MakeShared<FJsonObject>());
		TArray<TSharedPtr<FJsonValue>> ErrorValues;
		for (const FString& E : Errors)
		{
			ErrorValues.Add(MakeShared<FJsonValueString>(E));
		}
		Root->SetArrayField(TEXT("errors"), ErrorValues);
		FString Out;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
		FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
		return Out;
	}

	TSharedPtr<FJsonObject> VFXParseJson(const FString& Json)
	{
		TSharedPtr<FJsonObject> Obj;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
		if (!FJsonSerializer::Deserialize(Reader, Obj))
		{
			return nullptr;
		}
		return Obj;
	}

	UWorld* ResolveWorld(const TSharedPtr<FJsonObject>& Params)
	{
		const FString Which = Params->HasField(TEXT("world")) ? Params->GetStringField(TEXT("world")) : TEXT("editor");
		if (!GEditor)
		{
			return nullptr;
		}
		if (Which.Equals(TEXT("pie"), ESearchCase::IgnoreCase))
		{
			return GEditor->PlayWorld;
		}
		return GEditor->GetEditorWorldContext().World();
	}
}

FString UGameForgeVFXLibrary::SpawnSystem(const FString& ParamsJson)
{
	const TSharedPtr<FJsonObject> Params = VFXParseJson(ParamsJson);
	if (!Params.IsValid())
	{
		return VFXEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}
	UWorld* World = ResolveWorld(Params);
	if (!World)
	{
		return VFXEnvelope(false, nullptr, {TEXT("Requested world is not running (start PIE for world=pie).")});
	}
	const FString SystemPath = Params->GetStringField(TEXT("system_path"));
	UNiagaraSystem* System = LoadObject<UNiagaraSystem>(nullptr, *SystemPath);
	if (!System)
	{
		return VFXEnvelope(false, nullptr, {FString::Printf(TEXT("Not a NiagaraSystem: %s"), *SystemPath)});
	}
	FVector Location = FVector::ZeroVector;
	const TSharedPtr<FJsonObject>* Loc = nullptr;
	if (Params->TryGetObjectField(TEXT("location"), Loc) && Loc)
	{
		Location = FVector((*Loc)->GetNumberField(TEXT("x")), (*Loc)->GetNumberField(TEXT("y")), (*Loc)->GetNumberField(TEXT("z")));
	}
	UNiagaraComponent* Comp = UNiagaraFunctionLibrary::SpawnSystemAtLocation(World, System, Location, FRotator::ZeroRotator,
		FVector(1.0f), /*bAutoDestroy=*/false, /*bAutoActivate=*/true, ENCPoolMethod::None, /*bPreCullCheck=*/false);
	if (!Comp)
	{
		return VFXEnvelope(false, nullptr, {TEXT("SpawnSystemAtLocation returned null.")});
	}
	const FString Label = Params->HasField(TEXT("label")) ? Params->GetStringField(TEXT("label")) : TEXT("GF_VFX");
	Comp->ComponentTags.Add(FName(*(FString(VFXLabelTagPrefix) + Label)));
	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("label"), Label);
	Data->SetStringField(TEXT("system"), System->GetPathName());
	Data->SetStringField(TEXT("world"), World->GetName());
	Data->SetBoolField(TEXT("active"), Comp->IsActive());
	return VFXEnvelope(true, Data);
}

FString UGameForgeVFXLibrary::InspectParticles(const FString& ParamsJson)
{
	const TSharedPtr<FJsonObject> Params = VFXParseJson(ParamsJson.IsEmpty() ? TEXT("{}") : ParamsJson);
	if (!Params.IsValid())
	{
		return VFXEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}
	UWorld* World = ResolveWorld(Params);
	if (!World)
	{
		return VFXEnvelope(false, nullptr, {TEXT("Requested world is not running.")});
	}
	const FString Filter = Params->HasField(TEXT("label")) ? Params->GetStringField(TEXT("label")) : TEXT("");
	TArray<TSharedPtr<FJsonValue>> Components;
	int64 Total = 0;
	for (TObjectIterator<UNiagaraComponent> It; It; ++It)
	{
		UNiagaraComponent* Comp = *It;
		if (!IsValid(Comp) || Comp->GetWorld() != World)
		{
			continue;
		}
		FString Label;
		for (const FName& Tag : Comp->ComponentTags)
		{
			const FString TagString = Tag.ToString();
			if (TagString.StartsWith(VFXLabelTagPrefix))
			{
				Label = TagString.RightChop(FCString::Strlen(VFXLabelTagPrefix));
			}
		}
		if (!Filter.IsEmpty() && Label != Filter)
		{
			continue;
		}
		TSharedPtr<FJsonObject> C = MakeShared<FJsonObject>();
		C->SetStringField(TEXT("label"), Label);
		C->SetStringField(TEXT("system"), Comp->GetAsset() ? Comp->GetAsset()->GetPathName() : TEXT(""));
		C->SetBoolField(TEXT("active"), Comp->IsActive());
		TArray<TSharedPtr<FJsonValue>> Emitters;
		int64 CompTotal = 0;
		FNiagaraSystemInstanceControllerPtr Controller = Comp->GetSystemInstanceController();
		if (Controller.IsValid())
		{
			if (FNiagaraSystemInstance* Instance = Controller->GetSystemInstance_Unsafe())
			{
				for (const FNiagaraEmitterInstanceRef& Emitter : Instance->GetEmitters())
				{
					TSharedPtr<FJsonObject> E = MakeShared<FJsonObject>();
					const int32 Num = Emitter->GetNumParticles();
					E->SetStringField(TEXT("name"), Emitter->GetEmitterHandle().GetName().ToString());
					E->SetStringField(TEXT("sim_target"), Emitter->GetSimTarget() == ENiagaraSimTarget::GPUComputeSim ? TEXT("GPU") : TEXT("CPU"));
					E->SetNumberField(TEXT("particles"), Num);
					CompTotal += Num;
					Emitters.Add(MakeShared<FJsonValueObject>(E));
				}
			}
		}
		C->SetArrayField(TEXT("emitters"), Emitters);
		C->SetNumberField(TEXT("particles"), (double)CompTotal);
		Total += CompTotal;
		Components.Add(MakeShared<FJsonValueObject>(C));
	}
	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("world"), World->GetName());
	Data->SetArrayField(TEXT("components"), Components);
	Data->SetNumberField(TEXT("total_particles"), (double)Total);
	return VFXEnvelope(Components.Num() > 0, Data, Components.Num() > 0 ? TArray<FString>() : TArray<FString>{TEXT("no Niagara components in that world")});
}
