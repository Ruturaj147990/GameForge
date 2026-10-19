#include "GameForgePlayerCharacter.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HealthComponent.h"
#include "StaminaComponent.h"

AGameForgePlayerCharacter::AGameForgePlayerCharacter()
{
    PrimaryActorTick.bCanEverTick = false;

    // Capsule dimensions matching Pilot 1 baseline
    GetCapsuleComponent()->InitCapsuleSize(35.0f, 90.0f);

    // DEFECT_MOVEMENT_REGRESSION: Degraded walk speed (400 instead of 600)
    /* DEFECT: movement regression */
    GetCharacterMovement()->MaxWalkSpeed = 400.0f;
    GetCharacterMovement()->MaxAcceleration = 4000.0f;
    GetCharacterMovement()->BrakingDecelerationWalking = 5500.0f;
    GetCharacterMovement()->JumpZVelocity = 485.0f;
    GetCharacterMovement()->GravityScale = 1.0f;

    // Camera Boom (4.0 m = 400 cm)
    CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
    CameraBoom->SetupAttachment(RootComponent);
    CameraBoom->TargetArmLength = 400.0f;
    CameraBoom->bDoCollisionTest = true;

    // Follow Camera
    FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
    FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);

    // Health Component
    HealthComponent = CreateDefaultSubobject<UHealthComponent>(TEXT("HealthComponent"));

    // Stamina Component
    StaminaComponent = CreateDefaultSubobject<UStaminaComponent>(TEXT("StaminaComponent"));
}

bool AGameForgePlayerCharacter::CanReceiveResource_Implementation(EGameForgeResourceType Type, float Amount) const
{
    if (Type == EGameForgeResourceType::Health)
    {
        if (HealthComponent)
        {
            return HealthComponent->IsAlive() && (HealthComponent->GetCurrentHealth() < HealthComponent->GetMaxHealth());
        }
        return false;
    }
    else if (Type == EGameForgeResourceType::Stamina)
    {
        if (StaminaComponent)
        {
            return StaminaComponent->GetCurrentStamina() < StaminaComponent->GetMaxStamina();
        }
        return false;
    }

    return false;
}

bool AGameForgePlayerCharacter::ReceiveResource_Implementation(EGameForgeResourceType Type, float Amount)
{
    if (Type == EGameForgeResourceType::Health)
    {
        if (HealthComponent)
        {
            return HealthComponent->ApplyHealing(Amount);
        }
        return false;
    }
    else if (Type == EGameForgeResourceType::Stamina)
    {
        if (StaminaComponent)
        {
            return StaminaComponent->ApplyStaminaRestoration(Amount);
        }
        return false;
    }

    return false;
}
