#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "PickupReceiverInterface.h"
#include "PickupComponent.generated.h"

UENUM(BlueprintType)
enum class EGameForgePickupType : uint8
{
    Health      UMETA(DisplayName = "Health"),
    Stamina     UMETA(DisplayName = "Stamina")
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnPickupCollectedSignature, AActor*, Collector, EGameForgePickupType, PickupType, float, Amount);

/**
 * UPickupComponent
 *
 * Implements the atomic pickup collection protocol.
 * Guarantees exactly-once collection, resource receiver validation, full-resource non-consumption,
 * and reentrancy safety.
 */
UCLASS(ClassGroup=(GameForge), meta=(BlueprintSpawnableComponent))
class GAMEFORGEPILOT_API UPickupComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UPickupComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Pickup")
    EGameForgePickupType PickupType;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Pickup", meta=(ClampMin="1.0"))
    float RestorationAmount;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Pickup")
    bool bIsConsumed;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Pickup")
    bool bPickupAvailable;

    UPROPERTY(BlueprintAssignable, Category="Events")
    FOnPickupCollectedSignature OnPickupCollected;

    UFUNCTION(BlueprintCallable, Category="Pickup")
    bool AttemptCollect(AActor* Collector);

    UFUNCTION(BlueprintCallable, Category="Pickup")
    bool IsAvailable() const { return bPickupAvailable && !bIsConsumed; }

    UFUNCTION(BlueprintCallable, Category="Pickup|Testing")
    void ResetPickupState();

private:
    bool bIsProcessingCollection;
};
