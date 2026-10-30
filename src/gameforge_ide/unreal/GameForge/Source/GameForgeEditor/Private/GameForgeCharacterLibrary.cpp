// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeCharacterLibrary.h"

#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "Editor.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "ReferenceSkeleton.h"
#include "Components/PoseableMeshComponent.h"
#include "Rendering/SkeletalMeshLODModel.h"
#include "Rendering/SkeletalMeshModel.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

static FString BuildJsonEnvelope(bool bOk, const TSharedPtr<FJsonObject>& Data, const TArray<FString>& Errors)
{
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetBoolField(TEXT("ok"), bOk);
	if (Data.IsValid())
	{
		Root->SetObjectField(TEXT("data"), Data);
	}
	TArray<TSharedPtr<FJsonValue>> ErrArray;
	for (const FString& Err : Errors)
	{
		ErrArray.Add(MakeShared<FJsonValueString>(Err));
	}
	Root->SetArrayField(TEXT("errors"), ErrArray);

	FString Output;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
	FJsonSerializer::Serialize(Root.ToSharedRef(), Writer);
	return Output;
}

FString UGameForgeCharacterLibrary::InspectSkeletalMesh(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}

	FString MeshPath = JsonObj->GetStringField(TEXT("skeletal_mesh_path"));
	if (MeshPath.IsEmpty())
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("skeletal_mesh_path is required") });
	}

	USkeletalMesh* SkelMesh = LoadObject<USkeletalMesh>(nullptr, *MeshPath);
	if (!SkelMesh)
	{
		return BuildJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load USkeletalMesh at path: %s"), *MeshPath) });
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("mesh_path"), MeshPath);
	Data->SetStringField(TEXT("asset_name"), SkelMesh->GetName());

	// Skeleton linkage
	USkeleton* Skeleton = SkelMesh->GetSkeleton();
	Data->SetStringField(TEXT("skeleton_path"), Skeleton ? Skeleton->GetPathName() : TEXT("None"));
	Data->SetBoolField(TEXT("has_skeleton"), Skeleton != nullptr);

	// Bone hierarchy
	const FReferenceSkeleton& RefSkel = SkelMesh->GetRefSkeleton();
	const int32 NumBones = RefSkel.GetNum();
	Data->SetNumberField(TEXT("bone_count"), NumBones);

	TArray<TSharedPtr<FJsonValue>> BoneNamesArray;
	TArray<TSharedPtr<FJsonValue>> ParentIndicesArray;
	for (int32 i = 0; i < NumBones; ++i)
	{
		BoneNamesArray.Add(MakeShared<FJsonValueString>(RefSkel.GetBoneName(i).ToString()));
		ParentIndicesArray.Add(MakeShared<FJsonValueNumber>(RefSkel.GetParentIndex(i)));
	}
	Data->SetArrayField(TEXT("bone_names"), BoneNamesArray);
	Data->SetArrayField(TEXT("parent_indices"), ParentIndicesArray);

	// Root bone
	FString RootBoneName = NumBones > 0 ? RefSkel.GetBoneName(0).ToString() : TEXT("None");
	Data->SetStringField(TEXT("root_bone_name"), RootBoneName);

	// Bounds
	FBoxSphereBounds Bounds = SkelMesh->GetBounds();
	TSharedPtr<FJsonObject> BoundsObj = MakeShared<FJsonObject>();
	BoundsObj->SetNumberField(TEXT("box_extent_x"), Bounds.BoxExtent.X);
	BoundsObj->SetNumberField(TEXT("box_extent_y"), Bounds.BoxExtent.Y);
	BoundsObj->SetNumberField(TEXT("box_extent_z"), Bounds.BoxExtent.Z);
	BoundsObj->SetNumberField(TEXT("sphere_radius"), Bounds.SphereRadius);
	Data->SetObjectField(TEXT("bounds"), BoundsObj);

	// Materials
	const TArray<FSkeletalMaterial>& Materials = SkelMesh->GetMaterials();
	TArray<TSharedPtr<FJsonValue>> MatArray;
	for (const FSkeletalMaterial& Mat : Materials)
	{
		MatArray.Add(MakeShared<FJsonValueString>(Mat.MaterialInterface ? Mat.MaterialInterface->GetPathName() : Mat.MaterialSlotName.ToString()));
	}
	Data->SetArrayField(TEXT("materials"), MatArray);
	Data->SetNumberField(TEXT("material_count"), Materials.Num());

	// LODs
	Data->SetNumberField(TEXT("lod_count"), SkelMesh->GetLODNum());

	return BuildJsonEnvelope(true, Data, {});
}

