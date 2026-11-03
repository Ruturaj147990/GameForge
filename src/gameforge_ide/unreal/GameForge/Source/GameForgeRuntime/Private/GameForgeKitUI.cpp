#include "GameForgeKitUI.h"
#include "GameForgeGameDefinition.h"
#include "GameForgeGameState.h"
#include "GameForgeEventNames.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/VerticalBoxSlot.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/World.h"
#include "TimerManager.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"

// ── HUD Widget ────────────────────────────────────────────────────────────────

TSharedRef<SWidget> UGameForgeHUDWidget::RebuildWidget()
{
	if (!WidgetTree)
	{
		WidgetTree = NewObject<UWidgetTree>(this, TEXT("WidgetTree"));
	}

	if (WidgetTree && !WidgetTree->RootWidget)
	{
		UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("Root"));
		WidgetTree->RootWidget = Root;
		BuildRows(Root);
	}

	return Super::RebuildWidget();
}

void UGameForgeHUDWidget::BuildRows(UCanvasPanel* Root)
{
	if (!Root || !WidgetTree)
	{
		return;
	}

	RowBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("RowBox"));
	if (UCanvasPanelSlot* BoxSlot = Root->AddChildToCanvas(RowBox))
	{
		BoxSlot->SetAnchors(FAnchors(0.f, 0.f, 0.f, 0.f));
		BoxSlot->SetOffsets(FMargin(20.f, 20.f, 300.f, 400.f));
		BoxSlot->SetAutoSize(true);
	}

	MessageText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("MessageText"));
	if (MessageText)
	{
		MessageText->SetText(FText::GetEmpty());
		if (UCanvasPanelSlot* MsgSlot = Root->AddChildToCanvas(MessageText))
		{
			MsgSlot->SetAnchors(FAnchors(0.5f, 0.2f, 0.5f, 0.2f));
			MsgSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			MsgSlot->SetAutoSize(true);
		}
	}

	// Center Crosshair for first-person / shooting
	UTextBlock* Crosshair = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("Crosshair"));
	if (Crosshair)
	{
		Crosshair->SetText(FText::FromString(TEXT("+")));
		Crosshair->SetColorAndOpacity(FSlateColor(FLinearColor(1.0f, 1.0f, 1.0f, 0.85f)));
		if (UCanvasPanelSlot* CrossSlot = Root->AddChildToCanvas(Crosshair))
		{
			CrossSlot->SetAnchors(FAnchors(0.5f, 0.5f, 0.5f, 0.5f));
			CrossSlot->SetAlignment(FVector2D(0.5f, 0.5f));
			CrossSlot->SetAutoSize(true);
		}
	}

	// Read HUD items from settings definition
	const UGameForgeRuntimeSettings* Settings = GetDefault<UGameForgeRuntimeSettings>();
	UGameForgeGameDefinition* DefAsset = (Settings && !Settings->GameDefinition.IsNull())
		? Settings->GameDefinition.LoadSynchronous()
		: nullptr;
	if (!DefAsset)
	{
		DefAsset = LoadObject<UGameForgeGameDefinition>(nullptr, TEXT("/Game/GameForge/GD_Main.GD_Main"));
	}
	if (!DefAsset)
	{
		DefAsset = LoadObject<UGameForgeGameDefinition>(nullptr, TEXT("/Game/GameForge/GD_Main"));
	}
	if (!DefAsset)
	{
		return;
	}

	TSharedPtr<FJsonObject> Def = DefAsset->GetParsed();
	if (!Def.IsValid())
	{
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* HudArr = nullptr;
	if (Def->TryGetArrayField(TEXT("hud"), HudArr) && HudArr)
	{
		for (const TSharedPtr<FJsonValue>& Val : *HudArr)
		{
			TSharedPtr<FJsonObject> HObj = Val->AsObject();
			if (!HObj.IsValid())
			{
				continue;
			}

			FHudRow Row;
			HObj->TryGetStringField(TEXT("id"), Row.Id);
			HObj->TryGetStringField(TEXT("kind"), Row.Kind);
			FString StatStr;
			HObj->TryGetStringField(TEXT("stat"), StatStr);
			Row.StatName = FName(*StatStr);
			HObj->TryGetStringField(TEXT("label"), Row.Label);

			double OfVal = 100.0;
			if (HObj->TryGetNumberField(TEXT("of"), OfVal))
			{
				Row.MaxValue = static_cast<float>(OfVal);
			}

			if (Row.Kind == TEXT("bar"))
			{
				UTextBlock* Lbl = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
				Lbl->SetText(FText::FromString(Row.Label));
				RowBox->AddChildToVerticalBox(Lbl);

				Row.BarWidget = WidgetTree->ConstructWidget<UProgressBar>(UProgressBar::StaticClass());
				Row.BarWidget->SetPercent(1.0f);
				RowBox->AddChildToVerticalBox(Row.BarWidget);
			}
			else
			{
				Row.TextWidget = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
				Row.TextWidget->SetText(FText::FromString(FString::Printf(TEXT("%s: --"), *Row.Label)));
				RowBox->AddChildToVerticalBox(Row.TextWidget);
			}

			Rows.Add(Row);
		}
	}
}

void UGameForgeHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();

	if (UWorld* W = GetWorld())
	{
		if (AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>())
		{
			GS->OnStatChanged.AddDynamic(this, &UGameForgeHUDWidget::OnStatChanged);

			// Initial refresh from current stats
			for (const auto& Pair : GS->GetAllStats())
			{
				OnStatChanged(Pair.Key, Pair.Value);
			}
		}

		W->GetTimerManager().SetTimer(TimerRefreshHandle, [this, W]()
		{
			if (AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>())
			{
				for (FHudRow& Row : Rows)
				{
					if (Row.Kind == TEXT("timer") && Row.TextWidget)
					{
						float Secs = GS->GetStat(Row.StatName);
						int32 Mins = static_cast<int32>(Secs) / 60;
						int32 RemSecs = static_cast<int32>(Secs) % 60;
						Row.TextWidget->SetText(FText::FromString(FString::Printf(TEXT("%s: %02d:%02d"), *Row.Label, Mins, RemSecs)));
					}
				}
			}
		}, 0.25f, true);
	}
}

void UGameForgeHUDWidget::NativeDestruct()
{
	if (UWorld* W = GetWorld())
	{
		W->GetTimerManager().ClearTimer(TimerRefreshHandle);
		W->GetTimerManager().ClearTimer(MessageFadeHandle);
	}
	Super::NativeDestruct();
}

void UGameForgeHUDWidget::OnStatChanged(FName StatName, float NewValue)
{
	for (FHudRow& Row : Rows)
	{
		if (Row.StatName == StatName)
		{
			if (Row.Kind == TEXT("bar") && Row.BarWidget)
			{
				Row.BarWidget->SetPercent(FMath::Clamp(NewValue / FMath::Max(Row.MaxValue, 1.0f), 0.f, 1.f));
			}
			else if (Row.Kind == TEXT("counter") && Row.TextWidget)
			{
				Row.TextWidget->SetText(FText::FromString(FString::Printf(TEXT("%s: %.0f / %.0f"), *Row.Label, NewValue, Row.MaxValue)));
			}
			else if (Row.TextWidget)
			{
				Row.TextWidget->SetText(FText::FromString(FString::Printf(TEXT("%s: %.0f"), *Row.Label, NewValue)));
			}
		}
	}
}

void UGameForgeHUDWidget::ShowMessage(const FString& Message, float DurationSeconds)
{
	if (!MessageText)
	{
		return;
	}

	MessageText->SetText(FText::FromString(Message));
	if (UWorld* W = GetWorld())
	{
		W->GetTimerManager().SetTimer(MessageFadeHandle, [this]()
		{
			if (MessageText)
			{
				MessageText->SetText(FText::GetEmpty());
			}
		}, DurationSeconds, false);
	}
}

// ── Menu Widget ───────────────────────────────────────────────────────────────

TSharedRef<SWidget> UGameForgeMenuWidget::RebuildWidget()
{
	if (!WidgetTree)
	{
		WidgetTree = NewObject<UWidgetTree>(this, TEXT("WidgetTree"));
	}

	if (WidgetTree && !WidgetTree->RootWidget)
	{
		MenuRoot = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("MenuRoot"));
		WidgetTree->RootWidget = MenuRoot;

		TitleText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("TitleText"));
		TitleText->SetText(FText::FromString(TEXT("GameForge")));
		if (UCanvasPanelSlot* PanelSlot1 = MenuRoot->AddChildToCanvas(TitleText))
		{
			PanelSlot1->SetAnchors(FAnchors(0.5f, 0.3f, 0.5f, 0.3f));
			PanelSlot1->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot1->SetAutoSize(true);
		}

		PrimaryButton = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("PrimaryButton"));
		if (UCanvasPanelSlot* PanelSlot2 = MenuRoot->AddChildToCanvas(PrimaryButton))
		{
			PanelSlot2->SetAnchors(FAnchors(0.5f, 0.5f, 0.5f, 0.5f));
			PanelSlot2->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot2->SetSize(FVector2D(200.f, 50.f));
		}

		SecondaryButton = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("SecondaryButton"));
		if (UCanvasPanelSlot* PanelSlot3 = MenuRoot->AddChildToCanvas(SecondaryButton))
		{
			PanelSlot3->SetAnchors(FAnchors(0.5f, 0.6f, 0.5f, 0.6f));
			PanelSlot3->SetAlignment(FVector2D(0.5f, 0.5f));
			PanelSlot3->SetSize(FVector2D(200.f, 50.f));
		}
	}

	return Super::RebuildWidget();
}

