#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "HealthStaminaHUDWidget.generated.h"

class APawn;
class UHealthComponent;
class UStaminaComponent;

/**
 * UHealthStaminaHUDWidget
 *
 * Engine-native UMG HUD widget bound to player health and stamina components.
 * Listens to component delegate events and updates normalized display values.
 * Features duplicate subscription guards and safe unbinding on pawn changes or destruction.
 */
UCLASS(Blueprintable, ClassGroup=(GameForge))
class GAMEFORGEPILOT_API UHealthStaminaHUDWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UHealthStaminaHUDWidget(const FObjectInitializer& ObjectInitializer);

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Health")
    float DisplayedHealth;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Health")
    float MaxHealth;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Health")
    float HealthPercent;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Stamina")
    float DisplayedStamina;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Stamina")
    float MaxStamina;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Stamina")
    float StaminaPercent;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|State")
    bool bIsDead;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|State")
    bool bIsBound;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="HUD|Diagnostics")
    int32 EventUpdateCount;

    UFUNCTION(BlueprintCallable, Category="HUD")
    void BindToPlayer(APawn* InPlayer);

    UFUNCTION(BlueprintCallable, Category="HUD")
    void UnbindFromPlayer();

    UFUNCTION(BlueprintCallable, Category="HUD")
    void RefreshDisplay();

    // Event handlers for HealthComponent
    UFUNCTION()
    void HandleHealthChanged(float NewHealth, float Delta);

    UFUNCTION()
    void HandleDamageAccepted(float DamageAmount, float RemainingHealth);

    UFUNCTION()
    void HandleDeath();

    // Event handlers for StaminaComponent
    UFUNCTION()
    void HandleStaminaChanged(float NewStamina, float Delta);

    virtual void NativeDestruct() override;

private:
    TWeakObjectPtr<APawn> BoundPlayer;
    TWeakObjectPtr<UHealthComponent> BoundHealthComponent;
    TWeakObjectPtr<UStaminaComponent> BoundStaminaComponent;
};
