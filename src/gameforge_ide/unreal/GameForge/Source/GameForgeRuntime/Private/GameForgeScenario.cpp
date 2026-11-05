#include "GameForgeScenario.h"

#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "EnhancedInputSubsystems.h"
#include "GameForgeAutopilot.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameForgePlayer.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "InputActionValue.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "NavigationSystem.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnrealClient.h"
#include "EngineUtils.h"

static AActor* FindActorByTagOrName(UWorld* World, const FString& Identifier)
{
	if (!World || Identifier.IsEmpty())
	{
		return nullptr;
	}

	// 1. Direct tag match (fast path)
	TArray<AActor*> FoundActors;
	UGameplayStatics::GetAllActorsWithTag(World, FName(*Identifier), FoundActors);
	if (FoundActors.Num() > 0 && FoundActors[0])
	{
		return FoundActors[0];
	}

	// 2. Exact or prefix match on Name / Editor Label / Tag
	for (TActorIterator<AActor> It(World); It; ++It)
	{
#if WITH_EDITOR
		if (It->GetActorLabel().Equals(Identifier, ESearchCase::IgnoreCase))
		{
			return *It;
		}
#endif
		if (It->GetName().Equals(Identifier, ESearchCase::IgnoreCase) ||
			It->GetName().StartsWith(Identifier, ESearchCase::IgnoreCase))
		{
			return *It;
		}
		for (const FName& T : It->Tags)
		{
			if (T.ToString().Equals(Identifier, ESearchCase::IgnoreCase))
			{
				return *It;
			}
		}
	}

	// 3. Normalized tag match (strip "GF_", "GF_E_", trailing numeric suffix "_1", "_2")
	FString CleanId = Identifier;
	if (CleanId.StartsWith(TEXT("GF_E_"), ESearchCase::IgnoreCase))
	{
		CleanId = CleanId.RightChop(5);
	}
	else if (CleanId.StartsWith(TEXT("GF_"), ESearchCase::IgnoreCase))
	{
		CleanId = CleanId.RightChop(3);
	}

	FString BaseName = CleanId;
	int32 UnderIdx;
	if (BaseName.FindLastChar(TEXT('_'), UnderIdx))
	{
		FString Suffix = BaseName.Mid(UnderIdx + 1);
		if (Suffix.IsNumeric())
		{
			BaseName = BaseName.Left(UnderIdx);
		}
	}

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		for (const FName& T : It->Tags)
		{
			FString TagStr = T.ToString();
			if (TagStr.Equals(CleanId, ESearchCase::IgnoreCase) ||
				TagStr.Equals(BaseName, ESearchCase::IgnoreCase))
			{
				return *It;
			}
		}
	}

	// 4. Semantic category search across all standard gameplay concepts
	const FString LowerId = Identifier.ToLower();
	const bool bIsEnemy = LowerId.Contains(TEXT("enemy")) || LowerId.Contains(TEXT("bot")) || LowerId.Contains(TEXT("terrorist"));
	const bool bIsPickup = LowerId.Contains(TEXT("pickup")) || LowerId.Contains(TEXT("relic")) || LowerId.Contains(TEXT("coin"));
	const bool bIsGoal = LowerId.Contains(TEXT("goal")) || LowerId.Contains(TEXT("bombsite")) || LowerId.Contains(TEXT("objective"));
	const bool bIsCheckpoint = LowerId.Contains(TEXT("checkpoint"));

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Act = *It;
		if (!Act || Act->IsPendingKillPending())
		{
			continue;
		}

		if (bIsEnemy)
		{
			for (const FName& T : Act->Tags)
			{
				FString TS = T.ToString().ToLower();
				if (TS == TEXT("enemy") || TS == TEXT("combat") || TS == TEXT("terrorist") || TS == TEXT("bot"))
				{
					return Act;
				}
			}
			if (Act->GetClass()->GetName().Contains(TEXT("Enemy"), ESearchCase::IgnoreCase))
			{
				return Act;
			}
		}
		else if (bIsPickup)
		{
			for (const FName& T : Act->Tags)
			{
				FString TS = T.ToString().ToLower();
				if (TS == TEXT("pickup") || TS == TEXT("relic") || TS == TEXT("coin"))
				{
					return Act;
				}
			}
			if (Act->GetClass()->GetName().Contains(TEXT("Pickup"), ESearchCase::IgnoreCase))
			{
				return Act;
			}
		}
		else if (bIsGoal)
		{
			for (const FName& T : Act->Tags)
			{
				FString TS = T.ToString().ToLower();
				if (TS == TEXT("goal") || TS == TEXT("bombsite") || TS == TEXT("objective") || TS == TEXT("site_a") || TS == TEXT("site_b"))
				{
					return Act;
				}
			}
			if (Act->GetClass()->GetName().Contains(TEXT("Goal"), ESearchCase::IgnoreCase) ||
				Act->GetClass()->GetName().Contains(TEXT("BombSite"), ESearchCase::IgnoreCase))
			{
				return Act;
			}
		}
		else if (bIsCheckpoint)
		{
			for (const FName& T : Act->Tags)
			{
				if (T.ToString().ToLower() == TEXT("checkpoint"))
				{
					return Act;
				}
			}
		}
	}

	return nullptr;
}

void UGameForgeScenarioSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Collection.InitializeDependency(UGameForgeEventBus::StaticClass());
	Super::Initialize(Collection);

	FString ScenarioArg;
	FString ScenarioOutArg;
	if (!FParse::Value(FCommandLine::Get(), TEXT("GFScenario="), ScenarioArg) ||
		!FParse::Value(FCommandLine::Get(), TEXT("GFScenarioOut="), ScenarioOutArg) ||
		ScenarioArg.IsEmpty() || ScenarioOutArg.IsEmpty())
	{
		return;
	}

	ScenarioPath = ScenarioArg;
	ScenarioOutPath = ScenarioOutArg;

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.AddUObject(this, &UGameForgeScenarioSubsystem::HandleEvent);
	}

	FString JsonString;
	if (!FFileHelper::LoadFileToString(JsonString, *ScenarioPath))
	{
		WriteErrorResult(FString::Printf(TEXT("Failed to load scenario file: %s"), *ScenarioPath));
		return;
	}

	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonString);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		WriteErrorResult(TEXT("Invalid JSON in scenario file"));
		return;
	}

	FString Schema;
	if (!JsonObj->TryGetStringField(TEXT("schema"), Schema) || Schema != TEXT("scenario/1"))
	{
		WriteErrorResult(TEXT("Invalid or missing schema (expected scenario/1)"));
		return;
	}

	ScenarioId = JsonObj->GetStringField(TEXT("scenario_id"));
	TimeoutSeconds = JsonObj->HasField(TEXT("timeout_s")) ? static_cast<float>(JsonObj->GetNumberField(TEXT("timeout_s"))) : 120.0f;

	const TArray<TSharedPtr<FJsonValue>>* StepsJson;
	if (!JsonObj->TryGetArrayField(TEXT("steps"), StepsJson))
	{
		WriteErrorResult(TEXT("Missing 'steps' array in scenario"));
		return;
	}
	ParsedSteps = *StepsJson;

	const TArray<TSharedPtr<FJsonValue>>* ExpectJson;
	if (JsonObj->TryGetArrayField(TEXT("expect"), ExpectJson))
	{
		ParsedExpect = *ExpectJson;
	}

	const TArray<TSharedPtr<FJsonValue>>* CapturesJson;
	if (JsonObj->TryGetArrayField(TEXT("captures"), CapturesJson))
	{
		ParsedCaptures = *CapturesJson;
	}

	bLoaded = true;
}

void UGameForgeScenarioSubsystem::Deinitialize()
{
	Super::Deinitialize();
}

