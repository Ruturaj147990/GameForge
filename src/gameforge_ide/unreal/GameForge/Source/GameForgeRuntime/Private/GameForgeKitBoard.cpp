#include "GameForgeKitBoard.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameState.h"
#include "Engine/World.h"
#include "UObject/ConstructorHelpers.h"

// ── Grid Cell Component ───────────────────────────────────────────────────────

UGameForgeGridCellComponent::UGameForgeGridCellComponent()
{
	SetCollisionProfileName(TEXT("BlockAllDynamic"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> PlaneMesh(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (PlaneMesh.Succeeded())
	{
		SetStaticMesh(PlaneMesh.Object);
	}
}

void UGameForgeGridCellComponent::OnSelected(APlayerController* PC)
{
	if (AGameForgeGridBoard* Board = Cast<AGameForgeGridBoard>(GetOwner()))
	{
		Board->MakeMove(Row, Col, 1);
	}
}

// ── Grid Board Actor ──────────────────────────────────────────────────────────

AGameForgeGridBoard::AGameForgeGridBoard()
{
	PrimaryActorTick.bCanEverTick = false;
	Box = CreateDefaultSubobject<UBoxComponent>(TEXT("Box"));
	RootComponent = Box;
	Box->SetBoxExtent(FVector(200.f, 200.f, 50.f));
	Box->SetCollisionProfileName(TEXT("OverlapAllDynamic"));
	Box->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
}

void AGameForgeGridBoard::OnSelected(APlayerController* PC)
{
	for (int32 r = 0; r < BoardSize; ++r)
	{
		for (int32 c = 0; c < BoardSize; ++c)
		{
			if (GetCellState(r, c) == 0)
			{
				MakeMove(r, c, 1);
				return;
			}
		}
	}
}

void AGameForgeGridBoard::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
}

void AGameForgeGridBoard::BeginPlay()
{
	Super::BeginPlay();
	Grid.Init(0, BoardSize * BoardSize);
	bGameOver = false;
	CurrentTurn = 1;

	// Spawn cell components
	for (int32 r = 0; r < BoardSize; r++)
	{
		for (int32 c = 0; c < BoardSize; c++)
		{
			FString CompName = FString::Printf(TEXT("Cell_%d_%d"), r, c);
			UGameForgeGridCellComponent* Cell = NewObject<UGameForgeGridCellComponent>(this, *CompName);
			if (Cell)
			{
				Cell->Row = r;
				Cell->Col = c;
				Cell->ComponentTags.Add(FName(*FString::Printf(TEXT("GF_Cell_%d_%d"), r, c)));
				Cell->RegisterComponent();
				Cell->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepRelativeTransform);
				Cell->SetRelativeLocation(FVector(r * CellSizeCm, c * CellSizeCm, 0.f));
			}
		}
	}
}

int32 AGameForgeGridBoard::GetCellState(int32 Row, int32 Col) const
{
	if (Row >= 0 && Row < BoardSize && Col >= 0 && Col < BoardSize)
	{
		return Grid[Row * BoardSize + Col];
	}
	return -1;
}

bool AGameForgeGridBoard::IsBoardFull() const
{
	for (int32 Val : Grid)
	{
		if (Val == 0) return false;
	}
	return true;
}

bool AGameForgeGridBoard::CheckWin(int32 Player) const
{
	// Check rows, columns, and diagonals
	for (int32 r = 0; r < BoardSize; r++)
	{
		for (int32 c = 0; c < BoardSize; c++)
		{
			if (GetCellState(r, c) != Player) continue;

			// Horizontal
			if (c + WinLength <= BoardSize)
			{
				bool bWin = true;
				for (int32 k = 0; k < WinLength; k++)
				{
					if (GetCellState(r, c + k) != Player) { bWin = false; break; }
				}
				if (bWin) return true;
			}

			// Vertical
			if (r + WinLength <= BoardSize)
			{
				bool bWin = true;
				for (int32 k = 0; k < WinLength; k++)
				{
					if (GetCellState(r + k, c) != Player) { bWin = false; break; }
				}
				if (bWin) return true;
			}

			// Diagonal down-right
			if (r + WinLength <= BoardSize && c + WinLength <= BoardSize)
			{
				bool bWin = true;
				for (int32 k = 0; k < WinLength; k++)
				{
					if (GetCellState(r + k, c + k) != Player) { bWin = false; break; }
				}
				if (bWin) return true;
			}

			// Diagonal down-left
			if (r + WinLength <= BoardSize && c - WinLength + 1 >= 0)
			{
				bool bWin = true;
				for (int32 k = 0; k < WinLength; k++)
				{
					if (GetCellState(r + k, c - k) != Player) { bWin = false; break; }
				}
				if (bWin) return true;
			}
		}
	}
	return false;
}

bool AGameForgeGridBoard::MakeMove(int32 Row, int32 Col, int32 Player)
{
	if (bGameOver || Row < 0 || Row >= BoardSize || Col < 0 || Col >= BoardSize)
	{
		return false;
	}

	int32 TargetRow = Row;
	if (bGravity)
	{
		TargetRow = -1;
		for (int32 r = BoardSize - 1; r >= 0; r--)
		{
			if (GetCellState(r, Col) == 0)
			{
				TargetRow = r;
				break;
			}
		}
		if (TargetRow < 0) return false;
	}
	else
	{
		if (GetCellState(Row, Col) != 0)
		{
			return false;
		}
	}

	Grid[TargetRow * BoardSize + Col] = Player;

	UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this);
	if (Bus)
	{
		FString MoveData = FString::Printf(TEXT("{\"row\":%d,\"col\":%d,\"player\":%d}"), TargetRow, Col, Player);
		Bus->Emit(GFEvent::BoardMove, GetName(), MoveData, EntityId);
	}

	// Check win
	if (CheckWin(Player))
	{
		bGameOver = true;
		if (Bus)
		{
			FString WinnerStr = (Player == 1) ? TEXT("player") : TEXT("ai");
			FString WinData = FString::Printf(TEXT("{\"winner\":\"%s\"}"), *WinnerStr);
			if (Player != 1)
			{
				if (AGameForgeGameState* GS = GetWorld()->GetGameState<AGameForgeGameState>())
				{
					GS->SetStat(FName(TEXT("game.counter.ai_won")), 1.f);
				}
			}
			Bus->Emit(GFEvent::BoardWin, GetName(), WinData, EntityId);
		}
		return true;
	}

	// Check draw
	if (IsBoardFull())
	{
		bGameOver = true;
		if (Bus)
		{
			Bus->Emit(GFEvent::BoardDraw, GetName(), TEXT("{}"), EntityId);
		}
		return true;
	}

	if (Bus)
	{
		Bus->Emit(GFEvent::TurnEnded, GetName(), TEXT("{}"), EntityId);
	}

	if (!bGameOver && bVsAI && Player == 1)
	{
		MakeAIMove();
	}

	return true;
}

