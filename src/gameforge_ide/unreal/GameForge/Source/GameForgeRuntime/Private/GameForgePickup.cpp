// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgePickup.h"

#include "GameForgeEventNames.h"
#include "GameForgeEvents.h"
#include "GameForgeGameState.h"
#include "GameForgeObjectives.h"
#include "GameForgePlayer.h"
#include "GameForgeVisuals.h"
#include "Components/AudioComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

AGameForgePickup::AGameForgePickup()
{
	Trigger = CreateDefaultSubobject<USphereComponent>(TEXT("Trigger"));
	Trigger->InitSphereRadius(120.0f);
	Trigger->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Trigger->SetGenerateOverlapEvents(true);
	RootComponent = Trigger;

	Visual = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Visual"));
	Visual->SetupAttachment(Trigger);
	Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Visual->SetRelativeScale3D(FVector(0.5f));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (Sphere.Succeeded())
	{
		Visual->SetStaticMesh(Sphere.Object);
	}

	Trigger->OnComponentBeginOverlap.AddDynamic(this, &AGameForgePickup::HandleOverlap);
	PrimaryActorTick.bCanEverTick = true;
}

void AGameForgePickup::SyncEffectFromName()
{
	if (EffectName.IsEmpty())
	{
		return;
	}
	if (EffectName.Equals(TEXT("Heal"), ESearchCase::IgnoreCase) || EffectName.Equals(TEXT("heal"), ESearchCase::IgnoreCase))
	{
		Effect = EGameForgePickupEffect::Heal;
	}
	else if (EffectName.Equals(TEXT("GrantItem"), ESearchCase::IgnoreCase) || EffectName.Equals(TEXT("grant_item"), ESearchCase::IgnoreCase))
	{
		Effect = EGameForgePickupEffect::GrantItem;
	}
	else if (EffectName.Equals(TEXT("SpeedBoost"), ESearchCase::IgnoreCase) || EffectName.Equals(TEXT("speed_boost"), ESearchCase::IgnoreCase))
	{
		Effect = EGameForgePickupEffect::SpeedBoost;
	}
	else if (EffectName.Equals(TEXT("CustomEvent"), ESearchCase::IgnoreCase) || EffectName.Equals(TEXT("custom_event"), ESearchCase::IgnoreCase))
	{
		Effect = EGameForgePickupEffect::CustomEvent;
	}
	else if (EffectName.Equals(TEXT("AddScore"), ESearchCase::IgnoreCase) || EffectName.Equals(TEXT("add_score"), ESearchCase::IgnoreCase))
	{
		Effect = EGameForgePickupEffect::AddScore;
	}
}

void AGameForgePickup::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);
	SyncEffectFromName();
	BaseVisualLocation = Visual->GetRelativeLocation();
	Age = FMath::FRandRange(0.f, 6.f);   // de-synchronise the bobbing of neighbouring pickups
	GameForgeVisuals::Tint(Visual, PickupColor);
}

void AGameForgePickup::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bCollected || !Visual)
	{
		return;
	}
	Age += DeltaSeconds;
	Visual->SetRelativeLocation(BaseVisualLocation + FVector(0.f, 0.f, FMath::Sin(Age * 2.5f) * BobHeight));
	Visual->AddLocalRotation(FRotator(0.f, SpinSpeed * DeltaSeconds, 0.f));
}

void AGameForgePickup::Respawn()
{
	bCollected = false;
	SetActorHiddenInGame(false);
	Visual->SetVisibility(true);
	Trigger->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
}

