// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgeBridgeClient.h"
#include "Editor.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformMisc.h"
#include "HttpModule.h"
#include "Misc/EngineVersion.h"
#include "JsonObjectConverter.h"
#include "Dom/JsonObject.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Selection.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"

FGameForgeBridgeClient::FGameForgeBridgeClient(const FString& InIDEServerUrl)
{
	if (InIDEServerUrl.StartsWith(TEXT("http://127.0.0.1:")) || InIDEServerUrl.StartsWith(TEXT("http://localhost:")) || InIDEServerUrl.StartsWith(TEXT("http://[::1]:")))
	{
		IDEServerUrl = InIDEServerUrl;
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("GameForge Bridge URL must be a local loopback address. Defaulting to http://127.0.0.1:47815"));
		IDEServerUrl = TEXT("http://127.0.0.1:47815");
	}
}

FGameForgeBridgeClient::~FGameForgeBridgeClient()
{
}

FGameForgeEditorContext FGameForgeBridgeClient::GatherCurrentContext() const
{
	FGameForgeEditorContext Context;
	Context.ProjectName = FApp::GetProjectName();
	Context.EngineVersion = FEngineVersion::Current().ToString(EVersionComponent::Patch);
	Context.SelectedActorName = TEXT("");
	Context.ActiveAssetPath = TEXT("");

	if (GEditor)
	{
		if (USelection* Selection = GEditor->GetSelectedActors())
		{
			TArray<AActor*> SelectedActors;
			Selection->GetSelectedObjects<AActor>(SelectedActors);
			for (int32 Index = 0; Index < SelectedActors.Num() && Index < 32; ++Index)
			{
				if (IsValid(SelectedActors[Index]))
				{
					Context.SelectedActorName += SelectedActors[Index]->GetPathName();
					Context.SelectedActorName += TEXT("\n");
				}
			}
			Context.SelectedActorName.TrimEndInline();
		}

		if (UAssetEditorSubsystem* AssetEditors = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>())
		{
			for (UObject* Asset : AssetEditors->GetAllEditedAssets())
			{
				if (IsValid(Asset) && Context.OpenAssetPaths.Num() < 32)
				{
					Context.OpenAssetPaths.Add(Asset->GetPathName());
				}
			}
			// Unreal exposes the open asset set here, but does not identify a focused
			// editor for all editor types. Only call it active when the choice is unique.
			if (Context.OpenAssetPaths.Num() == 1)
			{
				Context.ActiveAssetPath = Context.OpenAssetPaths[0];
			}
		}
	}
	return Context;
}

void FGameForgeBridgeClient::SendContextToIDE()
{
	const FString BridgeToken = FPlatformMisc::GetEnvironmentVariable(TEXT("GAMEFORGE_BRIDGE_TOKEN"));
	if (BridgeToken.IsEmpty())
	{
		UE_LOG(LogTemp, Error, TEXT("GameForge Unreal Bridge is disabled: GAMEFORGE_BRIDGE_TOKEN is not set in this editor process."));
		return;
	}

	FGameForgeEditorContext Context = GatherCurrentContext();

	TSharedPtr<FJsonObject> JsonObj = MakeShared<FJsonObject>();
	JsonObj->SetStringField(TEXT("project_name"), Context.ProjectName);
	JsonObj->SetStringField(TEXT("engine_version"), Context.EngineVersion);
	JsonObj->SetStringField(TEXT("selected_actor"), Context.SelectedActorName);
	JsonObj->SetStringField(TEXT("active_asset"), Context.ActiveAssetPath);
	TArray<TSharedPtr<FJsonValue>> OpenAssetsJson;
	for (const FString& AssetPath : Context.OpenAssetPaths)
	{
		OpenAssetsJson.Add(MakeShared<FJsonValueString>(AssetPath));
	}
	JsonObj->SetArrayField(TEXT("open_assets"), OpenAssetsJson);

	FString OutputString;
	TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
	FJsonSerializer::Serialize(JsonObj.ToSharedRef(), Writer);

	TSharedRef<IHttpRequest> Request = FHttpModule::Get().CreateRequest();
	Request->SetTimeout(5.0f);
	Request->OnProcessRequestComplete().BindRaw(this, &FGameForgeBridgeClient::OnContextResponseReceived);
	Request->SetURL(IDEServerUrl + TEXT("/api/unreal/context"));
	Request->SetVerb(TEXT("POST"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
	Request->SetHeader(TEXT("Authorization"), TEXT("Bearer ") + BridgeToken);
	Request->SetContentAsString(OutputString);
	Request->ProcessRequest();
}

void FGameForgeBridgeClient::PingIDE(TFunction<void(bool bConnected)> OnComplete)
{
	TSharedRef<IHttpRequest> Request = FHttpModule::Get().CreateRequest();
	Request->SetTimeout(3.0f);
	Request->SetURL(IDEServerUrl + TEXT("/api/health"));
	Request->SetVerb(TEXT("GET"));
	Request->OnProcessRequestComplete().BindLambda([OnComplete](FHttpRequestPtr Req, FHttpResponsePtr Resp, bool bSuccess)
	{
		OnComplete(bSuccess && Resp.IsValid() && Resp->GetResponseCode() == 200);
	});
	Request->ProcessRequest();
}

void FGameForgeBridgeClient::OnContextResponseReceived(FHttpRequestPtr Request, FHttpResponsePtr Response, bool bWasSuccessful)
{
	if (bWasSuccessful && Response.IsValid() && Response->GetResponseCode() == 200)
	{
		UE_LOG(LogTemp, Log, TEXT("GameForge Unreal Bridge successfully synced context with IDE: %s"), *Response->GetContentAsString());
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("GameForge Unreal Bridge could not reach IDE at %s"), *IDEServerUrl);
	}
}
