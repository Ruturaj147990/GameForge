// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeLandscapeLibrary.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "LandscapeComponent.h"
#include "LandscapeEdit.h"
#include "LandscapeLayerInfoObject.h"
#include "LandscapeUtils.h"
#include "Components/SplineComponent.h"
#include "Components/SplineMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "NavMesh/NavMeshBoundsVolume.h"
#include "Materials/MaterialInterface.h"
#include "Engine/StaticMesh.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	FString MakeLandscapeJsonString(TSharedPtr<FJsonObject> JsonObj)
	{
		FString Output;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
		FJsonSerializer::Serialize(JsonObj.ToSharedRef(), Writer);
		return Output;
	}

	FString MakeLandscapeEnvelope(bool bSuccess, TSharedPtr<FJsonObject> Data, const TArray<FString>& Errors = {}, const TArray<FString>& Warnings = {})
	{
		TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
		Root->SetBoolField(TEXT("success"), bSuccess);
		Root->SetObjectField(TEXT("data"), Data.IsValid() ? Data : MakeShared<FJsonObject>());

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

		return MakeLandscapeJsonString(Root);
	}

	UWorld* GetActiveEditorWorld()
	{
		if (GEditor && GEditor->GetEditorWorldContext().World())
		{
			return GEditor->GetEditorWorldContext().World();
		}
		if (GEngine)
		{
			for (const FWorldContext& Context : GEngine->GetWorldContexts())
			{
				if (Context.WorldType == EWorldType::Editor && Context.World())
				{
					return Context.World();
				}
				if (Context.WorldType == EWorldType::PIE && Context.World())
				{
					return Context.World();
				}
			}
		}
		return nullptr;
	}

	float CoherentNoise(float X, float Y, int32 Seed)
	{
		float Val = FMath::Sin(X * 12.9898f + Y * 78.233f + (float)Seed * 1.57f) * 43758.5453f;
		return Val - FMath::FloorToFloat(Val);
	}

	float SmoothNoise(float X, float Y, int32 Seed)
	{
		float IntX = FMath::FloorToFloat(X);
		float FracX = X - IntX;
		float IntY = FMath::FloorToFloat(Y);
		float FracY = Y - IntY;

		float Sx = FracX * FracX * (3.0f - 2.0f * FracX);
		float Sy = FracY * FracY * (3.0f - 2.0f * FracY);

		float V00 = CoherentNoise(IntX, IntY, Seed);
		float V10 = CoherentNoise(IntX + 1.0f, IntY, Seed);
		float V01 = CoherentNoise(IntX, IntY + 1.0f, Seed);
		float V11 = CoherentNoise(IntX + 1.0f, IntY + 1.0f, Seed);

		float InterpX0 = FMath::Lerp(V00, V10, Sx);
		float InterpX1 = FMath::Lerp(V01, V11, Sx);
		return FMath::Lerp(InterpX0, InterpX1, Sy);
	}

	float MultiOctaveFBM(float X, float Y, int32 Seed, int32 Octaves)
	{
		float Total = 0.0f;
		float Frequency = 1.0f;
		float Amplitude = 1.0f;
		float MaxAmp = 0.0f;
		for (int32 O = 0; O < Octaves; ++O)
		{
			Total += SmoothNoise(X * Frequency, Y * Frequency, Seed + O * 37) * Amplitude;
			MaxAmp += Amplitude;
			Frequency *= 2.0f;
			Amplitude *= 0.5f;
		}
		return Total / FMath::Max(0.001f, MaxAmp);
	}
}

