// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeVFXLibrary.generated.h"

/**
 * Niagara spawning and read-back for the GameForge editor link (roadmap M13).
 * Particle counts come from the running system instances (FNiagaraEmitterInstance::GetNumParticles).
 */
UCLASS()
class GAMEFORGEEDITOR_API UGameForgeVFXLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Spawns a Niagara system with UNiagaraFunctionLibrary::SpawnSystemAtLocation.
	 * Params: {"system_path", "location": {x,y,z}, "label", "world": "editor" | "pie"}.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|VFX")
	static FString SpawnSystem(const FString& ParamsJson);

	/**
	 * Lists Niagara components in the chosen world with their system asset, active state, GameForge label and
	 * per-emitter particle counts. Params: {"world": "editor" | "pie", "label": optional filter}.
	 */
	UFUNCTION(BlueprintCallable, Category = "GameForge|VFX")
	static FString InspectParticles(const FString& ParamsJson);
};