void UGameForgeMenuWidget::ShowMainMenu()
{
	if (TitleText) TitleText->SetText(FText::FromString(TEXT("Main Menu")));
}

void UGameForgeMenuWidget::ShowPauseMenu()
{
	if (TitleText) TitleText->SetText(FText::FromString(TEXT("Paused")));
}

void UGameForgeMenuWidget::ShowEndScreen(bool bWon, const FString& Reason, float Score)
{
	if (TitleText)
	{
		TitleText->SetText(FText::FromString(bWon ? TEXT("You Win!") : TEXT("Game Over")));
	}
}

void UGameForgeMenuWidget::StartGameForScenario(UWorld* World)
{
	// Scenarios bypass menus
}

// ── Camera Shake ──────────────────────────────────────────────────────────────

UGameForgeCameraShake::UGameForgeCameraShake(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

// ── Feedback Subsystem ────────────────────────────────────────────────────────

void UGameForgeFeedbackSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);

	const UGameForgeRuntimeSettings* Settings = GetDefault<UGameForgeRuntimeSettings>();
	if (Settings && !Settings->GameDefinition.IsNull())
	{
		if (UGameForgeGameDefinition* DefAsset = Settings->GameDefinition.LoadSynchronous())
		{
			Def = DefAsset->GetParsed();
		}
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(&InWorld))
	{
		Bus->OnEvent.AddUObject(this, &UGameForgeFeedbackSubsystem::HandleEvent);
	}
}

void UGameForgeFeedbackSubsystem::HandleEvent(const FGameForgeEvent& Event)
{
	if (!Def.IsValid())
	{
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* FeedbackArr = nullptr;
	if (Def->TryGetArrayField(TEXT("feedback"), FeedbackArr) && FeedbackArr)
	{
		for (const TSharedPtr<FJsonValue>& Val : *FeedbackArr)
		{
			TSharedPtr<FJsonObject> FObj = Val->AsObject();
			if (!FObj.IsValid())
			{
				continue;
			}

			FString EventName;
			if (FObj->TryGetStringField(TEXT("e"), EventName) && FName(*EventName) == Event.Name)
			{
				UWorld* W = GetWorld();
				if (!W) continue;

				FVector Location = FVector::ZeroVector;
				if (APlayerController* PC = UGameplayStatics::GetPlayerController(W, 0))
				{
					if (PC->GetPawn())
					{
						Location = PC->GetPawn()->GetActorLocation();
					}
				}

				// VFX
				FString VfxPath;
				if (FObj->TryGetStringField(TEXT("vfx"), VfxPath) && !VfxPath.IsEmpty())
				{
					if (UNiagaraSystem* NS = LoadObject<UNiagaraSystem>(nullptr, *VfxPath))
					{
						UNiagaraFunctionLibrary::SpawnSystemAtLocation(W, NS, Location);
					}
				}

				// SFX
				FString SfxPath;
				if (FObj->TryGetStringField(TEXT("sfx"), SfxPath) && !SfxPath.IsEmpty())
				{
					if (USoundBase* SB = LoadObject<USoundBase>(nullptr, *SfxPath))
					{
						UGameplayStatics::PlaySoundAtLocation(W, SB, Location);
					}
				}
			}
		}
	}
}

// ── Save Subsystem ────────────────────────────────────────────────────────────

void UGameForgeSaveSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	SaveSlotName = TEXT("GF_Save_Slot");

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.AddUObject(this, &UGameForgeSaveSubsystem::HandleEvent);
	}

	LoadGame();
}

void UGameForgeSaveSubsystem::HandleEvent(const FGameForgeEvent& Event)
{
	if (Event.Name == GFEvent::GameWon || Event.Name == GFEvent::CheckpointReached)
	{
		SaveGame();
	}
}

void UGameForgeSaveSubsystem::SaveGame()
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::SaveWritten, TEXT("SaveSubsystem"), TEXT("{\"slot\":\"default\"}"));
	}
}

void UGameForgeSaveSubsystem::LoadGame()
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::SaveLoaded, TEXT("SaveSubsystem"), TEXT("{\"slot\":\"default\"}"));
	}
}
