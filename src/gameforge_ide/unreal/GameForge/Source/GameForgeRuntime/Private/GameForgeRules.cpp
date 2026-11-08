#include "GameForgeRules.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameDefinition.h"
#include "GameForgeGameState.h"
#include "GameForgePlayer.h"
#include "Engine/World.h"
#include "TimerManager.h"
#include "Kismet/GameplayStatics.h"

// ── FGameForgeConditionEvaluator ──────────────────────────────────────────────

bool FGameForgeConditionEvaluator::Evaluate(
	const TSharedPtr<FJsonObject>& Condition,
	const FContext& Ctx,
	FString& Error,
	int32 Depth)
{
	if (Depth > 3)
	{
		Error = TEXT("Condition evaluation exceeded maximum depth of 3");
		return false;
	}

	if (!Condition.IsValid())
	{
		Error = TEXT("Null condition object");
		return false;
	}

	FString Kind;
	if (!Condition->TryGetStringField(TEXT("kind"), Kind))
	{
		Error = TEXT("Condition missing 'kind' field");
		return false;
	}

	if (Kind == TEXT("count_at_least"))
	{
		FString EventName;
		if (!Condition->TryGetStringField(TEXT("event"), EventName))
		{
			Error = TEXT("count_at_least missing 'event' field");
			return false;
		}

		double N = 0;
		if (!Condition->TryGetNumberField(TEXT("n"), N))
		{
			Error = TEXT("count_at_least missing 'n' field");
			return false;
		}

		FName EntityName = NAME_None;
		FString Source;
		if (Condition->TryGetStringField(TEXT("source"), Source) && !Source.IsEmpty())
		{
			EntityName = FName(*Source);
		}

		int32 Count = Ctx.CountEvents ? Ctx.CountEvents(FName(*EventName), EntityName) : 0;
		return Count >= static_cast<int32>(N);
	}
	else if (Kind == TEXT("stat"))
	{
		FString StatName;
		if (!Condition->TryGetStringField(TEXT("stat"), StatName))
		{
			Error = TEXT("stat condition missing 'stat' field");
			return false;
		}

		FString Op;
		if (!Condition->TryGetStringField(TEXT("op"), Op))
		{
			Error = TEXT("stat condition missing 'op' field");
			return false;
		}

		double TargetVal = 0.0;
		if (!Condition->TryGetNumberField(TEXT("value"), TargetVal))
		{
			Error = TEXT("stat condition missing 'value' field");
			return false;
		}

		float CurrentVal = Ctx.GetStat ? Ctx.GetStat(FName(*StatName)) : NAN;
		if (FMath::IsNaN(CurrentVal))
		{
			return false;
		}

		if (Op == TEXT("=="))
		{
			return FMath::IsNearlyEqual(CurrentVal, static_cast<float>(TargetVal), 1e-4f);
		}
		else if (Op == TEXT("<="))
		{
			return CurrentVal <= static_cast<float>(TargetVal) + 1e-4f;
		}
		else if (Op == TEXT("<"))
		{
			return CurrentVal < static_cast<float>(TargetVal) - 1e-4f;
		}
		else if (Op == TEXT(">="))
		{
			return CurrentVal >= static_cast<float>(TargetVal) - 1e-4f;
		}
		else if (Op == TEXT(">"))
		{
			return CurrentVal > static_cast<float>(TargetVal) + 1e-4f;
		}
		else
		{
			Error = FString::Printf(TEXT("Unknown operator '%s' in stat condition"), *Op);
			return false;
		}
	}
	else if (Kind == TEXT("timer"))
	{
		double Seconds = 0.0;
		if (!Condition->TryGetNumberField(TEXT("seconds"), Seconds))
		{
			Error = TEXT("timer condition missing 'seconds' field");
			return false;
		}
		return Ctx.ElapsedSeconds >= static_cast<float>(Seconds);
	}
	else if (Kind == TEXT("event"))
	{
		FString EventName;
		if (!Condition->TryGetStringField(TEXT("event"), EventName))
		{
			Error = TEXT("event condition missing 'event' field");
			return false;
		}
		FName EntityName = NAME_None;
		FString Source;
		if (Condition->TryGetStringField(TEXT("source"), Source) && !Source.IsEmpty())
		{
			EntityName = FName(*Source);
		}
		return Ctx.HasEvent ? Ctx.HasEvent(FName(*EventName), EntityName) : false;
	}
	else if (Kind == TEXT("all"))
	{
		const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
		if (!Condition->TryGetArrayField(TEXT("conditions"), Items) &&
			!Condition->TryGetArrayField(TEXT("items"), Items))
		{
			Error = TEXT("'all' condition missing 'conditions' array");
			return false;
		}

		if (Items->Num() == 0)
		{
			Error = TEXT("Empty 'all' condition is malformed");
			return false;
		}

		for (const TSharedPtr<FJsonValue>& Val : *Items)
		{
			TSharedPtr<FJsonObject> Sub = Val->AsObject();
			if (!Evaluate(Sub, Ctx, Error, Depth + 1))
			{
				return false;
			}
		}
		return true;
	}
	else if (Kind == TEXT("any"))
	{
		const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
		if (!Condition->TryGetArrayField(TEXT("conditions"), Items) &&
			!Condition->TryGetArrayField(TEXT("items"), Items))
		{
			Error = TEXT("'any' condition missing 'conditions' array");
			return false;
		}

		if (Items->Num() == 0)
		{
			return false;
		}

		for (const TSharedPtr<FJsonValue>& Val : *Items)
		{
			TSharedPtr<FJsonObject> Sub = Val->AsObject();
			FString SubErr;
			if (Evaluate(Sub, Ctx, SubErr, Depth + 1))
			{
				return true;
			}
		}
		return false;
	}

	Error = FString::Printf(TEXT("Unknown condition kind '%s'"), *Kind);
	return false;
}

