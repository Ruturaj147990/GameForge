// Copyright 2026 GameForge Systems. All Rights Reserved.

#include "GameForgePickup.h"

#include "Engine/GameInstance.h"
#include "GameForgeObjectives.h"
#include "Components/AudioComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
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
}

void AGameForgePickup::HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor,
	UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	APawn* Pawn = Cast<APawn>(OtherActor);
	if (bCollected || !Pawn || !Pawn->IsPlayerControlled())
	{
		return;
	}
	bCollected = true;
	CollectedBy = Pawn->GetName();
	Visual->SetVisibility(false);
	Trigger->SetCollisionEnabled(ECollisionEnabled::NoCollision);

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
	OnCollected.Broadcast(Pawn);
}
