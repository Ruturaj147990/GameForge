#include "PickupActor.h"

APickupActor::APickupActor()
{
    PrimaryActorTick.bCanEverTick = false;

    SphereCollision = CreateDefaultSubobject<USphereComponent>(TEXT("SphereCollision"));
    RootComponent = SphereCollision;
    SphereCollision->InitSphereRadius(50.0f);
    SphereCollision->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
    SphereCollision->SetGenerateOverlapEvents(true);

    PickupComponent = CreateDefaultSubobject<UPickupComponent>(TEXT("PickupComponent"));
}

void APickupActor::OnOverlapBegin(
    UPrimitiveComponent* OverlappedComponent,
    AActor* OtherActor,
    UPrimitiveComponent* OtherComp,
    int32 OtherBodyIndex,
    bool bFromSweep,
    const FHitResult& SweepResult)
{
    if (PickupComponent && PickupComponent->AttemptCollect(OtherActor))
    {
        // Successful collection: shutdown collision and hide
        if (SphereCollision)
        {
            SphereCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        }
        SetActorHiddenInGame(true);
    }
}

void APickupActor::ResetPickupActor()
{
    if (PickupComponent)
    {
        PickupComponent->ResetPickupState();
    }
    if (SphereCollision)
    {
        SphereCollision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    }
    SetActorHiddenInGame(false);
}
