// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeObjectives.h"
#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameForgeGameState.h"
#include "GameForgeVisuals.h"

#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/ConstructorHelpers.h"

static const TCHAR* ObjectiveStateName(EGameForgeObjectiveState State)
{
	switch (State)
	{
		case EGameForgeObjectiveState::Inactive: return TEXT("Inactive");
		case EGameForgeObjectiveState::Active: return TEXT("Active");
		case EGameForgeObjectiveState::Completed: return TEXT("Completed");
	}
	return TEXT("Unknown");
}

void UGameForgeObjectiveSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	if (UGameplayStatics::DoesSaveGameExist(SlotName, 0))
	{
		if (const UGameForgeObjectiveSave* Save = Cast<UGameForgeObjectiveSave>(UGameplayStatics::LoadGameFromSlot(SlotName, 0)))
		{
			Objectives = Save->Objectives;
			SaveCount = Save->SaveCount;
			bLoadedFromSlot = true;
			UE_LOG(LogTemp, Display, TEXT("GF_EVENT objective_load slot=%s objectives=%d saves=%d"), *SlotName, Objectives.Num(), SaveCount);
			UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::SaveLoaded, SlotName,
				FString::Printf(TEXT("{\"objectives\":%d}"), Objectives.Num()), NAME_None);
		}
	}
}

UGameForgeObjectiveSubsystem* UGameForgeObjectiveSubsystem::GetForWorld(const UObject* WorldContextObject)
{
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<UGameForgeObjectiveSubsystem>() : nullptr;
}

FGameForgeObjective* UGameForgeObjectiveSubsystem::Find(FName Id)
{
	return Objectives.FindByPredicate([Id](const FGameForgeObjective& O) { return O.Id == Id; });
}

bool UGameForgeObjectiveSubsystem::StartObjective(FName Id, const FString& Title, int32 Target)
{
	FGameForgeObjective* O = Find(Id);
	if (O && O->State != EGameForgeObjectiveState::Inactive)
	{
		return false;  // already running or done (e.g. restored from the save)
	}
	if (!O)
	{
		O = &Objectives.AddDefaulted_GetRef();
		O->Id = Id;
	}
	O->Title = Title;
	O->Target = FMath::Max(1, Target);
	O->Progress = 0;
	O->State = EGameForgeObjectiveState::Active;
	UE_LOG(LogTemp, Display, TEXT("GF_EVENT objective_start id=%s target=%d"), *Id.ToString(), O->Target);
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::ObjectiveStarted, Id.ToString(),
		FString::Printf(TEXT("{\"target\":%d}"), O->Target), NAME_None);
	SaveNow();
	return true;
}

bool UGameForgeObjectiveSubsystem::AddProgress(FName Id, int32 Amount)
{
	FGameForgeObjective* O = Find(Id);
	if (!O || O->State != EGameForgeObjectiveState::Active)
	{
		return false;
	}
	O->Progress = FMath::Min(O->Target, O->Progress + Amount);
	UE_LOG(LogTemp, Display, TEXT("GF_EVENT objective_progress id=%s progress=%d/%d"), *Id.ToString(), O->Progress, O->Target);
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::ObjectiveUpdated, Id.ToString(),
		FString::Printf(TEXT("{\"progress\":%d,\"target\":%d}"), O->Progress, O->Target), NAME_None);
	if (O->Progress >= O->Target)
	{
		O->State = EGameForgeObjectiveState::Completed;
		UE_LOG(LogTemp, Display, TEXT("GF_EVENT objective_complete id=%s"), *Id.ToString());
		UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::ObjectiveCompleted, Id.ToString(), TEXT("{}"), NAME_None);
	}
	SaveNow();
	return true;
}

EGameForgeObjectiveState UGameForgeObjectiveSubsystem::GetState(FName Id) const
{
	const FGameForgeObjective* O = Objectives.FindByPredicate([Id](const FGameForgeObjective& X) { return X.Id == Id; });
	return O ? O->State : EGameForgeObjectiveState::Inactive;
}

bool UGameForgeObjectiveSubsystem::SaveNow()
{
	UGameForgeObjectiveSave* Save = Cast<UGameForgeObjectiveSave>(UGameplayStatics::CreateSaveGameObject(UGameForgeObjectiveSave::StaticClass()));
	Save->Objectives = Objectives;
	Save->SaveCount = ++SaveCount;
	const bool bOk = UGameplayStatics::SaveGameToSlot(Save, SlotName, 0);
	UE_LOG(LogTemp, Display, TEXT("GF_EVENT objective_save slot=%s ok=%d count=%d"), *SlotName, bOk ? 1 : 0, SaveCount);
	if (bOk)
	{
		UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::SaveWritten, SlotName,
			TEXT("{\"ok\":true}"), NAME_None);
	}
	return bOk;
}