// ── UGameForgeCustomRule ──────────────────────────────────────────────────────

AGameForgeGameState* UGameForgeCustomRule::GameState() const
{
	return World ? World->GetGameState<AGameForgeGameState>() : nullptr;
}

void UGameForgeCustomRule::Emit(FName Name, const FString& DataJson, FName Entity)
{
	if (World)
	{
		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(World))
		{
			Bus->Emit(Name, GetName(), DataJson, Entity);
		}
	}
}

// ── UGameForgeRulesSubsystem ──────────────────────────────────────────────────

void UGameForgeRulesSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	StartTime = InWorld.GetTimeSeconds();
	bGameEnded = false;
	ReentrancyDepth = 0;

	// Load definition from settings
	const UGameForgeRuntimeSettings* Settings = GetDefault<UGameForgeRuntimeSettings>();
	if (Settings && !Settings->GameDefinition.IsNull())
	{
		if (UGameForgeGameDefinition* DefAsset = Settings->GameDefinition.LoadSynchronous())
		{
			Def = DefAsset->GetParsed();
		}
	}
	if (!Def.IsValid())
	{
		if (UGameForgeGameDefinition* FallbackAsset = LoadObject<UGameForgeGameDefinition>(nullptr, TEXT("/Game/GameForge/GD_Main.GD_Main")))
		{
			Def = FallbackAsset->GetParsed();
		}
	}
	if (!Def.IsValid())
	{
		if (UGameForgeGameDefinition* FallbackAsset = LoadObject<UGameForgeGameDefinition>(nullptr, TEXT("/Game/GameForge/GD_Main")))
		{
			Def = FallbackAsset->GetParsed();
		}
	}

	if (!Def.IsValid())
	{
		UE_LOG(LogGameForgeEvents, Warning, TEXT("No valid GameForge definition found in settings."));
		return;
	}

	// Initialize stats in GameState
	if (AGameForgeGameState* GS = InWorld.GetGameState<AGameForgeGameState>())
	{
		const TSharedPtr<FJsonObject>* StatsObj = nullptr;
		if (Def->TryGetObjectField(TEXT("stats"), StatsObj) && StatsObj)
		{
			for (const auto& Pair : (*StatsObj)->Values)
			{
				FName StatName(*Pair.Key);
				const TSharedPtr<FJsonObject> Info = Pair.Value->AsObject();
				if (Info.IsValid())
				{
					double Initial = 0.0;
					Info->TryGetNumberField(TEXT("initial"), Initial);

					double MinVal = -1e9;
					double MaxVal = 1e9;
					bool bHasMin = Info->TryGetNumberField(TEXT("min"), MinVal);
					bool bHasMax = Info->TryGetNumberField(TEXT("max"), MaxVal);

					GS->SetStatBounds(StatName, static_cast<float>(MinVal), static_cast<float>(MaxVal), bHasMin, bHasMax);
					GS->SetStat(StatName, static_cast<float>(Initial));
				}
			}
		}
	}

	// Subscribe to event bus
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(&InWorld))
	{
		Bus->OnEvent.AddUObject(this, &UGameForgeRulesSubsystem::HandleEvent);
	}

	// Instantiate custom rules
	const TArray<TSharedPtr<FJsonValue>>* CustomArr = nullptr;
	if (Def->TryGetArrayField(TEXT("custom_rules"), CustomArr) && CustomArr)
	{
		for (const TSharedPtr<FJsonValue>& Val : *CustomArr)
		{
			const TSharedPtr<FJsonObject> CInfo = Val->AsObject();
			if (CInfo.IsValid())
			{
				FString ClassPath;
				if (CInfo->TryGetStringField(TEXT("class"), ClassPath))
				{
					UClass* RuleClass = LoadClass<UGameForgeCustomRule>(nullptr, *ClassPath);
					if (RuleClass)
					{
						UGameForgeCustomRule* CR = NewObject<UGameForgeCustomRule>(this, RuleClass);
						CR->Initialize(&InWorld);
						CustomRules.Add(CR);
					}
					else
					{
						UE_LOG(LogGameForgeEvents, Warning, TEXT("Failed to load custom rule class %s"), *ClassPath);
					}
				}
			}
		}
	}

	// 0.25s timer for win/lose and custom rules tick
	InWorld.GetTimerManager().SetTimer(WinLoseTimerHandle, [this]()
	{
		CheckWinLose();
		for (UGameForgeCustomRule* CR : CustomRules)
		{
			if (CR)
			{
				CR->Tick(0.25f);
			}
		}
	}, 0.25f, true);
}

