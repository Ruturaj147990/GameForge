#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Engine/DeveloperSettings.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "GameForgeGameDefinition.generated.h"

/**
 * Primary data asset holding the validated gfdef/1 game definition (WI-5.1).
 */
UCLASS(BlueprintType)
class GAMEFORGERUNTIME_API UGameForgeGameDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "GameForge")
	FString SchemaVersion = TEXT("gfdef/1");

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "GameForge", meta = (MultiLine = true))
	FString DefinitionJson;

	/** Parsed once; nullptr if invalid (errors in ParseErrors). */
	TSharedPtr<FJsonObject> GetParsed() const;

	UPROPERTY(Transient, VisibleAnywhere, Category = "GameForge")
	mutable TArray<FString> ParseErrors;

	/** In-editor validator wrapper. */
	UFUNCTION(BlueprintCallable, Category = "GameForge")
	TArray<FString> ValidateDefinition();

	virtual FPrimaryAssetId GetPrimaryAssetId() const override
	{
		return FPrimaryAssetId(TEXT("GameForgeGameDefinition"), GetFName());
	}

private:
	mutable TSharedPtr<FJsonObject> Cached;
	mutable FString CachedSourceJson;
};

/**
 * Developer settings pointing to the default game definition for runtime and packaging.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "GameForge Runtime"))
class GAMEFORGERUNTIME_API UGameForgeRuntimeSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	UGameForgeRuntimeSettings();

	UPROPERTY(Config, EditAnywhere, Category = "GameForge")
	TSoftObjectPtr<UGameForgeGameDefinition> GameDefinition;
};