void AGameForgeGridBoard::MakeAIMove()
{
	if (bGameOver) return;

	TArray<TPair<int32, int32>> EmptyCells;
	for (int32 r = 0; r < BoardSize; r++)
	{
		for (int32 c = 0; c < BoardSize; c++)
		{
			if (bGravity)
			{
				if (r == 0 && GetCellState(r, c) == 0)
				{
					EmptyCells.Add(TPair<int32, int32>(0, c));
				}
			}
			else
			{
				if (GetCellState(r, c) == 0)
				{
					EmptyCells.Add(TPair<int32, int32>(r, c));
				}
			}
		}
	}

	if (EmptyCells.Num() == 0) return;

	// Greedy check: winning move for AI or block player
	if (AILevel != TEXT("random"))
	{
		for (const auto& Cell : EmptyCells)
		{
			// Check if AI wins
			Grid[Cell.Key * BoardSize + Cell.Value] = 2;
			bool bAIWin = CheckWin(2);
			Grid[Cell.Key * BoardSize + Cell.Value] = 0;
			if (bAIWin)
			{
				MakeMove(Cell.Key, Cell.Value, 2);
				return;
			}
		}

		for (const auto& Cell : EmptyCells)
		{
			// Check if player would win (block)
			Grid[Cell.Key * BoardSize + Cell.Value] = 1;
			bool bPlayerWin = CheckWin(1);
			Grid[Cell.Key * BoardSize + Cell.Value] = 0;
			if (bPlayerWin)
			{
				MakeMove(Cell.Key, Cell.Value, 2);
				return;
			}
		}
	}

	// Default / random move
	int32 Choice = FMath::RandRange(0, EmptyCells.Num() - 1);
	MakeMove(EmptyCells[Choice].Key, EmptyCells[Choice].Value, 2);
}

// ── Card Match Component & Table ──────────────────────────────────────────────

UGameForgeCardMatchComponent::UGameForgeCardMatchComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UGameForgeCardMatchComponent::PlayCard(int32 CardIndex, int32 TargetLane)
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		FString Data = FString::Printf(TEXT("{\"card\":%d,\"lane\":%d}"), CardIndex, TargetLane);
		Bus->Emit(GFEvent::CardPlayed, GetName(), Data);
	}
}

void UGameForgeCardMatchComponent::EndTurn()
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::TurnEnded, GetName(), TEXT("{}"));
		Bus->Emit(GFEvent::LaneResolved, GetName(), TEXT("{}"));
	}
}

AGameForgeCardTable::AGameForgeCardTable()
{
	PrimaryActorTick.bCanEverTick = false;
	MatchComponent = CreateDefaultSubobject<UGameForgeCardMatchComponent>(TEXT("MatchComponent"));
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}
