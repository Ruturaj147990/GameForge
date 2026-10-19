#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "PickupReceiverInterface.h"
#include "GameForgePlayerCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UHealthComponent;
class UStaminaComponent;

/**
 * AGameForgePlayerCharacter
 *
 * Fully composed third-person player character combining kinematics, camera rig,
 * health component, stamina component, and pickup receiver interface.
 */
UCLASS(ClassGroup=(GameForge), Blueprintable)
class GAMEFORGEPILOT_API AGameForgePlayerCharacter : public ACharacter, public IPickupReceiverInterface
{
    GENERATED_BODY()

public:
    AGameForgePlayerCharacter();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Camera")
    USpringArmComponent* CameraBoom;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Camera")
    UCameraComponent* FollowCamera;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Gameplay")
    UHealthComponent* HealthComponent;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Gameplay")
    UStaminaComponent* StaminaComponent;

    // IPickupReceiverInterface implementation
    virtual bool CanReceiveResource_Implementation(EGameForgeResourceType Type, float Amount) const override;
    virtual bool ReceiveResource_Implementation(EGameForgeResourceType Type, float Amount) override;
};