FString UGameForgeCharacterLibrary::SpawnCharacterPreviewActor(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}

	FString MeshPath = JsonObj->GetStringField(TEXT("skeletal_mesh_path"));
	FString ActorLabel = JsonObj->GetStringField(TEXT("actor_label"));
	if (ActorLabel.IsEmpty())
	{
		ActorLabel = TEXT("GF_CharacterPreview");
	}

	USkeletalMesh* SkelMesh = LoadObject<USkeletalMesh>(nullptr, *MeshPath);
	if (!SkelMesh)
	{
		return BuildJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load USkeletalMesh at path: %s"), *MeshPath) });
	}

	UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
	if (!World)
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("No active editor world context found") });
	}

	// Coordinates
	FVector Location = FVector::ZeroVector;
	if (JsonObj->HasField(TEXT("location")))
	{
		const TArray<TSharedPtr<FJsonValue>>& LocArr = JsonObj->GetArrayField(TEXT("location"));
		if (LocArr.Num() >= 3)
		{
			Location = FVector(LocArr[0]->AsNumber(), LocArr[1]->AsNumber(), LocArr[2]->AsNumber());
		}
	}

	FRotator Rotation = FRotator::ZeroRotator;
	if (JsonObj->HasField(TEXT("rotation")))
	{
		const TArray<TSharedPtr<FJsonValue>>& RotArr = JsonObj->GetArrayField(TEXT("rotation"));
		if (RotArr.Num() >= 3)
		{
			Rotation = FRotator(RotArr[0]->AsNumber(), RotArr[1]->AsNumber(), RotArr[2]->AsNumber());
		}
	}

	FActorSpawnParameters SpawnParams;
	AActor* SpawnedActor = World->SpawnActor<AActor>(Location, Rotation, SpawnParams);
	if (!SpawnedActor)
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("Failed to spawn preview actor in world") });
	}

	USkeletalMeshComponent* MeshComp = NewObject<USkeletalMeshComponent>(SpawnedActor, TEXT("CharacterSkeletalMesh"));
	MeshComp->SetSkeletalMesh(SkelMesh);
	SpawnedActor->SetRootComponent(MeshComp);
	MeshComp->RegisterComponent();
	SpawnedActor->SetActorLabel(ActorLabel);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("actor_name"), SpawnedActor->GetName());
	Data->SetStringField(TEXT("actor_label"), ActorLabel);
	Data->SetStringField(TEXT("mesh_path"), MeshPath);
	Data->SetNumberField(TEXT("location_x"), Location.X);
	Data->SetNumberField(TEXT("location_y"), Location.Y);
	Data->SetNumberField(TEXT("location_z"), Location.Z);

	return BuildJsonEnvelope(true, Data, {});
}