FString UGameForgeObjectiveSubsystem::GetObjectivesJson() const
{
	TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
	Root->SetBoolField(TEXT("loaded_from_slot"), bLoadedFromSlot);
	Root->SetNumberField(TEXT("save_count"), SaveCount);
	TArray<TSharedPtr<FJsonValue>> List;
	for (const FGameForgeObjective& O : Objectives)
	{
		TSharedPtr<FJsonObject> J = MakeShared<FJsonObject>();
		J->SetStringField(TEXT("id"), O.Id.ToString());
		J->SetStringField(TEXT("title"), O.Title);
		J->SetStringField(TEXT("state"), ObjectiveStateName(O.State));
		J->SetNumberField(TEXT("progress"), O.Progress);
		J->SetNumberField(TEXT("target"), O.Target);
		List.Add(MakeShared<FJsonValueObject>(J));
	}
	Root->SetArrayField(TEXT("objectives"), List);
	FString Out;
	FJsonSerializer::Serialize(Root.ToSharedRef(), TJsonWriterFactory<>::Create(&Out));
	return Out;
}

AGameForgeQuestGiver::AGameForgeQuestGiver()
{
	TalkRadius = CreateDefaultSubobject<USphereComponent>(TEXT("TalkRadius"));
	TalkRadius->InitSphereRadius(220.0f);
	TalkRadius->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	TalkRadius->SetGenerateOverlapEvents(true);
	RootComponent = TalkRadius;

	Visual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Visual"));
	Visual->SetupAttachment(TalkRadius);
	Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Visual->SetRelativeScale3D(FVector(0.6f, 0.6f, 1.8f));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Cylinder.Succeeded())
	{
		Visual->SetStaticMesh(Cylinder.Object);
	}
	TalkRadius->OnComponentBeginOverlap.AddDynamic(this, &AGameForgeQuestGiver::HandleOverlap);
}

void AGameForgeQuestGiver::SyncQuestProperties()
{
	if (ObjectiveId.IsNone() && !QuestId.IsNone())
	{
		ObjectiveId = QuestId;
	}
	if (ObjectiveTitle.IsEmpty() && !ObjectiveText.IsEmpty())
	{
		ObjectiveTitle = ObjectiveText;
	}
	else if (ObjectiveText.IsEmpty() && !ObjectiveTitle.IsEmpty())
	{
		ObjectiveText = ObjectiveTitle;
	}
	if (ObjectiveTarget <= 1 && TargetCount > 1)
	{
		ObjectiveTarget = TargetCount;
	}
	if (IntroLines.Num() == 0)
	{
		const FString DefaultLine = !ObjectiveText.IsEmpty() ? ObjectiveText : ObjectiveTitle;
		if (!DefaultLine.IsEmpty())
		{
			IntroLines.Add(DefaultLine);
		}
	}
}

void AGameForgeQuestGiver::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	SyncQuestProperties();
	GameForgeVisuals::Tint(Visual, FLinearColor(0.25f, 0.85f, 0.55f, 1.f));
}

void AGameForgeQuestGiver::Say(const FString& Line)
{
	SpokenLines.Add(Line);
	UE_LOG(LogTemp, Display, TEXT("GF_EVENT dialogue speaker=%s line=\"%s\""), *GetName(), *Line);
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::DialogueLine, GetName(),
		FString::Printf(TEXT("{\"line\":\"%s\",\"speaker\":\"%s\"}"),
			*Line.ReplaceCharWithEscapedChar(),
			*NpcName.ReplaceCharWithEscapedChar()), EntityId);
}

void AGameForgeQuestGiver::TriggerTalk(const APawn* Pawn)
{
	SyncQuestProperties();
	UGameInstance* GI = GetGameInstance();
	UGameForgeObjectiveSubsystem* Objectives = GI ? GI->GetSubsystem<UGameForgeObjectiveSubsystem>() : nullptr;
	if (!Pawn || !Pawn->IsPlayerControlled() || !Objectives)
	{
		return;
	}
	if (ObjectiveId.IsNone())
	{
		for (const FString& Line : IntroLines)  // plain NPC: talks, starts nothing
		{
			Say(Line);
		}
		return;
	}
	switch (Objectives->GetState(ObjectiveId))
	{
		case EGameForgeObjectiveState::Inactive:
			for (const FString& Line : IntroLines)
			{
				Say(Line);
			}
			Objectives->StartObjective(ObjectiveId, ObjectiveTitle, ObjectiveTarget);
			break;
		case EGameForgeObjectiveState::Completed:
			if (!TurnInLine.IsEmpty())
			{
				Say(TurnInLine);
			}
			if (RewardScore > 0 && GetWorld())
			{
				if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
				{
					GS->AddStat(FName(TEXT("game.score")), static_cast<float>(RewardScore));
					RewardScore = 0; // grant once
				}
			}
			break;
		default:
			break;
	}
}

void AGameForgeQuestGiver::Interact(AController* InController)
{
	const APawn* Pawn = nullptr;
	if (InController)
	{
		Pawn = InController->GetPawn();
	}
	else
	{
		Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
	}
	TriggerTalk(Pawn);
}

void AGameForgeQuestGiver::HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (!bTalkOnOverlap)
	{
		return;
	}
	if (const APawn* Pawn = Cast<APawn>(OtherActor))
	{
		TriggerTalk(Pawn);
	}
}
