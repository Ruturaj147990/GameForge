#include "GameForgeKitUI.h"
#include "GameFramework/SaveGame.h"
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
#include "Sound/SoundBase.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Fonts/SlateFontInfo.h"

// ── HUD Widget ────────────────────────────────────────────────────────────────

namespace
{
	TSharedPtr<FJsonObject> LoadHudDefinition()
	{
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
		TSharedPtr<FJsonObject> Parsed;
		if (DefAsset)
		{
			Parsed = DefAsset->GetParsed();
		}
		return Parsed;
	}
}

UTextBlock* UGameForgeHUDWidget::MakeText(const FName& Name, int32 Size, const FLinearColor& Color)
{
	UTextBlock* T = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), Name);
	if (T)
	{
		FSlateFontInfo Font = T->GetFont();
		Font.Size = Size;
		Font.OutlineSettings.OutlineSize = FMath::Max(1, Size / 12);
		Font.OutlineSettings.OutlineColor = FLinearColor(0.f, 0.f, 0.f, 0.85f);
		T->SetFont(Font);
		T->SetColorAndOpacity(FSlateColor(Color));
		T->SetJustification(ETextJustify::Center);
		T->SetText(FText::GetEmpty());
	}
	return T;
}

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

	auto Place = [Root](UWidget* W, const FAnchors& Anchors, const FVector2D& Align, const FVector2D& Pos = FVector2D::ZeroVector)
	{
		if (UCanvasPanelSlot* S = Root->AddChildToCanvas(W))
		{
			S->SetAnchors(Anchors);
			S->SetAlignment(Align);
			S->SetPosition(Pos);
			S->SetAutoSize(true);
		}
	};

	RowBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("RowBox"));
	Place(RowBox, FAnchors(0.f, 0.f, 0.f, 0.f), FVector2D(0.f, 0.f), FVector2D(24.f, 24.f));

	MessageText = MakeText(TEXT("MessageText"), 28, FLinearColor(1.f, 0.95f, 0.7f));
	Place(MessageText, FAnchors(0.5f, 0.22f, 0.5f, 0.22f), FVector2D(0.5f, 0.5f));

	TitleCardText = MakeText(TEXT("TitleCard"), 54, FLinearColor::White);
	Place(TitleCardText, FAnchors(0.5f, 0.36f, 0.5f, 0.36f), FVector2D(0.5f, 0.5f));

	ObjectiveText = MakeText(TEXT("ObjectiveCard"), 24, FLinearColor(0.85f, 0.92f, 1.f));
	Place(ObjectiveText, FAnchors(0.5f, 0.46f, 0.5f, 0.46f), FVector2D(0.5f, 0.5f));

	HintText = MakeText(TEXT("HintText"), 16, FLinearColor(1.f, 1.f, 1.f, 0.8f));
	Place(HintText, FAnchors(0.5f, 1.f, 0.5f, 1.f), FVector2D(0.5f, 1.f), FVector2D(0.f, -20.f));

	EndTitleText = MakeText(TEXT("EndTitle"), 72, FLinearColor::White);
	Place(EndTitleText, FAnchors(0.5f, 0.4f, 0.5f, 0.4f), FVector2D(0.5f, 0.5f));

	EndSubtitleText = MakeText(TEXT("EndSubtitle"), 26, FLinearColor(0.9f, 0.9f, 0.9f));
	Place(EndSubtitleText, FAnchors(0.5f, 0.52f, 0.5f, 0.52f), FVector2D(0.5f, 0.5f));

	// Crosshair only where aiming uses the screen centre (first / third person shooters).
	CrosshairText = MakeText(TEXT("Crosshair"), 22, FLinearColor(1.f, 1.f, 1.f, 0.85f));
	Place(CrosshairText, FAnchors(0.5f, 0.5f, 0.5f, 0.5f), FVector2D(0.5f, 0.5f));

	Def = LoadHudDefinition();
	if (!Def.IsValid())
	{
		return;
	}

	FString Camera;
	const TSharedPtr<FJsonObject>* PlayerObj = nullptr;
	if (Def->TryGetObjectField(TEXT("player"), PlayerObj) && PlayerObj)
	{
		(*PlayerObj)->TryGetStringField(TEXT("camera"), Camera);
	}
	FString AttackMode;
	if (PlayerObj)
	{
		(*PlayerObj)->TryGetStringField(TEXT("attack_mode"), AttackMode);
	}
	const bool bAims = Camera == TEXT("first_person") || (Camera == TEXT("third_person") && AttackMode == TEXT("projectile"));
	CrosshairText->SetText(bAims ? FText::FromString(TEXT("+")) : FText::GetEmpty());

	FString Title, Objective, Controls;
	Def->TryGetStringField(TEXT("title"), Title);
	Def->TryGetStringField(TEXT("objective"), Objective);
	Def->TryGetStringField(TEXT("controls"), Controls);
	TitleCardText->SetText(FText::FromString(Title));
	ObjectiveText->SetText(FText::FromString(Objective));
	HintText->SetText(FText::FromString(Controls.IsEmpty() ? Objective : FString::Printf(TEXT("%s    |    %s"), *Objective, *Controls)));

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

			// "of" is the counter target / bar maximum. Without it counters showed "Score: 10 / 100".
			double OfVal = 0.0;
			Row.MaxValue = HObj->TryGetNumberField(TEXT("of"), OfVal) ? static_cast<float>(OfVal) : 0.f;

			if (Row.Kind == TEXT("bar"))
			{
				if (Row.MaxValue <= 0.f)
				{
					Row.MaxValue = 100.f;
				}
				UTextBlock* Lbl = MakeText(NAME_None, 16, FLinearColor::White);
				Lbl->SetJustification(ETextJustify::Left);
				Lbl->SetText(FText::FromString(Row.Label));
				RowBox->AddChildToVerticalBox(Lbl);

				Row.BarWidget = WidgetTree->ConstructWidget<UProgressBar>(UProgressBar::StaticClass());
				Row.BarWidget->SetPercent(1.0f);
				Row.BarWidget->SetFillColorAndOpacity(Row.StatName == FName(TEXT("player.health"))
					? FLinearColor(0.2f, 0.85f, 0.3f) : FLinearColor(0.3f, 0.6f, 1.f));
				if (UVerticalBoxSlot* BarSlot = RowBox->AddChildToVerticalBox(Row.BarWidget))
				{
					BarSlot->SetPadding(FMargin(0.f, 2.f, 0.f, 8.f));
				}
			}
			else
			{
				Row.TextWidget = MakeText(NAME_None, 20, FLinearColor::White);
				Row.TextWidget->SetJustification(ETextJustify::Left);
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
		}
		RefreshRows();

		TWeakObjectPtr<UGameForgeHUDWidget> WeakThis(this);
		W->GetTimerManager().SetTimer(TimerRefreshHandle, [WeakThis]()
		{
			if (UGameForgeHUDWidget* Self = WeakThis.Get())
			{
				Self->RefreshRows();
			}
		}, 0.25f, true);

		// Title card for the first few seconds so the player knows what game this is and what to do.
		W->GetTimerManager().SetTimer(TitleCardHandle, [WeakThis]()
		{
			if (UGameForgeHUDWidget* Self = WeakThis.Get())
			{
				if (Self->TitleCardText) { Self->TitleCardText->SetText(FText::GetEmpty()); }
				if (Self->ObjectiveText) { Self->ObjectiveText->SetText(FText::GetEmpty()); }
			}
		}, 4.5f, false);

		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W))
		{
			BusHandle = Bus->OnEvent.AddUObject(this, &UGameForgeHUDWidget::HandleBusEvent);
		}
	}
}