FString UGameForgeLandscapeLibrary::CreateLandscape(const FString& ParamsJson)
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}

	TSharedPtr<FJsonObject> Json;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}

	const int32 ComponentCountX = Json->HasField(TEXT("component_count_x")) ? Json->GetIntegerField(TEXT("component_count_x")) : 2;
	const int32 ComponentCountY = Json->HasField(TEXT("component_count_y")) ? Json->GetIntegerField(TEXT("component_count_y")) : 2;
	const int32 QuadsPerSection = Json->HasField(TEXT("quads_per_section")) ? Json->GetIntegerField(TEXT("quads_per_section")) : 63;
	const int32 SectionsPerComponent = Json->HasField(TEXT("sections_per_component")) ? Json->GetIntegerField(TEXT("sections_per_component")) : 1;
	const float ElevationScale = Json->HasField(TEXT("elevation_scale")) ? (float)Json->GetNumberField(TEXT("elevation_scale")) : 2000.0f;
	const int32 Seed = Json->HasField(TEXT("seed")) ? Json->GetIntegerField(TEXT("seed")) : 1337;
	const FString TerrainType = Json->HasField(TEXT("terrain_type")) ? Json->GetStringField(TEXT("terrain_type")) : TEXT("Valley");
	const FString MaterialPath = Json->HasField(TEXT("material_path")) ? Json->GetStringField(TEXT("material_path")) : TEXT("");

	const int32 SizeX = ComponentCountX * SectionsPerComponent * QuadsPerSection + 1;
	const int32 SizeY = ComponentCountY * SectionsPerComponent * QuadsPerSection + 1;

	TArray<uint16> HeightData;
	HeightData.SetNumUninitialized(SizeX * SizeY);
	TArray<float> HeightNormData;
	HeightNormData.SetNumUninitialized(SizeX * SizeY);

	float MinElevFound = 99999.0f;
	float MaxElevFound = -99999.0f;

	for (int32 Y = 0; Y < SizeY; ++Y)
	{
		const float NY = (float)Y / (float)(SizeY - 1);
		for (int32 X = 0; X < SizeX; ++X)
		{
			const float NX = (float)X / (float)(SizeX - 1);

			float NoiseVal = MultiOctaveFBM(NX * 3.5f, NY * 3.5f, Seed, 4);
			float HeightNorm = NoiseVal;

			if (TerrainType.Equals(TEXT("Valley"), ESearchCase::IgnoreCase))
			{
				const float ValleyProfile = FMath::Square((NX - 0.5f) * 2.0f);
				HeightNorm = (ValleyProfile * 0.65f + NoiseVal * 0.35f);
			}
			else if (TerrainType.Equals(TEXT("Mountains"), ESearchCase::IgnoreCase))
			{
				HeightNorm = 1.0f - FMath::Abs(NoiseVal * 2.0f - 1.0f);
			}
			else if (TerrainType.Equals(TEXT("Plateau"), ESearchCase::IgnoreCase))
			{
				float Stepped = FMath::FloorToFloat(NoiseVal * 3.0f) / 3.0f;
				HeightNorm = Stepped * 0.8f + NoiseVal * 0.2f;
			}

			// Map to Unreal Engine uint16 heightfield (32768 is Z=0 cm)
			const float HeightDeltaRaw = (HeightNorm - 0.5f) * (ElevationScale * 128.0f / 100.0f);
			const int32 ClampedVal = FMath::Clamp((int32)(32768.0f + HeightDeltaRaw), 1000, 64500);
			HeightData[X + Y * SizeX] = (uint16)ClampedVal;
			HeightNormData[X + Y * SizeX] = HeightNorm;

			const float ActualZ = (float)(ClampedVal - 32768) * (100.0f / 128.0f);
			MinElevFound = FMath::Min(MinElevFound, ActualZ);
			MaxElevFound = FMath::Max(MaxElevFound, ActualZ);
		}
	}

	TMap<FGuid, TArray<uint16>> HeightDataPerLayers;
	FGuid LayerGuid = FGuid(); // Default Guid required by ALandscapeProxy::Import FinalLayerGuid
	HeightDataPerLayers.Add(LayerGuid, HeightData);

	const FVector Scale(100.0f, 100.0f, 100.0f);
	const FVector OriginOffset(-(SizeX - 1) * Scale.X * 0.5f, -(SizeY - 1) * Scale.Y * 0.5f, 0.0f);

	FActorSpawnParameters SpawnParams;
	// A fixed name is fatal once a previous landscape was destroyed in this level (the name stays reserved), so
	// ask the level for a unique one.
	SpawnParams.Name = MakeUniqueObjectName(World->PersistentLevel, ALandscape::StaticClass(), FName(TEXT("Landscape_ProceduralWorld")));
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	ALandscape* Landscape = World->SpawnActor<ALandscape>(OriginOffset, FRotator::ZeroRotator, SpawnParams);
	if (!Landscape)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to spawn ALandscape actor in world.")});
	}

	Landscape->SetActorRelativeScale3D(Scale);

	if (!MaterialPath.IsEmpty())
	{
		if (UMaterialInterface* Mat = Cast<UMaterialInterface>(StaticLoadObject(UMaterialInterface::StaticClass(), nullptr, *MaterialPath)))
		{
			Landscape->LandscapeMaterial = Mat;
		}
	}

	// Optional paint layers: "paint_layers": [{"name": "Grass", "rule": "low"}, {"name": "Rock", "rule": "steep"},
	// {"name": "Snow", "rule": "high"}]. Weights are derived from the generated heightfield (height and slope) and
	// normalised so every vertex sums to 255, as weight-blended landscape layers require.
	TArray<FLandscapeImportLayerInfo> ImportLayers;
	TArray<FString> LayerWarnings;
	const TArray<TSharedPtr<FJsonValue>>* LayerSpecs = nullptr;
	if (Json->TryGetArrayField(TEXT("paint_layers"), LayerSpecs) && LayerSpecs && LayerSpecs->Num() > 0)
	{
		const FString LayerFolder = Json->HasField(TEXT("layer_info_path")) ? Json->GetStringField(TEXT("layer_info_path")) : TEXT("/Game/Landscape/LayerInfo");
		const float HighStart = Json->HasField(TEXT("high_start")) ? (float)Json->GetNumberField(TEXT("high_start")) : 0.72f;
		const float SteepStart = Json->HasField(TEXT("steep_start_cm_per_quad")) ? (float)Json->GetNumberField(TEXT("steep_start_cm_per_quad")) : 45.0f;

		TArray<FString> Rules;
		for (const TSharedPtr<FJsonValue>& Value : *LayerSpecs)
		{
			const TSharedPtr<FJsonObject> Spec = Value->AsObject();
			if (!Spec.IsValid() || !Spec->HasField(TEXT("name")))
			{
				continue;
			}
			const FString LayerName = Spec->GetStringField(TEXT("name"));
			FLandscapeImportLayerInfo Info = FLandscapeImportLayerInfo(FName(*LayerName));
			Info.LayerInfo = UE::Landscape::CreateTargetLayerInfo(FName(*LayerName), LayerFolder, FString::Printf(TEXT("LI_%s"), *LayerName));
			Info.LayerData.SetNumZeroed(SizeX * SizeY);
			ImportLayers.Add(Info);
			Rules.Add(Spec->HasField(TEXT("rule")) ? Spec->GetStringField(TEXT("rule")) : TEXT("low"));
		}

		const float CmPerUnit = 100.0f / 128.0f;
		for (int32 Y = 0; Y < SizeY; ++Y)
		{
			for (int32 X = 0; X < SizeX; ++X)
			{
				const int32 I = X + Y * SizeX;
				const float DX = ((float)HeightData[FMath::Min(X + 1, SizeX - 1) + Y * SizeX] - (float)HeightData[FMath::Max(X - 1, 0) + Y * SizeX]) * 0.5f * CmPerUnit;
				const float DY = ((float)HeightData[X + FMath::Min(Y + 1, SizeY - 1) * SizeX] - (float)HeightData[X + FMath::Max(Y - 1, 0) * SizeX]) * 0.5f * CmPerUnit;
				const float Slope = FMath::Sqrt(DX * DX + DY * DY); // cm of rise per 100 cm quad
				const float High = FMath::SmoothStep(HighStart, HighStart + 0.12f, HeightNormData[I]);
				const float Steep = FMath::SmoothStep(SteepStart, SteepStart * 2.0f, Slope) * (1.0f - High);
				const float Low = FMath::Max(0.0f, 1.0f - High - Steep);

				TArray<float> Raw;
				float Sum = 0.0f;
				for (const FString& Rule : Rules)
				{
					const float W = Rule.Equals(TEXT("high")) ? High : Rule.Equals(TEXT("steep")) ? Steep : Low;
					Raw.Add(W);
					Sum += W;
				}
				int32 Assigned = 0;
				for (int32 L = 0; L < Raw.Num(); ++L)
				{
					const int32 W = (L == Raw.Num() - 1) ? 255 - Assigned
						: (Sum > KINDA_SMALL_NUMBER ? FMath::RoundToInt(255.0f * Raw[L] / Sum) : (L == 0 ? 255 : 0));
					ImportLayers[L].LayerData[I] = (uint8)FMath::Clamp(W, 0, 255);
					Assigned += ImportLayers[L].LayerData[I];
				}
			}
		}
	}

	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayerDataPerLayers;
	MaterialLayerDataPerLayers.Add(LayerGuid, ImportLayers);
	Landscape->Import(FGuid::NewGuid(), 0, 0, SizeX - 1, SizeY - 1, SectionsPerComponent, QuadsPerSection,
	                  HeightDataPerLayers, TEXT(""), MaterialLayerDataPerLayers,
	                  ELandscapeImportAlphamapType::Additive, TArrayView<const FLandscapeLayer>());

	if (ULandscapeInfo* Info = Landscape->GetLandscapeInfo())
	{
		Info->UpdateLayerInfoMap(Landscape);
		// Register each imported layer as a target layer (as the editor's New Landscape tool does) so it shows
		// in Paint mode and the material's LandscapeLayerBlend can find it.
		for (const FLandscapeImportLayerInfo& Layer : ImportLayers)
		{
			if (!Layer.LayerInfo)
			{
				LayerWarnings.Add(FString::Printf(TEXT("layer %s has no layer info asset"), *Layer.LayerName.ToString()));
				continue;
			}
			Landscape->AddTargetLayer(Layer.LayerInfo->GetLayerName(), FLandscapeTargetLayerSettings(Layer.LayerInfo));
			const int32 Index = Info->GetLayerInfoIndex(Layer.LayerName);
			if (Index != INDEX_NONE)
			{
				Info->Layers[Index].LayerInfoObj = Layer.LayerInfo;
			}
			else
			{
				Info->Layers.Add(FLandscapeInfoLayerSettings(Layer.LayerInfo, Landscape));
			}
			Layer.LayerInfo->MarkPackageDirty();
		}
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	TArray<TSharedPtr<FJsonValue>> LayerNames;
	for (const FLandscapeImportLayerInfo& Layer : ImportLayers)
	{
		LayerNames.Add(MakeShared<FJsonValueString>(Layer.LayerName.ToString()));
	}
	Data->SetArrayField(TEXT("paint_layers"), LayerNames);
	Data->SetStringField(TEXT("actor_name"), Landscape->GetName());
	Data->SetStringField(TEXT("actor_label"), Landscape->GetActorLabel());
	Data->SetNumberField(TEXT("size_x"), SizeX);
	Data->SetNumberField(TEXT("size_y"), SizeY);
	Data->SetNumberField(TEXT("component_count_x"), ComponentCountX);
	Data->SetNumberField(TEXT("component_count_y"), ComponentCountY);
	Data->SetNumberField(TEXT("quads_per_section"), QuadsPerSection);
	Data->SetNumberField(TEXT("vertex_count"), SizeX * SizeY);
	Data->SetNumberField(TEXT("min_elevation_cm"), MinElevFound);
	Data->SetNumberField(TEXT("max_elevation_cm"), MaxElevFound);
	Data->SetNumberField(TEXT("elevation_range_cm"), MaxElevFound - MinElevFound);
	Data->SetNumberField(TEXT("seed"), Seed);
	Data->SetStringField(TEXT("terrain_type"), TerrainType);

	return MakeLandscapeEnvelope(true, Data, {}, LayerWarnings);
}

