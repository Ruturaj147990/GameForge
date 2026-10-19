#include "StaminaComponent.h"
#include "Math/UnrealMathUtility.h"

UStaminaComponent::UStaminaComponent()
    : MaxStamina(100.0f)
    , CurrentStamina(100.0f)
    , bIsProcessingOperation(false)
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UStaminaComponent::ResetComponentState()
{
    CurrentStamina = MaxStamina;
    bIsProcessingOperation = false;
}

void UStaminaComponent::SetCurrentStamina(float NewStamina)
{
    if (FMath::IsFinite(NewStamina))
    {
        CurrentStamina = FMath::Clamp(NewStamina, 0.0f, MaxStamina);
    }
}

bool UStaminaComponent::ApplyStaminaRestoration(float Amount)
{
    if (bIsProcessingOperation)
    {
        return false;
    }

    if (!FMath::IsFinite(Amount) || Amount <= 0.0f)
    {
        return false;
    }

    if (CurrentStamina >= MaxStamina)
    {
        return false;
    }

    bIsProcessingOperation = true;

    const float OldStamina = CurrentStamina;
    const float NewStamina = FMath::Clamp(OldStamina + Amount, 0.0f, MaxStamina);
    const float Delta = NewStamina - OldStamina;

    if (Delta > 0.0f)
    {
        CurrentStamina = NewStamina;
        OnStaminaChanged.Broadcast(CurrentStamina, Delta);
        bIsProcessingOperation = false;
        return true;
    }

    bIsProcessingOperation = false;
    return false;
}

bool UStaminaComponent::ConsumeStamina(float Amount)
{
    if (bIsProcessingOperation)
    {
        return false;
    }

    if (!FMath::IsFinite(Amount) || Amount <= 0.0f)
    {
        return false;
    }

    if (CurrentStamina <= 0.0f)
    {
        return false;
    }

    bIsProcessingOperation = true;

    const float OldStamina = CurrentStamina;
    const float NewStamina = FMath::Clamp(OldStamina - Amount, 0.0f, MaxStamina);
    const float Delta = NewStamina - OldStamina;

    CurrentStamina = NewStamina;
    OnStaminaChanged.Broadcast(CurrentStamina, Delta);

    bIsProcessingOperation = false;
    return true;
}
