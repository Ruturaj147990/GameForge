// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeAnimationLibrary.h"

#include "Animation/AnimBlueprint.h"
#include "Animation/AnimBlueprintGeneratedClass.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "AIController.h"
#include "Blueprint/AIBlueprintHelperLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "EngineUtils.h"
#include "GameForgeLocomotionAnimInstance.h"
#include "GameForgeLocomotionDriver.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Animation/AnimData/IAnimationDataController.h"
#include "Misc/FileHelper.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Editor.h"
#include "Factories/AnimBlueprintFactory.h"
#include "FileHelpers.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"

static FString BuildAnimJsonEnvelope(bool bOk, const TSharedPtr<FJsonObject>& Data, const TArray<FString>& Errors)
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

FString UGameForgeAnimationLibrary::InspectAnimationSequence(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}

	FString SeqPath = JsonObj->GetStringField(TEXT("anim_sequence_path"));
	if (SeqPath.IsEmpty())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("anim_sequence_path is required") });
	}

	UAnimSequence* AnimSeq = LoadObject<UAnimSequence>(nullptr, *SeqPath);
	if (!AnimSeq)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load UAnimSequence at path: %s"), *SeqPath) });
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("sequence_path"), SeqPath);
	Data->SetStringField(TEXT("asset_name"), AnimSeq->GetName());

	USkeleton* Skeleton = AnimSeq->GetSkeleton();
	Data->SetStringField(TEXT("skeleton_path"), Skeleton ? Skeleton->GetPathName() : TEXT("None"));
	Data->SetBoolField(TEXT("has_skeleton"), Skeleton != nullptr);

	Data->SetNumberField(TEXT("duration_seconds"), AnimSeq->GetPlayLength());
	Data->SetNumberField(TEXT("number_of_frames"), AnimSeq->GetNumberOfSampledKeys());
	Data->SetNumberField(TEXT("rate_scale"), AnimSeq->RateScale);
	Data->SetBoolField(TEXT("bEnableRootMotion"), AnimSeq->bEnableRootMotion);

	TArray<TSharedPtr<FJsonValue>> TrackNamesArray;
	IAnimationDataModel* DataModel = AnimSeq->GetDataModel();
	if (DataModel)
	{
		TArray<FName> BoneNames;
		DataModel->GetBoneTrackNames(BoneNames);
		Data->SetNumberField(TEXT("bone_track_count"), BoneNames.Num());
		for (const FName& BName : BoneNames)
		{
			TrackNamesArray.Add(MakeShared<FJsonValueString>(BName.ToString()));
		}
	}
	else
	{
		Data->SetNumberField(TEXT("bone_track_count"), 0);
	}
	Data->SetArrayField(TEXT("bone_tracks"), TrackNamesArray);

	return BuildAnimJsonEnvelope(true, Data, {});
}

FString UGameForgeAnimationLibrary::InspectAnimationBlueprint(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}

	FString BpPath = JsonObj->GetStringField(TEXT("anim_blueprint_path"));
	if (BpPath.IsEmpty())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("anim_blueprint_path is required") });
	}

	UAnimBlueprint* AnimBP = LoadObject<UAnimBlueprint>(nullptr, *BpPath);
	if (!AnimBP)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load UAnimBlueprint at path: %s"), *BpPath) });
	}

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), BpPath);
	Data->SetStringField(TEXT("asset_name"), AnimBP->GetName());

	USkeleton* Skeleton = AnimBP->TargetSkeleton;
	Data->SetStringField(TEXT("skeleton_path"), Skeleton ? Skeleton->GetPathName() : TEXT("None"));
	Data->SetBoolField(TEXT("has_skeleton"), Skeleton != nullptr);

	Data->SetStringField(TEXT("parent_class"), AnimBP->ParentClass ? AnimBP->ParentClass->GetName() : TEXT("None"));
	Data->SetStringField(TEXT("generated_class"), AnimBP->GeneratedClass ? AnimBP->GeneratedClass->GetName() : TEXT("None"));

	FString CompileStatusStr = TEXT("Unknown");
	switch (AnimBP->Status)
	{
	case BS_UpToDate: CompileStatusStr = TEXT("UpToDate"); break;
	case BS_Dirty: CompileStatusStr = TEXT("Dirty"); break;
	case BS_Error: CompileStatusStr = TEXT("Error"); break;
	case BS_UpToDateWithWarnings: CompileStatusStr = TEXT("UpToDateWithWarnings"); break;
	default: break;
	}
	Data->SetStringField(TEXT("compile_status"), CompileStatusStr);
	Data->SetBoolField(TEXT("is_compiled"), AnimBP->Status == BS_UpToDate || AnimBP->Status == BS_UpToDateWithWarnings);

	return BuildAnimJsonEnvelope(true, Data, {});
}