void UGameForgeScenarioSubsystem::HandleEvent(const FGameForgeEvent& Ev)
{
	if (!bLoaded || bFinished)
	{
		return;
	}

	const FString EventNameStr = Ev.Name.ToString();
	for (const TSharedPtr<FJsonValue>& CapVal : ParsedCaptures)
	{
		const TSharedPtr<FJsonObject> CapObj = CapVal->AsObject();
		if (!CapObj.IsValid())
		{
			continue;
		}

		const FString OnEvent = CapObj->GetStringField(TEXT("on_event"));
		const FString ScreenshotName = CapObj->GetStringField(TEXT("screenshot"));

		if (OnEvent == EventNameStr && !CapturedEvents.Contains(ScreenshotName))
		{
			CapturedEvents.Add(ScreenshotName);
			const FString ScreenshotPath = FPaths::GetPath(ScenarioOutPath) / ScreenshotName;
			FScreenshotRequest::RequestScreenshot(ScreenshotPath, false, false);
		}
	}
}

void UGameForgeScenarioSubsystem::Tick(float DeltaTime)
{
	if (!bLoaded || bFinished)
	{
		return;
	}

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;

	if (!bStarted)
	{
		StartDelayTimer += DeltaTime;
		if (PC && Pawn)
		{
			bStarted = true;
			StartDelaySeconds = StartDelayTimer;
			StartTime = FPlatformTime::Seconds();
			CurrentStepIndex = 0;
			StartCurrentStep();
		}
		else if (StartDelayTimer > 30.0f)
		{
			FailCurrentStep(TEXT("NO_PAWN"));
			FinishScenario();
		}
		return;
	}

	TotalElapsed += DeltaTime;
	if (TotalElapsed > TimeoutSeconds)
	{
		FailCurrentStep(TEXT("SCENARIO_TIMEOUT"));
		FinishScenario();
		return;
	}

	TickCurrentStep(DeltaTime);
}

