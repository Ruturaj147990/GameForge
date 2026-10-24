// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeEditorModule.h"
#include "GameForgeBridgeClient.h"
#include "HAL/IConsoleManager.h"
#include "ToolMenus.h"

#define LOCTEXT_NAMESPACE "FGameForgeEditorModule"

void FGameForgeEditorModule::StartupModule()
{
	BridgeClient = MakeShared<FGameForgeBridgeClient>();
	SyncContextCommand = IConsoleManager::Get().RegisterConsoleCommand(
		TEXT("GameForge.SyncContext"),
		TEXT("Send the current Unreal editor context to the authenticated GameForge loopback bridge."),
		FConsoleCommandDelegate::CreateRaw(this, &FGameForgeEditorModule::OnOpenGameForgeIDEClicked),
		ECVF_Default
	);

	UToolMenus::RegisterStartupCallback(
		FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FGameForgeEditorModule::RegisterMenus)
	);

	UE_LOG(LogTemp, Log, TEXT("GameForge Unreal Bridge initialized for Unreal Engine 5.7."));
}

void FGameForgeEditorModule::ShutdownModule()
{
	UToolMenus::UnRegisterStartupCallback(this);
	UToolMenus::UnregisterOwner(this);
	if (SyncContextCommand)
	{
		IConsoleManager::Get().UnregisterConsoleObject(SyncContextCommand, false);
		SyncContextCommand = nullptr;
	}
	BridgeClient.Reset();
}

void FGameForgeEditorModule::RegisterMenus()
{
	FToolMenuOwnerScoped OwnerScoped(this);

	UToolMenu* Menu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Tools");
	FToolMenuSection& Section = Menu->AddSection("GameForgeSection", LOCTEXT("GameForgeSection", "GameForge AI"));

	Section.AddMenuEntry(
		"OpenGameForgeIDE",
		LOCTEXT("OpenGameForgeIDE", "Sync with GameForge IDE"),
		LOCTEXT("OpenGameForgeIDETooltip", "Transmits active editor context and asset selection to GameForge IDE."),
		FSlateIcon(),
		FUIAction(FExecuteAction::CreateRaw(this, &FGameForgeEditorModule::OnOpenGameForgeIDEClicked))
	);
}

void FGameForgeEditorModule::OnOpenGameForgeIDEClicked()
{
	if (BridgeClient.IsValid())
	{
		BridgeClient->SendContextToIDE();
	}
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FGameForgeEditorModule, GameForgeEditor)