void UGameForgeRulesSubsystem::Deinitialize()
{
	if (UWorld* W = GetWorld())
	{
		W->GetTimerManager().ClearTimer(WinLoseTimerHandle);
	}
	CustomRules.Empty();
	Super::Deinitialize();
}

void UGameForgeRulesSubsystem::HandleEvent(const FGameForgeEvent& Event)
{
	if (bGameEnded || !Def.IsValid())
	{
		return;
	}

	// Forward to custom rules
	for (UGameForgeCustomRule* CR : CustomRules)
	{
		if (CR)
		{
			CR->OnEvent(Event);
		}
	}

	// Check rules table
	const TArray<TSharedPtr<FJsonValue>>* RulesArr = nullptr;
	if (Def->TryGetArrayField(TEXT("rules"), RulesArr) && RulesArr)
	{
		for (const TSharedPtr<FJsonValue>& Val : *RulesArr)
		{
			const TSharedPtr<FJsonObject> RuleObj = Val->AsObject();
			if (!RuleObj.IsValid())
			{
				continue;
			}

			// when match
			const TSharedPtr<FJsonObject>* WhenObj = nullptr;
			if (!RuleObj->TryGetObjectField(TEXT("when"), WhenObj) || !WhenObj)
			{
				continue;
			}

			FString WhenE;
			(*WhenObj)->TryGetStringField(TEXT("e"), WhenE);
			if (FName(*WhenE) != Event.Name)
			{
				continue;
			}

			FString WhenEnt;
			if ((*WhenObj)->TryGetStringField(TEXT("ent"), WhenEnt) && !WhenEnt.IsEmpty() && WhenEnt != TEXT("null"))
			{
				if (FName(*WhenEnt) != Event.Entity)
				{
					continue;
				}
			}

			// evaluate if conditions
			UWorld* W = GetWorld();
			AGameForgeGameState* GS = W ? W->GetGameState<AGameForgeGameState>() : nullptr;
			UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W);

			FGameForgeConditionEvaluator::FContext Ctx;
			Ctx.GetStat = [GS](FName S) -> float
			{
				return GS ? GS->GetStat(S) : 0.f;
			};
			Ctx.CountEvents = [Bus](FName E, FName Ent) -> int32
			{
				return Bus ? Bus->Count(E, Ent) : 0;
			};
			Ctx.HasEvent = [Bus](FName E, FName Ent) -> bool
			{
				return Bus ? (Bus->Count(E, Ent) > 0) : false;
			};
			Ctx.ElapsedSeconds = W ? static_cast<float>(W->GetTimeSeconds() - StartTime) : 0.f;

			bool bConditionsMet = true;
			const TArray<TSharedPtr<FJsonValue>>* IfArr = nullptr;
			if (RuleObj->TryGetArrayField(TEXT("if"), IfArr) && IfArr)
			{
				for (const TSharedPtr<FJsonValue>& CondVal : *IfArr)
				{
					FString Err;
					if (!FGameForgeConditionEvaluator::Evaluate(CondVal->AsObject(), Ctx, Err))
					{
						bConditionsMet = false;
						break;
					}
				}
			}

			if (bConditionsMet)
			{
				const TArray<TSharedPtr<FJsonValue>>* DoArr = nullptr;
				if (RuleObj->TryGetArrayField(TEXT("do"), DoArr) && DoArr)
				{
					for (const TSharedPtr<FJsonValue>& EffVal : *DoArr)
					{
						ApplyEffect(EffVal->AsObject(), Event);
					}
				}
			}
		}
	}

	CheckWinLose();
}