FString UGameForgeLandscapeLibrary::AddPaintLayer(const FString& ParamsJson)
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}

	TSharedPtr<FJsonObject> Json;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}

	const FString LayerNameStr = Json->HasField(TEXT("layer_name")) ? Json->GetStringField(TEXT("layer_name"))
		: (Json->HasField(TEXT("name")) ? Json->GetStringField(TEXT("name")) : TEXT("Grass"));
	const FString LayerFolder = Json->HasField(TEXT("layer_info_path")) ? Json->GetStringField(TEXT("layer_info_path")) : TEXT("/Game/Landscape/LayerInfo");

	ALandscape* Landscape = nullptr;
	for (TActorIterator<ALandscape> It(World); It; ++It)
	{
		Landscape = *It;
		break;
	}
	if (!Landscape)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No ALandscape found in world.")});
	}

	ULandscapeInfo* Info = Landscape->GetLandscapeInfo();
	if (!Info)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Landscape has no ULandscapeInfo.")});
	}

	const FName LayerFName(*LayerNameStr);
	ULandscapeLayerInfoObject* LayerInfo = UE::Landscape::CreateTargetLayerInfo(LayerFName, LayerFolder, FString::Printf(TEXT("LI_%s"), *LayerNameStr));
	if (!LayerInfo)
	{
		return MakeLandscapeEnvelope(false, nullptr, {FString::Printf(TEXT("Failed to create ULandscapeLayerInfoObject for '%s'."), *LayerNameStr)});
	}

	Landscape->AddTargetLayer(LayerInfo->GetLayerName(), FLandscapeTargetLayerSettings(LayerInfo));
	Info->UpdateLayerInfoMap(Landscape);
	const int32 ExistingIdx = Info->GetLayerInfoIndex(LayerFName);
	if (ExistingIdx != INDEX_NONE)
	{
		Info->Layers[ExistingIdx].LayerInfoObj = LayerInfo;
	}
	else
	{
		Info->Layers.Add(FLandscapeInfoLayerSettings(LayerInfo, Landscape));
	}
	LayerInfo->MarkPackageDirty();

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("landscape"), Landscape->GetActorLabel());
	Data->SetStringField(TEXT("layer_name"), LayerNameStr);
	Data->SetStringField(TEXT("layer_info_path"), LayerInfo->GetPathName());
	Data->SetNumberField(TEXT("total_layers"), Info->Layers.Num());
	return MakeLandscapeEnvelope(true, Data);
}