void AGameForgePickup::HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	APawn* Pawn = Cast<APawn>(OtherActor);
	if (bCollected || !Pawn || !Pawn->IsPlayerControlled())
	{
		return;
	}
	SyncEffectFromName();

	bCollected = true;
	CollectedBy = Pawn->GetName();
	Visual->SetVisibility(false);
	Trigger->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	if (bRespawns)
	{
		GetWorldTimerManager().SetTimer(RespawnTimer, this, &AGameForgePickup::Respawn, FMath::Max(1.f, RespawnSeconds), false);
	}
	else
	{
		// Hidden actors drop out of the derived entity.<id>.remaining stat.
		SetActorHiddenInGame(true);
	}

	AGameForgeGameState* GS = GetWorld() ? GetWorld()->GetGameState<AGameForgeGameState>() : nullptr;
	AGameForgeCharacter* GFChar = Cast<AGameForgeCharacter>(Pawn);

	switch (Effect)
	{
	case EGameForgePickupEffect::AddScore:
		if (GS)
		{
			GS->AddStat(FName(TEXT("game.score")), static_cast<float>(Value));
			GS->IncrementCounter(FName(TEXT("game.counter.collected")), 1);
		}
		break;
	case EGameForgePickupEffect::Heal:
		if (GFChar && GFChar->AttributeSet)
		{
			const float NewHP = FMath::Clamp(GFChar->AttributeSet->GetHealth() + static_cast<float>(Value), 0.f, GFChar->AttributeSet->GetMaxHealth());
			GFChar->AttributeSet->SetHealth(NewHP);
			if (GS)
			{
				GS->SetStat(FName(TEXT("player.health")), NewHP);
			}
		}
		else if (GS)
		{
			GS->AddStat(FName(TEXT("player.health")), static_cast<float>(Value));
		}
		if (GS)
		{
			GS->IncrementCounter(FName(TEXT("game.counter.collected")), 1);
		}
		break;
	case EGameForgePickupEffect::GrantItem:
		if (GS)
		{
			if (!ItemId.IsNone())
			{
				GS->AddStat(FName(*(FString(TEXT("item.")) + ItemId.ToString())), static_cast<float>(FMath::Max(1, Value)));
			}
			GS->IncrementCounter(FName(TEXT("game.counter.collected")), 1);
		}
		break;
	case EGameForgePickupEffect::SpeedBoost:
		if (GFChar)
		{
			GFChar->MoveSpeed += FMath::Max(50.f, static_cast<float>(Value));
			GFChar->ApplyMovementSettings();
		}
		if (GS)
		{
			GS->IncrementCounter(FName(TEXT("game.counter.collected")), 1);
		}
		break;
	case EGameForgePickupEffect::CustomEvent:
		if (!CustomEvent.IsNone())
		{
			UGameForgeEventLibrary::EmitGameForgeEvent(this, CustomEvent, GetName(),
				FString::Printf(TEXT("{\"value\":%d}"), Value), EntityId);
		}
		if (GS)
		{
			GS->IncrementCounter(FName(TEXT("game.counter.collected")), 1);
		}
		break;
	}

	if (CollectVFX)
	{
		SpawnedVFX = UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), CollectVFX, GetActorLocation(),
			FRotator::ZeroRotator, FVector(1.0f), /*bAutoDestroy=*/false, /*bAutoActivate=*/true, ENCPoolMethod::None,
			/*bPreCullCheck=*/false);
		if (SpawnedVFX)
		{
			SpawnedVFX->ComponentTags.Add(FName(*(TEXT("GF_VFX:") + VFXLabel)));
		}
	}
	if (CollectSound)
	{
		// Not auto-destroyed, so tools can read its playing state after the event.
		SpawnedSound = UGameplayStatics::SpawnSoundAtLocation(this, CollectSound, GetActorLocation(), FRotator::ZeroRotator,
			1.0f, 1.0f, 0.0f, CollectAttenuation, nullptr, /*bAutoDestroy=*/false);
	}
	if (!ObjectiveId.IsNone())
	{
		if (UGameInstance* GI = GetGameInstance())
		{
			if (UGameForgeObjectiveSubsystem* Objectives = GI->GetSubsystem<UGameForgeObjectiveSubsystem>())
			{
				Objectives->AddProgress(ObjectiveId, 1);
			}
		}
	}
	UE_LOG(LogTemp, Display, TEXT("GF_EVENT pickup actor=%s collected_by=%s vfx=%s spawned=%d sound=%s sound_playing=%d"),
		*GetName(), *CollectedBy, CollectVFX ? *CollectVFX->GetName() : TEXT("None"), SpawnedVFX ? 1 : 0,
		CollectSound ? *CollectSound->GetName() : TEXT("None"), SpawnedSound && SpawnedSound->IsPlaying() ? 1 : 0);
	const FString DataJson = FString::Printf(TEXT("{\"objective\":\"%s\",\"by\":\"%s\",\"value\":%d,\"item_id\":\"%s\"}"),
		*ObjectiveId.ToString().ReplaceCharWithEscapedChar(),
		*CollectedBy.ReplaceCharWithEscapedChar(),
		Value,
		*ItemId.ToString().ReplaceCharWithEscapedChar());
	UGameForgeEventLibrary::EmitGameForgeEvent(this, GFEvent::PickupCollected, GetName(), DataJson, EntityId);
	OnCollected.Broadcast(Pawn);
}
