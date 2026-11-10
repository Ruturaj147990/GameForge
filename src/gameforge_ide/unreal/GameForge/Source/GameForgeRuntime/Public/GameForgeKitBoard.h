#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Components/ActorComponent.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameForgeEvents.h"
#include "GameForgeKitBoard.generated.h"

// ── Selection Interface ───────────────────────────────────────────────────────

UINTERFACE(MinimalAPI, Blueprintable)
class UGameForgeSelectable : public UInterface
{
	GENERATED_BODY()
};

class GAMEFORGERUNTIME_API IGameForgeSelectable
{
	GENERATED_BODY()
public:
	virtual void OnSelected(APlayerController* PC) = 0;
};

// ── Grid Cell Actor Component ─────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API UGameForgeGridCellComponent : public UStaticMeshComponent, public IGameForgeSelectable
{
	GENERATED_BODY()
public:
	UGameForgeGridCellComponent();
	virtual void OnSelected(APlayerController* PC) override;

	int32 Row = 0;
	int32 Col = 0;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> PieceVisual = nullptr;
};

// ── Grid Board Actor ──────────────────────────────────────────────────────────

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeGridBoard : public AActor, public IGameForgeSelectable
{
	GENERATED_BODY()

public:
	AGameForgeGridBoard();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Board")
	TObjectPtr<UBoxComponent> Box;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	FString BoardMode = TEXT("n_in_a_row");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	int32 BoardSize = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	int32 WinLength = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	bool bGravity = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	bool bVsAI = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	FString AILevel = TEXT("random");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	float CellSizeCm = 120.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	bool bHasDice = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	int32 DiceSides = 6;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	int32 Players = 2;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	int32 SnakesCount = 5;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	int32 LaddersCount = 5;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	TMap<int32, int32> Snakes;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	TMap<int32, int32> Ladders;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	TMap<int32, int32> ForwardWarps;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Board")
	TMap<int32, int32> BackwardWarps;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Board")
	TArray<int32> PlayerPositions;

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void OnSelected(APlayerController* PC) override;

	UFUNCTION(BlueprintCallable, Category = "GameForge|Board")
	bool MakeMove(int32 Row, int32 Col, int32 Player);

	UFUNCTION(BlueprintCallable, Category = "GameForge|Board")
	void MakeAIMove();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Board")
	bool AdvanceDiceTurn(int32 DiceRoll, int32 Player);

	int32 GetCellState(int32 Row, int32 Col) const;
	bool CheckWin(int32 Player) const;
	bool IsBoardFull() const;

private:
	void HandleBusEvent(const FGameForgeEvent& Event);
	UGameForgeGridCellComponent* FindCellComponent(int32 Row, int32 Col) const;
	void UpdateCellVisual(int32 Row, int32 Col, int32 Val);
	void InitializeRaceBoard();
	void InitializeSudokuBoard();
	void InitializeConstraintGrid() { InitializeSudokuBoard(); }
	void InitializeChessOrCheckersBoard();
	bool HasSudokuConflict(int32 Row, int32 Col, int32 Val) const;
	bool HasConstraintConflict(int32 Row, int32 Col, int32 Val) const { return HasSudokuConflict(Row, Col, Val); }
	bool IsSudokuComplete() const;
	bool IsConstraintGridComplete() const { return IsSudokuComplete(); }
	bool MakeRaceMove(int32 DiceRoll, int32 Player);
	bool MakeSudokuMove(int32 Row, int32 Col);
	bool MakeConstraintMove(int32 Row, int32 Col) { return MakeSudokuMove(Row, Col); }
	bool MakeChessOrCheckersMove(int32 Row, int32 Col, int32 Player);
	int32 EvaluateMinimaxBoard() const;
	int32 MinimaxSearch(int32 Depth, bool bMaximizing, int32 Alpha, int32 Beta);

	TArray<int32> Grid; // 0=empty, 1=player, 2=ai/p2, or 1..9 in Sudoku
	TArray<bool> FixedClues;
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> RaceTokenVisuals;

	int32 TotalRaceTiles = 100;
	int32 SelectedRow = -1;
	int32 SelectedCol = -1;
	bool bGameOver = false;
	int32 CurrentTurn = 1; // 1=player, 2=ai/p2
	FDelegateHandle BusEventHandle;
};

// ── Card Match Component & Table ──────────────────────────────────────────────

USTRUCT(BlueprintType)
struct GAMEFORGERUNTIME_API FGameForgeCard
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 CardId = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	FString Name;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 Cost = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 Attack = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 Health = 2;
};

UCLASS(Blueprintable, ClassGroup = (GameForge), meta = (BlueprintSpawnableComponent))
class GAMEFORGERUNTIME_API UGameForgeCardMatchComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UGameForgeCardMatchComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 DeckSize = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 HandSize = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 StartingHandSize = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 MaxHandSize = 7;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 EnergyPerTurn = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 BaseEnergyPerTurn = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 PlayerBaseHealth = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 OpponentBaseHealth = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 LaneCount = 3;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	int32 CurrentEnergy = 3;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	int32 PlayerHealth = 20;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	int32 OpponentHealth = 20;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	int32 TurnCount = 1;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	TArray<FGameForgeCard> Deck;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	TArray<FGameForgeCard> Hand;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	TArray<FGameForgeCard> PlayerLanes;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	TArray<FGameForgeCard> OpponentLanes;

	virtual void BeginPlay() override;
	void InitializeMatch(int32 Seed = 2026);
	void DrawCards(int32 Count);
	void SyncStatsToGameState();

	UFUNCTION(BlueprintCallable, Category = "GameForge|Cards")
	void PlayCard(int32 CardIndex, int32 TargetLane);

	UFUNCTION(BlueprintCallable, Category = "GameForge|Cards")
	void EndTurn();

private:
	bool bMatchEnded = false;
};

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeCardTable : public AActor, public IGameForgeSelectable
{
	GENERATED_BODY()

public:
	AGameForgeCardTable();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	TObjectPtr<UStaticMeshComponent> TableMesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge|Cards")
	TObjectPtr<UGameForgeCardMatchComponent> MatchComponent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 DeckSize = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 HandSize = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 StartingHandSize = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 MaxHandSize = 7;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 EnergyPerTurn = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 BaseEnergyPerTurn = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 PlayerBaseHealth = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 OpponentBaseHealth = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge|Cards")
	int32 LaneCount = 3;

	virtual void BeginPlay() override;
	virtual void OnSelected(APlayerController* PC) override;

	void RefreshSlotVisuals();

private:
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> PlayerLaneSlotVisuals;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> OpponentLaneSlotVisuals;
};
