// Copyright 2026 GameForge Systems. All Rights Reserved.
#pragma once

#include "CoreMinimal.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

/**
 * Small presentation helpers shared by the kit actors.
 *
 * Kit actors are built from engine basic shapes so they work in a blank project, but untinted basic shapes all render
 * as the same flat white, which made pickups, hazards, goals and enemies indistinguishable. BasicShapeMaterial exposes
 * a "Color" vector parameter, so a dynamic instance per component gives each role a readable colour without any
 * project content.
 */
namespace GameForgeVisuals
{
	inline const TCHAR* BasicShapeMaterialPath() { return TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"); }

	/** Tints every material slot of Comp; returns the created dynamic instances (may be empty). */
	inline TArray<UMaterialInstanceDynamic*> Tint(UStaticMeshComponent* Comp, const FLinearColor& Color)
	{
		TArray<UMaterialInstanceDynamic*> Out;
		if (!Comp || !Comp->GetStaticMesh())
		{
			return Out;
		}
		const int32 NumSlots = FMath::Max(1, Comp->GetNumMaterials());
		for (int32 Slot = 0; Slot < NumSlots; ++Slot)
		{
			UMaterialInterface* Base = Comp->GetMaterial(Slot);
			if (!Base)
			{
				Base = LoadObject<UMaterialInterface>(nullptr, BasicShapeMaterialPath());
			}
			if (!Base)
			{
				continue;
			}
			UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(Base);
			if (!MID)
			{
				MID = UMaterialInstanceDynamic::Create(Base, Comp);
				Comp->SetMaterial(Slot, MID);
			}
			if (MID)
			{
				MID->SetVectorParameterValue(TEXT("Color"), Color);
				Out.Add(MID);
			}
		}
		return Out;
	}

	/** Assigns an engine basic shape ("Cube", "Sphere", "Cylinder", "Cone", "Plane") at runtime. */
	inline bool SetBasicShape(UStaticMeshComponent* Comp, const TCHAR* ShapeName)
	{
		if (!Comp)
		{
			return false;
		}
		const FString Path = FString::Printf(TEXT("/Engine/BasicShapes/%s.%s"), ShapeName, ShapeName);
		if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, *Path))
		{
			Comp->SetStaticMesh(SM);
			return true;
		}
		return false;
	}

	/** Parses [r,g,b(,a)] from a JSON-like number array already converted to doubles. */
	inline FLinearColor ColorFromArray(const TArray<double>& Values, const FLinearColor& Fallback)
	{
		if (Values.Num() < 3)
		{
			return Fallback;
		}
		return FLinearColor(
			static_cast<float>(Values[0]), static_cast<float>(Values[1]), static_cast<float>(Values[2]),
			Values.Num() > 3 ? static_cast<float>(Values[3]) : 1.f);
	}
}
