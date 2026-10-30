// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeCharacterLibrary.generated.h"

/**
 * Native C++ editor library providing genuine Unreal Engine 5.7.4 character
 * skeletal mesh inspection, skeleton validation, and preview actor instantiation.
 *
 * Zero mocks, zero simulators. Interacts with real USkeletalMesh, USkeleton,
 * and USkeletalMeshComponent inside the actual Unreal Engine editor.
 */
UCLASS()
class GAMEFORGEEDITOR_API UGameForgeCharacterLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Authoritatively inspects a USkeletalMesh asset on disk/memory:
	 * Skeleton linkage, bone count, bone names, parent indices, bounding box, materials, and LODs.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Character")
	static FString InspectSkeletalMesh(const FString& ParamsJson);

	/**
	 * Spawns a preview character actor in the active editor world with a USkeletalMeshComponent
	 * configured to display the specified skeletal mesh.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Character")
	static FString SpawnCharacterPreviewActor(const FString& ParamsJson);

	/**
	 * Skins the mesh's imported LOD0 vertices (Unreal's own skin weights and reference skeleton)
	 * with one bone rotated, and reports how the surface deforms: vertices driven by the bone's
	 * subtree must move, all others must stay put, and nothing may become NaN/Inf.
	 * Params: skeletal_mesh_path, bone_name, axis ("X"|"Y"|"Z"), angle_degrees,
	 * optional posed_preview {x,y,z} to spawn a GPU-skinned PoseableMesh actor in that pose.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Character")
	static FString MeasureSkinDeformation(const FString& ParamsJson);
};