FString UGameForgeAnimationLibrary::CreateLocomotionAnimBlueprint(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}

	FString BpName = JsonObj->GetStringField(TEXT("blueprint_name"));
	FString DestPath = JsonObj->GetStringField(TEXT("destination_path"));
	FString SkeletonPath = JsonObj->GetStringField(TEXT("skeleton_path"));

	if (BpName.IsEmpty() || DestPath.IsEmpty() || SkeletonPath.IsEmpty())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("blueprint_name, destination_path, and skeleton_path are required") });
	}

	USkeleton* TargetSkeleton = LoadObject<USkeleton>(nullptr, *SkeletonPath);
	if (!TargetSkeleton)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load USkeleton at: %s"), *SkeletonPath) });
	}

	FString PackagePath = FString::Printf(TEXT("%s/%s"), *DestPath, *BpName);
	UPackage* Package = CreatePackage(*PackagePath);
	if (!Package)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to create package: %s"), *PackagePath) });
	}

	UAnimBlueprintFactory* Factory = NewObject<UAnimBlueprintFactory>();
	Factory->TargetSkeleton = TargetSkeleton;
	Factory->ParentClass = UGameForgeLocomotionAnimInstance::StaticClass();

	UAnimBlueprint* AnimBP = Cast<UAnimBlueprint>(Factory->FactoryCreateNew(
		UAnimBlueprint::StaticClass(),
		Package,
		FName(*BpName),
		RF_Public | RF_Standalone,
		nullptr,
		GWarn
	));

	if (!AnimBP)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("FactoryCreateNew failed to create UAnimBlueprint") });
	}

	// Compile the blueprint
	FKismetEditorUtilities::CompileBlueprint(AnimBP);

	// Assign the locomotion clips on the generated class defaults.
	TArray<FString> ClipErrors;
	TSharedPtr<FJsonObject> Assigned = MakeShared<FJsonObject>();
	const TSharedPtr<FJsonObject>* ClipsObj = nullptr;
	UGameForgeLocomotionAnimInstance* CDO = AnimBP->GeneratedClass
		? Cast<UGameForgeLocomotionAnimInstance>(AnimBP->GeneratedClass->GetDefaultObject()) : nullptr;
	if (JsonObj->TryGetObjectField(TEXT("clips"), ClipsObj) && ClipsObj)
	{
		if (!CDO)
		{
			ClipErrors.Add(TEXT("AnimBP generated class is not a UGameForgeLocomotionAnimInstance"));
		}
		const TPair<const TCHAR*, TObjectPtr<UAnimSequence> UGameForgeLocomotionAnimInstance::*> Slots[] = {
			{TEXT("Idle"), &UGameForgeLocomotionAnimInstance::IdleClip}, {TEXT("Walk"), &UGameForgeLocomotionAnimInstance::WalkClip},
			{TEXT("Run"), &UGameForgeLocomotionAnimInstance::RunClip}, {TEXT("Jump"), &UGameForgeLocomotionAnimInstance::JumpClip},
			{TEXT("Fall"), &UGameForgeLocomotionAnimInstance::FallClip}, {TEXT("Land"), &UGameForgeLocomotionAnimInstance::LandClip}};
		for (const auto& Slot : Slots)
		{
			FString ClipPath;
			if (!(*ClipsObj)->TryGetStringField(Slot.Key, ClipPath))
			{
				ClipErrors.Add(FString::Printf(TEXT("clips.%s missing"), Slot.Key));
				continue;
			}
			UAnimSequence* Seq = LoadObject<UAnimSequence>(nullptr, *ClipPath);
			if (!Seq || Seq->GetSkeleton() != TargetSkeleton)
			{
				ClipErrors.Add(FString::Printf(TEXT("clips.%s '%s' is not an AnimSequence on the target skeleton"), Slot.Key, *ClipPath));
				continue;
			}
			if (CDO)
			{
				CDO->Modify();
				CDO->*(Slot.Value) = Seq;
				Assigned->SetStringField(Slot.Key, Seq->GetPathName());
			}
		}
	}

	// Optional locomotion blend space (Idle/Walk/Run by ground speed).
	FString BlendSpacePath;
	if (JsonObj->TryGetStringField(TEXT("blend_space"), BlendSpacePath) && !BlendSpacePath.IsEmpty())
	{
		UBlendSpace* BS = LoadObject<UBlendSpace>(nullptr, *BlendSpacePath);
		if (!BS || BS->GetSkeleton() != TargetSkeleton)
		{
			ClipErrors.Add(FString::Printf(TEXT("blend_space '%s' is not a BlendSpace on the target skeleton"), *BlendSpacePath));
		}
		else if (CDO)
		{
			CDO->Modify();
			CDO->LocomotionBlendSpace = BS;
			Assigned->SetStringField(TEXT("BlendSpace"), BS->GetPathName());
		}
	}

	// Defaults edited on the CDO become Blueprint defaults once the Blueprint is recompiled (the same
	// path as editing Class Defaults in the editor); then read back what the new CDO really holds.
	if (Assigned->Values.Num() > 0)
	{
		FBlueprintEditorUtils::MarkBlueprintAsModified(AnimBP);
		FKismetEditorUtilities::CompileBlueprint(AnimBP);
		const UGameForgeLocomotionAnimInstance* NewCDO = AnimBP->GeneratedClass
			? Cast<UGameForgeLocomotionAnimInstance>(AnimBP->GeneratedClass->GetDefaultObject()) : nullptr;
		const UAnimSequence* Back[] = { NewCDO ? NewCDO->IdleClip.Get() : nullptr, NewCDO ? NewCDO->WalkClip.Get() : nullptr,
			NewCDO ? NewCDO->RunClip.Get() : nullptr, NewCDO ? NewCDO->JumpClip.Get() : nullptr,
			NewCDO ? NewCDO->FallClip.Get() : nullptr, NewCDO ? NewCDO->LandClip.Get() : nullptr };
		int32 Persisted = 0;
		for (const UAnimSequence* S : Back) Persisted += S ? 1 : 0;
		Assigned->SetNumberField(TEXT("persisted_after_recompile"), Persisted);
		Assigned->SetStringField(TEXT("blend_space_after_recompile"),
			NewCDO && NewCDO->LocomotionBlendSpace ? NewCDO->LocomotionBlendSpace->GetPathName() : TEXT(""));
		if (Persisted != 6)
		{
			ClipErrors.Add(FString::Printf(TEXT("only %d/6 clips survived recompilation"), Persisted));
		}
	}

	// Mark and save
	Package->MarkPackageDirty();
	FAssetRegistryModule::AssetCreated(AnimBP);
	UEditorLoadingAndSavingUtils::SavePackages({ Package }, false);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("blueprint_path"), PackagePath);
	Data->SetStringField(TEXT("blueprint_name"), BpName);
	Data->SetStringField(TEXT("skeleton_path"), SkeletonPath);
	const bool bCompiled = AnimBP->Status == BS_UpToDate || AnimBP->Status == BS_UpToDateWithWarnings;
	Data->SetBoolField(TEXT("compiled"), bCompiled);
	Data->SetStringField(TEXT("parent_class"), AnimBP->ParentClass ? AnimBP->ParentClass->GetName() : TEXT("None"));
	Data->SetStringField(TEXT("generated_class"), AnimBP->GeneratedClass ? AnimBP->GeneratedClass->GetPathName() : TEXT("None"));
	Data->SetObjectField(TEXT("assigned_clips"), Assigned);
	if (!bCompiled)
	{
		ClipErrors.Add(TEXT("AnimBP failed to compile"));
	}
	return BuildAnimJsonEnvelope(ClipErrors.Num() == 0, Data, ClipErrors);
}

