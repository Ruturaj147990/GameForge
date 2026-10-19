#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "StaminaComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnStaminaChangedSignature, float, NewStamina, float, Delta);

/**
 * UStaminaComponent
 *
 * GameForge Pilot Resource Component managing character stamina.
 * Supports configurable maximum stamina, safe restoration, clamping, and change events.
 */
UCLASS(ClassGroup=(GameForge), meta=(BlueprintSpawnableComponent))
class GAMEFORGEPILOT_API UStaminaComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UStaminaComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Stamina", meta=(ClampMin="1.0"))
    float MaxStamina;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Stamina")
    float CurrentStamina;

    UPROPERTY(BlueprintAssignable, Category="Events")
    FOnStaminaChangedSignature OnStaminaChanged;

    UFUNCTION(BlueprintCallable, Category="Stamina")
    bool ApplyStaminaRestoration(float Amount);

    UFUNCTION(BlueprintCallable, Category="Stamina")
    bool ConsumeStamina(float Amount);

    UFUNCTION(BlueprintCallable, Category="Stamina")
    void SetCurrentStamina(float NewStamina);

    UFUNCTION(BlueprintCallable, Category="Stamina")
    float GetCurrentStamina() const { return CurrentStamina; }

    UFUNCTION(BlueprintCallable, Category="Stamina")
    float GetMaxStamina() const { return MaxStamina; }

    UFUNCTION(BlueprintCallable, Category="Stamina|Testing")
    void ResetComponentState();

private:
    bool bIsProcessingOperation;
};