FString UGameForgeLandscapeLibrary::InspectLandscapeLayers()
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}
	ALandscape* Landscape = nullptr;
	for (TActorIterator<ALandscape> It(World); It; ++It)
	{
		Landscape = *It;
		break;
	}
	ULandscapeInfo* Info = Landscape ? Landscape->GetLandscapeInfo() : nullptr;
	if (!Info)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No landscape in the editor world.")});
	}
	int32 MinX = 0, MinY = 0, MaxX = 0, MaxY = 0;
	if (!Info->GetLandscapeExtent(MinX, MinY, MaxX, MaxY))
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Landscape has no extent.")});
	}
	const int32 W = MaxX - MinX + 1;
	const int32 H = MaxY - MinY + 1;
	FLandscapeEditDataInterface Edit(Info);
	TArray<TSharedPtr<FJsonValue>> Layers;
	for (const FLandscapeInfoLayerSettings& Settings : Info->Layers)
	{
		TSharedPtr<FJsonObject> L = MakeShared<FJsonObject>();
		L->SetStringField(TEXT("name"), Settings.GetLayerName().ToString());
		L->SetStringField(TEXT("layer_info"), Settings.LayerInfoObj ? Settings.LayerInfoObj->GetPathName() : TEXT(""));
		if (Settings.LayerInfoObj)
		{
			TArray<uint8> Weights;
			Weights.SetNumZeroed(W * H);
			int32 X1 = MinX, Y1 = MinY, X2 = MaxX, Y2 = MaxY;
			Edit.GetWeightData(Settings.LayerInfoObj, X1, Y1, X2, Y2, Weights.GetData(), 0);
			double Sum = 0.0;
			int32 Dominant = 0;
			for (uint8 V : Weights)
			{
				Sum += V;
				Dominant += V > 127 ? 1 : 0;
			}
			L->SetNumberField(TEXT("mean_weight"), Weights.Num() ? Sum / Weights.Num() : 0.0);
			L->SetNumberField(TEXT("dominant_fraction"), Weights.Num() ? (double)Dominant / Weights.Num() : 0.0);
		}
		Layers.Add(MakeShared<FJsonValueObject>(L));
	}
	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("landscape"), Landscape->GetActorLabel());
	Data->SetStringField(TEXT("material"), Landscape->LandscapeMaterial ? Landscape->LandscapeMaterial->GetPathName() : TEXT(""));
	Data->SetNumberField(TEXT("vertices"), W * H);
	Data->SetArrayField(TEXT("layers"), Layers);
	return MakeLandscapeEnvelope(Layers.Num() > 0, Data, Layers.Num() > 0 ? TArray<FString>() : TArray<FString>{TEXT("landscape has no paint layers")});
}

