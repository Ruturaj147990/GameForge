#include "HealthStaminaHUDWidget.h"
#include "HealthComponent.h"
#include "StaminaComponent.h"
#include "GameFramework/Pawn.h"
#include "Math/UnrealMathUtility.h"

UHealthStaminaHUDWidget::UHealthStaminaHUDWidget(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
    , DisplayedHealth(100.0f)
    , MaxHealth(100.0f)
    , HealthPercent(1.0f)
    , DisplayedStamina(100.0f)
    , MaxStamina(100.0f)
    , StaminaPercent(1.0f)
    , bIsDead(false)
    , bIsBound(false)
    , EventUpdateCount(0)
{
}

void UHealthStaminaHUDWidget::BindToPlayer(APawn* InPlayer)
{
    // Prevent duplicate subscriptions if already bound
    if (bIsBound)
    {
        UnbindFromPlayer();
    }

    if (!IsValid(InPlayer))
    {
        return;
    }

    BoundPlayer = InPlayer;

    // Discover HealthComponent
    UHealthComponent* HC = InPlayer->FindComponentByClass<UHealthComponent>();
    if (IsValid(HC))
    {
        BoundHealthComponent = HC;
        HC->OnHealthChanged.AddDynamic(this, &UHealthStaminaHUDWidget::HandleHealthChanged);
        HC->OnDamageAccepted.AddDynamic(this, &UHealthStaminaHUDWidget::HandleDamageAccepted);
        HC->OnDeath.AddDynamic(this, &UHealthStaminaHUDWidget::HandleDeath);

        MaxHealth = HC->GetMaxHealth();
        DisplayedHealth = HC->GetCurrentHealth();
        bIsDead = !HC->IsAlive();
    }

    // Discover StaminaComponent
    UStaminaComponent* SC = InPlayer->FindComponentByClass<UStaminaComponent>();
    if (IsValid(SC))
    {
        BoundStaminaComponent = SC;
        SC->OnStaminaChanged.AddDynamic(this, &UHealthStaminaHUDWidget::HandleStaminaChanged);

        MaxStamina = SC->GetMaxStamina();
        DisplayedStamina = SC->GetCurrentStamina();
    }

    bIsBound = true;
    RefreshDisplay();
}

void UHealthStaminaHUDWidget::UnbindFromPlayer()
{
    if (BoundHealthComponent.IsValid())
    {
        BoundHealthComponent->OnHealthChanged.RemoveDynamic(this, &UHealthStaminaHUDWidget::HandleHealthChanged);
        BoundHealthComponent->OnDamageAccepted.RemoveDynamic(this, &UHealthStaminaHUDWidget::HandleDamageAccepted);
        BoundHealthComponent->OnDeath.RemoveDynamic(this, &UHealthStaminaHUDWidget::HandleDeath);
        BoundHealthComponent.Reset();
    }

    if (BoundStaminaComponent.IsValid())
    {
        BoundStaminaComponent->OnStaminaChanged.RemoveDynamic(this, &UHealthStaminaHUDWidget::HandleStaminaChanged);
        BoundStaminaComponent.Reset();
    }

    BoundPlayer.Reset();
    bIsBound = false;
}

void UHealthStaminaHUDWidget::RefreshDisplay()
{
    // Safe clamping prevents division by zero or invalid percent intervals
    const float SafeMaxHealth = FMath::Max(1.0f, MaxHealth);
    HealthPercent = FMath::Clamp(DisplayedHealth / SafeMaxHealth, 0.0f, 1.0f);

    const float SafeMaxStamina = FMath::Max(1.0f, MaxStamina);
    StaminaPercent = FMath::Clamp(DisplayedStamina / SafeMaxStamina, 0.0f, 1.0f);
}

void UHealthStaminaHUDWidget::HandleHealthChanged(float NewHealth, float Delta)
{
    DisplayedHealth = FMath::Clamp(NewHealth, 0.0f, MaxHealth);
    bIsDead = (DisplayedHealth <= 0.0f);
    EventUpdateCount++;
    RefreshDisplay();
}

void UHealthStaminaHUDWidget::HandleDamageAccepted(float DamageAmount, float RemainingHealth)
{
    DisplayedHealth = FMath::Clamp(RemainingHealth, 0.0f, MaxHealth);
    bIsDead = (DisplayedHealth <= 0.0f);
    EventUpdateCount++;
    RefreshDisplay();
}

void UHealthStaminaHUDWidget::HandleDeath()
{
    bIsDead = true;
    DisplayedHealth = 0.0f;
    EventUpdateCount++;
    RefreshDisplay();
}

void UHealthStaminaHUDWidget::HandleStaminaChanged(float NewStamina, float Delta)
{
    DisplayedStamina = FMath::Clamp(NewStamina, 0.0f, MaxStamina);
    EventUpdateCount++;
    RefreshDisplay();
}

void UHealthStaminaHUDWidget::NativeDestruct()
{
    UnbindFromPlayer();
    Super::NativeDestruct();
}