FString UGameForgeAnimationLibrary::RetargetAnimationSequence(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}

	FString SourceSeqPath = JsonObj->GetStringField(TEXT("source_sequence_path"));
	FString TargetSkeletonPath = JsonObj->GetStringField(TEXT("target_skeleton_path"));
	FString DestPath = JsonObj->GetStringField(TEXT("destination_path"));
	FString DestName = JsonObj->GetStringField(TEXT("destination_name"));

	UAnimSequence* SrcSeq = LoadObject<UAnimSequence>(nullptr, *SourceSeqPath);
	if (!SrcSeq)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load source UAnimSequence: %s"), *SourceSeqPath) });
	}

	USkeleton* TargetSkeleton = LoadObject<USkeleton>(nullptr, *TargetSkeletonPath);
	if (!TargetSkeleton)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load target USkeleton: %s"), *TargetSkeletonPath) });
	}

	FString FullDestPath = FString::Printf(TEXT("%s/%s"), *DestPath, *DestName);
	UPackage* DestPackage = CreatePackage(*FullDestPath);
	if (!DestPackage)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to create package: %s"), *FullDestPath) });
	}

	// Duplicate asset and assign target skeleton
	UAnimSequence* DuplicateSeq = Cast<UAnimSequence>(StaticDuplicateObject(SrcSeq, DestPackage, FName(*DestName)));
	if (!DuplicateSeq)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("StaticDuplicateObject failed") });
	}

	DuplicateSeq->SetSkeleton(TargetSkeleton);
	DuplicateSeq->MarkPackageDirty();
	FAssetRegistryModule::AssetCreated(DuplicateSeq);
	UEditorLoadingAndSavingUtils::SavePackages({ DestPackage }, false);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("retargeted_sequence_path"), FullDestPath);
	Data->SetStringField(TEXT("target_skeleton_path"), TargetSkeletonPath);
	Data->SetNumberField(TEXT("duration_seconds"), DuplicateSeq->GetPlayLength());

	return BuildAnimJsonEnvelope(true, Data, {});
}