FString UGameForgeLandscapeLibrary::CreateSplineRoad(const FString& ParamsJson)
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}

	TSharedPtr<FJsonObject> Json;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}

	const FString RoadName = Json->HasField(TEXT("road_name")) ? Json->GetStringField(TEXT("road_name")) : TEXT("Road_MainTrail");
	const float RoadWidth = Json->HasField(TEXT("road_width")) ? (float)Json->GetNumberField(TEXT("road_width")) : 400.0f;
	const FString MeshPath = Json->HasField(TEXT("mesh_path")) ? Json->GetStringField(TEXT("mesh_path")) : TEXT("/Engine/BasicShapes/Cube.Cube");
	const FString MaterialPath = Json->HasField(TEXT("material_path")) ? Json->GetStringField(TEXT("material_path"))
		: (Json->HasField(TEXT("road_material")) ? Json->GetStringField(TEXT("road_material")) : TEXT(""));

	UStaticMesh* RoadMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, *MeshPath));
	if (!RoadMesh)
	{
		RoadMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	}

	UMaterialInterface* RoadMat = nullptr;
	if (!MaterialPath.IsEmpty())
	{
		RoadMat = Cast<UMaterialInterface>(StaticLoadObject(UMaterialInterface::StaticClass(), nullptr, *MaterialPath));
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.Name = MakeUniqueObjectName(World->PersistentLevel, AActor::StaticClass(), FName(*RoadName));
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AActor* SplineActor = World->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
	if (!SplineActor)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to spawn spline road actor.")});
	}

	USceneComponent* RootComp = NewObject<USceneComponent>(SplineActor, TEXT("RootSceneComponent"));
	SplineActor->SetRootComponent(RootComp);
	RootComp->RegisterComponent();

	USplineComponent* SplineComp = NewObject<USplineComponent>(SplineActor, TEXT("SplineComponent"));
	SplineComp->AttachToComponent(RootComp, FAttachmentTransformRules::KeepRelativeTransform);
	SplineComp->ClearSplinePoints(false);

	TArray<FVector> Points;
	const TArray<TSharedPtr<FJsonValue>>* PointsArr = nullptr;
	if (Json->TryGetArrayField(TEXT("points"), PointsArr) && PointsArr)
	{
		for (const TSharedPtr<FJsonValue>& Val : *PointsArr)
		{
			TSharedPtr<FJsonObject> PtObj = Val->AsObject();
			if (PtObj.IsValid())
			{
				float X = (float)PtObj->GetNumberField(TEXT("x"));
				float Y = (float)PtObj->GetNumberField(TEXT("y"));
				float Z = (float)PtObj->GetNumberField(TEXT("z"));
				Points.Add(FVector(X, Y, Z));
			}
		}
	}

	if (Points.Num() < 2)
	{
		// Default scenic winding trail from south to north
		Points = {
			FVector(-2500.0f, -2000.0f, 150.0f),
			FVector(-1200.0f, -800.0f, 220.0f),
			FVector(0.0f, 0.0f, 280.0f),
			FVector(1400.0f, 800.0f, 350.0f),
			FVector(2500.0f, 2000.0f, 420.0f)
		};
	}

	for (int32 I = 0; I < Points.Num(); ++I)
	{
		SplineComp->AddSplinePoint(Points[I], ESplineCoordinateSpace::World, false);
		SplineComp->SetSplinePointType(I, ESplinePointType::Curve, false);
	}
	SplineComp->UpdateSpline();
	SplineComp->RegisterComponent();
	SplineActor->AddInstanceComponent(SplineComp);

	int32 SegmentCount = 0;
	for (int32 I = 0; I < SplineComp->GetNumberOfSplinePoints() - 1; ++I)
	{
		FVector StartPos, StartTan, EndPos, EndTan;
		SplineComp->GetLocationAndTangentAtSplinePoint(I, StartPos, StartTan, ESplineCoordinateSpace::World);
		SplineComp->GetLocationAndTangentAtSplinePoint(I + 1, EndPos, EndTan, ESplineCoordinateSpace::World);

		USplineMeshComponent* SMC = NewObject<USplineMeshComponent>(SplineActor, FName(*FString::Printf(TEXT("SplineMesh_%d"), I)));
		SMC->SetMobility(EComponentMobility::Movable);
		SMC->AttachToComponent(SplineComp, FAttachmentTransformRules::KeepWorldTransform);
		if (RoadMesh) SMC->SetStaticMesh(RoadMesh);
		if (RoadMat) SMC->SetMaterial(0, RoadMat);

		SMC->SetStartAndEnd(StartPos, StartTan, EndPos, EndTan, true);
		SMC->SetStartScale(FVector2D(RoadWidth / 100.0f, 0.15f));
		SMC->SetEndScale(FVector2D(RoadWidth / 100.0f, 0.15f));
		SMC->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		SMC->SetCollisionResponseToAllChannels(ECR_Block);
		SMC->RegisterComponent();
		SplineActor->AddInstanceComponent(SMC);
		SegmentCount++;
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("actor_name"), SplineActor->GetName());
	Data->SetNumberField(TEXT("point_count"), SplineComp->GetNumberOfSplinePoints());
	Data->SetNumberField(TEXT("segment_count"), SegmentCount);
	Data->SetNumberField(TEXT("total_length_cm"), SplineComp->GetSplineLength());
	Data->SetNumberField(TEXT("road_width_cm"), RoadWidth);

	return MakeLandscapeEnvelope(true, Data);
}

