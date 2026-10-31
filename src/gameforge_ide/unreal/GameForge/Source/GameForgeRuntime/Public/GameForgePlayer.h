#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "GameForgePlayer.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UInputMappingContext;

UENUM(BlueprintType)
enum class EGameForgeCameraMode : uint8 { ThirdPerson, TopDown, FirstPerson, SideScroller };

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeCharacter : public ACharacter
{
	GENERATED_BODY()
public:
	AGameForgeCharacter();
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge") TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge") TObjectPtr<UCameraComponent> Camera;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") EGameForgeCameraMode CameraMode = EGameForgeCameraMode::ThirdPerson;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") float MoveSpeed = 600.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge") float JumpVelocity = 650.f;
	UFUNCTION(BlueprintCallable, Category = "GameForge") void ApplyCameraMode();
protected:
	virtual void BeginPlay() override;
};

/** Builds its Enhanced Input actions at runtime (no input assets needed; works in cooked builds). */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgePlayerController : public APlayerController
{
	GENERATED_BODY()
public:
	UFUNCTION(BlueprintCallable, Category = "GameForge|Input") UInputAction* FindAction(FName ActionId) const;
	/** Same path the IA_Select handler uses after reading the mouse: hit-test at a screen position and select. */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Input") AActor* SelectAtScreenPosition(FVector2D ScreenPosition);
	UPROPERTY(Transient, BlueprintReadOnly, Category = "GameForge|Input") TObjectPtr<UInputMappingContext> MappingContext;
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
	UPROPERTY(Transient) TMap<FName, TObjectPtr<UInputAction>> Actions;
	bool bContextAdded = false;
};

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGameModeBase : public AGameModeBase
{
	GENERATED_BODY()
public:
	AGameForgeGameModeBase();
	virtual void StartPlay() override;   // emits game.started
};
