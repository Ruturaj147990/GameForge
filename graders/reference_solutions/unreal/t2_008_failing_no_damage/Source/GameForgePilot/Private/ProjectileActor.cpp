#include "ProjectileActor.h"
#include "HealthComponent.h"
#include "Components/SphereComponent.h"
#include "Math/UnrealMathUtility.h"

AProjectileActor::AProjectileActor()
    : ProjectileSpeed(2000.0f)
    , DamageAmount(20.0f)
    , LifespanSeconds(5.0f)
    , bHasImpacted(false)
    , ProjectileOwner(nullptr)
    , ImpactEventCount(0)
    , DamageAppliedCount(0)
{
    PrimaryActorTick.bCanEverTick = false;

    SphereCollision = CreateDefaultSubobject<USphereComponent>(TEXT("SphereCollision"));
    RootComponent = SphereCollision;
    SphereCollision->InitSphereRadius(15.0f);
    SphereCollision->SetCollisionProfileName(TEXT("BlockAllDynamic"));
    SphereCollision->SetGenerateOverlapEvents(true);
    SphereCollision->SetNotifyRigidBodyCollision(true);
}

void AProjectileActor::BeginPlay()
{
    Super::BeginPlay();

    if (SphereCollision)
    {
        SphereCollision->OnComponentBeginOverlap.AddDynamic(this, &AProjectileActor::OnOverlapBegin);
        SphereCollision->OnComponentHit.AddDynamic(this, &AProjectileActor::OnHit);
    }

    if (LifespanSeconds > 0.0f)
    {
        SetLifeSpan(LifespanSeconds);
    }
}

void AProjectileActor::Launch(FVector Direction, AActor* InOwner)
{
    ProjectileOwner = InOwner;
    SetInstigator(Cast<APawn>(InOwner));
    bHasImpacted = false;
    ImpactEventCount = 0;
    DamageAppliedCount = 0;
}

void AProjectileActor::OnOverlapBegin(
    UPrimitiveComponent* OverlappedComp,
    AActor* OtherActor,
    UPrimitiveComponent* OtherComp,
    int32 OtherBodyIndex,
    bool bFromSweep,
    const FHitResult& SweepResult)
{
    ProcessHit(OtherActor);
}

void AProjectileActor::OnHit(
    UPrimitiveComponent* HitComp,
    AActor* OtherActor,
    UPrimitiveComponent* OtherComp,
    FVector NormalImpulse,
    const FHitResult& Hit)
{
    ProcessHit(OtherActor);
}

bool AProjectileActor::ProcessHit(AActor* HitTarget)
{
    // DEFECT_NO_DAMAGE_APPLIED: Impacts occur but no damage is applied
    /* DEFECT: no damage */
    // Atomic check: exactly-once impact handling
    if (bHasImpacted)
    {
        return false;
    }

    // Owner exclusion: projectiles cannot damage their own launcher/owner
    if (IsValid(HitTarget) && (HitTarget == ProjectileOwner || HitTarget == GetInstigator()))
    {
        return false;
    }

    if (!FMath::IsFinite(DamageAmount) || DamageAmount <= 0.0f)
    {
        return false;
    }

    bHasImpacted = true;
    ImpactEventCount++;

    bool bDamageAccepted = false;
    if (IsValid(HitTarget))
    {
        if (UHealthComponent* HC = HitTarget->FindComponentByClass<UHealthComponent>())
        {
            bDamageAccepted = HC->ApplyDamage(DamageAmount);
            if (bDamageAccepted)
            {
                DamageAppliedCount++;
            }
        }
    }

    // Disable collision and hide actor immediately upon impact
    if (SphereCollision)
    {
        SphereCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    }
    SetActorHiddenInGame(true);
    SetLifeSpan(0.01f);

    return bDamageAccepted;
}

void AProjectileActor::ResetProjectile()
{
    bHasImpacted = false;
    ImpactEventCount = 0;
    DamageAppliedCount = 0;
    if (SphereCollision)
    {
        SphereCollision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    }
    SetActorHiddenInGame(false);
}
