#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PickupComponent.h"
#include "Components/SphereComponent.h"
#include "PickupActor.generated.h"

/**
 * APickupActor
 *
 * Engine-native pickup actor with collision sphere and pickup component.
 * Automatically handles collision disabling and visibility toggling upon successful collection.
 */
UCLASS(ClassGroup=(GameForge), Blueprintable)
class GAMEFORGEPILOT_API APickupActor : public AActor
{
    GENERATED_BODY()

public:
    APickupActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components")
    USphereComponent* SphereCollision;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components")
    UPickupComponent* PickupComponent;

    UFUNCTION()
    void OnOverlapBegin(
        UPrimitiveComponent* OverlappedComponent,
        AActor* OtherActor,
        UPrimitiveComponent* OtherComp,
        int32 OtherBodyIndex,
        bool bFromSweep,
        const FHitResult& SweepResult
    );

    UFUNCTION(BlueprintCallable, Category="Pickup|Testing")
    void ResetPickupActor();
};