FString UGameForgeAnimationLibrary::ImportMotionClip(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> Params;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(ParamsJson);
	if (!FJsonSerializer::Deserialize(Reader, Params) || !Params.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}
	const FString SkeletonPath = Params->GetStringField(TEXT("skeleton_path"));
	const FString MotionPath = Params->GetStringField(TEXT("motion_json_path"));
	const FString DestPath = Params->GetStringField(TEXT("destination_path"));
	const FString DestName = Params->GetStringField(TEXT("destination_name"));

	USkeleton* Skeleton = LoadObject<USkeleton>(nullptr, *SkeletonPath);
	if (!Skeleton)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to load USkeleton at: %s"), *SkeletonPath) });
	}
	FString MotionText;
	TSharedPtr<FJsonObject> Motion;
	if (!FFileHelper::LoadFileToString(MotionText, *MotionPath)
		|| !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(MotionText), Motion) || !Motion.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Failed to read motion bundle: %s"), *MotionPath) });
	}
	const TSharedPtr<FJsonObject>* Tracks = nullptr;
	if (!Motion->TryGetObjectField(TEXT("tracks"), Tracks) || !Tracks)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Motion bundle has no tracks") });
	}
	const int32 SampleRate = FMath::Max(1, (int32)Motion->GetNumberField(TEXT("sample_rate_hz")));
	const FReferenceSkeleton& RefSkel = Skeleton->GetReferenceSkeleton();
	const TArray<FTransform>& RefPose = RefSkel.GetRefBonePose();

	UPackage* Package = CreatePackage(*FString::Printf(TEXT("%s/%s"), *DestPath, *DestName));
	UAnimSequence* Seq = NewObject<UAnimSequence>(Package, FName(*DestName), RF_Public | RF_Standalone);
	Seq->SetSkeleton(Skeleton);

	IAnimationDataController& Controller = Seq->GetController();
	Controller.InitializeModel();
	Controller.OpenBracket(FText::FromString(TEXT("GameForge motion import")), false);
	Controller.ResetModel(false);
	Controller.SetFrameRate(FFrameRate(SampleRate, 1), false);

	TArray<FString> Missing;
	int32 NumKeys = 0, Imported = 0;
	for (const TPair<FString, TSharedPtr<FJsonValue>>& Track : (*Tracks)->Values)
	{
		const int32 BoneIndex = RefSkel.FindBoneIndex(FName(*Track.Key));
		if (BoneIndex == INDEX_NONE)
		{
			Missing.Add(Track.Key);
			continue;
		}
		const TArray<TSharedPtr<FJsonValue>>& Frames = Track.Value->AsArray();
		if (NumKeys == 0)
		{
			NumKeys = Frames.Num();
			Controller.SetNumberOfFrames(FFrameNumber(FMath::Max(1, NumKeys - 1)), false);
		}
		if (Frames.Num() != NumKeys)
		{
			Controller.CloseBracket(false);
			return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("Track '%s' has %d keys, expected %d"), *Track.Key, Frames.Num(), NumKeys) });
		}
		const FTransform& Bind = RefPose[BoneIndex];
		TArray<FVector3f> Pos;
		TArray<FQuat4f> Rot;
		TArray<FVector3f> Scl;
		for (const TSharedPtr<FJsonValue>& FrameVal : Frames)
		{
			const TSharedPtr<FJsonObject> F = FrameVal->AsObject();
			const TArray<TSharedPtr<FJsonValue>>& L = F->GetArrayField(TEXT("location"));
			const TArray<TSharedPtr<FJsonValue>>& Q = F->GetArrayField(TEXT("rotation_quat"));
			const FVector Offset(L[0]->AsNumber(), L[1]->AsNumber(), L[2]->AsNumber());
			const FQuat Local(Q[0]->AsNumber(), Q[1]->AsNumber(), Q[2]->AsNumber(), Q[3]->AsNumber());
			// Offsets and rotations are relative to this bone's bind pose.
			Pos.Add(FVector3f(Bind.GetTranslation() + Offset));
			Rot.Add(FQuat4f((Bind.GetRotation() * Local).GetNormalized()));
			Scl.Add(FVector3f(Bind.GetScale3D()));
		}
		Controller.AddBoneCurve(FName(*Track.Key), false);
		Controller.SetBoneTrackKeys(FName(*Track.Key), Pos, Rot, Scl, false);
		++Imported;
	}
	Controller.NotifyPopulated();
	Controller.CloseBracket(false);

	if (Imported == 0 || Missing.Num() > 0)
	{
		TArray<FString> Errors = { FString::Printf(TEXT("%d bone tracks imported, %d missing from skeleton"), Imported, Missing.Num()) };
		for (const FString& M : Missing)
		{
			Errors.Add(TEXT("missing bone: ") + M);
		}
		return BuildAnimJsonEnvelope(false, nullptr, Errors);
	}

	Seq->MarkPackageDirty();
	FAssetRegistryModule::AssetCreated(Seq);
	UEditorLoadingAndSavingUtils::SavePackages({ Package }, false);

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("anim_sequence_path"), Seq->GetPathName());
	Data->SetStringField(TEXT("skeleton_path"), SkeletonPath);
	Data->SetNumberField(TEXT("bone_tracks"), Imported);
	Data->SetNumberField(TEXT("keys"), NumKeys);
	Data->SetNumberField(TEXT("sample_rate_hz"), SampleRate);
	Data->SetNumberField(TEXT("play_length_s"), Seq->GetPlayLength());
	return BuildAnimJsonEnvelope(true, Data, {});
}

