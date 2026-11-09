// Copyright 2026 GameForge Systems. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/SaveGame.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "GameForgeKitActors.h"
#include "GameForgeObjectives.generated.h"

class USphereComponent;
class UStaticMeshComponent;

UENUM(BlueprintType)
enum class EGameForgeObjectiveState : uint8
{
	Inactive,
	Active,
	Completed
};

USTRUCT(BlueprintType)
struct GAMEFORGERUNTIME_API FGameForgeObjective
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Objective")
	FName Id;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Objective")
	FString Title;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Objective")
	EGameForgeObjectiveState State = EGameForgeObjectiveState::Inactive;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Objective")
	int32 Progress = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "Objective")
	int32 Target = 1;
};

/** Save file for objective state (UGameplayStatics slot). */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeObjectiveSave : public USaveGame
{
	GENERATED_BODY()

public:
	UPROPERTY(SaveGame)
	TArray<FGameForgeObjective> Objectives;

	UPROPERTY(SaveGame)
	int32 SaveCount = 0;
};

/**
 * Gameplay kit objective/quest state for the running game. Objectives are started, advanced and completed by
 * gameplay (quest givers, pickups). Every change is written to the save slot, and a new game session loads the slot
 * on start, so progress persists across sessions. Logs "GF_EVENT objective ...".
 */
UCLASS()
class GAMEFORGERUNTIME_API UGameForgeObjectiveSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	/** The subsystem of the context's game instance (scripting/tools: SubsystemBlueprintLibrary is not exposed to
	 *  Python in 5.7 and GetSubsystem<> is a template). */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Objectives", meta = (WorldContext = "WorldContextObject"))
	static UGameForgeObjectiveSubsystem* GetForWorld(const UObject* WorldContextObject);

	UFUNCTION(BlueprintCallable, Category = "GameForge|Objectives")
	bool StartObjective(FName Id, const FString& Title, int32 Target);

	UFUNCTION(BlueprintCallable, Category = "GameForge|Objectives")
	bool AddProgress(FName Id, int32 Amount = 1);

	UFUNCTION(BlueprintCallable, Category = "GameForge|Objectives")
	EGameForgeObjectiveState GetState(FName Id) const;

	/** {"loaded_from_slot": bool, "save_count": n, "objectives": [{id,title,state,progress,target}]} */
	UFUNCTION(BlueprintCallable, Category = "GameForge|Objectives")
	FString GetObjectivesJson() const;

	const TArray<FGameForgeObjective>& GetObjectives() const { return Objectives; }

	UFUNCTION(BlueprintCallable, Category = "GameForge|Objectives")
	bool SaveNow();

	UFUNCTION(BlueprintPure, Category = "GameForge|Objectives")
	bool WasLoadedFromSlot() const { return bLoadedFromSlot; }

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Objectives")
	FString SlotName = TEXT("GF_Objectives");

private:
	FGameForgeObjective* Find(FName Id);
	TArray<FGameForgeObjective> Objectives;
	bool bLoadedFromSlot = false;
	int32 SaveCount = 0;
};

/**
 * Gameplay kit quest giver (content-neutral: dialogue and objective come from the game spec, not defaults): when the player-controlled pawn walks up or interacts, it "speaks" its dialogue lines (logged as
 * GF_EVENT dialogue, kept in SpokenLines) and starts its objective; after completion it speaks its turn-in line.
 */
UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeQuestGiver : public AActor, public IGameForgeInteractable
{
	GENERATED_BODY()

public:
	AGameForgeQuestGiver();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Quest")
	TObjectPtr<USphereComponent> TalkRadius;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Quest")
	TObjectPtr<UStaticMeshComponent> Visual;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	FString NpcName = TEXT("Guide");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	FName ObjectiveId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	FName QuestId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	FString ObjectiveTitle;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	FString ObjectiveText;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	int32 ObjectiveTarget = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	int32 TargetCount = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	int32 RewardScore = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	bool bTalkOnOverlap = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	TArray<FString> IntroLines;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Quest")
	FString TurnInLine;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category = "Quest|State")
	TArray<FString> SpokenLines;

	virtual void BeginPlay() override;
	virtual bool CanInteract(AController* InController) const override { return true; }
	virtual void Interact(AController* InController) override;

protected:
	UFUNCTION()
	void HandleOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp,
		int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

private:
	void SyncQuestProperties();
	void TriggerTalk(const APawn* Pawn);
	void Say(const FString& Line);
};
