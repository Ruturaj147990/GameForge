#include "GameForgeEvents.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"

DEFINE_LOG_CATEGORY(LogGameForgeEvents);

void UGameForgeEventBus::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	StartSeconds = FPlatformTime::Seconds();
	FString Override;
	FParse::Value(FCommandLine::Get(), TEXT("GFRunId="), RunId);
	if (FParse::Value(FCommandLine::Get(), TEXT("GFEventsOut="), Override) && !Override.IsEmpty())
	{
		SessionPath = Override;
	}
	else
	{
		SessionPath = FPaths::ProjectSavedDir() / TEXT("GameForge/events") /
			(FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")) + TEXT(".jsonl"));
	}
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(SessionPath), true);
}

UGameForgeEventBus* UGameForgeEventBus::Get(const UObject* WorldContext)
{
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContext, EGetWorldErrorMode::ReturnNull) : nullptr;
	UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UGameForgeEventBus>() : nullptr;
}

void UGameForgeEventBus::Emit(FName Name, const FString& Source, const FString& DataJson, FName Entity)
{
	FGameForgeEvent Ev;
	Ev.Name = Name;
	Ev.Source = Source;
	Ev.Entity = Entity;
	Ev.DataJson = DataJson.TrimStartAndEnd().StartsWith(TEXT("{")) ? DataJson : TEXT("{}");
	Ev.Time = static_cast<float>(FPlatformTime::Seconds() - StartSeconds);
	if (Events.Num() < MaxEvents)
	{
		Events.Add(Ev);
	}
	EventCountsByName.FindOrAdd(Name)++;
	if (!Entity.IsNone())
	{
		FString EntityKey = FString::Printf(TEXT("%s|%s"), *Name.ToString(), *Entity.ToString());
		EventCountsByEntity.FindOrAdd(EntityKey)++;
	}
	const FString Line = FString::Printf(TEXT("{\"schema\":\"gameforge_event/1\",\"run_id\":\"%s\",\"e\":\"%s\",\"t\":%.3f,\"src\":\"%s\",\"ent\":\"%s\",\"d\":%s}"),
		*RunId, *Name.ToString(), Ev.Time, *Source.ReplaceCharWithEscapedChar(),
		Entity.IsNone() ? TEXT("") : *Entity.ToString(), *Ev.DataJson);
	UE_LOG(LogGameForgeEvents, Display, TEXT("GF_EVENT %s"), *Line);           // compiled out in Shipping (fine)
	if (!FFileHelper::SaveStringToFile(Line + TEXT("\n"), *SessionPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
		&IFileManager::Get(), FILEWRITE_Append))
	{
		UE_LOG(LogGameForgeEvents, Warning, TEXT("Failed to append event to %s"), *SessionPath);
	}
	OnEvent.Broadcast(Ev);
}

int32 UGameForgeEventBus::Count(FName Name, FName Entity) const
{
	if (Entity.IsNone())
	{
		const int32* Found = EventCountsByName.Find(Name);
		return Found ? *Found : 0;
	}
	else
	{
		FString EntityKey = FString::Printf(TEXT("%s|%s"), *Name.ToString(), *Entity.ToString());
		const int32* Found = EventCountsByEntity.Find(EntityKey);
		return Found ? *Found : 0;
	}
}

void UGameForgeEventBus::ResetCounters()
{
	Events.Reset();
	EventCountsByName.Reset();
	EventCountsByEntity.Reset();
}

FName UGameForgeEventLibrary::ResolveEntityId(const AActor* Actor, FName Current)
{
	if (!Current.IsNone() || !Actor)
	{
		return Current;
	}
	static const FString Prefix(TEXT("GF_E_"));
	for (const FName& Tag : Actor->Tags)
	{
		const FString TagStr = Tag.ToString();
		if (TagStr.StartsWith(Prefix) && TagStr.Len() > Prefix.Len())
		{
			return FName(*TagStr.RightChop(Prefix.Len()));
		}
	}
	return Current;
}

void UGameForgeEventLibrary::EmitGameForgeEvent(const UObject* WorldContextObject, FName Name, const FString& Source,
	const FString& DataJson, FName Entity)
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(WorldContextObject))
	{
		Bus->Emit(Name, Source, DataJson, Entity);
	}
}