FString UGameForgeLandscapeLibrary::CreateFoliageScatter(const FString& ParamsJson)
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}

	TSharedPtr<FJsonObject> Json;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}

	const FString ClusterName = Json->HasField(TEXT("cluster_name")) ? Json->GetStringField(TEXT("cluster_name")) : TEXT("Foliage_PineForest");
	FString MeshPath = Json->HasField(TEXT("mesh_path")) ? Json->GetStringField(TEXT("mesh_path"))
		: (Json->HasField(TEXT("static_mesh")) ? Json->GetStringField(TEXT("static_mesh")) : TEXT(""));
	if (MeshPath.IsEmpty())
	{
		MeshPath = TEXT("/Engine/BasicShapes/Cylinder.Cylinder");
	}
	const FString MaterialPath = Json->HasField(TEXT("material_path")) ? Json->GetStringField(TEXT("material_path")) : TEXT("");
	const int32 TargetCount = Json->HasField(TEXT("instance_count")) ? Json->GetIntegerField(TEXT("instance_count")) : 60;
	const int32 Seed = Json->HasField(TEXT("seed")) ? Json->GetIntegerField(TEXT("seed")) : 777;
	const float AreaRadius = Json->HasField(TEXT("area_radius")) ? (float)Json->GetNumberField(TEXT("area_radius")) : 3500.0f;
	const float MinElevation = Json->HasField(TEXT("min_elevation")) ? (float)Json->GetNumberField(TEXT("min_elevation")) : -500.0f;
	const float MaxElevation = Json->HasField(TEXT("max_elevation")) ? (float)Json->GetNumberField(TEXT("max_elevation")) : 2500.0f;
	const float MaxSlopeDegrees = Json->HasField(TEXT("max_slope_degrees")) ? (float)Json->GetNumberField(TEXT("max_slope_degrees")) : 35.0f;
	const float RoadClearance = Json->HasField(TEXT("road_clearance")) ? (float)Json->GetNumberField(TEXT("road_clearance")) : 450.0f;

	UStaticMesh* FoliageMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, *MeshPath));
	if (!FoliageMesh)
	{
		FoliageMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")));
	}

	UMaterialInterface* FoliageMat = nullptr;
	if (!MaterialPath.IsEmpty())
	{
		FoliageMat = Cast<UMaterialInterface>(StaticLoadObject(UMaterialInterface::StaticClass(), nullptr, *MaterialPath));
	}

	TArray<USplineComponent*> Splines;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (USplineComponent* SC = It->FindComponentByClass<USplineComponent>())
		{
			Splines.Add(SC);
		}
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.Name = MakeUniqueObjectName(World->PersistentLevel, AActor::StaticClass(), FName(*ClusterName));
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AActor* ClusterActor = World->SpawnActor<AActor>(AActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, SpawnParams);
	if (!ClusterActor)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to spawn foliage cluster actor.")});
	}

	USceneComponent* RootComp = NewObject<USceneComponent>(ClusterActor, TEXT("RootComponent"));
	ClusterActor->SetRootComponent(RootComp);
	RootComp->RegisterComponent();

	UHierarchicalInstancedStaticMeshComponent* HISM = NewObject<UHierarchicalInstancedStaticMeshComponent>(ClusterActor, TEXT("HISM_Component"));
	HISM->AttachToComponent(RootComp, FAttachmentTransformRules::KeepRelativeTransform);
	if (FoliageMesh) HISM->SetStaticMesh(FoliageMesh);
	if (FoliageMat) HISM->SetMaterial(0, FoliageMat);
	HISM->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	HISM->SetCollisionResponseToAllChannels(ECR_Block);
	HISM->RegisterComponent();
	ClusterActor->AddInstanceComponent(HISM);

	FRandomStream Rng(Seed);
	int32 SpawnedCount = 0;
	const int32 MaxAttempts = TargetCount * 6;

	for (int32 Attempt = 0; Attempt < MaxAttempts && SpawnedCount < TargetCount; ++Attempt)
	{
		const float Angle = Rng.FRandRange(0.0f, 2.0f * PI);
		const float Dist = FMath::Sqrt(Rng.FRand()) * AreaRadius;
		const float X = FMath::Cos(Angle) * Dist;
		const float Y = FMath::Sin(Angle) * Dist;

		bool bTooCloseToRoad = false;
		for (USplineComponent* SC : Splines)
		{
			FVector ClosestPt = SC->FindLocationClosestToWorldLocation(FVector(X, Y, 0.0f), ESplineCoordinateSpace::World);
			if (FVector2D::Distance(FVector2D(X, Y), FVector2D(ClosestPt.X, ClosestPt.Y)) < RoadClearance)
			{
				bTooCloseToRoad = true;
				break;
			}
		}
		if (bTooCloseToRoad)
		{
			continue;
		}

		FHitResult Hit;
		FCollisionQueryParams QueryParams(TEXT("FoliageGroundTrace"), true, ClusterActor);
		const FVector TraceStart(X, Y, 10000.0f);
		const FVector TraceEnd(X, Y, -10000.0f);

		if (World->LineTraceSingleByChannel(Hit, TraceStart, TraceEnd, ECC_WorldStatic, QueryParams))
		{
			const float GroundZ = Hit.ImpactPoint.Z;
			if (GroundZ < MinElevation || GroundZ > MaxElevation)
			{
				continue;
			}

			const float SlopeDeg = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Hit.ImpactNormal.Z, 0.0f, 1.0f)));
			if (SlopeDeg > MaxSlopeDegrees)
			{
				continue;
			}

			const float Yaw = Rng.FRandRange(0.0f, 360.0f);
			const float ScaleVar = Rng.FRandRange(0.8f, 1.4f);
			const FTransform InstTrans(FRotator(0.0f, Yaw, 0.0f), Hit.ImpactPoint, FVector(ScaleVar, ScaleVar, ScaleVar * 1.5f));
			HISM->AddInstance(InstTrans);
			SpawnedCount++;
		}
		else
		{
			// Fallback placement on analytical height
			const float GroundZ = 150.0f;
			const float Yaw = Rng.FRandRange(0.0f, 360.0f);
			const float ScaleVar = Rng.FRandRange(0.8f, 1.4f);
			const FTransform InstTrans(FRotator(0.0f, Yaw, 0.0f), FVector(X, Y, GroundZ), FVector(ScaleVar, ScaleVar, ScaleVar * 1.5f));
			HISM->AddInstance(InstTrans);
			SpawnedCount++;
		}
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("cluster_name"), ClusterActor->GetName());
	Data->SetNumberField(TEXT("instances_spawned"), SpawnedCount);
	Data->SetNumberField(TEXT("target_count"), TargetCount);
	Data->SetNumberField(TEXT("seed"), Seed);
	Data->SetNumberField(TEXT("area_radius"), AreaRadius);

	return MakeLandscapeEnvelope(true, Data);
}