void UGameForgeHUDWidget::NativeDestruct()
{
	if (UWorld* W = GetWorld())
	{
		W->GetTimerManager().ClearTimer(TimerRefreshHandle);
		W->GetTimerManager().ClearTimer(MessageFadeHandle);
		W->GetTimerManager().ClearTimer(TitleCardHandle);
		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(W))
		{
			Bus->OnEvent.Remove(BusHandle);
		}
	}
	Super::NativeDestruct();
}

void UGameForgeHUDWidget::RefreshRows()
{
	UWorld* W = GetWorld();
	AGameForgeGameState* GS = W ? W->GetGameState<AGameForgeGameState>() : nullptr;
	if (!GS)
	{
		return;
	}
	for (FHudRow& Row : Rows)
	{
		if (Row.StatName.IsNone())
		{
			continue;
		}
		const float Value = GS->GetStat(Row.StatName);
		if (Row.Kind == TEXT("timer") && Row.TextWidget)
		{
			// Count down when the timer has a limit, otherwise count up.
			const float Shown = Row.MaxValue > 0.f ? FMath::Max(0.f, Row.MaxValue - Value) : Value;
			const int32 Mins = static_cast<int32>(Shown) / 60;
			const int32 RemSecs = static_cast<int32>(Shown) % 60;
			Row.TextWidget->SetText(FText::FromString(FString::Printf(TEXT("%s: %02d:%02d"), *Row.Label, Mins, RemSecs)));
		}
		else
		{
			OnStatChanged(Row.StatName, Value);
		}
	}
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
				Row.TextWidget->SetText(FText::FromString(Row.MaxValue > 0.f
					? FString::Printf(TEXT("%s: %.0f / %.0f"), *Row.Label, NewValue, Row.MaxValue)
					: FString::Printf(TEXT("%s: %.0f"), *Row.Label, NewValue)));
			}
			else if (Row.Kind != TEXT("timer") && Row.TextWidget)
			{
				Row.TextWidget->SetText(FText::FromString(FString::Printf(TEXT("%s: %.0f"), *Row.Label, NewValue)));
			}
		}
	}
}

