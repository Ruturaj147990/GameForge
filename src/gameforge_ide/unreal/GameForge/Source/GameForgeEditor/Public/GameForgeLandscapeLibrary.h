// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeLandscapeLibrary.generated.h"

/**
 * Native C++ editor library providing genuine Unreal Engine 5.7.4 procedural landscape,
 * spline road/trail, instanced foliage/prop scattering, and landmark authoring.
 *
 * Zero mocks, zero simulators. Interacts with real ALandscape, USplineComponent,
 * USplineMeshComponent, and UHierarchicalInstancedStaticMeshComponent.
 */
UCLASS()
class GAMEFORGEEDITOR_API UGameForgeLandscapeLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Creates a genuine ALandscape actor with procedural multi-octave heightfield in the current active editor world.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Landscape")
	static FString CreateLandscape(const FString& ParamsJson);

	/**
	 * Creates a genuine spline road/trail actor with USplineComponent and USplineMeshComponent segments.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Landscape")
	static FString CreateSplineRoad(const FString& ParamsJson);

	/**
	 * Scatters procedural vegetation and environmental props using UHierarchicalInstancedStaticMeshComponent (HISM)
	 * with slope, elevation, and road clearance filtering.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Landscape")
	static FString CreateFoliageScatter(const FString& ParamsJson);

	/**
	 * Spawns an architectural point-of-interest landmark structure in the active world.
	 * Returns structured JSON envelope.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Landscape")
	static FString CreateLandmark(const FString& ParamsJson);

	/**
	 * Performs authoritative inspection of the procedural world in the active world.
	 * Returns structured JSON envelope with landscape dimensions, spline metrics, foliage instance counts, and landmark status.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Landscape")
	static FString InspectProceduralWorld();
};
