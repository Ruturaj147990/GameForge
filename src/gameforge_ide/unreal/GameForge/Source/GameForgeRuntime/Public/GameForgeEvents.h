#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "GameForgeEvents.generated.h"

GAMEFORGERUNTIME_API DECLARE_LOG_CATEGORY_EXTERN(LogGameForgeEvents, Log, All);

USTRUCT(BlueprintType)
struct GAMEFORGERUNTIME_API FGameForgeEvent
{
	GENERATED_BODY()
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FName Name;
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") float Time = 0.f;     // seconds since this game instance started
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString Source;       // emitting actor name (diagnostics only)
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FName Entity;         // GDS entity id (the actor's EntityId); matching uses this
	UPROPERTY(BlueprintReadOnly, Category = "GameForge") FString DataJson;     // a JSON object, "{}" when empty
};

DECLARE_MULTICAST_DELEGATE_OneParam(FOnGameForgeEvent, const FGameForgeEvent&);

/** One bus per game instance: in-game listeners, a JSONL file that works in Shipping, and a log line when logging exists. */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeEventBus : public UGameInstanceSubsystem
{
	GENERATED_BODY()
public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	static UGameForgeEventBus* Get(const UObject* WorldContext);

	void Emit(FName Name, const FString& Source, const FString& DataJson = TEXT("{}"), FName Entity = NAME_None);
	/** Events named Name; when Entity is not None, only those whose Entity matches. */
	int32 Count(FName Name, FName Entity = NAME_None) const;
	const TArray<FGameForgeEvent>& History() const { return Events; }
	const FString& SessionFile() const { return SessionPath; }

	FOnGameForgeEvent OnEvent;

private:
	TArray<FGameForgeEvent> Events;     // bounded to MaxEvents
	FString SessionPath;
	double StartSeconds = 0.0;
	static constexpr int32 MaxEvents = 20000;
};

UCLASS()
class GAMEFORGERUNTIME_API UGameForgeEventLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintCallable, Category = "GameForge|Events", meta = (WorldContext = "WorldContextObject"))
	static void EmitGameForgeEvent(const UObject* WorldContextObject, FName Name, const FString& Source, const FString& DataJson,
		FName Entity = NAME_None);
};