void UGameForgeRulesSubsystem::ApplyEffect(const TSharedPtr<FJsonObject>& Effect, const FGameForgeEvent& TriggerEvent)
{
	if (!Effect.IsValid())
	{
		return;
	}

	FString Kind;
	if (!Effect->TryGetStringField(TEXT("kind"), Kind))
	{
		return;
	}

	UWorld* W = GetWorld();
	AGameForgeGameState* GS = W ? W->GetGameState<AGameForgeGameState>() : nullptr;

	if (Kind == TEXT("add_stat"))
	{
		FString Stat;
		double Delta = 0.0;
		if (Effect->TryGetStringField(TEXT("stat"), Stat) && Effect->TryGetNumberField(TEXT("delta"), Delta))
		{
			if (GS)
			{
				GS->AddStat(FName(*Stat), static_cast<float>(Delta));
			}
		}
	}
	else if (Kind == TEXT("set_stat"))
	{
		FString Stat;
		double Value = 0.0;
		if (Effect->TryGetStringField(TEXT("stat"), Stat) && Effect->TryGetNumberField(TEXT("value"), Value))
		{
			if (GS)
			{
				GS->SetStat(FName(*Stat), static_cast<float>(Value));
			}
		}
	}
	else if (Kind == TEXT("emit"))
	{
		if (ReentrancyDepth > 4)
		{
			UE_LOG(LogGameForgeEvents, Warning, TEXT("RULE_LOOP detected; aborting emit"));
			return;
		}

		FString EventName;
		if (Effect->TryGetStringField(TEXT("event"), EventName))
		{
			ReentrancyDepth++;
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W))
			{
				Bus->Emit(FName(*EventName), TEXT("RulesSubsystem"), TEXT("{}"));
			}
			ReentrancyDepth--;
		}
	}
	else if (Kind == TEXT("spawn"))
	{
		FString EntityId;
		double Count = 1.0;
		Effect->TryGetStringField(TEXT("entity_id"), EntityId);
		Effect->TryGetNumberField(TEXT("count"), Count);
		SpawnEntity(EntityId, static_cast<int32>(Count));
	}
}