FString UGameForgeCharacterLibrary::MeasureSkinDeformation(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> P;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ParamsJson), P) || !P.IsValid())
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *P->GetStringField(TEXT("skeletal_mesh_path")));
	if (!Mesh || !Mesh->GetImportedModel() || Mesh->GetImportedModel()->LODModels.Num() == 0)
	{
		return BuildJsonEnvelope(false, nullptr, { TEXT("Skeletal mesh (with imported LOD model) not found") });
	}
	const FName BoneName(*P->GetStringField(TEXT("bone_name")));
	const FString AxisStr = P->GetStringField(TEXT("axis"));
	const double Angle = FMath::DegreesToRadians(P->GetNumberField(TEXT("angle_degrees")));
	const FVector Axis = AxisStr == TEXT("X") ? FVector::XAxisVector : AxisStr == TEXT("Y") ? FVector::YAxisVector : FVector::ZAxisVector;

	const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
	const int32 Bone = Ref.FindBoneIndex(BoneName);
	if (Bone == INDEX_NONE)
	{
		return BuildJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Bone '%s' not in skeleton"), *BoneName.ToString()) });
	}
	const int32 NumBones = Ref.GetNum();
	const TArray<FTransform>& Local = Ref.GetRefBonePose();
	TArray<FTransform> Bind, Posed;
	Bind.SetNum(NumBones);
	Posed.SetNum(NumBones);
	TArray<bool> InSubtree;
	InSubtree.Init(false, NumBones);
	for (int32 i = 0; i < NumBones; ++i)
	{
		const int32 Parent = Ref.GetParentIndex(i);
		FTransform PosedLocal = Local[i];
		if (i == Bone)
		{
			PosedLocal.SetRotation(PosedLocal.GetRotation() * FQuat(Axis, Angle));
		}
		Bind[i] = Parent == INDEX_NONE ? Local[i] : Local[i] * Bind[Parent];
		Posed[i] = Parent == INDEX_NONE ? PosedLocal : PosedLocal * Posed[Parent];
		InSubtree[i] = i == Bone || (Parent != INDEX_NONE && InSubtree[Parent]);
	}

	const FSkeletalMeshLODModel& LOD = Mesh->GetImportedModel()->LODModels[0];
	int32 Vertices = 0, Moved = 0, BadValues = 0, SubtreeVerts = 0, OutsideVerts = 0;
	double MaxDisp = 0.0, MaxOutsideDisp = 0.0, SubtreeDispSum = 0.0;
	for (const FSkelMeshSection& Section : LOD.Sections)
	{
		for (const FSoftSkinVertex& V : Section.SoftVertices)
		{
			++Vertices;
			const FVector Pos(V.Position);
			FVector Skinned = FVector::ZeroVector;
			double WeightSum = 0.0, SubtreeWeight = 0.0;
			for (int32 k = 0; k < MAX_TOTAL_INFLUENCES; ++k)
			{
				const double W = V.InfluenceWeights[k];
				if (W <= 0.0 || !Section.BoneMap.IsValidIndex(V.InfluenceBones[k])) continue;
				const int32 B = Section.BoneMap[V.InfluenceBones[k]];
				Skinned += W * Posed[B].TransformPosition(Bind[B].InverseTransformPosition(Pos));
				WeightSum += W;
				SubtreeWeight += InSubtree[B] ? W : 0.0;
			}
			if (WeightSum <= 0.0) { ++BadValues; continue; }
			Skinned /= WeightSum;
			if (Skinned.ContainsNaN() || !FMath::IsFinite(Skinned.X) || !FMath::IsFinite(Skinned.Y) || !FMath::IsFinite(Skinned.Z)) { ++BadValues; continue; }
			const double D = FVector::Dist(Skinned, Pos);
			MaxDisp = FMath::Max(MaxDisp, D);
			Moved += D > 0.01 ? 1 : 0;
			// Linear blend skinning: a vertex with any weight on the rotated subtree may move; a vertex
			// with none must stay exactly where it is.
			if (SubtreeWeight > 0.0) { ++SubtreeVerts; SubtreeDispSum += D; }
			else { ++OutsideVerts; MaxOutsideDisp = FMath::Max(MaxOutsideDisp, D); }
		}
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("bone"), BoneName.ToString());
	Data->SetStringField(TEXT("axis"), AxisStr);
	Data->SetNumberField(TEXT("angle_degrees"), P->GetNumberField(TEXT("angle_degrees")));
	Data->SetNumberField(TEXT("vertices"), Vertices);
	Data->SetNumberField(TEXT("vertices_moved"), Moved);
	Data->SetNumberField(TEXT("max_displacement_cm"), MaxDisp);
	Data->SetNumberField(TEXT("subtree_vertices"), SubtreeVerts);
	Data->SetNumberField(TEXT("subtree_mean_displacement_cm"), SubtreeVerts ? SubtreeDispSum / SubtreeVerts : 0.0);
	Data->SetNumberField(TEXT("outside_vertices"), OutsideVerts);
	Data->SetNumberField(TEXT("outside_max_displacement_cm"), MaxOutsideDisp);
	Data->SetNumberField(TEXT("invalid_vertices"), BadValues);

	const TSharedPtr<FJsonObject>* PreviewLoc = nullptr;
	if (P->TryGetObjectField(TEXT("posed_preview"), PreviewLoc) && PreviewLoc)
	{
		UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
		if (World)
		{
			const FVector L((*PreviewLoc)->GetNumberField(TEXT("x")), (*PreviewLoc)->GetNumberField(TEXT("y")), (*PreviewLoc)->GetNumberField(TEXT("z")));
			AActor* Actor = World->SpawnActor<AActor>(L, FRotator::ZeroRotator);
			UPoseableMeshComponent* Poseable = NewObject<UPoseableMeshComponent>(Actor, TEXT("PosedMesh"));
			Actor->SetRootComponent(Poseable);
			Poseable->RegisterComponent();
			Actor->AddInstanceComponent(Poseable);
			Poseable->SetSkinnedAssetAndUpdate(Mesh);
			Poseable->SetWorldLocation(L);
			// Same pose as measured above, rendered with GPU skinning (component-space rotation).
			Poseable->SetBoneRotationByName(BoneName, Posed[Bone].GetRotation().Rotator(), EBoneSpaces::ComponentSpace);
			Actor->SetActorLabel(FString::Printf(TEXT("GF_Posed_%s"), *BoneName.ToString()));
			Data->SetStringField(TEXT("posed_preview_actor"), Actor->GetActorLabel());
		}
	}

	const bool bOk = Vertices > 0 && BadValues == 0 && SubtreeVerts > 0 && Moved > 0 && MaxOutsideDisp < 0.01;
	return BuildJsonEnvelope(bOk, Data, bOk ? TArray<FString>() : TArray<FString>{ TEXT("Deformation check failed (see data)") });
}
