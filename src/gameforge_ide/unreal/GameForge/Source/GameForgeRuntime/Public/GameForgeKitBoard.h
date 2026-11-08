#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Components/ActorComponent.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
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

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UBoxComponent> Box;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 BoardSize = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 WinLength = 3;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bGravity = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	bool bVsAI = true;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FString AILevel = TEXT("random");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	float CellSizeCm = 120.f;

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void OnSelected(APlayerController* PC) override;

	bool MakeMove(int32 Row, int32 Col, int32 Player);
	void MakeAIMove();

	int32 GetCellState(int32 Row, int32 Col) const;
	bool CheckWin(int32 Player) const;
	bool IsBoardFull() const;

private:
	TArray<int32> Grid; // 0=empty, 1=player, 2=ai/p2
	bool bGameOver = false;
	int32 CurrentTurn = 1; // 1=player, 2=ai/p2
};

// ── Card Match Component & Table ──────────────────────────────────────────────

USTRUCT(BlueprintType)
struct GAMEFORGERUNTIME_API FGameForgeCard
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 CardId = 0;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FString Name;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 Cost = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 Attack = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 Health = 2;
};

UCLASS(Blueprintable, ClassGroup = (GameForge), meta = (BlueprintSpawnableComponent))
class GAMEFORGERUNTIME_API UGameForgeCardMatchComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UGameForgeCardMatchComponent();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 DeckSize = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 HandSize = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 EnergyPerTurn = 3;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	int32 CurrentEnergy = 3;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	int32 PlayerHealth = 20;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	int32 OpponentHealth = 20;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	int32 TurnCount = 1;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TArray<FGameForgeCard> Deck;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TArray<FGameForgeCard> Hand;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TArray<FGameForgeCard> PlayerLanes;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TArray<FGameForgeCard> OpponentLanes;

	virtual void BeginPlay() override;
	void InitializeMatch(int32 Seed = 2026);
	void DrawCards(int32 Count);

	void PlayCard(int32 CardIndex, int32 TargetLane);
	void EndTurn();
};

UCLASS(Blueprintable)
class GAMEFORGERUNTIME_API AGameForgeCardTable : public AActor
{
	GENERATED_BODY()

public:
	AGameForgeCardTable();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "GameForge")
	TObjectPtr<UGameForgeCardMatchComponent> MatchComponent;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	FName EntityId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 DeckSize = 20;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 HandSize = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "GameForge")
	int32 EnergyPerTurn = 3;
};