void UGameForgeRulesSubsystem::SpawnEntity(const FString& EntityId, int32 Count)
{
	if (!Def.IsValid())
	{
		return;
	}

	const TSharedPtr<FJsonObject>* EntitiesObj = nullptr;
	if (!Def->TryGetObjectField(TEXT("entities"), EntitiesObj) || !EntitiesObj)
	{
		return;
	}

	const TSharedPtr<FJsonObject>* EntSpec = nullptr;
	if (!(*EntitiesObj)->TryGetObjectField(EntityId, EntSpec) || !EntSpec)
	{
		return;
	}

	FString ClassPath;
	FString SpawnTag;
	(*EntSpec)->TryGetStringField(TEXT("class"), ClassPath);
	(*EntSpec)->TryGetStringField(TEXT("spawn_tag"), SpawnTag);

	UClass* SpawnCls = LoadClass<AActor>(nullptr, *ClassPath);
	if (!SpawnCls)
	{
		return;
	}

	UWorld* W = GetWorld();
	if (!W)
	{
		return;
	}

	TArray<AActor*> SpawnPoints;
	if (!SpawnTag.IsEmpty())
	{
		UGameplayStatics::GetAllActorsWithTag(W, FName(*SpawnTag), SpawnPoints);
	}

	for (int32 i = 0; i < Count; i++)
	{
		FTransform SpawnTransform = FTransform::Identity;
		if (SpawnPoints.Num() > 0)
		{
			AActor* Sp = SpawnPoints[i % SpawnPoints.Num()];
			if (Sp)
			{
				SpawnTransform = Sp->GetActorTransform();
			}
		}

		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
		AActor* Spawned = W->SpawnActor<AActor>(SpawnCls, SpawnTransform, Params);
		if (Spawned)
		{
			Spawned->Tags.AddUnique(FName(*(FString(TEXT("GF_E_")) + EntityId)));
		}
	}
}

void UGameForgeRulesSubsystem::CheckWinLose()
{
	if (bGameEnded || !Def.IsValid())
	{
		return;
	}

	UWorld* W = GetWorld();
	if (!W)
	{
		return;
	}

	AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>();
	UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W);

	FGameForgeConditionEvaluator::FContext Ctx;
	Ctx.GetStat = [GS](FName S) -> float
	{
		return GS ? GS->GetStat(S) : 0.f;
	};
	Ctx.CountEvents = [Bus](FName E, FName Ent) -> int32
	{
		return Bus ? Bus->Count(E, Ent) : 0;
	};
	Ctx.HasEvent = [Bus](FName E, FName Ent) -> bool
	{
		return Bus ? (Bus->Count(E, Ent) > 0) : false;
	};
	Ctx.ElapsedSeconds = static_cast<float>(W->GetTimeSeconds() - StartTime);

	// Evaluate LOSE conditions first (tie-break rule)
	const TArray<TSharedPtr<FJsonValue>>* LoseArr = nullptr;
	if (Def->TryGetArrayField(TEXT("lose"), LoseArr) && LoseArr)
	{
		for (int32 i = 0; i < LoseArr->Num(); i++)
		{
			FString Err;
			if (FGameForgeConditionEvaluator::Evaluate((*LoseArr)[i]->AsObject(), Ctx, Err))
			{
				bGameEnded = true;
				FString Reason = FString::Printf(TEXT("lose[%d]"), i);
				FString DataJson = FString::Printf(TEXT("{\"reason\":\"%s\"}"), *Reason);
				if (Bus)
				{
					Bus->Emit(GFEvent::GameLost, TEXT("RulesSubsystem"), DataJson);
				}
				return;
			}
		}
	}

	// Evaluate WIN conditions
	const TArray<TSharedPtr<FJsonValue>>* WinArr = nullptr;
	if (Def->TryGetArrayField(TEXT("win"), WinArr) && WinArr)
	{
		for (int32 i = 0; i < WinArr->Num(); i++)
		{
			FString Err;
			if (FGameForgeConditionEvaluator::Evaluate((*WinArr)[i]->AsObject(), Ctx, Err))
			{
				bGameEnded = true;
				FString Reason = FString::Printf(TEXT("win[%d]"), i);
				FString DataJson = FString::Printf(TEXT("{\"reason\":\"%s\"}"), *Reason);
				if (Bus)
				{
					Bus->Emit(GFEvent::GameWon, TEXT("RulesSubsystem"), DataJson);
				}
				return;
			}
		}
	}
}
