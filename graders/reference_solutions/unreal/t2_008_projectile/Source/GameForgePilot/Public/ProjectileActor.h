#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ProjectileActor.generated.h"

class USphereComponent;
class UHealthComponent;

/**
 * AProjectileActor
 *
 * Engine-native combat projectile with collision detection, configurable speed/damage,
 * owner exclusion, blocking geometry collision, and exactly-once damage application.
 */
UCLASS(Blueprintable, ClassGroup=(GameForge))
class GAMEFORGEPILOT_API AProjectileActor : public AActor
{
    GENERATED_BODY()

public:
    AProjectileActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components")
    USphereComponent* SphereCollision;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Projectile")
    float ProjectileSpeed;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Projectile")
    float DamageAmount;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Projectile")
    float LifespanSeconds;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Projectile|State")
    bool bHasImpacted;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Projectile|State")
    AActor* ProjectileOwner;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Projectile|State")
    int32 ImpactEventCount;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Projectile|State")
    int32 DamageAppliedCount;

    UFUNCTION(BlueprintCallable, Category="Projectile")
    void Launch(FVector Direction, AActor* InOwner);

    UFUNCTION()
    void OnOverlapBegin(
        UPrimitiveComponent* OverlappedComp,
        AActor* OtherActor,
        UPrimitiveComponent* OtherComp,
        int32 OtherBodyIndex,
        bool bFromSweep,
        const FHitResult& SweepResult
    );

    UFUNCTION()
    void OnHit(
        UPrimitiveComponent* HitComp,
        AActor* OtherActor,
        UPrimitiveComponent* OtherComp,
        FVector NormalImpulse,
        const FHitResult& Hit
    );

    UFUNCTION(BlueprintCallable, Category="Projectile")
    bool ProcessHit(AActor* HitTarget);

    UFUNCTION(BlueprintCallable, Category="Projectile|Testing")
    void ResetProjectile();

protected:
    virtual void BeginPlay() override;
};
