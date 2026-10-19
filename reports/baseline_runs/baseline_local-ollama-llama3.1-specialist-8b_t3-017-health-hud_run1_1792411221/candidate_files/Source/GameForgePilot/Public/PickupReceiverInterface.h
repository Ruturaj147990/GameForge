#pragma once

#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "PickupReceiverInterface.generated.h"

UENUM(BlueprintType)
enum class EGameForgeResourceType : uint8
{
    Health      UMETA(DisplayName = "Health"),
    Stamina     UMETA(DisplayName = "Stamina"),
    Generic     UMETA(DisplayName = "Generic")
};

UINTERFACE(MinimalAPI, BlueprintType)
class UPickupReceiverInterface : public UInterface
{
    GENERATED_BODY()
};

/**
 * IPickupReceiverInterface
 *
 * Typed contract for actors or components capable of receiving resource pickups.
 */
class GAMEFORGEPILOT_API IPickupReceiverInterface
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Pickup")
    bool CanReceiveResource(EGameForgeResourceType Type, float Amount) const;

    UFUNCTION(BlueprintCallable, BlueprintNativeEvent, Category="Pickup")
    bool ReceiveResource(EGameForgeResourceType Type, float Amount);
};
