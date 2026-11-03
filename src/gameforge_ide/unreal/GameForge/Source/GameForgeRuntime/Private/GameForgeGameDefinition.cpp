#include "GameForgeGameDefinition.h"

UGameForgeRuntimeSettings::UGameForgeRuntimeSettings()
{
	CategoryName = TEXT("Game");
	SectionName = TEXT("GameForge Runtime");
	GameDefinition = FSoftObjectPath(TEXT("/Game/GameForge/GD_Main.GD_Main"));
}

TSharedPtr<FJsonObject> UGameForgeGameDefinition::GetParsed() const
{
	if (Cached.IsValid() && CachedSourceJson == DefinitionJson)
	{
		return Cached;
	}

	ParseErrors.Empty();
	Cached = nullptr;
	CachedSourceJson = DefinitionJson;

	if (DefinitionJson.IsEmpty())
	{
		ParseErrors.Add(TEXT("DefinitionJson is empty"));
		return nullptr;
	}

	TSharedPtr<FJsonObject> Root;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(DefinitionJson);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		ParseErrors.Add(FString::Printf(TEXT("JSON parse error: %s"), *Reader->GetErrorMessage()));
		return nullptr;
	}

	// Schema validation
	FString Schema;
	if (!Root->TryGetStringField(TEXT("schema"), Schema) || Schema != TEXT("gfdef/1"))
	{
		ParseErrors.Add(FString::Printf(TEXT("Expected schema 'gfdef/1', found '%s'"), *Schema));
	}

	if (!Root->HasField(TEXT("title")))
	{
		ParseErrors.Add(TEXT("Missing required field 'title'"));
	}

	if (ParseErrors.Num() == 0)
	{
		Cached = Root;
	}

	return Cached;
}

TArray<FString> UGameForgeGameDefinition::ValidateDefinition()
{
	GetParsed();
	return ParseErrors;
}