FString UGameForgeLandscapeLibrary::CreateLandmark(const FString& ParamsJson)
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}

	TSharedPtr<FJsonObject> Json;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, Json) || !Json.IsValid())
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to parse ParamsJson.")});
	}

	const FString LandmarkName = Json->HasField(TEXT("landmark_name")) ? Json->GetStringField(TEXT("landmark_name")) : TEXT("Landmark_AncientRuins");
	const FString LandmarkType = Json->HasField(TEXT("landmark_type")) ? Json->GetStringField(TEXT("landmark_type")) : TEXT("Ruins");
	const FString MaterialPath = Json->HasField(TEXT("material_path")) ? Json->GetStringField(TEXT("material_path")) : TEXT("");

	float PosX = 2500.0f, PosY = 2000.0f, PosZ = 450.0f;
	if (Json->HasField(TEXT("location")))
	{
		TSharedPtr<FJsonObject> LocObj = Json->GetObjectField(TEXT("location"));
		if (LocObj.IsValid())
		{
			PosX = (float)LocObj->GetNumberField(TEXT("x"));
			PosY = (float)LocObj->GetNumberField(TEXT("y"));
			PosZ = (float)LocObj->GetNumberField(TEXT("z"));
		}
	}

	UStaticMesh* PillarMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder")));
	UStaticMesh* AltarMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	UStaticMesh* RelicMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, TEXT("/Engine/BasicShapes/Sphere.Sphere")));

	UMaterialInterface* StoneMat = nullptr;
	if (!MaterialPath.IsEmpty())
	{
		StoneMat = Cast<UMaterialInterface>(StaticLoadObject(UMaterialInterface::StaticClass(), nullptr, *MaterialPath));
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.Name = MakeUniqueObjectName(World->PersistentLevel, AActor::StaticClass(), FName(*LandmarkName));
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	AActor* LandmarkActor = World->SpawnActor<AActor>(AActor::StaticClass(), FVector(PosX, PosY, PosZ), FRotator::ZeroRotator, SpawnParams);
	if (!LandmarkActor)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("Failed to spawn landmark actor.")});
	}

	USceneComponent* RootComp = NewObject<USceneComponent>(LandmarkActor, TEXT("RootComponent"));
	LandmarkActor->SetRootComponent(RootComp);
	RootComp->RegisterComponent();

	// 4 Stone Pillars
	const FVector PillarOffsets[] = {
		FVector(-250.0f, -250.0f, 0.0f),
		FVector(250.0f, -250.0f, 0.0f),
		FVector(250.0f, 250.0f, 0.0f),
		FVector(-250.0f, 250.0f, 0.0f)
	};
	for (int32 I = 0; I < 4; ++I)
	{
		UStaticMeshComponent* Pillar = NewObject<UStaticMeshComponent>(LandmarkActor, FName(*FString::Printf(TEXT("Pillar_%d"), I)));
		Pillar->AttachToComponent(RootComp, FAttachmentTransformRules::KeepRelativeTransform);
		Pillar->SetRelativeLocation(PillarOffsets[I]);
		Pillar->SetRelativeScale3D(FVector(1.0f, 1.0f, 4.0f));
		if (PillarMesh) Pillar->SetStaticMesh(PillarMesh);
		if (StoneMat) Pillar->SetMaterial(0, StoneMat);
		Pillar->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Pillar->RegisterComponent();
		LandmarkActor->AddInstanceComponent(Pillar);
	}

	// Central Altar
	UStaticMeshComponent* Altar = NewObject<UStaticMeshComponent>(LandmarkActor, TEXT("CentralAltar"));
	Altar->AttachToComponent(RootComp, FAttachmentTransformRules::KeepRelativeTransform);
	Altar->SetRelativeLocation(FVector(0.0f, 0.0f, 50.0f));
	Altar->SetRelativeScale3D(FVector(2.0f, 2.0f, 1.0f));
	if (AltarMesh) Altar->SetStaticMesh(AltarMesh);
	if (StoneMat) Altar->SetMaterial(0, StoneMat);
	Altar->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Altar->SetCollisionResponseToAllChannels(ECR_Block);
	Altar->RegisterComponent();
	LandmarkActor->AddInstanceComponent(Altar);

	// Golden Relic / Beacon
	UStaticMeshComponent* Relic = NewObject<UStaticMeshComponent>(LandmarkActor, TEXT("RelicBeacon"));
	Relic->AttachToComponent(RootComp, FAttachmentTransformRules::KeepRelativeTransform);
	Relic->SetRelativeLocation(FVector(0.0f, 0.0f, 160.0f));
	Relic->SetRelativeScale3D(FVector(0.8f, 0.8f, 0.8f));
	if (RelicMesh) Relic->SetStaticMesh(RelicMesh);
	Relic->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Relic->RegisterComponent();
	LandmarkActor->AddInstanceComponent(Relic);

	// Discovery Trigger Box
	UBoxComponent* TriggerBox = NewObject<UBoxComponent>(LandmarkActor, TEXT("DiscoveryTriggerBox"));
	TriggerBox->AttachToComponent(RootComp, FAttachmentTransformRules::KeepRelativeTransform);
	TriggerBox->SetBoxExtent(FVector(400.0f, 400.0f, 250.0f));
	TriggerBox->SetRelativeLocation(FVector(0.0f, 0.0f, 150.0f));
	TriggerBox->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	TriggerBox->SetCollisionResponseToAllChannels(ECR_Overlap);
	TriggerBox->RegisterComponent();
	LandmarkActor->AddInstanceComponent(TriggerBox);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("landmark_name"), LandmarkActor->GetName());
	Data->SetStringField(TEXT("landmark_type"), LandmarkType);
	Data->SetNumberField(TEXT("location_x"), PosX);
	Data->SetNumberField(TEXT("location_y"), PosY);
	Data->SetNumberField(TEXT("location_z"), PosZ);
	Data->SetBoolField(TEXT("has_trigger_box"), true);

	return MakeLandscapeEnvelope(true, Data);
}

