#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "AbilitySystemInterface.h"
#include "AbilitySystemComponent.h"
#include "GameForgeAttributes.h"
#include "GameForgeEvents.h"
#include "GameForgePlayer.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UInputMappingContext;
class UGameForgeMenuWidget;

UENUM(BlueprintType)
enum class EGameForgeCameraMode : uint8
{
	ThirdPerson UMETA(DisplayName = "Third Person"),
	TopDown UMETA(DisplayName = "Top Down"),
	FirstPerson UMETA(DisplayName = "First Person"),
	SideScroller UMETA(DisplayName = "Side Scroller"),
	FixedBoard UMETA(DisplayName = "Fixed Board")
};

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

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	EGameForgeCameraMode CameraMode = EGameForgeCameraMode::ThirdPerson;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float MoveSpeed = 600.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float WalkSpeed = 600.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float SprintSpeed = 900.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float JumpVelocity = 650.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float JumpZVelocity = 650.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float AttackDamage = 35.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float AttackRange = 250.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float AttackCooldown = 0.4f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float MaxHealth = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float MaxStamina = 100.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float DashImpulse = 1200.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	int32 Lives = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	bool bProjectileAttack = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	bool bRangedAttack = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float ProjectileSpeed = 2500.f;

	/** Movement feel (previously engine defaults: AirControl 0.05 made platforming nearly impossible). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float AirControl = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float GravityScale = 1.0f;

	/** 2 = double jump. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	int32 MaxJumps = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	bool bDoubleJump = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float SprintMultiplier = 1.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	TArray<FString> Weapons;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	int32 ActiveWeaponIndex = 0;

	/** Falling below this Z counts as a death (fall-out-of-world used to destroy the pawn and soft-lock the game). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	float KillZ = -2000.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	FLinearColor BodyColor = FLinearColor(0.15f, 0.45f, 1.f, 1.f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Player")
	FString VisualStyle = TEXT("humanoid");

	/** Primitive body used when the project has no character content (the player used to be an invisible capsule). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> ProxyBody;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> ProxyHead;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UStaticMeshComponent> ProxyVisor;

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void ApplyCameraMode();

	/** Loads MeshPath/AnimClassPath (falling back to the Mannequins, then to the primitive proxy body). */
	void ApplyVisuals(const FString& MeshPath, const FString& AnimClassPath);
	void ApplyMovementSettings();
	void SetSprinting(bool bNewSprinting);
	/** Restores health, re-arms death detection and re-enables movement after a respawn. */
	void ResetForRespawn();
	bool IsDead() const { return bDead; }

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void PerformAttack();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void PerformMeleeAttack();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void PerformRangedAttack();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void PerformInteract();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void PerformDash();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Player")
	void SwitchWeapon(int32 NewWeaponIndex = -1);

	virtual void FellOutOfWorld(const UDamageType& dmgType) override;
	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;
	virtual void PossessedBy(AController* NewController) override;

private:
	/** Direction projectiles travel: camera aim in first/third person, cursor in top-down, facing in side view. */
	FVector ComputeAimDirection(FVector& OutMuzzle) const;

	float LastAttackTime = -100.f;
	float LastDashTime = -100.f;
	bool bSprinting = false;
	bool bDead = false;
	bool bVisualsApplied = false;
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

	UPROPERTY(Transient)
	TObjectPtr<UGameForgeMenuWidget> PauseMenuWidget;

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
	void HandleRollDice(const FInputActionValue& Value);
	void HandleAttack(const FInputActionValue& Value);
	void HandleInteract(const FInputActionValue& Value);
	void HandleSprintStarted(const FInputActionValue& Value);
	void HandleSprintCompleted(const FInputActionValue& Value);
	void HandleDash(const FInputActionValue& Value);
	void HandleSwitchWeapon(const FInputActionValue& Value);
	void HandlePause(const FInputActionValue& Value);
	void HandleRestart(const FInputActionValue& Value);
	/** True while the game is over or paused: gameplay input (move, attack) is ignored, menu keys still work. */
	bool IsGameplayBlocked() const;
	bool IsCursorOverSelectable() const;

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
	bool IsGameOver() const { return bEnded; }

	/** Seconds between death and respawn when the game is not lost. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float RespawnDelay = 1.5f;

private:
	void HandleEvent(const FGameForgeEvent& Event);
	void RespawnPlayerNow();

	bool bEnded = false;
	FTransform RespawnTransform;
	FTransform InitialTransform;
	bool bHasInitialTransform = false;
	FTimerHandle RespawnTimer;
};
