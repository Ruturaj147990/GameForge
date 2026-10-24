// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class IConsoleObject;

class FGameForgeEditorModule : public IModuleInterface
{
public:
	/** IModuleInterface implementation */
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	void RegisterMenus();
	void OnOpenGameForgeIDEClicked();

	TSharedPtr<class FGameForgeBridgeClient> BridgeClient;
	IConsoleObject* SyncContextCommand = nullptr;
};