FString UGameForgeLandscapeLibrary::InspectProceduralWorld()
{
	UWorld* World = GetActiveEditorWorld();
	if (!World)
	{
		return MakeLandscapeEnvelope(false, nullptr, {TEXT("No active editor world found.")});
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();

	// Landscape
	int32 LandscapeCount = 0;
	TSharedPtr<FJsonObject> LandscapeObj = MakeShared<FJsonObject>();
	for (TActorIterator<ALandscape> It(World); It; ++It)
	{
		ALandscape* L = *It;
		LandscapeCount++;
		LandscapeObj->SetStringField(TEXT("actor_name"), L->GetName());
		LandscapeObj->SetNumberField(TEXT("component_count"), L->LandscapeComponents.Num());
		FBox LoadedBounds = L->GetLoadedBounds();
		LandscapeObj->SetNumberField(TEXT("bounds_min_z"), LoadedBounds.Min.Z);
		LandscapeObj->SetNumberField(TEXT("bounds_max_z"), LoadedBounds.Max.Z);
		LandscapeObj->SetNumberField(TEXT("bounds_extent_x"), LoadedBounds.GetExtent().X);
		LandscapeObj->SetNumberField(TEXT("bounds_extent_y"), LoadedBounds.GetExtent().Y);
		break;
	}
	Data->SetNumberField(TEXT("landscape_count"), LandscapeCount);
	Data->SetObjectField(TEXT("landscape"), LandscapeObj);

	// Splines
	int32 SplineCount = 0;
	float TotalSplineLength = 0.0f;
	TArray<TSharedPtr<FJsonValue>> SplinesArr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (USplineComponent* SC = It->FindComponentByClass<USplineComponent>())
		{
			SplineCount++;
			TotalSplineLength += SC->GetSplineLength();
			TSharedPtr<FJsonObject> SObj = MakeShared<FJsonObject>();
			SObj->SetStringField(TEXT("actor_name"), It->GetName());
			SObj->SetNumberField(TEXT("points"), SC->GetNumberOfSplinePoints());
			SObj->SetNumberField(TEXT("length_cm"), SC->GetSplineLength());
			SplinesArr.Add(MakeShared<FJsonValueObject>(SObj));
		}
	}
	Data->SetNumberField(TEXT("spline_count"), SplineCount);
	Data->SetNumberField(TEXT("total_spline_length_cm"), TotalSplineLength);
	Data->SetArrayField(TEXT("splines"), SplinesArr);

	// Foliage HISM
	int32 TotalInstances = 0;
	TArray<TSharedPtr<FJsonValue>> FoliageArr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		TArray<UHierarchicalInstancedStaticMeshComponent*> HISMs;
		It->GetComponents<UHierarchicalInstancedStaticMeshComponent>(HISMs);
		for (UHierarchicalInstancedStaticMeshComponent* HISM : HISMs)
		{
			const int32 Num = HISM->GetInstanceCount();
			TotalInstances += Num;
			TSharedPtr<FJsonObject> FObj = MakeShared<FJsonObject>();
			FObj->SetStringField(TEXT("actor_name"), It->GetName());
			FObj->SetNumberField(TEXT("instances"), Num);
			FoliageArr.Add(MakeShared<FJsonValueObject>(FObj));
		}
	}
	Data->SetNumberField(TEXT("total_foliage_instances"), TotalInstances);
	Data->SetArrayField(TEXT("foliage_clusters"), FoliageArr);

	// Landmarks
	int32 LandmarkCount = 0;
	TArray<TSharedPtr<FJsonValue>> LandmarkArr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetName().Contains(TEXT("Landmark")))
		{
			LandmarkCount++;
			TSharedPtr<FJsonObject> LObj = MakeShared<FJsonObject>();
			LObj->SetStringField(TEXT("name"), It->GetName());
			LObj->SetNumberField(TEXT("x"), It->GetActorLocation().X);
			LObj->SetNumberField(TEXT("y"), It->GetActorLocation().Y);
			LObj->SetNumberField(TEXT("z"), It->GetActorLocation().Z);
			LandmarkArr.Add(MakeShared<FJsonValueObject>(LObj));
		}
	}
	Data->SetNumberField(TEXT("landmark_count"), LandmarkCount);
	Data->SetArrayField(TEXT("landmarks"), LandmarkArr);

	// NavMesh
	bool bHasNavMesh = false;
	for (TActorIterator<ANavMeshBoundsVolume> It(World); It; ++It)
	{
		bHasNavMesh = true;
		break;
	}
	Data->SetBoolField(TEXT("has_navmesh"), bHasNavMesh);

	return MakeLandscapeEnvelope(true, Data);
}
