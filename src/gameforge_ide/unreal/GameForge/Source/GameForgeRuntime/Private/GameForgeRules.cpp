#include "GameForgeRules.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameDefinition.h"
#include "GameForgeGameState.h"
#include "GameForgeGuard.h"
#include "GameForgeKitActors.h"
#include "GameForgeObjectives.h"
#include "GameForgePickup.h"
#include "GameForgePlayer.h"
#include "GameForgeVisuals.h"
#include "Engine/World.h"
#include "NavigationSystem.h"
#include "TimerManager.h"
#include "Kismet/GameplayStatics.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

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

		if (Op == TEXT("==") || Op == TEXT("="))
		{
			return FMath::IsNearlyEqual(CurrentVal, static_cast<float>(TargetVal), 1e-4f);
		}
		else if (Op == TEXT("!=") || Op == TEXT("<>"))
		{
			return !FMath::IsNearlyEqual(CurrentVal, static_cast<float>(TargetVal), 1e-4f);
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
		const FName EvFName(*EventName);
		const bool bHas = Ctx.HasEvent ? Ctx.HasEvent(EvFName, EntityName) : false;
		if (!bHas)
		{
			return false;
		}

		// Optional payload field matching ("where": {"key": "expected"})
		const TSharedPtr<FJsonObject>* WhereObj = nullptr;
		if (Condition->TryGetObjectField(TEXT("where"), WhereObj) && WhereObj && (*WhereObj).IsValid())
		{
			if (!Ctx.GetEventField)
			{
				return false;
			}
			for (const auto& Pair : (*WhereObj)->Values)
			{
				FString ActualVal;
				if (!Ctx.GetEventField(EvFName, Pair.Key, ActualVal, EntityName))
				{
					return false;
				}
				FString ExpectedVal;
				if (Pair.Value->TryGetString(ExpectedVal))
				{
					if (!ActualVal.Equals(ExpectedVal, ESearchCase::IgnoreCase))
					{
						return false;
					}
				}
			}
			return true;
		}

		// Default filter for board.win: ensure AI wins (winner == "ai") do not trigger player victory rules
		if (EventName.Equals(TEXT("board.win"), ESearchCase::IgnoreCase) && Ctx.GetEventField)
		{
			FString WinnerVal;
			if (Ctx.GetEventField(EvFName, TEXT("winner"), WinnerVal, EntityName))
			{
				if (WinnerVal.Equals(TEXT("ai"), ESearchCase::IgnoreCase))
				{
					return false;
				}
			}
		}
		return true;
	}
	else if (Kind == TEXT("not"))
	{
		TSharedPtr<FJsonObject> SubCond;
		const TSharedPtr<FJsonObject>* CondObj = nullptr;
		if (Condition->TryGetObjectField(TEXT("condition"), CondObj) && CondObj && (*CondObj).IsValid())
		{
			SubCond = *CondObj;
		}
		else
		{
			const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
			if ((Condition->TryGetArrayField(TEXT("conditions"), Items) || Condition->TryGetArrayField(TEXT("items"), Items)) &&
				Items && Items->Num() > 0 && (*Items)[0].IsValid())
			{
				SubCond = (*Items)[0]->AsObject();
			}
		}
		if (!SubCond.IsValid())
		{
			Error = TEXT("'not' condition missing inner 'condition' object");
			return false;
		}
		FString SubErr;
		const bool bSubRes = Evaluate(SubCond, Ctx, SubErr, Depth + 1);
		if (!SubErr.IsEmpty())
		{
			Error = SubErr;
			return false;
		}
		return !bSubRes;
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
	return CachedWorld ? CachedWorld->GetGameState<AGameForgeGameState>() : nullptr;
}

