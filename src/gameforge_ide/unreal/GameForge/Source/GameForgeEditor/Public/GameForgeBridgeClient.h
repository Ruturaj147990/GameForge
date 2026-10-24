// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"

struct FGameForgeEditorContext
{
	FString ProjectName;
	FString EngineVersion;
	FString SelectedActorName;
	FString ActiveAssetPath;
	TArray<FString> OpenAssetPaths;
};

class FGameForgeBridgeClient : public TSharedFromThis<FGameForgeBridgeClient>
{
public:
	FGameForgeBridgeClient(const FString& InIDEServerUrl = TEXT("http://127.0.0.1:8000"));
	~FGameForgeBridgeClient();

	/** Extracts active editor selection, open assets, and engine context */
	FGameForgeEditorContext GatherCurrentContext() const;

	/** Transmits current editor context to the GameForge IDE backend */
	void SendContextToIDE();

	/** Pings the IDE to verify connection */
	void PingIDE(TFunction<void(bool bConnected)> OnComplete);

private:
	void OnContextResponseReceived(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful);

	FString IDEServerUrl;
};