static UWorld* GFFindPIEWorld()
{
	if (GEditor && GEditor->PlayWorld)
	{
		return GEditor->PlayWorld.Get();
	}
	if (GEngine)
	{
		for (const FWorldContext& Context : GEngine->GetWorldContexts())
		{
			if (Context.WorldType == EWorldType::PIE && Context.World())
			{
				return Context.World();
			}
		}
	}
	return nullptr;
}

FString UGameForgeAnimationLibrary::StartLocomotionTest(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> P;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ParamsJson), P) || !P.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}
	UWorld* World = GFFindPIEWorld();
	if (!World)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("No active PIE world") });
	}
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *P->GetStringField(TEXT("skeletal_mesh_path")));
	UAnimBlueprint* AnimBP = LoadObject<UAnimBlueprint>(nullptr, *P->GetStringField(TEXT("anim_blueprint_path")));
	if (!Mesh || !AnimBP || !AnimBP->GeneratedClass)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("skeletal_mesh_path or anim_blueprint_path did not load") });
	}
	FVector Location(0, 0, 200);
	const TSharedPtr<FJsonObject>* Loc = nullptr;
	if (P->TryGetObjectField(TEXT("location"), Loc) && Loc)
	{
		Location = FVector((*Loc)->GetNumberField(TEXT("x")), (*Loc)->GetNumberField(TEXT("y")), (*Loc)->GetNumberField(TEXT("z")));
	}
	for (TActorIterator<AGameForgeLocomotionDriver> It(World); It; ++It)
	{
		if (It->Target) It->Target->Destroy();
		It->Destroy();
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	ACharacter* Character = World->SpawnActor<ACharacter>(ACharacter::StaticClass(), Location, FRotator::ZeroRotator, SpawnParams);
	if (!Character)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to spawn ACharacter") });
	}
	Character->GetCapsuleComponent()->SetCapsuleSize(34.0f, 90.0f);
	USkeletalMeshComponent* MeshComp = Character->GetMesh();
	MeshComp->SetSkeletalMesh(Mesh);
	MeshComp->SetRelativeLocation(FVector(0, 0, -90.0f));
	MeshComp->SetAnimationMode(EAnimationMode::AnimationBlueprint);
	MeshComp->SetAnimInstanceClass(AnimBP->GeneratedClass);
	MeshComp->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	UCharacterMovementComponent* Move = Character->GetCharacterMovement();
	Move->MaxWalkSpeed = 600.0f;
	Move->JumpZVelocity = 520.0f;
	Move->bOrientRotationToMovement = true;
	Character->AIControllerClass = AAIController::StaticClass();
	Character->SpawnDefaultController();

	AGameForgeLocomotionDriver* Driver = World->SpawnActor<AGameForgeLocomotionDriver>(Location, FRotator::ZeroRotator);
	Driver->Target = Character;

	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetStringField(TEXT("character"), Character->GetName());
	Data->SetStringField(TEXT("controller"), Character->GetController() ? Character->GetController()->GetClass()->GetName() : TEXT("None"));
	Data->SetStringField(TEXT("anim_instance"), MeshComp->GetAnimInstance() ? MeshComp->GetAnimInstance()->GetClass()->GetName() : TEXT("None"));
	Data->SetStringField(TEXT("driver"), Driver->GetName());
	return BuildAnimJsonEnvelope(Character->GetController() != nullptr && MeshComp->GetAnimInstance() != nullptr, Data,
		Character->GetController() ? TArray<FString>() : TArray<FString>{ TEXT("Character has no controller") });
}

