#include "PickupComponent.h"
#include "HealthComponent.h"
#include "StaminaComponent.h"
#include "PickupReceiverInterface.h"
#include "Math/UnrealMathUtility.h"

UPickupComponent::UPickupComponent()
    : PickupType(EGameForgePickupType::Health)
    , RestorationAmount(25.0f)
    , bIsConsumed(false)
    , bPickupAvailable(true)
    , bIsProcessingCollection(false)
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UPickupComponent::ResetPickupState()
{
    bIsConsumed = false;
    bPickupAvailable = true;
    bIsProcessingCollection = false;
}

bool UPickupComponent::AttemptCollect(AActor* Collector)
{
    // DEFECT_DUPLICATE_CONSUMPTION: Do not check bIsConsumed or bPickupAvailable, allowing repeated collection
    /* DEFECT: duplicate */
    if (!IsValid(Collector))
    {
        return false;
    }

    if (!FMath::IsFinite(RestorationAmount) || RestorationAmount <= 0.0f)
    {
        return false;
    }

    bIsProcessingCollection = true;

    bool bEffectApplied = false;
    const EGameForgeResourceType TargetResource = (PickupType == EGameForgePickupType::Health) 
        ? EGameForgeResourceType::Health 
        : EGameForgeResourceType::Stamina;

    // Check if Collector implements IPickupReceiverInterface
    if (Collector->GetClass()->ImplementsInterface(UPickupReceiverInterface::StaticClass()))
    {
        const bool bCanReceive = IPickupReceiverInterface::Execute_CanReceiveResource(Collector, TargetResource, RestorationAmount);
        if (bCanReceive)
        {
            bEffectApplied = IPickupReceiverInterface::Execute_ReceiveResource(Collector, TargetResource, RestorationAmount);
        }
    }
    else
    {
        // Direct component discovery fallback
        if (PickupType == EGameForgePickupType::Health)
        {
            if (UHealthComponent* HC = Collector->FindComponentByClass<UHealthComponent>())
            {
                if (HC->IsAlive() && HC->GetCurrentHealth() < HC->GetMaxHealth())
                {
                    bEffectApplied = HC->ApplyHealing(RestorationAmount);
                }
            }
        }
        else if (PickupType == EGameForgePickupType::Stamina)
        {
            if (UStaminaComponent* SC = Collector->FindComponentByClass<UStaminaComponent>())
            {
                if (SC->GetCurrentStamina() < SC->GetMaxStamina())
                {
                    bEffectApplied = SC->ApplyStaminaRestoration(RestorationAmount);
                }
            }
        }
    }

    if (bEffectApplied)
    {
        bIsConsumed = true;
        bPickupAvailable = false;
        bIsProcessingCollection = false;

        // Emit exactly once after state committed
        OnPickupCollected.Broadcast(Collector, PickupType, RestorationAmount);
        return true;
    }

    bIsProcessingCollection = false;
    return false;
}
