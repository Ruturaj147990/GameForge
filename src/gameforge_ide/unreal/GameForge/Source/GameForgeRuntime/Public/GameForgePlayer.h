#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "AbilitySystemInterface.h"
#include "AbilitySystemComponent.h"
#include "GameForgeAttributes.h"
#include "GameForgePlayer.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UInputMappingContext;

UENUM(BlueprintType)
enum class EGameForgeCameraMode : uint8 { ThirdPerson, TopDown, FirstPerson, SideScroller };

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeCharacter : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	AGameForgeCharacter();

	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override { return AbilitySystemComponent; }

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UGameForgeAttributeSet> AttributeSet;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> WeaponMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	EGameForgeCameraMode CameraMode = EGameForgeCameraMode::ThirdPerson;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float MoveSpeed = 600.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float JumpVelocity = 650.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AttackDamage = 35.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AttackRange = 250.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float AttackCooldown = 0.4f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float MaxHealth = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 Lives = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bProjectileAttack = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float ProjectileSpeed = 2500.f;

	UFUNCTION(BlueprintCallable, Category = "GameForge")
	void ApplyCameraMode();

	void PerformAttack();
	void PerformMeleeAttack();
	void PerformRangedAttack();
	void PerformInteract();

	virtual void FellOutOfWorld(const UDamageType& dmgType) override;

protected:
	virtual void BeginPlay() override;
	virtual void PossessedBy(AController* NewController) override;

private:
	float LastAttackTime = -100.f;
};

/** Builds its Enhanced Input actions at runtime (no input assets needed; works in cooked builds). */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgePlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "GameForge|Input")
	UInputAction* FindAction(FName ActionId) const;

	/** Same path the IA_Select handler uses after reading the mouse: hit-test at a screen position and select. */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Input")
	AActor* SelectAtScreenPosition(FVector2D ScreenPosition);

	UPROPERTY(Transient, BlueprintReadOnly, Category = "GameForge|Input")
	TObjectPtr<UInputMappingContext> MappingContext;

	bool IsContextAdded() const { return bContextAdded; }

protected:
	virtual void BeginPlay() override;
	virtual void SetupInputComponent() override;
	void BuildDefaultInput();
	void HandleMove(const FInputActionValue& Value);
	void HandleLook(const FInputActionValue& Value);
	void HandleJumpStarted(const FInputActionValue& Value);
	void HandleJumpCompleted(const FInputActionValue& Value);
	void HandleSelect(const FInputActionValue& Value);
	void HandleAttack(const FInputActionValue& Value);
	void HandleInteract(const FInputActionValue& Value);

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<UInputAction>> Actions;

	bool bContextAdded = false;
};

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGameModeBase : public AGameModeBase
{
	GENERATED_BODY()

public:
	AGameForgeGameModeBase();
	virtual void StartPlay() override;
	virtual void RestartPlayer(AController* NewPlayer) override;
	void ConfigurePlayer(AController* Controller);
};

/**
 * Full data-driven GameMode applying gfdef settings and handling game end / restart (WI-5.5).
 */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGameMode : public AGameForgeGameModeBase
{
	GENERATED_BODY()

public:
	AGameForgeGameMode();
	virtual void StartPlay() override;

	void EndGame(bool bWon, const FString& Reason);
	void RestartCurrentGame();
	void SetRespawnTransform(const FTransform& NewTransform) { RespawnTransform = NewTransform; }

private:
	void HandleEvent(const FGameForgeEvent& Event);

	bool bEnded = false;
	FTransform RespawnTransform;
};