void UGameForgeHUDWidget::HandleBusEvent(const FGameForgeEvent& Event)
{
	static const FName UiMessage(TEXT("ui.message"));
	if (Event.Name == UiMessage)
	{
		TSharedPtr<FJsonObject> Payload;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Event.DataJson);
		if (FJsonSerializer::Deserialize(Reader, Payload) && Payload.IsValid())
		{
			FString Text;
			double Seconds = 3.0;
			Payload->TryGetStringField(TEXT("text"), Text);
			Payload->TryGetNumberField(TEXT("seconds"), Seconds);
			if (!Text.IsEmpty() && !bEndShown)
			{
				ShowMessage(Text, static_cast<float>(Seconds));
			}
		}
		return;
	}
	if (Event.Name == GFEvent::GameWon || Event.Name == GFEvent::GameLost)
	{
		ShowEndScreen(Event.Name == GFEvent::GameWon);
		return;
	}
	if (Event.Name == GFEvent::GamePaused && !bEndShown)
	{
		EndTitleText->SetText(FText::FromString(TEXT("Paused")));
		EndSubtitleText->SetText(FText::FromString(TEXT("P to resume  -  R to restart")));
		return;
	}
	if (Event.Name == GFEvent::GameResumed && !bEndShown)
	{
		EndTitleText->SetText(FText::GetEmpty());
		EndSubtitleText->SetText(FText::GetEmpty());
		return;
	}

	// Feedback rows may carry a HUD message ("msg") for any event.
	if (Def.IsValid() && !bEndShown)
	{
		const TArray<TSharedPtr<FJsonValue>>* FeedbackArr = nullptr;
		if (Def->TryGetArrayField(TEXT("feedback"), FeedbackArr) && FeedbackArr)
		{
			for (const TSharedPtr<FJsonValue>& Val : *FeedbackArr)
			{
				const TSharedPtr<FJsonObject> FObj = Val->AsObject();
				FString EventName, Msg;
				if (FObj.IsValid() && FObj->TryGetStringField(TEXT("e"), EventName) && FName(*EventName) == Event.Name &&
					FObj->TryGetStringField(TEXT("msg"), Msg) && !Msg.IsEmpty())
				{
					ShowMessage(Msg, 2.f);
					break;
				}
			}
		}
	}
}

void UGameForgeHUDWidget::ShowEndScreen(bool bWon)
{
	if (bEndShown)
	{
		return;
	}
	bEndShown = true;
	if (MessageText) { MessageText->SetText(FText::GetEmpty()); }
	if (TitleCardText) { TitleCardText->SetText(FText::GetEmpty()); }
	if (ObjectiveText) { ObjectiveText->SetText(FText::GetEmpty()); }
	if (CrosshairText) { CrosshairText->SetText(FText::GetEmpty()); }

	float Score = 0.f;
	if (UWorld* W = GetWorld())
	{
		if (AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>())
		{
			Score = GS->GetStat(FName(TEXT("game.score")));
		}
	}
	EndTitleText->SetColorAndOpacity(FSlateColor(bWon ? FLinearColor(1.f, 0.85f, 0.2f) : FLinearColor(1.f, 0.3f, 0.25f)));
	EndTitleText->SetText(FText::FromString(bWon ? TEXT("VICTORY!") : TEXT("GAME OVER")));
	EndSubtitleText->SetText(FText::FromString(FString::Printf(TEXT("Score %.0f   -   press R to play again"), Score)));
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
		TWeakObjectPtr<UGameForgeHUDWidget> WeakThis(this);
		W->GetTimerManager().SetTimer(MessageFadeHandle, [WeakThis]()
		{
			if (UGameForgeHUDWidget* Self = WeakThis.Get())
			{
				if (Self->MessageText)
				{
					Self->MessageText->SetText(FText::GetEmpty());
				}
			}
		}, FMath::Max(0.5f, DurationSeconds), false);
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

	// Same lookup order as the rules subsystem (settings asset, then /Game/GameForge/GD_Main); feedback used to
	// require the settings asset, so most generated games had no VFX/SFX at all.
	Def = LoadHudDefinition();

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
	bool bOk = false;
	if (USaveGame* SaveObj = UGameplayStatics::CreateSaveGameObject(USaveGame::StaticClass()))
	{
		bOk = UGameplayStatics::SaveGameToSlot(SaveObj, SaveSlotName, 0);
	}
	if (bOk)
	{
		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
		{
			Bus->Emit(GFEvent::SaveWritten, TEXT("SaveSubsystem"), FString::Printf(TEXT("{\"slot\":\"%s\"}"), *SaveSlotName));
		}
	}
}

void UGameForgeSaveSubsystem::LoadGame()
{
	bool bOk = false;
	if (UGameplayStatics::DoesSaveGameExist(SaveSlotName, 0))
	{
		USaveGame* Loaded = UGameplayStatics::LoadGameFromSlot(SaveSlotName, 0);
		bOk = (Loaded != nullptr);
	}
	if (bOk)
	{
		if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
		{
			Bus->Emit(GFEvent::SaveLoaded, TEXT("SaveSubsystem"), FString::Printf(TEXT("{\"slot\":\"%s\"}"), *SaveSlotName));
		}
	}
}
