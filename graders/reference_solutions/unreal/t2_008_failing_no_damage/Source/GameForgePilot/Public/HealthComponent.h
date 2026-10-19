#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HealthComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnHealthChangedSignature, float, NewHealth, float, Delta);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnDamageAcceptedSignature, float, DamageAmount, float, RemainingHealth);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnDeathSignature);

/**
 * UHealthComponent
 * 
 * GameForge Pilot 2 Reference Health & Damage Component.
 * Supports configurable maximum health, damage clamping, temporary invulnerability,
 * non-reviving healing, exactly-once death notification, and deterministic test clock control.
 */
UCLASS(ClassGroup=(GameForge), meta=(BlueprintSpawnableComponent))
class GAMEFORGEPILOT_API UHealthComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UHealthComponent();

    // Configuration
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Health", meta=(ClampMin="1.0"))
    float MaxHealth;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Health")
    float CurrentHealth;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Health")
    bool bIsDead;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Health", meta=(ClampMin="0.0"))
    float InvulnerabilityDuration;

    // Events
    UPROPERTY(BlueprintAssignable, Category="Events")
    FOnHealthChangedSignature OnHealthChanged;

    UPROPERTY(BlueprintAssignable, Category="Events")
    FOnDamageAcceptedSignature OnDamageAccepted;

    UPROPERTY(BlueprintAssignable, Category="Events")
    FOnDeathSignature OnDeath;

    // Operations
    UFUNCTION(BlueprintCallable, Category="Health")
    bool ApplyDamage(float DamageAmount);

    UFUNCTION(BlueprintCallable, Category="Health")
    bool ApplyHealing(float HealAmount);

    UFUNCTION(BlueprintCallable, Category="Health")
    bool IsInvulnerable() const;

    UFUNCTION(BlueprintCallable, Category="Health")
    float GetCurrentHealth() const { return CurrentHealth; }

    UFUNCTION(BlueprintCallable, Category="Health")
    float GetMaxHealth() const { return MaxHealth; }

    UFUNCTION(BlueprintCallable, Category="Health")
    bool IsAlive() const { return !bIsDead; }

    // Deterministic simulation & clock interface
    UFUNCTION(BlueprintCallable, Category="Health|Testing")
    void SetSimulationTimeOverride(bool bEnable, float InSimulationTime = 0.0f);

    UFUNCTION(BlueprintCallable, Category="Health|Testing")
    void AdvanceSimulationTime(float DeltaSeconds);

    UFUNCTION(BlueprintCallable, Category="Health|Testing")
    float GetCurrentGameTime() const;

    UFUNCTION(BlueprintCallable, Category="Health|Testing")
    void ResetComponentState();

private:
    float LastAcceptedHitTime;
    bool bUseSimulationTime;
    float CurrentSimulationTime;
    bool bIsProcessingOperation;
};
