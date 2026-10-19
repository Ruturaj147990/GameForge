#include "HealthComponent.h"
#include "Engine/World.h"
#include "Math/UnrealMathUtility.h"

UHealthComponent::UHealthComponent()
    : MaxHealth(100.0f)
    , CurrentHealth(100.0f)
    , bIsDead(false)
    , InvulnerabilityDuration(0.75f)
    , LastAcceptedHitTime(-1000.0f)
    , bUseSimulationTime(false)
    , CurrentSimulationTime(0.0f)
    , bIsProcessingOperation(false)
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UHealthComponent::ResetComponentState()
{
    CurrentHealth = MaxHealth;
    bIsDead = false;
    LastAcceptedHitTime = -1000.0f;
    CurrentSimulationTime = 0.0f;
    bIsProcessingOperation = false;
}

void UHealthComponent::SetSimulationTimeOverride(bool bEnable, float InSimulationTime)
{
    bUseSimulationTime = bEnable;
    CurrentSimulationTime = InSimulationTime;
}

void UHealthComponent::AdvanceSimulationTime(float DeltaSeconds)
{
    if (FMath::IsFinite(DeltaSeconds) && DeltaSeconds >= 0.0f)
    {
        CurrentSimulationTime += DeltaSeconds;
    }
}

float UHealthComponent::GetCurrentGameTime() const
{
    if (bUseSimulationTime)
    {
        return CurrentSimulationTime;
    }

    if (const UWorld* World = GetWorld())
    {
        return World->GetTimeSeconds();
    }

    return 0.0f;
}

bool UHealthComponent::IsInvulnerable() const
{
    if (bIsDead)
    {
        return false;
    }

    const float CurrentTime = GetCurrentGameTime();
    return (CurrentTime - LastAcceptedHitTime) < InvulnerabilityDuration;
}

bool UHealthComponent::ApplyDamage(float DamageAmount)
{
    // Reentrancy guard
    if (bIsProcessingOperation)
    {
        return false;
    }

    // Reject non-finite, negative, or zero damage
    if (!FMath::IsFinite(DamageAmount) || DamageAmount <= 0.0f)
    {
        return false;
    }

    // DEFECT: Allows damage after death
    // if (bIsDead) return false;

    // Damage during active invulnerability is rejected without modifying state or timer
    const float CurrentTime = GetCurrentGameTime();
    if ((CurrentTime - LastAcceptedHitTime) < InvulnerabilityDuration)
    {
        return false;
    }

    bIsProcessingOperation = true;

    // Accept hit and begin invulnerability window
    LastAcceptedHitTime = CurrentTime;

    const float OldHealth = CurrentHealth;
    const float NewHealth = FMath::Clamp(OldHealth - DamageAmount, 0.0f, MaxHealth);
    const float Delta = NewHealth - OldHealth;

    CurrentHealth = NewHealth;

    // Emit health change event first
    OnHealthChanged.Broadcast(CurrentHealth, Delta);

    // Emit accepted damage event
    OnDamageAccepted.Broadcast(DamageAmount, CurrentHealth);

    // DEFECT: Emits OnDeath repeatedly on every zero-health hit
    if (CurrentHealth <= 0.0f)
    {
        bIsDead = true;
        OnDeath.Broadcast();
    }

    bIsProcessingOperation = false;
    return true;
}

bool UHealthComponent::ApplyHealing(float HealAmount)
{
    // Reentrancy guard
    if (bIsProcessingOperation)
    {
        return false;
    }

    // Reject non-finite, negative, or zero healing
    if (!FMath::IsFinite(HealAmount) || HealAmount <= 0.0f)
    {
        return false;
    }

    // Dead characters cannot be revived via healing in this pilot
    if (bIsDead)
    {
        return false;
    }

    // Healing at maximum health is rejected and emits no health-changed event
    if (CurrentHealth >= MaxHealth)
    {
        return false;
    }

    bIsProcessingOperation = true;

    const float OldHealth = CurrentHealth;
    const float NewHealth = FMath::Clamp(OldHealth + HealAmount, 0.0f, MaxHealth);
    const float Delta = NewHealth - OldHealth;

    if (Delta > 0.0f)
    {
        CurrentHealth = NewHealth;
        OnHealthChanged.Broadcast(CurrentHealth, Delta);
        bIsProcessingOperation = false;
        return true;
    }

    bIsProcessingOperation = false;
    return false;
}