void UGameForgeCustomRule::Emit(FName Name, const FString& DataJson, FName Entity)
{
	if (CachedWorld)
	{
		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(CachedWorld))
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

	// Fresh counters for every play session / restart (the bus outlives the world).
	if (UGameForgeEventBus* ResetBus = UGameForgeEventBus::Get(&InWorld))
	{
		ResetBus->ResetCounters();
	}

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

void UGameForgeRulesSubsystem::SyncPlayerStatToAttributes(const FString& StatName, float NewVal) const
{
	UWorld* W = GetWorld();
	if (!W)
	{
		return;
	}
	APlayerController* PC = UGameplayStatics::GetPlayerController(W, 0);
	AGameForgeCharacter* GFChar = PC ? Cast<AGameForgeCharacter>(PC->GetPawn()) : nullptr;
	if (!GFChar || !GFChar->AttributeSet)
	{
		return;
	}
	if (StatName.Equals(TEXT("player.health"), ESearchCase::IgnoreCase))
	{
		GFChar->AttributeSet->SetHealth(FMath::Clamp(NewVal, 0.f, GFChar->AttributeSet->GetMaxHealth()));
	}
	else if (StatName.Equals(TEXT("player.max_health"), ESearchCase::IgnoreCase))
	{
		GFChar->AttributeSet->SetMaxHealth(FMath::Max(1.f, NewVal));
	}
	else if (StatName.Equals(TEXT("player.stamina"), ESearchCase::IgnoreCase))
	{
		GFChar->AttributeSet->SetStamina(FMath::Clamp(NewVal, 0.f, GFChar->AttributeSet->GetMaxStamina()));
	}
	else if (StatName.Equals(TEXT("player.max_stamina"), ESearchCase::IgnoreCase))
	{
		GFChar->AttributeSet->SetMaxStamina(FMath::Max(1.f, NewVal));
	}
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
			Ctx.GetEventField = [Bus](FName E, const FString& Key, FString& OutVal, FName Ent) -> bool
			{
				return Bus ? Bus->GetLastEventDataField(E, Key, OutVal, Ent) : false;
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
		if (!Effect->TryGetNumberField(TEXT("delta"), Delta))
		{
			Effect->TryGetNumberField(TEXT("amount"), Delta);
		}
		if (Effect->TryGetStringField(TEXT("stat"), Stat))
		{
			if (GS)
			{
				GS->AddStat(FName(*Stat), static_cast<float>(Delta));
				SyncPlayerStatToAttributes(Stat, GS->GetStat(FName(*Stat)));
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
				SyncPlayerStatToAttributes(Stat, GS->GetStat(FName(*Stat)));
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
	else if (Kind == TEXT("message"))
	{
		// Previously ignored: rule messages ("The gate is open!") never reached the player.
		FString Text;
		double Seconds = 3.0;
		Effect->TryGetStringField(TEXT("text"), Text);
		Effect->TryGetNumberField(TEXT("seconds"), Seconds);
		if (!Text.IsEmpty())
		{
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W))
			{
				TSharedRef<FJsonObject> Payload = MakeShared<FJsonObject>();
				Payload->SetStringField(TEXT("text"), Text);
				Payload->SetNumberField(TEXT("seconds"), Seconds);
				FString PayloadStr;
				TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&PayloadStr);
				FJsonSerializer::Serialize(Payload, Writer);
				Bus->Emit(FName(TEXT("ui.message")), TEXT("RulesSubsystem"), PayloadStr);
			}
		}
	}
	else if (Kind == TEXT("end_game"))
	{
		// Previously ignored, so rule-driven endings (e.g. "the AI won the board -> lose") never ended the game.
		FString Outcome;
		Effect->TryGetStringField(TEXT("outcome"), Outcome);
		if (!bGameEnded)
		{
			bGameEnded = true;
			const bool bWon = Outcome.Equals(TEXT("win"), ESearchCase::IgnoreCase);
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W))
			{
				Bus->Emit(bWon ? GFEvent::GameWon : GFEvent::GameLost, TEXT("RulesSubsystem"),
					FString::Printf(TEXT("{\"reason\":\"rule:%s\"}"), *TriggerEvent.Name.ToString()));
			}
		}
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
	FString EntityType;
	FString SpawnTag;
	(*EntSpec)->TryGetStringField(TEXT("class"), ClassPath);
	(*EntSpec)->TryGetStringField(TEXT("type"), EntityType);
	(*EntSpec)->TryGetStringField(TEXT("spawn_tag"), SpawnTag);

	UClass* SpawnCls = !ClassPath.IsEmpty() ? LoadClass<AActor>(nullptr, *ClassPath) : nullptr;
	if (!SpawnCls)
	{
		if (EntityType.Equals(TEXT("enemy"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("ranged_enemy"), ESearchCase::IgnoreCase) ||
			EntityType.Equals(TEXT("kit.enemy"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("kit.enemy_melee"), ESearchCase::IgnoreCase) ||
			EntityType.Equals(TEXT("kit.enemy_ranged"), ESearchCase::IgnoreCase))
		{
			SpawnCls = AGameForgeEnemy::StaticClass();
		}
		else if (EntityType.Equals(TEXT("pickup"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("kit.pickup"), ESearchCase::IgnoreCase))
		{
			SpawnCls = AGameForgePickup::StaticClass();
		}
		else if (EntityType.Equals(TEXT("hazard"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("kit.hazard"), ESearchCase::IgnoreCase))
		{
			SpawnCls = AGameForgeHazard::StaticClass();
		}
		else if (EntityType.Equals(TEXT("goal"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("kit.goal"), ESearchCase::IgnoreCase))
		{
			SpawnCls = AGameForgeGoal::StaticClass();
		}
		else if (EntityType.Equals(TEXT("guard"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("kit.guard"), ESearchCase::IgnoreCase))
		{
			SpawnCls = AGameForgeGuard::StaticClass();
		}
		else if (EntityType.Equals(TEXT("npc"), ESearchCase::IgnoreCase) || EntityType.Equals(TEXT("kit.quest_giver"), ESearchCase::IgnoreCase))
		{
			SpawnCls = AGameForgeQuestGiver::StaticClass();
		}
	}
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
	if (SpawnPoints.Num() == 0)
	{
		UGameplayStatics::GetAllActorsWithTag(W, FName(*(FString(TEXT("GF_SP_")) + EntityId)), SpawnPoints);
	}

	APawn* PlayerPawn = UGameplayStatics::GetPlayerPawn(W, 0);
	const FVector BaseOrigin = PlayerPawn ? PlayerPawn->GetActorLocation() : FVector::ZeroVector;
	UNavigationSystemV1* NavSys = FNavigationSystem::GetCurrent<UNavigationSystemV1>(W);

	const TSharedPtr<FJsonObject>* Props = nullptr;
	(*EntSpec)->TryGetObjectField(TEXT("properties"), Props);

	for (int32 i = 0; i < Count; i++)
	{
		FTransform SpawnTransform = FTransform::Identity;
		if (SpawnPoints.Num() > 0)
		{
			if (AActor* Sp = SpawnPoints[i % SpawnPoints.Num()])
			{
				SpawnTransform = Sp->GetActorTransform();
			}
		}
		else
		{
			const float Angle = (static_cast<float>(i) / FMath::Max(1, Count)) * 2.f * PI;
			FVector CandLoc = BaseOrigin + FVector(FMath::Cos(Angle) * 450.f, FMath::Sin(Angle) * 450.f, 90.f);
			FNavLocation Proj;
			if (NavSys && NavSys->ProjectPointToNavigation(CandLoc, Proj, FVector(300.f, 300.f, 500.f)))
			{
				CandLoc = Proj.Location + FVector(0.f, 0.f, 90.f);
			}
			SpawnTransform.SetLocation(CandLoc);
		}

		AActor* Spawned = W->SpawnActorDeferred<AActor>(SpawnCls, SpawnTransform, nullptr, nullptr,
			ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
		if (Spawned)
		{
			Spawned->Tags.AddUnique(FName(*(FString(TEXT("GF_E_")) + EntityId)));
			Spawned->Tags.AddUnique(FName(TEXT("GF_Owned")));

			if (Props && (*Props).IsValid())
			{
				const TSharedPtr<FJsonObject>& P = *Props;
				double V = 0.0;
				if (AGameForgeEnemy* Enemy = Cast<AGameForgeEnemy>(Spawned))
				{
					Enemy->EntityId = FName(*EntityId);
					if (P->TryGetNumberField(TEXT("max_health"), V)) Enemy->MaxHealth = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("attack_damage"), V)) Enemy->AttackDamage = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("attack_range"), V)) Enemy->AttackRange = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("attack_cooldown"), V)) Enemy->AttackCooldown = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("move_speed"), V)) Enemy->MoveSpeed = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("aggro_range"), V)) Enemy->AggroRange = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("projectile_speed"), V)) { Enemy->ProjectileSpeed = static_cast<float>(V); Enemy->bRanged = true; }
					bool bRangedFlag = false;
					if (P->TryGetBoolField(TEXT("ranged"), bRangedFlag)) Enemy->bRanged = bRangedFlag;
				}
				else if (AGameForgePickup* Pickup = Cast<AGameForgePickup>(Spawned))
				{
					Pickup->EntityId = FName(*EntityId);
					if (P->TryGetNumberField(TEXT("value"), V)) Pickup->Value = static_cast<int32>(V);
					FString EffStr;
					if (P->TryGetStringField(TEXT("effect"), EffStr)) Pickup->EffectName = EffStr;
					FString ItemStr;
					if (P->TryGetStringField(TEXT("item_id"), ItemStr)) Pickup->ItemId = FName(*ItemStr);
				}
				else if (AGameForgeGuard* Guard = Cast<AGameForgeGuard>(Spawned))
				{
					Guard->EntityId = FName(*EntityId);
					if (P->TryGetNumberField(TEXT("patrol_radius"), V)) Guard->PatrolRadius = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("aggro_radius"), V)) Guard->AggroRadius = static_cast<float>(V);
					if (P->TryGetNumberField(TEXT("move_speed"), V)) Guard->MoveSpeed = static_cast<float>(V);
				}
			}

			UGameplayStatics::FinishSpawningActor(Spawned, SpawnTransform);
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
	Ctx.GetEventField = [Bus](FName E, const FString& Key, FString& OutVal, FName Ent) -> bool
	{
		return Bus ? Bus->GetLastEventDataField(E, Key, OutVal, Ent) : false;
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