FString UGameForgeAnimationLibrary::FinalizeBlendSpace(const FString& BlendSpacePath)
{
	UBlendSpace* BS = LoadObject<UBlendSpace>(nullptr, *BlendSpacePath);
	if (!BS)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { FString::Printf(TEXT("not a BlendSpace: %s"), *BlendSpacePath) });
	}
	BS->Modify();
	BS->ValidateSampleData();
	BS->ResampleData();
	BS->MarkPackageDirty();
	const FBlendSpaceData& Runtime = BS->GetBlendSpaceData();
	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetNumberField(TEXT("samples"), BS->GetNumberOfBlendSamples());
	Data->SetNumberField(TEXT("runtime_segments"), Runtime.Segments.Num());
	Data->SetNumberField(TEXT("runtime_triangles"), Runtime.Triangles.Num());
	return BuildAnimJsonEnvelope(!Runtime.IsEmpty(), Data,
		Runtime.IsEmpty() ? TArray<FString>{ TEXT("blend space has no runtime segments/triangles after ResampleData") } : TArray<FString>());
}

FString UGameForgeAnimationLibrary::GetLocomotionTestResult()
{
	UWorld* World = GFFindPIEWorld();
	if (!World)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("No active PIE world") });
	}
	AGameForgeLocomotionDriver* Driver = nullptr;
	for (TActorIterator<AGameForgeLocomotionDriver> It(World); It; ++It)
	{
		Driver = *It;
		break;
	}
	if (!Driver || !Driver->Target)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("No locomotion test is running") });
	}
	const UGameForgeLocomotionAnimInstance* Anim = Cast<UGameForgeLocomotionAnimInstance>(Driver->Target->GetMesh()->GetAnimInstance());
	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	Data->SetBoolField(TEXT("finished"), Driver->bFinished);
	Data->SetNumberField(TEXT("elapsed_s"), Driver->Elapsed);
	TArray<TSharedPtr<FJsonValue>> Phases, Transitions;
	for (const FString& S : Driver->PhaseLog) Phases.Add(MakeShared<FJsonValueString>(S));
	if (Anim)
	{
		for (const FString& S : Anim->TransitionLog) Transitions.Add(MakeShared<FJsonValueString>(S));
		Data->SetStringField(TEXT("current_state"), UGameForgeLocomotionAnimInstance::StateName(Anim->CurrentState));
		Data->SetNumberField(TEXT("ground_speed"), Anim->GroundSpeed);
		Data->SetStringField(TEXT("blend_space"), Anim->LocomotionBlendSpace ? Anim->LocomotionBlendSpace->GetPathName() : TEXT(""));
		Data->SetStringField(TEXT("blend_space_weights"), Anim->BlendSpaceWeights);
	}
	Data->SetArrayField(TEXT("phases"), Phases);
	Data->SetArrayField(TEXT("transitions"), Transitions);
	const FVector L = Driver->Target->GetActorLocation();
	Data->SetStringField(TEXT("character_location"), FString::Printf(TEXT("%.0f,%.0f,%.0f"), L.X, L.Y, L.Z));
	// A posed bone proves the clips are actually evaluated on the mesh (not the ref pose).
	USkeletalMeshComponent* MeshComp = Driver->Target->GetMesh();
	const int32 Thigh = MeshComp->GetBoneIndex(TEXT("thigh_l"));
	if (Thigh != INDEX_NONE && MeshComp->GetSkinnedAsset())
	{
		const TArray<FTransform> LocalPose = MeshComp->GetBoneSpaceTransforms();
		const FQuat Live = LocalPose.IsValidIndex(Thigh) ? LocalPose[Thigh].GetRotation() : FQuat::Identity;
		const FQuat Ref = MeshComp->GetSkinnedAsset()->GetRefSkeleton().GetRefBonePose()[Thigh].GetRotation();
		Data->SetNumberField(TEXT("thigh_l_deviation_deg"), FMath::RadiansToDegrees(Live.AngularDistance(Ref)));
	}
	return BuildAnimJsonEnvelope(Anim != nullptr, Data, Anim ? TArray<FString>() : TArray<FString>{ TEXT("Mesh is not driven by a GameForge locomotion anim instance") });
}

FString UGameForgeAnimationLibrary::MovePIEPlayerTo(const FString& ParamsJson)
{
	TSharedPtr<FJsonObject> P;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ParamsJson), P) || !P.IsValid())
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("Failed to parse ParamsJson") });
	}
	UWorld* World = GFFindPIEWorld();
	APlayerController* PC = World ? UGameplayStatics::GetPlayerController(World, 0) : nullptr;
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	if (!Pawn)
	{
		return BuildAnimJsonEnvelope(false, nullptr, { TEXT("No PIE player pawn") });
	}
	const FVector Goal(P->GetNumberField(TEXT("x")), P->GetNumberField(TEXT("y")), P->GetNumberField(TEXT("z")));
	UAIBlueprintHelperLibrary::SimpleMoveToLocation(PC, Goal);
	TSharedPtr<FJsonObject> Data = MakeShared<FJsonObject>();
	const FVector From = Pawn->GetActorLocation();
	Data->SetStringField(TEXT("pawn"), Pawn->GetClass()->GetName());
	Data->SetStringField(TEXT("from"), FString::Printf(TEXT("%.0f,%.0f,%.0f"), From.X, From.Y, From.Z));
	return BuildAnimJsonEnvelope(true, Data, {});
}
