#include "GameForgeAttributes.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameState.h"
#include "GameplayEffectExtension.h"
#include "GameFramework/Character.h"
#include "Engine/World.h"
#include "AbilitySystemInterface.h"
#include "GameForgeKitActors.h"

UE_DEFINE_GAMEPLAY_TAG(TAG_GF_Data_Damage, "GameForge.Data.Damage");

UGameForgeAttributeSet::UGameForgeAttributeSet()
	: Health(100.f)
	, MaxHealth(100.f)
	, Stamina(100.f)
	, MaxStamina(100.f)
	, Damage(0.f)
{
}

void UGameForgeAttributeSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
	Super::PostGameplayEffectExecute(Data);

	if (Data.EvaluatedData.Attribute == GetDamageAttribute())
	{
		const float LocalDamageDone = GetDamage();
		SetDamage(0.f);

		if (LocalDamageDone > 0.f)
		{
			const float OldHealth = GetHealth();
			const float NewHealth = FMath::Clamp(OldHealth - LocalDamageDone, 0.f, GetMaxHealth());
			SetHealth(NewHealth);

			AActor* TargetActor = Data.Target.GetAvatarActor();
			UWorld* World = TargetActor ? TargetActor->GetWorld() : nullptr;
			UGameForgeEventBus* Bus = World ? UGameForgeEventBus::Get(World) : nullptr;
			AGameForgeGameState* GS = World ? World->GetGameState<AGameForgeGameState>() : nullptr;

			bool bIsPlayer = false;
			if (APawn* P = Cast<APawn>(TargetActor))
			{
				bIsPlayer = P->IsPlayerControlled();
			}
			AGameForgeEnemy* Enemy = Cast<AGameForgeEnemy>(TargetActor);
			const FName EntityId = UGameForgeEventLibrary::ResolveEntityId(TargetActor, Enemy ? Enemy->EntityId : NAME_None);

			if (bIsPlayer)
			{
				if (GS)
				{
					GS->SetStat(FName(TEXT("player.health")), NewHealth);
				}
				if (Bus && TargetActor)
				{
					Bus->Emit(GFEvent::PlayerDamaged, TargetActor->GetName(),
						FString::Printf(TEXT("{\"damage\":%f,\"health\":%f}"), LocalDamageDone, NewHealth));
				}
			}
			else
			{
				if (Bus && TargetActor)
				{
					Bus->Emit(GFEvent::EnemyAttacked, TargetActor->GetName(),
						FString::Printf(TEXT("{\"damage\":%f,\"health\":%f}"), LocalDamageDone, NewHealth), EntityId);
				}
				if (Enemy && NewHealth > 0.f)
				{
					Enemy->OnDamaged(Data.EffectSpec.GetContext().GetInstigator());
				}
			}

			if (NewHealth <= 0.f && !bDiedEmitted)
			{
				bDiedEmitted = true;
				if (bIsPlayer)
				{
					if (Bus && TargetActor)
					{
						Bus->Emit(GFEvent::PlayerDied, TargetActor->GetName(), TEXT("{}"));
					}
				}
				else
				{
					if (Bus && TargetActor)
					{
						Bus->Emit(GFEvent::EnemyKilled, TargetActor->GetName(), TEXT("{}"), EntityId);
					}
					if (GS)
					{
						GS->AddStat(FName(TEXT("game.counter.enemies_killed")), 1.f);
					}
					// Dead enemies used to stand in place forever: they still blocked the player, still counted
					// towards entity.<id>.remaining (so "defeat all" could never be won) and kept their AI tick.
					if (Enemy)
					{
						Enemy->HandleDeath();
					}
				}
			}
		}
	}
}

bool UGameForgeDamageLibrary::ApplyDamage(AActor* Target, AActor* Instigator, float Amount)
{
	if (!Target || Amount <= 0.f)
	{
		return false;
	}

	UAbilitySystemComponent* ASC = nullptr;
	if (IAbilitySystemInterface* ASI = Cast<IAbilitySystemInterface>(Target))
	{
		ASC = ASI->GetAbilitySystemComponent();
	}
	if (!ASC)
	{
		ASC = Target->FindComponentByClass<UAbilitySystemComponent>();
	}

	if (!ASC)
	{
		return false;
	}

	// Apply instant damage using GameplayEffect
	UGameplayEffect* GE = NewObject<UGameplayEffect>(GetTransientPackage(), FName(TEXT("GE_GameForgeDamage")));
	GE->DurationPolicy = EGameplayEffectDurationType::Instant;

	int32 ModIdx = GE->Modifiers.Num();
	GE->Modifiers.SetNum(ModIdx + 1);
	FGameplayModifierInfo& Info = GE->Modifiers[ModIdx];
	Info.Attribute = UGameForgeAttributeSet::GetDamageAttribute();
	Info.ModifierOp = EGameplayModOp::Additive;
	Info.ModifierMagnitude = FGameplayEffectModifierMagnitude(FScalableFloat(Amount));

	FGameplayEffectContextHandle Context = ASC->MakeEffectContext();
	Context.AddInstigator(Instigator, Instigator);
	ASC->ApplyGameplayEffectToSelf(GE, 1.0f, Context);

	return true;
}
