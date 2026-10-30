// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeAnimationLibrary.generated.h"

/**
 * Native C++ editor library providing genuine Unreal Engine 5.7.4 animation sequence
 * inspection, Animation Blueprint authoring, compilation, and retargeting verification.
 *
 * Zero mocks, zero simulators. Interacts directly with real UAnimSequence, UAnimBlueprint,
 * USkeleton, and FKismetEditorUtilities inside the actual editor runtime.
 */
UCLASS()
class GAMEFORGEEDITOR_API UGameForgeAnimationLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Authoritatively inspects a UAnimSequence asset:
	 * Target skeleton, duration, sampling rate, frame count, bone tracks, and root motion.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString InspectAnimationSequence(const FString& ParamsJson);

	/**
	 * Authoritatively inspects a UAnimBlueprint asset:
	 * Target skeleton, parent class, generated class, and compilation status.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString InspectAnimationBlueprint(const FString& ParamsJson);

	/**
	 * Creates and compiles a UAnimBlueprint whose parent is UGameForgeLocomotionAnimInstance (a native,
	 * movement-driven Idle/Walk/Run/Jump/Fall/Land state machine) and assigns its clips.
	 * Params: blueprint_name, destination_path, skeleton_path, clips {Idle, Walk, Run, Jump, Fall, Land: path}.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString CreateLocomotionAnimBlueprint(const FString& ParamsJson);

	/**
	 * Performs authoritative retargeting / duplication of an animation sequence to a compatible skeleton.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString RetargetAnimationSequence(const FString& ParamsJson);

	/**
	 * Creates a real UAnimSequence on the given skeleton from a GameForge motion bundle
	 * (*.motion.json: per-bone keys with rotation_quat [x,y,z,w] and location offsets from the
	 * bind pose). Params: skeleton_path, motion_json_path, destination_path, destination_name.
	 * Bones missing from the skeleton are reported, never silently dropped.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString ImportMotionClip(const FString& ParamsJson);

	/**
	 * In the running PIE world, spawns an AI-possessed ACharacter using the given skeletal mesh and
	 * AnimBP plus an AGameForgeLocomotionDriver that walks, runs and jumps it with real movement.
	 * Params: skeletal_mesh_path, anim_blueprint_path, location {x,y,z}.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString StartLocomotionTest(const FString& ParamsJson);

	/** Reads the driver's phases and the anim instance's observed state transitions. */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString GetLocomotionTestResult();

	/** Sends the PIE player's pawn along a NavMesh path to {x,y,z} (UAIBlueprintHelperLibrary::SimpleMoveToLocation). */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Animation")
	static FString MovePIEPlayerTo(const FString& ParamsJson);
};
