#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"
#include "GameplayTagContainer.h"
#include "NativeGameplayTags.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GameForgeAttributes.generated.h"

GAMEFORGERUNTIME_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(TAG_GF_Data_Damage);

#define GAMEFORGE_ATTRIBUTE_ACCESSORS(ClassName, PropertyName) \
	GAMEPLAYATTRIBUTE_PROPERTY_GETTER(ClassName, PropertyName) \
	GAMEPLAYATTRIBUTE_VALUE_GETTER(PropertyName) \
	GAMEPLAYATTRIBUTE_VALUE_SETTER(PropertyName) \
	GAMEPLAYATTRIBUTE_VALUE_INITTER(PropertyName)

/**
 * Standard GAS attributes for player and enemies (WI-5.6).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeAttributeSet : public UAttributeSet
{
	GENERATED_BODY()

public:
	UGameForgeAttributeSet();

	virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;

	UPROPERTY(BlueprintReadOnly, Category = "GameForge|Attributes")
	FGameplayAttributeData Health;
	GAMEFORGE_ATTRIBUTE_ACCESSORS(UGameForgeAttributeSet, Health)

	UPROPERTY(BlueprintReadOnly, Category = "GameForge|Attributes")
	FGameplayAttributeData MaxHealth;
	GAMEFORGE_ATTRIBUTE_ACCESSORS(UGameForgeAttributeSet, MaxHealth)

	UPROPERTY(BlueprintReadOnly, Category = "GameForge|Attributes")
	FGameplayAttributeData Stamina;
	GAMEFORGE_ATTRIBUTE_ACCESSORS(UGameForgeAttributeSet, Stamina)

	UPROPERTY(BlueprintReadOnly, Category = "GameForge|Attributes")
	FGameplayAttributeData MaxStamina;
	GAMEFORGE_ATTRIBUTE_ACCESSORS(UGameForgeAttributeSet, MaxStamina)

	UPROPERTY(BlueprintReadOnly, Category = "GameForge|Attributes")
	FGameplayAttributeData Damage;
	GAMEFORGE_ATTRIBUTE_ACCESSORS(UGameForgeAttributeSet, Damage)

	/** Re-arms the one-shot death event after a respawn (previously a respawned player could never die again,
	 *  so lose conditions and checkpoints silently stopped working after the first death). */
	void ResetDeathState() { bDiedEmitted = false; }
	bool HasDied() const { return bDiedEmitted; }

private:
	bool bDiedEmitted = false;
};

/**
 * Helper library to apply instant damage via GAS (WI-5.6).
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeDamageLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "GameForge|Damage")
	static bool ApplyDamage(AActor* Target, AActor* Instigator, float Amount);
};