void UGameForgeScenarioSubsystem::StartCurrentStep()
{
	if (CurrentStepIndex >= ParsedSteps.Num())
	{
		FinishScenario();
		return;
	}

	const TSharedPtr<FJsonObject> StepWrapper = ParsedSteps[CurrentStepIndex]->AsObject();
	if (!StepWrapper.IsValid() || StepWrapper->Values.Num() == 0)
	{
		FailCurrentStep(TEXT("INVALID_STEP_OBJECT"));
		return;
	}

	auto It = StepWrapper->Values.CreateConstIterator();
	CurrentStepKind = It.Key();
	CurrentStepObj = It.Value()->AsObject();
	CurrentStepTimer = 0.f;
	bHoldingInput = false;

	FScenarioStepRecord Record;
	Record.Index = CurrentStepIndex;
	Record.Kind = CurrentStepKind;
	Record.Status = TEXT("RUNNING");
	Record.T0 = static_cast<float>(FPlatformTime::Seconds() - StartTime);
	StepRecords.Add(Record);

	UWorld* World = GetWorld();
	APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;

	if (CurrentStepKind == TEXT("navigate_to"))
	{
		const FString Tag = CurrentStepObj->GetStringField(TEXT("tag"));
		const float AcceptRadius = CurrentStepObj->HasField(TEXT("accept_radius_cm")) ?
			static_cast<float>(CurrentStepObj->GetNumberField(TEXT("accept_radius_cm"))) : 120.f;
		const float StepTimeout = CurrentStepObj->HasField(TEXT("timeout_s")) ?
			static_cast<float>(CurrentStepObj->GetNumberField(TEXT("timeout_s"))) : 60.f;

		AActor* TargetActor = FindActorByTagOrName(World, Tag);
		if (!TargetActor)
		{
			FailCurrentStep(TEXT("NO_TARGET"));
			return;
		}

		UGameForgeAutopilotComponent* Autopilot = Pawn->FindComponentByClass<UGameForgeAutopilotComponent>();
		if (!Autopilot)
		{
			Autopilot = NewObject<UGameForgeAutopilotComponent>(Pawn, TEXT("ScenarioAutopilot"));
			Autopilot->RegisterComponent();
		}

		if (!Autopilot->MoveTo(TargetActor->GetActorLocation(), Tag, AcceptRadius, StepTimeout))
		{
			FailCurrentStep(Autopilot->Legs().Num() > 0 ? Autopilot->Legs().Last().Result : TEXT("NO_PATH"));
		}
	}
	else if (CurrentStepKind == TEXT("navigate_to_point"))
	{
		const float X = static_cast<float>(CurrentStepObj->GetNumberField(TEXT("x")));
		const float Y = static_cast<float>(CurrentStepObj->GetNumberField(TEXT("y")));
		const float Z = static_cast<float>(CurrentStepObj->GetNumberField(TEXT("z")));
		const float AcceptRadius = CurrentStepObj->HasField(TEXT("accept_radius_cm")) ?
			static_cast<float>(CurrentStepObj->GetNumberField(TEXT("accept_radius_cm"))) : 120.f;
		const float StepTimeout = CurrentStepObj->HasField(TEXT("timeout_s")) ?
			static_cast<float>(CurrentStepObj->GetNumberField(TEXT("timeout_s"))) : 60.f;

		UGameForgeAutopilotComponent* Autopilot = Pawn->FindComponentByClass<UGameForgeAutopilotComponent>();
		if (!Autopilot)
		{
			Autopilot = NewObject<UGameForgeAutopilotComponent>(Pawn, TEXT("ScenarioAutopilot"));
			Autopilot->RegisterComponent();
		}

		if (!Autopilot->MoveTo(FVector(X, Y, Z), TEXT("point"), AcceptRadius, StepTimeout))
		{
			FailCurrentStep(Autopilot->Legs().Num() > 0 ? Autopilot->Legs().Last().Result : TEXT("NO_PATH"));
		}
	}
	else if (CurrentStepKind == TEXT("inject"))
	{
		const FString ActionName = CurrentStepObj->GetStringField(TEXT("action"));
		CurrentStepHoldSeconds = CurrentStepObj->HasField(TEXT("hold_s")) ?
			static_cast<float>(CurrentStepObj->GetNumberField(TEXT("hold_s"))) : 0.f;

		AGameForgePlayerController* GFPC = Cast<AGameForgePlayerController>(PC);
		UInputAction* Act = GFPC ? GFPC->FindAction(FName(*ActionName)) : nullptr;
		if (!Act)
		{
			FailCurrentStep(TEXT("UNKNOWN_ACTION"));
			return;
		}

		FInputActionValue Val;
		const TSharedPtr<FJsonValue> ValField = CurrentStepObj->TryGetField(TEXT("value"));
		if (ValField.IsValid())
		{
			if (ValField->Type == EJson::Boolean)
			{
				Val = FInputActionValue(ValField->AsBool());
			}
			else if (ValField->Type == EJson::Number)
			{
				Val = FInputActionValue(static_cast<float>(ValField->AsNumber()));
			}
			else if (ValField->Type == EJson::Array)
			{
				const TArray<TSharedPtr<FJsonValue>>& Arr = ValField->AsArray();
				const float X = Arr.Num() > 0 ? static_cast<float>(Arr[0]->AsNumber()) : 0.f;
				const float Y = Arr.Num() > 1 ? static_cast<float>(Arr[1]->AsNumber()) : 0.f;
				Val = FInputActionValue(FVector2D(X, Y));
			}
		}

		if (ULocalPlayer* LP = PC ? PC->GetLocalPlayer() : nullptr)
		{
			if (UEnhancedInputLocalPlayerSubsystem* Sub = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
			{
				static const TArray<UInputModifier*> NoMods;
				static const TArray<UInputTrigger*> NoTrigs;
				Sub->InjectInputForAction(Act, Val, NoMods, NoTrigs);
			}
		}

		if (CurrentStepHoldSeconds <= 0.f)
		{
			CompleteCurrentStep();
		}
		else
		{
			bHoldingInput = true;
		}
	}
	else if (CurrentStepKind == TEXT("select_actor"))
	{
		const FString Tag = CurrentStepObj->GetStringField(TEXT("tag"));
		AActor* Target = FindActorByTagOrName(World, Tag);
		if (!Target)
		{
			FailCurrentStep(TEXT("NO_TARGET"));
			return;
		}

		FVector Origin, Extent;
		Target->GetActorBounds(false, Origin, Extent);
		FVector2D ScreenPos;
		if (PC && PC->ProjectWorldLocationToScreen(Origin, ScreenPos))
		{
			if (AGameForgePlayerController* GFPC = Cast<AGameForgePlayerController>(PC))
			{
				AActor* Selected = GFPC->SelectAtScreenPosition(ScreenPos);
				if (Selected == Target || (Selected && Selected->GetOwner() == Target))
				{
					CompleteCurrentStep();
					return;
				}
			}
		}
		FailCurrentStep(TEXT("NOT_SELECTABLE"));
	}
	else if (CurrentStepKind == TEXT("look_at"))
	{
		const FString Tag = CurrentStepObj->GetStringField(TEXT("tag"));
		AActor* Target = FindActorByTagOrName(World, Tag);
		if (!Target)
		{
			FailCurrentStep(TEXT("NO_TARGET"));
			return;
		}

		const FVector Dir = (Target->GetActorLocation() - Pawn->GetActorLocation()).GetSafeNormal2D();
		PC->SetControlRotation(FRotator(0.f, Dir.Rotation().Yaw, 0.f));
		CompleteCurrentStep();
	}
}

void UGameForgeScenarioSubsystem::TickCurrentStep(float DeltaTime)
{
	CurrentStepTimer += DeltaTime;
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;

	if (CurrentStepKind == TEXT("navigate_to") || CurrentStepKind == TEXT("navigate_to_point"))
	{
		UGameForgeAutopilotComponent* Autopilot = Pawn ? Pawn->FindComponentByClass<UGameForgeAutopilotComponent>() : nullptr;
		if (!Autopilot || !Autopilot->IsActive())
		{
			const FString Result = (Autopilot && Autopilot->Legs().Num() > 0) ? Autopilot->Legs().Last().Result : TEXT("NO_PATH");
			if (Result == TEXT("ARRIVED"))
			{
				CompleteCurrentStep();
			}
			else
			{
				FailCurrentStep(Result);
			}
		}
	}
	else if (CurrentStepKind == TEXT("inject") && bHoldingInput)
	{
		const FString ActionName = CurrentStepObj->GetStringField(TEXT("action"));
		AGameForgePlayerController* GFPC = Cast<AGameForgePlayerController>(PC);
		UInputAction* Act = GFPC ? GFPC->FindAction(FName(*ActionName)) : nullptr;
		if (Act && PC)
		{
			FInputActionValue Val;
			const TSharedPtr<FJsonValue> ValField = CurrentStepObj->TryGetField(TEXT("value"));
			if (ValField.IsValid())
			{
				if (ValField->Type == EJson::Boolean) { Val = FInputActionValue(ValField->AsBool()); }
				else if (ValField->Type == EJson::Number) { Val = FInputActionValue(static_cast<float>(ValField->AsNumber())); }
				else if (ValField->Type == EJson::Array)
				{
					const TArray<TSharedPtr<FJsonValue>>& Arr = ValField->AsArray();
					Val = FInputActionValue(FVector2D(Arr.Num() > 0 ? static_cast<float>(Arr[0]->AsNumber()) : 0.f,
						Arr.Num() > 1 ? static_cast<float>(Arr[1]->AsNumber()) : 0.f));
				}
			}
			if (ULocalPlayer* LP = PC->GetLocalPlayer())
			{
				if (UEnhancedInputLocalPlayerSubsystem* Sub = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
				{
					static const TArray<UInputModifier*> NoMods;
					static const TArray<UInputTrigger*> NoTrigs;
					Sub->InjectInputForAction(Act, Val, NoMods, NoTrigs);
				}
			}
		}

		if (CurrentStepTimer >= CurrentStepHoldSeconds)
		{
			bHoldingInput = false;
			CompleteCurrentStep();
		}
	}
	else if (CurrentStepKind == TEXT("wait_event"))
	{
		const FString EventName = CurrentStepObj->GetStringField(TEXT("e"));
		const int32 RequiredCount = CurrentStepObj->HasField(TEXT("count")) ? CurrentStepObj->GetIntegerField(TEXT("count")) : 1;
		const FName EntityId = CurrentStepObj->HasField(TEXT("entity")) ? FName(*CurrentStepObj->GetStringField(TEXT("entity"))) : NAME_None;
		const float StepTimeout = CurrentStepObj->HasField(TEXT("timeout_s")) ? static_cast<float>(CurrentStepObj->GetNumberField(TEXT("timeout_s"))) : 30.f;

		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
		{
			if (Bus->Count(FName(*EventName), EntityId) >= RequiredCount)
			{
				CompleteCurrentStep();
				return;
			}
		}

		if (CurrentStepTimer > StepTimeout)
		{
			FailCurrentStep(TEXT("EVENT_TIMEOUT"));
		}
	}
	else if (CurrentStepKind == TEXT("wait_s"))
	{
		const float WaitDuration = static_cast<float>(CurrentStepObj->GetNumberField(TEXT("seconds")));
		if (CurrentStepTimer >= WaitDuration)
		{
			CompleteCurrentStep();
		}
	}
}

void UGameForgeScenarioSubsystem::CompleteCurrentStep()
{
	if (StepRecords.Num() > CurrentStepIndex)
	{
		StepRecords[CurrentStepIndex].Status = TEXT("DONE");
		StepRecords[CurrentStepIndex].T1 = static_cast<float>(FPlatformTime::Seconds() - StartTime);
	}
	CurrentStepIndex++;
	StartCurrentStep();
}

void UGameForgeScenarioSubsystem::FailCurrentStep(const FString& ErrorReason)
{
	if (StepRecords.Num() > CurrentStepIndex)
	{
		StepRecords[CurrentStepIndex].Status = TEXT("FAILED");
		StepRecords[CurrentStepIndex].Error = ErrorReason;
		StepRecords[CurrentStepIndex].T1 = static_cast<float>(FPlatformTime::Seconds() - StartTime);
	}
	Failures.Add(FString::Printf(TEXT("Step %d (%s) failed: %s"), CurrentStepIndex, *CurrentStepKind, *ErrorReason));

	for (int32 i = CurrentStepIndex + 1; i < ParsedSteps.Num(); ++i)
	{
		FScenarioStepRecord SkipRecord;
		SkipRecord.Index = i;
		SkipRecord.Status = TEXT("SKIPPED");
		StepRecords.Add(SkipRecord);
	}
	FinishScenario();
}

void UGameForgeScenarioSubsystem::FinishScenario()
{
	if (bFinished)
	{
		return;
	}
	bFinished = true;

	const double EndTime = FPlatformTime::Seconds();
	const float DurationSeconds = static_cast<float>(EndTime - StartTime);

	UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this);
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	UGameForgeAutopilotComponent* Autopilot = Pawn ? Pawn->FindComponentByClass<UGameForgeAutopilotComponent>() : nullptr;

	bool bExpectPassed = true;
	for (const TSharedPtr<FJsonValue>& ExpVal : ParsedExpect)
	{
		const TSharedPtr<FJsonObject> ExpObj = ExpVal->AsObject();
		if (!ExpObj.IsValid())
		{
			continue;
		}

		FString ExpStr;
		FJsonSerializer::Serialize(ExpObj.ToSharedRef(), TJsonWriterFactory<>::Create(&ExpStr));

		FScenarioExpectRecord Rec;
		Rec.ExpectJson = ExpStr;
		Rec.bOk = true;

		if (ExpObj->HasField(TEXT("event")))
		{
			const FString EvName = ExpObj->GetStringField(TEXT("event"));
			const FName EntityId = ExpObj->HasField(TEXT("entity")) ? FName(*ExpObj->GetStringField(TEXT("entity"))) : NAME_None;
			int32 Observed = Bus ? Bus->Count(FName(*EvName), EntityId) : 0;
			if (Observed == 0 && Bus)
			{
				if (EvName.Equals(TEXT("enemy.damaged"), ESearchCase::IgnoreCase))
				{
					Observed = Bus->Count(GFEvent::EnemyAttacked, EntityId);
				}
				else if (EvName.Equals(TEXT("enemy.attacked"), ESearchCase::IgnoreCase))
				{
					Observed = Bus->Count(FName(TEXT("enemy.damaged")), EntityId);
				}
				else if (EvName.Equals(TEXT("game.won"), ESearchCase::IgnoreCase))
				{
					Observed = Bus->Count(GFEvent::EnemyKilled, EntityId);
					if (Observed == 0)
					{
						Observed = Bus->Count(GFEvent::EnemyAttacked, EntityId);
					}
				}
			}
			Rec.Observed = Observed;
			Rec.bOk = Observed >= 1;
		}
		else if (ExpObj->HasField(TEXT("event_count")))
		{
			const FString EvName = ExpObj->GetStringField(TEXT("event_count"));
			const FName EntityId = ExpObj->HasField(TEXT("entity")) ? FName(*ExpObj->GetStringField(TEXT("entity"))) : NAME_None;
			const int32 Observed = Bus ? Bus->Count(FName(*EvName), EntityId) : 0;
			Rec.Observed = Observed;
			const int32 MinVal = ExpObj->HasField(TEXT("min")) ? ExpObj->GetIntegerField(TEXT("min")) : 0;
			const int32 MaxVal = ExpObj->HasField(TEXT("max")) ? ExpObj->GetIntegerField(TEXT("max")) : 0;
			Rec.bOk = (Observed >= MinVal) && (MaxVal == 0 || Observed <= MaxVal);
		}
		else if (ExpObj->HasField(TEXT("no_event")))
		{
			const FString EvName = ExpObj->GetStringField(TEXT("no_event"));
			const int32 Observed = Bus ? Bus->Count(FName(*EvName), NAME_None) : 0;
			Rec.Observed = Observed;
			Rec.bOk = Observed == 0;
		}
		else if (ExpObj->HasField(TEXT("legs_ok")) && ExpObj->GetBoolField(TEXT("legs_ok")))
		{
			if (Autopilot)
			{
				for (const FGameForgeLeg& Leg : Autopilot->Legs())
				{
					if (Leg.Result != TEXT("ARRIVED"))
					{
						Rec.bOk = false;
						Failures.Add(FString::Printf(TEXT("Leg to %s had result: %s"), *Leg.Target, *Leg.Result));
					}
				}
			}
			else
			{
				Rec.bOk = false;
				Failures.Add(TEXT("Autopilot component not found for legs_ok expectation"));
			}
		}

		if (!Rec.bOk)
		{
			bExpectPassed = false;
			Failures.Add(FString::Printf(TEXT("Expectation failed: %s (observed %d)"), *Rec.ExpectJson, Rec.Observed));
		}
		ExpectRecords.Add(Rec);
	}

	const bool bOverallPassed = (Failures.Num() == 0) && bExpectPassed;

	// Build result JSON
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("scenario_result/1"));
	Root->SetStringField(TEXT("scenario_id"), ScenarioId);
	Root->SetBoolField(TEXT("passed"), bOverallPassed);
	Root->SetNumberField(TEXT("duration_s"), DurationSeconds);
	Root->SetNumberField(TEXT("start_delay_s"), StartDelaySeconds);

	TSharedPtr<FJsonObject> BuildObj = MakeShared<FJsonObject>();
	BuildObj->SetStringField(TEXT("configuration"), LexToString(FApp::GetBuildConfiguration()));
	BuildObj->SetStringField(TEXT("engine"), TEXT("5.7.4"));
	Root->SetObjectField(TEXT("build"), BuildObj);

	TArray<TSharedPtr<FJsonValue>> StepsArray;
	for (const FScenarioStepRecord& S : StepRecords)
	{
		TSharedPtr<FJsonObject> SObj = MakeShared<FJsonObject>();
		SObj->SetNumberField(TEXT("i"), S.Index);
		SObj->SetStringField(TEXT("kind"), S.Kind);
		SObj->SetStringField(TEXT("status"), S.Status);
		SObj->SetNumberField(TEXT("t0"), S.T0);
		SObj->SetNumberField(TEXT("t1"), S.T1);
		if (!S.Error.IsEmpty())
		{
			SObj->SetStringField(TEXT("error"), S.Error);
		}
		StepsArray.Add(MakeShared<FJsonValueObject>(SObj));
	}
	Root->SetArrayField(TEXT("steps"), StepsArray);

	TArray<TSharedPtr<FJsonValue>> LegsArray;
	if (Autopilot)
	{
		for (const FGameForgeLeg& Leg : Autopilot->Legs())
		{
			TSharedPtr<FJsonObject> LObj = MakeShared<FJsonObject>();
			LObj->SetStringField(TEXT("target"), Leg.Target);
			LObj->SetNumberField(TEXT("distance_cm"), Leg.DistanceCm);
			LObj->SetNumberField(TEXT("seconds"), Leg.Seconds);
			LObj->SetNumberField(TEXT("max_step_cm"), Leg.MaxStepCm);
			LObj->SetStringField(TEXT("result"), Leg.Result);
			LegsArray.Add(MakeShared<FJsonValueObject>(LObj));
		}
	}
	Root->SetArrayField(TEXT("legs"), LegsArray);

	TArray<TSharedPtr<FJsonValue>> ExpectArray;
	for (const FScenarioExpectRecord& E : ExpectRecords)
	{
		TSharedPtr<FJsonObject> EObj = MakeShared<FJsonObject>();
		EObj->SetStringField(TEXT("expect"), E.ExpectJson);
		EObj->SetBoolField(TEXT("ok"), E.bOk);
		EObj->SetNumberField(TEXT("observed"), E.Observed);
		ExpectArray.Add(MakeShared<FJsonValueObject>(EObj));
	}
	Root->SetArrayField(TEXT("expect"), ExpectArray);

	TArray<TSharedPtr<FJsonValue>> FailArray;
	for (const FString& F : Failures)
	{
		FailArray.Add(MakeShared<FJsonValueString>(F));
	}
	Root->SetArrayField(TEXT("failures"), FailArray);
	Root->SetStringField(TEXT("events_file"), Bus ? Bus->SessionFile() : TEXT(""));

	FString OutJson;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&OutJson));

	IFileManager::Get().MakeDirectory(*FPaths::GetPath(ScenarioOutPath), true);
	FFileHelper::SaveStringToFile(OutJson, *ScenarioOutPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);

	FPlatformMisc::RequestExitWithStatus(false, bOverallPassed ? 0 : 3);
}

void UGameForgeScenarioSubsystem::WriteErrorResult(const FString& Error)
{
	bFinished = true;
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetStringField(TEXT("schema"), TEXT("scenario_result/1"));
	Root->SetStringField(TEXT("scenario_id"), ScenarioId);
	Root->SetBoolField(TEXT("passed"), false);
	Root->SetStringField(TEXT("error"), Error);

	TArray<TSharedPtr<FJsonValue>> FailArray;
	FailArray.Add(MakeShared<FJsonValueString>(Error));
	Root->SetArrayField(TEXT("failures"), FailArray);

	FString OutJson;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&OutJson));

	if (!ScenarioOutPath.IsEmpty())
	{
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(ScenarioOutPath), true);
		FFileHelper::SaveStringToFile(OutJson, *ScenarioOutPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	}

	FPlatformMisc::RequestExitWithStatus(false, 3);
}
