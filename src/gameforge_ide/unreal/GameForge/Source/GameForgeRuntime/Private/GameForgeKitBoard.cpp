#include "GameForgeKitBoard.h"
#include "GameForgeEvents.h"
#include "GameForgeEventNames.h"
#include "GameForgeGameState.h"
#include "GameForgeVisuals.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

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
	if (BoardMode.Equals(TEXT("race_board"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("grid_race"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("snakes_and_ladders"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("ludo"), ESearchCase::IgnoreCase))
	{
		MakeMove(0, 0, 1);
		return;
	}
	if ((BoardMode.Equals(TEXT("sudoku"), ESearchCase::IgnoreCase) || BoardMode.Equals(TEXT("number_grid"), ESearchCase::IgnoreCase)))
	{
		for (int32 r = 0; r < BoardSize; ++r)
		{
			for (int32 c = 0; c < BoardSize; ++c)
			{
				const int32 Idx = r * BoardSize + c;
				if (FixedClues.IsValidIndex(Idx) && !FixedClues[Idx] && GetCellState(r, c) == 0)
				{
					MakeMove(r, c, 1);
					return;
				}
			}
		}
		return;
	}
	if (BoardMode.Equals(TEXT("chess"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("checkers"), ESearchCase::IgnoreCase))
	{
		MakeChessOrCheckersMove(-1, -1, 1);
		return;
	}
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
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);

	// Guard against 100x100 cell explosion when BoardSize is set to tile count (e.g. 100 for Snakes & Ladders)
	if (BoardSize > 15)
	{
		TotalRaceTiles = BoardSize;
		BoardSize = FMath::Clamp(FMath::RoundToInt(FMath::Sqrt(static_cast<float>(BoardSize))), 4, 15);
		if (BoardMode.IsEmpty() || BoardMode.Equals(TEXT("n_in_a_row"), ESearchCase::IgnoreCase))
		{
			BoardMode = TEXT("snakes_and_ladders");
		}
	}
	else if (Snakes.Num() > 0 || Ladders.Num() > 0)
	{
		if (BoardMode.IsEmpty() || BoardMode.Equals(TEXT("n_in_a_row"), ESearchCase::IgnoreCase))
		{
			BoardMode = TEXT("snakes_and_ladders");
		}
		if (BoardSize < 6)
		{
			BoardSize = 10;
		}
		TotalRaceTiles = BoardSize * BoardSize;
	}

	if ((BoardMode.Equals(TEXT("sudoku"), ESearchCase::IgnoreCase) || BoardMode.Equals(TEXT("number_grid"), ESearchCase::IgnoreCase)))
	{
		BoardSize = 9;
	}
	else if (BoardMode.Equals(TEXT("chess"), ESearchCase::IgnoreCase) ||
			 BoardMode.Equals(TEXT("checkers"), ESearchCase::IgnoreCase))
	{
		BoardSize = 8;
	}
	else if (BoardMode.Equals(TEXT("race_board"), ESearchCase::IgnoreCase) ||
			 BoardMode.Equals(TEXT("grid_race"), ESearchCase::IgnoreCase) ||
			 BoardMode.Equals(TEXT("snakes_and_ladders"), ESearchCase::IgnoreCase) ||
			 BoardMode.Equals(TEXT("ludo"), ESearchCase::IgnoreCase))
	{
		if (BoardSize < 4)
		{
			BoardSize = 10;
		}
		TotalRaceTiles = BoardSize * BoardSize;
	}

	BoardSize = FMath::Clamp(BoardSize, 2, 15);
	Grid.Init(0, BoardSize * BoardSize);
	FixedClues.Init(false, BoardSize * BoardSize);
	bGameOver = false;
	CurrentTurn = 1;
	SelectedRow = -1;
	SelectedCol = -1;

	const float HalfSpan = (BoardSize - 1) * CellSizeCm * 0.5f;
	if (Box)
	{
		Box->SetBoxExtent(FVector(FMath::Max(200.f, HalfSpan + CellSizeCm), FMath::Max(200.f, HalfSpan + CellSizeCm), 50.f));
	}

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
				Cell->SetRelativeLocation(FVector(r * CellSizeCm - HalfSpan, c * CellSizeCm - HalfSpan, 0.f));
				const float TileScale = FMath::Max(0.4f, (CellSizeCm * 0.88f) / 100.f);
				Cell->SetRelativeScale3D(FVector(TileScale, TileScale, 1.f));
				const bool bDarkSquare = ((r + c) % 2) == 1;
				GameForgeVisuals::Tint(Cell, bDarkSquare
					? FLinearColor(0.22f, 0.25f, 0.30f, 1.f)
					: FLinearColor(0.75f, 0.78f, 0.82f, 1.f));
			}
		}
	}

	if (BoardMode.Equals(TEXT("race_board"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("grid_race"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("snakes_and_ladders"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("ludo"), ESearchCase::IgnoreCase) ||
		BoardMode.Contains(TEXT("roll")) ||
		BoardMode.Contains(TEXT("dice")) ||
		BoardMode.Contains(TEXT("path")) ||
		BoardMode.Contains(TEXT("track")) ||
		bHasDice)
	{
		InitializeRaceBoard();
	}
	else if (BoardMode.Equals(TEXT("sudoku"), ESearchCase::IgnoreCase) ||
			 BoardMode.Equals(TEXT("number_grid"), ESearchCase::IgnoreCase) ||
			 BoardMode.Contains(TEXT("constraint")) ||
			 BoardMode.Contains(TEXT("deduction")))
	{
		InitializeSudokuBoard();
	}
	else if (BoardMode.Equals(TEXT("chess"), ESearchCase::IgnoreCase) ||
			 BoardMode.Equals(TEXT("checkers"), ESearchCase::IgnoreCase))
	{
		InitializeChessOrCheckersBoard();
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		BusEventHandle = Bus->OnEvent.AddUObject(this, &AGameForgeGridBoard::HandleBusEvent);
	}
}

void AGameForgeGridBoard::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->OnEvent.Remove(BusEventHandle);
	}
	Super::EndPlay(EndPlayReason);
}

void AGameForgeGridBoard::HandleBusEvent(const FGameForgeEvent& Event)
{
	if (bGameOver)
	{
		return;
	}
	if (Event.Name == GFEvent::DiceRolled &&
		(BoardMode.Equals(TEXT("race_board"), ESearchCase::IgnoreCase) ||
		 BoardMode.Equals(TEXT("grid_race"), ESearchCase::IgnoreCase) ||
		 BoardMode.Equals(TEXT("snakes_and_ladders"), ESearchCase::IgnoreCase) ||
		 BoardMode.Equals(TEXT("ludo"), ESearchCase::IgnoreCase)))
	{
		int32 RollVal = 0;
		TSharedPtr<FJsonObject> Payload;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Event.DataJson);
		if (FJsonSerializer::Deserialize(Reader, Payload) && Payload.IsValid())
		{
			double V = 0.0;
			if (Payload->TryGetNumberField(TEXT("value"), V))
			{
				RollVal = static_cast<int32>(V);
			}
		}
		if (RollVal <= 0)
		{
			RollVal = FMath::RandRange(1, FMath::Max(2, DiceSides));
		}
		AdvanceDiceTurn(RollVal, 1);
	}
}

UGameForgeGridCellComponent* AGameForgeGridBoard::FindCellComponent(int32 Row, int32 Col) const
{
	TArray<UGameForgeGridCellComponent*> Cells;
	GetComponents<UGameForgeGridCellComponent>(Cells);
	for (UGameForgeGridCellComponent* Cell : Cells)
	{
		if (Cell && Cell->Row == Row && Cell->Col == Col)
		{
			return Cell;
		}
	}
	return nullptr;
}

void AGameForgeGridBoard::UpdateCellVisual(int32 Row, int32 Col, int32 Val)
{
	UGameForgeGridCellComponent* Cell = FindCellComponent(Row, Col);
	if (!Cell)
	{
		return;
	}
	if (Val <= 0)
	{
		if (Cell->PieceVisual)
		{
			Cell->PieceVisual->SetVisibility(false);
		}
		return;
	}

	if (!Cell->PieceVisual)
	{
		FString PieceName = FString::Printf(TEXT("Piece_%d_%d"), Row, Col);
		UStaticMeshComponent* Piece = NewObject<UStaticMeshComponent>(this, *PieceName);
		if (Piece)
		{
			Piece->RegisterComponent();
			Piece->AttachToComponent(Cell, FAttachmentTransformRules::KeepRelativeTransform);
			Piece->SetRelativeLocation(FVector(0.f, 0.f, 18.f));
			Piece->SetCollisionProfileName(TEXT("NoCollision"));
			Cell->PieceVisual = Piece;
		}
	}
	if (UStaticMeshComponent* Piece = Cell->PieceVisual)
	{
		Piece->SetVisibility(true);
		const TCHAR* MeshPath = (Val == 1) ? TEXT("/Engine/BasicShapes/Cylinder.Cylinder")
			: (Val == 2) ? TEXT("/Engine/BasicShapes/Cube.Cube")
			: TEXT("/Engine/BasicShapes/Sphere.Sphere");
		if (UStaticMesh* SM = LoadObject<UStaticMesh>(nullptr, MeshPath))
		{
			Piece->SetStaticMesh(SM);
		}
		Piece->SetRelativeScale3D(FVector(0.35f, 0.35f, 0.35f));
		const FLinearColor Color = (Val == 1)
			? FLinearColor(0.18f, 0.55f, 1.0f, 1.f)
			: (Val == 2)
				? FLinearColor(0.95f, 0.25f, 0.2f, 1.f)
				: FLinearColor::MakeFromHSV8(static_cast<uint8>((Val * 28) % 255), 200, 240);
		GameForgeVisuals::Tint(Piece, Color);
	}
}

void AGameForgeGridBoard::InitializeRaceBoard()
{
	const int32 NumPlayers = FMath::Max(2, Players);
	PlayerPositions.Init(1, NumPlayers);

	for (const auto& Kvp : ForwardWarps)
	{
		if (Kvp.Value <= TotalRaceTiles)
		{
			Ladders.Add(Kvp.Key, Kvp.Value);
		}
	}
	for (const auto& Kvp : BackwardWarps)
	{
		if (Kvp.Key <= TotalRaceTiles)
		{
			Snakes.Add(Kvp.Key, Kvp.Value);
		}
	}

	if (Ladders.Num() == 0 && LaddersCount > 0)
	{
		static const TPair<int32, int32> DefaultLadders[] = {
			{4, 14}, {9, 31}, {20, 38}, {28, 84}, {40, 59}, {51, 67}, {63, 81}, {71, 91}
		};
		for (int32 i = 0; i < FMath::Min<int32>(LaddersCount, UE_ARRAY_COUNT(DefaultLadders)); ++i)
		{
			if (DefaultLadders[i].Value <= TotalRaceTiles)
			{
				Ladders.Add(DefaultLadders[i].Key, DefaultLadders[i].Value);
			}
		}
	}
	if (Snakes.Num() == 0 && SnakesCount > 0)
	{
		static const TPair<int32, int32> DefaultSnakes[] = {
			{17, 7}, {54, 34}, {62, 19}, {64, 60}, {87, 24}, {93, 73}, {95, 75}, {99, 78}
		};
		for (int32 i = 0; i < FMath::Min<int32>(SnakesCount, UE_ARRAY_COUNT(DefaultSnakes)); ++i)
		{
			if (DefaultSnakes[i].Key < TotalRaceTiles)
			{
				Snakes.Add(DefaultSnakes[i].Key, DefaultSnakes[i].Value);
			}
		}
	}

	// Highlight snake and ladder tiles on the board
	auto TileToRowCol = [this](int32 TileOneBased, int32& OutRow, int32& OutCol)
	{
		const int32 Clamped = FMath::Clamp(TileOneBased - 1, 0, BoardSize * BoardSize - 1);
		OutRow = Clamped / BoardSize;
		const int32 ColInRow = Clamped % BoardSize;
		OutCol = (OutRow % 2 == 0) ? ColInRow : (BoardSize - 1 - ColInRow);
	};

	for (const auto& Kvp : Ladders)
	{
		int32 R = 0, C = 0;
		TileToRowCol(Kvp.Key, R, C);
		if (UGameForgeGridCellComponent* Cell = FindCellComponent(R, C))
		{
			GameForgeVisuals::Tint(Cell, FLinearColor(0.2f, 0.85f, 0.35f, 1.f));
		}
	}
	for (const auto& Kvp : Snakes)
	{
		int32 R = 0, C = 0;
		TileToRowCol(Kvp.Key, R, C);
		if (UGameForgeGridCellComponent* Cell = FindCellComponent(R, C))
		{
			GameForgeVisuals::Tint(Cell, FLinearColor(0.9f, 0.25f, 0.2f, 1.f));
		}
	}

	RaceTokenVisuals.Reset();
	for (int32 PIdx = 0; PIdx < NumPlayers; ++PIdx)
	{
		FString TokName = FString::Printf(TEXT("RaceToken_%d"), PIdx + 1);
		UStaticMeshComponent* Tok = NewObject<UStaticMeshComponent>(this, *TokName);
		if (Tok)
		{
			Tok->RegisterComponent();
			Tok->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepRelativeTransform);
			Tok->SetCollisionProfileName(TEXT("NoCollision"));
			GameForgeVisuals::SetBasicShape(Tok, PIdx == 0 ? TEXT("Cylinder") : TEXT("Cone"));
			Tok->SetRelativeScale3D(FVector(0.32f, 0.32f, 0.55f));
			GameForgeVisuals::Tint(Tok, PIdx == 0
				? FLinearColor(0.15f, 0.55f, 1.0f, 1.f)
				: FLinearColor(1.0f, 0.35f, 0.15f, 1.f));
			RaceTokenVisuals.Add(Tok);
		}
	}
}

void AGameForgeGridBoard::InitializeSudokuBoard()
{
	static const int32 Solution[9][9] = {
		{5,3,4, 6,7,8, 9,1,2},
		{6,7,2, 1,9,5, 3,4,8},
		{1,9,8, 3,4,2, 5,6,7},
		{8,5,9, 7,6,1, 4,2,3},
		{4,2,6, 8,5,3, 7,9,1},
		{7,1,3, 9,2,4, 8,5,6},
		{9,6,1, 5,3,7, 2,8,4},
		{2,8,7, 4,1,9, 6,3,5},
		{3,4,5, 2,8,6, 1,7,9}
	};
	const int32 DigitShift = FMath::Abs(static_cast<int32>(GetActorLocation().X + GetActorLocation().Y)) % 9;
	for (int32 r = 0; r < 9; ++r)
	{
		for (int32 c = 0; c < 9; ++c)
		{
			const int32 Idx = r * 9 + c;
			// Leave ~18 cells open for gameplay while pre-filling clues with deterministic digit permutation
			const bool bIsClue = ((r * 3 + c) % 4 != 0);
			FixedClues[Idx] = bIsClue;
			const int32 PermutedVal = ((Solution[r][c] - 1 + DigitShift) % 9) + 1;
			Grid[Idx] = bIsClue ? PermutedVal : 0;
			if (bIsClue)
			{
				UpdateCellVisual(r, c, Grid[Idx]);
			}
		}
	}
}

void AGameForgeGridBoard::InitializeChessOrCheckersBoard()
{
	const bool bIsChess = BoardMode.Equals(TEXT("chess"), ESearchCase::IgnoreCase);
	for (int32 r = 0; r < BoardSize; ++r)
	{
		for (int32 c = 0; c < BoardSize; ++c)
		{
			int32 PieceOwner = 0;
			if (bIsChess)
			{
				if (r <= 1) PieceOwner = 1;
				else if (r >= BoardSize - 2) PieceOwner = 2;
			}
			else
			{
				if (((r + c) % 2) == 1)
				{
					if (r <= 2) PieceOwner = 1;
					else if (r >= BoardSize - 3) PieceOwner = 2;
				}
			}
			Grid[r * BoardSize + c] = PieceOwner;
			if (PieceOwner != 0)
			{
				UpdateCellVisual(r, c, PieceOwner);
			}
		}
	}
}

bool AGameForgeGridBoard::HasSudokuConflict(int32 Row, int32 Col, int32 Val) const
{
	if (Val <= 0)
	{
		return false;
	}
	for (int32 i = 0; i < BoardSize; ++i)
	{
		if (i != Col && GetCellState(Row, i) == Val) return true;
		if (i != Row && GetCellState(i, Col) == Val) return true;
	}
	const int32 BoxR = (Row / 3) * 3;
	const int32 BoxC = (Col / 3) * 3;
	for (int32 r = BoxR; r < BoxR + 3 && r < BoardSize; ++r)
	{
		for (int32 c = BoxC; c < BoxC + 3 && c < BoardSize; ++c)
		{
			if ((r != Row || c != Col) && GetCellState(r, c) == Val)
			{
				return true;
			}
		}
	}
	return false;
}

bool AGameForgeGridBoard::IsSudokuComplete() const
{
	for (int32 r = 0; r < BoardSize; ++r)
	{
		for (int32 c = 0; c < BoardSize; ++c)
		{
			const int32 Val = GetCellState(r, c);
			if (Val < 1 || Val > 9 || HasSudokuConflict(r, c, Val))
			{
				return false;
			}
		}
	}
	return true;
}

bool AGameForgeGridBoard::AdvanceDiceTurn(int32 DiceRoll, int32 Player)
{
	return MakeRaceMove(DiceRoll, Player);
}

bool AGameForgeGridBoard::MakeRaceMove(int32 DiceRoll, int32 Player)
{
	if (bGameOver)
	{
		return false;
	}
	const int32 NumPlayers = FMath::Max(2, Players);
	if (PlayerPositions.Num() < NumPlayers)
	{
		PlayerPositions.Init(1, NumPlayers);
	}
	const int32 PIdx = FMath::Clamp(Player - 1, 0, PlayerPositions.Num() - 1);
	const int32 Sides = FMath::Max(2, DiceSides);
	const int32 Roll = (DiceRoll > 0) ? DiceRoll : FMath::RandRange(1, Sides);

	UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this);
	if (DiceRoll <= 0 && Bus)
	{
		Bus->Emit(GFEvent::DiceRolled, GetName(),
			FString::Printf(TEXT("{\"value\":%d,\"player\":%d}"), Roll, Player), EntityId);
	}

	const int32 OldTile = PlayerPositions[PIdx];
	int32 NewTile = FMath::Min(TotalRaceTiles, OldTile + Roll);

	if (const int32* LadderDest = Ladders.Find(NewTile))
	{
		const int32 FromTile = NewTile;
		NewTile = FMath::Clamp(*LadderDest, 1, TotalRaceTiles);
		if (Bus)
		{
			Bus->Emit(FName(TEXT("ladder.transition")), GetName(),
				FString::Printf(TEXT("{\"player\":%d,\"from\":%d,\"to\":%d}"), Player, FromTile, NewTile), EntityId);
		}
	}
	else if (const int32* SnakeDest = Snakes.Find(NewTile))
	{
		const int32 FromTile = NewTile;
		NewTile = FMath::Clamp(*SnakeDest, 1, TotalRaceTiles);
		if (Bus)
		{
			Bus->Emit(FName(TEXT("snake.transition")), GetName(),
				FString::Printf(TEXT("{\"player\":%d,\"from\":%d,\"to\":%d}"), Player, FromTile, NewTile), EntityId);
		}
	}

	PlayerPositions[PIdx] = NewTile;

	const int32 ClampedIdx = FMath::Clamp(NewTile - 1, 0, BoardSize * BoardSize - 1);
	const int32 Row = ClampedIdx / BoardSize;
	const int32 ColInRow = ClampedIdx % BoardSize;
	const int32 Col = (Row % 2 == 0) ? ColInRow : (BoardSize - 1 - ColInRow);

	if (RaceTokenVisuals.IsValidIndex(PIdx) && RaceTokenVisuals[PIdx])
	{
		const float HalfSpan = (BoardSize - 1) * CellSizeCm * 0.5f;
		const float Offset = (PIdx == 0) ? -18.f : 18.f;
		RaceTokenVisuals[PIdx]->SetRelativeLocation(FVector(Row * CellSizeCm - HalfSpan + Offset, Col * CellSizeCm - HalfSpan + Offset, 30.f));
	}

	if (AGameForgeGameState* GS = GetWorld() ? GetWorld()->GetGameState<AGameForgeGameState>() : nullptr)
	{
		GS->SetStat(FName(*(FString::Printf(TEXT("player_%d.tile"), Player))), static_cast<float>(NewTile));
		if (Player == 1)
		{
			GS->SetStat(FName(TEXT("game.score")), static_cast<float>(NewTile));
		}
	}

	if (Bus)
	{
		Bus->Emit(GFEvent::BoardMove, GetName(),
			FString::Printf(TEXT("{\"row\":%d,\"col\":%d,\"tile\":%d,\"roll\":%d,\"player\":%d}"), Row, Col, NewTile, Roll, Player), EntityId);
	}

	if (NewTile >= TotalRaceTiles)
	{
		bGameOver = true;
		if (Bus)
		{
			const FString WinnerStr = (Player == 1) ? TEXT("player") : TEXT("ai");
			Bus->Emit(GFEvent::BoardWin, GetName(), FString::Printf(TEXT("{\"winner\":\"%s\",\"tile\":%d}"), *WinnerStr, NewTile), EntityId);
			if (Player == 1)
			{
				Bus->Emit(GFEvent::MatchWon, GetName(), TEXT("{\"winner\":\"player\"}"), EntityId);
			}
			else
			{
				if (AGameForgeGameState* GS = GetWorld() ? GetWorld()->GetGameState<AGameForgeGameState>() : nullptr)
				{
					GS->SetStat(FName(TEXT("game.counter.ai_won")), 1.f);
				}
				Bus->Emit(GFEvent::BoardLose, GetName(), TEXT("{\"winner\":\"ai\"}"), EntityId);
				Bus->Emit(GFEvent::MatchLost, GetName(), TEXT("{\"winner\":\"ai\"}"), EntityId);
			}
		}
		return true;
	}

	if (Bus)
	{
		Bus->Emit(GFEvent::TurnEnded, GetName(), TEXT("{}"), EntityId);
	}

	if (!bGameOver && bVsAI && Player == 1)
	{
		const int32 AIRoll = FMath::RandRange(1, Sides);
		MakeRaceMove(AIRoll, 2);
	}
	return true;
}

bool AGameForgeGridBoard::MakeSudokuMove(int32 Row, int32 Col)
{
	if (bGameOver || Row < 0 || Row >= BoardSize || Col < 0 || Col >= BoardSize)
	{
		return false;
	}
	const int32 Idx = Row * BoardSize + Col;
	if (FixedClues.IsValidIndex(Idx) && FixedClues[Idx])
	{
		return false;
	}

	// Find the first conflict-free number >= current+1, or cycle 1..9
	int32 NextVal = (Grid[Idx] % 9) + 1;
	for (int32 Try = 0; Try < 9; ++Try)
	{
		const int32 Cand = ((Grid[Idx] + Try) % 9) + 1;
		if (!HasSudokuConflict(Row, Col, Cand))
		{
			NextVal = Cand;
			break;
		}
	}
	Grid[Idx] = NextVal;
	UpdateCellVisual(Row, Col, NextVal);

	UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this);
	if (Bus)
	{
		Bus->Emit(GFEvent::BoardMove, GetName(),
			FString::Printf(TEXT("{\"row\":%d,\"col\":%d,\"value\":%d,\"player\":1}"), Row, Col, NextVal), EntityId);
	}

	if (IsSudokuComplete())
	{
		bGameOver = true;
		if (Bus)
		{
			Bus->Emit(GFEvent::BoardWin, GetName(), TEXT("{\"winner\":\"player\"}"), EntityId);
			Bus->Emit(GFEvent::MatchWon, GetName(), TEXT("{\"winner\":\"player\"}"), EntityId);
		}
	}
	return true;
}

bool AGameForgeGridBoard::MakeChessOrCheckersMove(int32 Row, int32 Col, int32 Player)
{
	if (bGameOver)
	{
		return false;
	}

	auto ExecutePieceMove = [this, Player](int32 FromR, int32 FromC, int32 ToR, int32 ToC) -> bool
	{
		Grid[FromR * BoardSize + FromC] = 0;
		UpdateCellVisual(FromR, FromC, 0);

		// Jump capture in checkers/chess if moving 2 squares
		if (FMath::Abs(ToR - FromR) == 2 && FMath::Abs(ToC - FromC) == 2)
		{
			const int32 MidR = (FromR + ToR) / 2;
			const int32 MidC = (FromC + ToC) / 2;
			if (GetCellState(MidR, MidC) != 0 && GetCellState(MidR, MidC) != Player)
			{
				Grid[MidR * BoardSize + MidC] = 0;
				UpdateCellVisual(MidR, MidC, 0);
			}
		}

		Grid[ToR * BoardSize + ToC] = Player;
		UpdateCellVisual(ToR, ToC, Player);

		UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this);
		if (Bus)
		{
			Bus->Emit(GFEvent::BoardMove, GetName(),
				FString::Printf(TEXT("{\"from_row\":%d,\"from_col\":%d,\"row\":%d,\"col\":%d,\"player\":%d}"),
					FromR, FromC, ToR, ToC, Player), EntityId);
		}

		// Count remaining opponent pieces
		const int32 Opponent = (Player == 1) ? 2 : 1;
		int32 OppCount = 0;
		for (int32 V : Grid)
		{
			if (V == Opponent) OppCount++;
		}
		if (OppCount == 0)
		{
			bGameOver = true;
			if (Bus)
			{
				const FString WinnerStr = (Player == 1) ? TEXT("player") : TEXT("ai");
				Bus->Emit(GFEvent::BoardWin, GetName(), FString::Printf(TEXT("{\"winner\":\"%s\"}"), *WinnerStr), EntityId);
				if (Player == 1)
				{
					Bus->Emit(GFEvent::MatchWon, GetName(), TEXT("{\"winner\":\"player\"}"), EntityId);
				}
				else
				{
					Bus->Emit(GFEvent::BoardLose, GetName(), TEXT("{\"winner\":\"ai\"}"), EntityId);
					Bus->Emit(GFEvent::MatchLost, GetName(), TEXT("{\"winner\":\"ai\"}"), EntityId);
				}
			}
			return true;
		}

		if (Bus)
		{
			Bus->Emit(GFEvent::TurnEnded, GetName(), TEXT("{}"), EntityId);
		}
		return true;
	};

	// Step 1: If clicking own piece, select it
	if (Row >= 0 && Row < BoardSize && Col >= 0 && Col < BoardSize && GetCellState(Row, Col) == Player)
	{
		SelectedRow = Row;
		SelectedCol = Col;
		return true;
	}

	// Step 2: If a piece is already selected and clicking an empty or opponent square, move it
	if (SelectedRow >= 0 && SelectedCol >= 0 && Row >= 0 && Row < BoardSize && Col >= 0 && Col < BoardSize &&
		GetCellState(Row, Col) != Player)
	{
		const int32 FromR = SelectedRow;
		const int32 FromC = SelectedCol;
		SelectedRow = -1;
		SelectedCol = -1;
		const bool bMoved = ExecutePieceMove(FromR, FromC, Row, Col);
		if (bMoved && !bGameOver && bVsAI && Player == 1)
		{
			MakeChessOrCheckersMove(-1, -1, 2);
		}
		return bMoved;
	}

	// Fallback: auto-select a piece with a valid forward/capture move
	const int32 Dir = (Player == 1) ? 1 : -1;
	for (int32 r = 0; r < BoardSize; ++r)
	{
		for (int32 c = 0; c < BoardSize; ++c)
		{
			if (GetCellState(r, c) != Player) continue;
			const int32 NextR = r + Dir;
			if (NextR >= 0 && NextR < BoardSize)
			{
				for (int32 dc : { -1, 0, 1 })
				{
					const int32 NextC = c + dc;
					if (NextC >= 0 && NextC < BoardSize && GetCellState(NextR, NextC) != Player)
					{
						const bool bMoved = ExecutePieceMove(r, c, NextR, NextC);
						if (bMoved && !bGameOver && bVsAI && Player == 1)
						{
							MakeChessOrCheckersMove(-1, -1, 2);
						}
						return bMoved;
					}
				}
			}
		}
	}
	return false;
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
	if (bGameOver)
	{
		return false;
	}

	if (BoardMode.Equals(TEXT("race_board"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("grid_race"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("roll_and_move"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("snakes_and_ladders"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("ludo"), ESearchCase::IgnoreCase) ||
		BoardMode.Contains(TEXT("roll")))
	{
		return MakeRaceMove(0, Player);
	}
	if ((BoardMode.Equals(TEXT("sudoku"), ESearchCase::IgnoreCase) || BoardMode.Equals(TEXT("number_grid"), ESearchCase::IgnoreCase)))
	{
		return MakeSudokuMove(Row, Col);
	}
	if (BoardMode.Equals(TEXT("chess"), ESearchCase::IgnoreCase) ||
		BoardMode.Equals(TEXT("checkers"), ESearchCase::IgnoreCase))
	{
		return MakeChessOrCheckersMove(Row, Col, Player);
	}

	if (Row < 0 || Row >= BoardSize || Col < 0 || Col >= BoardSize)
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
	UpdateCellVisual(TargetRow, Col, Player);

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
			const bool bPlayerWon = (Player == 1) || !bVsAI;
			FString WinnerStr = bPlayerWon ? TEXT("player") : TEXT("ai");
			FString WinData = FString::Printf(TEXT("{\"winner\":\"%s\"}"), *WinnerStr);
			if (!bPlayerWon)
			{
				if (AGameForgeGameState* GS = GetWorld() ? GetWorld()->GetGameState<AGameForgeGameState>() : nullptr)
				{
					GS->SetStat(FName(TEXT("game.counter.ai_won")), 1.f);
				}
				Bus->Emit(GFEvent::BoardLose, GetName(), WinData, EntityId);
				Bus->Emit(GFEvent::MatchLost, GetName(), WinData, EntityId);
			}
			else
			{
				Bus->Emit(GFEvent::MatchWon, GetName(), WinData, EntityId);
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

int32 AGameForgeGridBoard::EvaluateMinimaxBoard() const
{
	if (CheckWin(2)) return 1000;
	if (CheckWin(1)) return -1000;

	int32 Score = 0;
	const int32 Center = BoardSize / 2;
	for (int32 r = 0; r < BoardSize; ++r)
	{
		for (int32 c = 0; c < BoardSize; ++c)
		{
			const int32 Val = GetCellState(r, c);
			if (Val == 0) continue;
			int32 PosWeight = 1;
			if (r == Center && c == Center) PosWeight += 4;
			else if ((r == 0 || r == BoardSize - 1) && (c == 0 || c == BoardSize - 1)) PosWeight += 2;
			Score += (Val == 2) ? PosWeight : -PosWeight;
		}
	}
	return Score;
}

int32 AGameForgeGridBoard::MinimaxSearch(int32 Depth, bool bMaximizing, int32 Alpha, int32 Beta)
{
	if (CheckWin(2)) return 1000 + Depth;
	if (CheckWin(1)) return -1000 - Depth;
	if (Depth <= 0 || IsBoardFull())
	{
		return EvaluateMinimaxBoard();
	}

	TArray<TPair<int32, int32>> LegalMoves;
	if (bGravity)
	{
		for (int32 c = 0; c < BoardSize; ++c)
		{
			for (int32 r = BoardSize - 1; r >= 0; --r)
			{
				if (GetCellState(r, c) == 0)
				{
					LegalMoves.Add(TPair<int32, int32>(r, c));
					break;
				}
			}
		}
	}
	else
	{
		for (int32 r = 0; r < BoardSize; ++r)
		{
			for (int32 c = 0; c < BoardSize; ++c)
			{
				if (GetCellState(r, c) == 0)
				{
					LegalMoves.Add(TPair<int32, int32>(r, c));
				}
			}
		}
	}

	if (bMaximizing)
	{
		int32 Best = -100000;
		for (const auto& M : LegalMoves)
		{
			Grid[M.Key * BoardSize + M.Value] = 2;
			const int32 Score = MinimaxSearch(Depth - 1, false, Alpha, Beta);
			Grid[M.Key * BoardSize + M.Value] = 0;
			Best = FMath::Max(Best, Score);
			Alpha = FMath::Max(Alpha, Best);
			if (Beta <= Alpha) break;
		}
		return Best;
	}
	else
	{
		int32 Best = 100000;
		for (const auto& M : LegalMoves)
		{
			Grid[M.Key * BoardSize + M.Value] = 1;
			const int32 Score = MinimaxSearch(Depth - 1, true, Alpha, Beta);
			Grid[M.Key * BoardSize + M.Value] = 0;
			Best = FMath::Min(Best, Score);
			Beta = FMath::Min(Beta, Best);
			if (Beta <= Alpha) break;
		}
		return Best;
	}
}

void AGameForgeGridBoard::MakeAIMove()
{
	if (bGameOver) return;

	TArray<TPair<int32, int32>> EmptyCells;
	if (bGravity)
	{
		for (int32 c = 0; c < BoardSize; c++)
		{
			for (int32 r = BoardSize - 1; r >= 0; r--)
			{
				if (GetCellState(r, c) == 0)
				{
					EmptyCells.Add(TPair<int32, int32>(r, c));
					break;
				}
			}
		}
	}
	else
	{
		for (int32 r = 0; r < BoardSize; r++)
		{
			for (int32 c = 0; c < BoardSize; c++)
			{
				if (GetCellState(r, c) == 0)
				{
					EmptyCells.Add(TPair<int32, int32>(r, c));
				}
			}
		}
	}

	if (EmptyCells.Num() == 0) return;

	// Greedy 1-ply check: winning move for AI or block player
	if (!AILevel.Equals(TEXT("random"), ESearchCase::IgnoreCase))
	{
		for (const auto& Cell : EmptyCells)
		{
			Grid[Cell.Key * BoardSize + Cell.Value] = 2;
			const bool bAIWin = CheckWin(2);
			Grid[Cell.Key * BoardSize + Cell.Value] = 0;
			if (bAIWin)
			{
				MakeMove(bGravity ? 0 : Cell.Key, Cell.Value, 2);
				return;
			}
		}

		for (const auto& Cell : EmptyCells)
		{
			Grid[Cell.Key * BoardSize + Cell.Value] = 1;
			const bool bPlayerWin = CheckWin(1);
			Grid[Cell.Key * BoardSize + Cell.Value] = 0;
			if (bPlayerWin)
			{
				MakeMove(bGravity ? 0 : Cell.Key, Cell.Value, 2);
				return;
			}
		}

		// 2-ply minimax lookahead + center/corner heuristics for perfect/minimax AI
		if (AILevel.Equals(TEXT("perfect"), ESearchCase::IgnoreCase) ||
			AILevel.Equals(TEXT("minimax"), ESearchCase::IgnoreCase))
		{
			const int32 SearchDepth = (EmptyCells.Num() <= 9) ? 4 : 2;
			int32 BestScore = -100000;
			TPair<int32, int32> BestMove = EmptyCells[0];
			for (const auto& Cell : EmptyCells)
			{
				Grid[Cell.Key * BoardSize + Cell.Value] = 2;
				const int32 Score = MinimaxSearch(SearchDepth - 1, false, -100000, 100000);
				Grid[Cell.Key * BoardSize + Cell.Value] = 0;
				if (Score > BestScore)
				{
					BestScore = Score;
					BestMove = Cell;
				}
			}
			MakeMove(bGravity ? 0 : BestMove.Key, BestMove.Value, 2);
			return;
		}
	}

	// Default / random move
	int32 Choice = FMath::RandRange(0, EmptyCells.Num() - 1);
	MakeMove(bGravity ? 0 : EmptyCells[Choice].Key, EmptyCells[Choice].Value, 2);
}

// ── Card Match Component & Table ──────────────────────────────────────────────

UGameForgeCardMatchComponent::UGameForgeCardMatchComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UGameForgeCardMatchComponent::BeginPlay()
{
	Super::BeginPlay();
	InitializeMatch(2026);
}

void UGameForgeCardMatchComponent::SyncStatsToGameState()
{
	if (UWorld* W = GetWorld())
	{
		if (AGameForgeGameState* GS = W->GetGameState<AGameForgeGameState>())
		{
			GS->SetStat(FName(TEXT("player.health")), static_cast<float>(PlayerHealth));
			GS->SetStat(FName(TEXT("player.max_health")), static_cast<float>(FMath::Max(1, PlayerBaseHealth)));
			GS->SetStat(FName(TEXT("opponent.health")), static_cast<float>(OpponentHealth));
			GS->SetStat(FName(TEXT("player.energy")), static_cast<float>(CurrentEnergy));
			GS->SetStat(FName(TEXT("turn.number")), static_cast<float>(TurnCount));
		}
	}
}

void UGameForgeCardMatchComponent::InitializeMatch(int32 Seed)
{
	bMatchEnded = false;
	if (StartingHandSize > 0 && HandSize == 4 && StartingHandSize != 4)
	{
		HandSize = StartingHandSize;
	}
	if (BaseEnergyPerTurn > 0 && EnergyPerTurn == 3 && BaseEnergyPerTurn != 3)
	{
		EnergyPerTurn = BaseEnergyPerTurn;
	}
	LaneCount = FMath::Clamp(LaneCount, 1, 8);
	PlayerHealth = (PlayerBaseHealth > 0) ? PlayerBaseHealth : 20;
	OpponentHealth = (OpponentBaseHealth > 0) ? OpponentBaseHealth : 20;
	CurrentEnergy = EnergyPerTurn;
	TurnCount = 1;

	Deck.Empty();
	Hand.Empty();
	PlayerLanes.Init(FGameForgeCard(), LaneCount);
	OpponentLanes.Init(FGameForgeCard(), LaneCount);

	// Deterministic seeded deck generation
	FRandomStream Rng(Seed);
	for (int32 i = 0; i < DeckSize; ++i)
	{
		FGameForgeCard Card;
		Card.CardId = i + 1;
		Card.Name = FString::Printf(TEXT("Card_%d"), Card.CardId);
		Card.Cost = 1 + (i % 3);
		Card.Attack = 2 + (i % 4);
		Card.Health = 2 + ((i * 2) % 5);
		Deck.Add(Card);
	}

	DrawCards(HandSize);
	SyncStatsToGameState();
}

void UGameForgeCardMatchComponent::DrawCards(int32 Count)
{
	const int32 Cap = FMath::Max(1, MaxHandSize);
	for (int32 i = 0; i < Count; ++i)
	{
		if (Deck.Num() > 0 && Hand.Num() < Cap)
		{
			Hand.Add(Deck[0]);
			Deck.RemoveAt(0);
		}
	}
}

void UGameForgeCardMatchComponent::PlayCard(int32 CardIndex, int32 TargetLane)
{
	if (bMatchEnded)
	{
		return;
	}
	if (CardIndex < 0 || CardIndex >= Hand.Num())
	{
		return;
	}
	const int32 NumLanes = FMath::Max(1, PlayerLanes.Num());
	if (TargetLane < 0 || TargetLane >= NumLanes)
	{
		return;
	}

	const FGameForgeCard& CardToPlay = Hand[CardIndex];
	if (CardToPlay.Cost > CurrentEnergy)
	{
		return;
	}

	CurrentEnergy -= CardToPlay.Cost;
	FGameForgeCard PlayedCard = CardToPlay;
	Hand.RemoveAt(CardIndex);
	PlayerLanes[TargetLane] = PlayedCard;

	SyncStatsToGameState();
	if (AGameForgeCardTable* Table = Cast<AGameForgeCardTable>(GetOwner()))
	{
		Table->RefreshSlotVisuals();
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		FString Data = FString::Printf(TEXT("{\"card\":%d,\"lane\":%d,\"cost\":%d,\"atk\":%d,\"hp\":%d}"),
			PlayedCard.CardId, TargetLane, PlayedCard.Cost, PlayedCard.Attack, PlayedCard.Health);
		Bus->Emit(GFEvent::CardPlayed, GetName(), Data);
	}
}

void UGameForgeCardMatchComponent::EndTurn()
{
	if (bMatchEnded)
	{
		return;
	}

	const int32 NumLanes = FMath::Max(1, PlayerLanes.Num());
	if (OpponentLanes.Num() < NumLanes)
	{
		OpponentLanes.SetNum(NumLanes);
	}

	// Deploy AI opponent cards into open lane(s) before combat resolution
	int32 AIEnergy = EnergyPerTurn;
	for (int32 Lane = 0; Lane < NumLanes; ++Lane)
	{
		if (OpponentLanes[Lane].CardId == 0 && AIEnergy >= 1)
		{
			FGameForgeCard AICard;
			AICard.CardId = 100 + TurnCount * 10 + Lane;
			AICard.Name = FString::Printf(TEXT("AI_Card_%d"), AICard.CardId);
			AICard.Cost = FMath::Clamp(1 + ((TurnCount + Lane) % 2), 1, AIEnergy);
			AICard.Attack = 1 + ((TurnCount + Lane) % 3);
			AICard.Health = 2 + (TurnCount % 3);
			OpponentLanes[Lane] = AICard;
			AIEnergy -= AICard.Cost;
		}
	}

	// Resolve lane combat
	for (int32 Lane = 0; Lane < NumLanes; ++Lane)
	{
		if (PlayerLanes[Lane].CardId > 0 && OpponentLanes[Lane].CardId > 0)
		{
			const int32 PlayerAtk = PlayerLanes[Lane].Attack;
			const int32 OppAtk = OpponentLanes[Lane].Attack;
			PlayerLanes[Lane].Health -= OppAtk;
			OpponentLanes[Lane].Health -= PlayerAtk;
			// Trample / excess damage reaches opponent base health so matches progress decisively
			if (OpponentLanes[Lane].Health < 0)
			{
				OpponentHealth = FMath::Max(0, OpponentHealth + OpponentLanes[Lane].Health);
			}
			if (PlayerLanes[Lane].Health <= 0) PlayerLanes[Lane] = FGameForgeCard();
			if (OpponentLanes[Lane].Health <= 0) OpponentLanes[Lane] = FGameForgeCard();
		}
		else if (PlayerLanes[Lane].CardId > 0 && OpponentLanes[Lane].CardId == 0)
		{
			OpponentHealth = FMath::Max(0, OpponentHealth - PlayerLanes[Lane].Attack);
		}
		else if (OpponentLanes[Lane].CardId > 0 && PlayerLanes[Lane].CardId == 0)
		{
			PlayerHealth = FMath::Max(0, PlayerHealth - OpponentLanes[Lane].Attack);
		}
	}

	TurnCount++;
	CurrentEnergy = EnergyPerTurn;
	DrawCards(1);

	SyncStatsToGameState();
	if (AGameForgeCardTable* Table = Cast<AGameForgeCardTable>(GetOwner()))
	{
		Table->RefreshSlotVisuals();
	}

	if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
	{
		Bus->Emit(GFEvent::TurnEnded, GetName(), FString::Printf(TEXT("{\"turn\":%d}"), TurnCount));
		Bus->Emit(GFEvent::LaneResolved, GetName(), FString::Printf(TEXT("{\"player_hp\":%d,\"opp_hp\":%d}"), PlayerHealth, OpponentHealth));

		if (OpponentHealth <= 0)
		{
			bMatchEnded = true;
			Bus->Emit(GFEvent::MatchWon, GetName(), FString::Printf(TEXT("{\"player_hp\":%d,\"opp_hp\":0}"), PlayerHealth));
		}
		else if (PlayerHealth <= 0)
		{
			bMatchEnded = true;
			Bus->Emit(GFEvent::MatchLost, GetName(), FString::Printf(TEXT("{\"player_hp\":0,\"opp_hp\":%d}"), OpponentHealth));
		}
	}
}

AGameForgeCardTable::AGameForgeCardTable()
{
	PrimaryActorTick.bCanEverTick = false;

	TableMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TableMesh"));
	RootComponent = TableMesh;
	TableMesh->SetCollisionProfileName(TEXT("BlockAllDynamic"));
	TableMesh->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMesh.Succeeded())
	{
		TableMesh->SetStaticMesh(CubeMesh.Object);
		TableMesh->SetRelativeScale3D(FVector(3.6f, 5.2f, 0.25f));
	}

	MatchComponent = CreateDefaultSubobject<UGameForgeCardMatchComponent>(TEXT("MatchComponent"));
}

void AGameForgeCardTable::BeginPlay()
{
	Super::BeginPlay();
	EntityId = UGameForgeEventLibrary::ResolveEntityId(this, EntityId);

	GameForgeVisuals::Tint(TableMesh, FLinearColor(0.16f, 0.32f, 0.22f, 1.f));

	if (MatchComponent)
	{
		MatchComponent->DeckSize = DeckSize;
		MatchComponent->HandSize = (StartingHandSize > 0 && HandSize == 4 && StartingHandSize != 4) ? StartingHandSize : HandSize;
		MatchComponent->StartingHandSize = MatchComponent->HandSize;
		MatchComponent->MaxHandSize = MaxHandSize;
		MatchComponent->EnergyPerTurn = (BaseEnergyPerTurn > 0 && EnergyPerTurn == 3 && BaseEnergyPerTurn != 3) ? BaseEnergyPerTurn : EnergyPerTurn;
		MatchComponent->BaseEnergyPerTurn = MatchComponent->EnergyPerTurn;
		MatchComponent->PlayerBaseHealth = PlayerBaseHealth;
		MatchComponent->OpponentBaseHealth = OpponentBaseHealth;
		MatchComponent->LaneCount = FMath::Clamp(LaneCount, 1, 8);
		MatchComponent->InitializeMatch(2026);
	}

	const int32 NumLanes = MatchComponent ? FMath::Clamp(MatchComponent->LaneCount, 1, 8) : 3;
	const float LaneSpacing = 130.f;
	const float HalfSpan = (NumLanes - 1) * LaneSpacing * 0.5f;

	PlayerLaneSlotVisuals.Reset();
	OpponentLaneSlotVisuals.Reset();
	for (int32 Lane = 0; Lane < NumLanes; ++Lane)
	{
		const float Y = Lane * LaneSpacing - HalfSpan;

		UStaticMeshComponent* PSlot = NewObject<UStaticMeshComponent>(this, *FString::Printf(TEXT("PlayerSlot_%d"), Lane));
		if (PSlot)
		{
			PSlot->RegisterComponent();
			PSlot->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepWorldTransform);
			PSlot->SetWorldLocation(GetActorLocation() + FVector(-85.f, Y, 18.f));
			PSlot->SetWorldScale3D(FVector(0.95f, 0.7f, 0.08f));
			PSlot->SetCollisionProfileName(TEXT("NoCollision"));
			GameForgeVisuals::SetBasicShape(PSlot, TEXT("Cube"));
			GameForgeVisuals::Tint(PSlot, FLinearColor(0.2f, 0.45f, 0.85f, 1.f));
			PlayerLaneSlotVisuals.Add(PSlot);
		}

		UStaticMeshComponent* OSlot = NewObject<UStaticMeshComponent>(this, *FString::Printf(TEXT("OpponentSlot_%d"), Lane));
		if (OSlot)
		{
			OSlot->RegisterComponent();
			OSlot->AttachToComponent(RootComponent, FAttachmentTransformRules::KeepWorldTransform);
			OSlot->SetWorldLocation(GetActorLocation() + FVector(85.f, Y, 18.f));
			OSlot->SetWorldScale3D(FVector(0.95f, 0.7f, 0.08f));
			OSlot->SetCollisionProfileName(TEXT("NoCollision"));
			GameForgeVisuals::SetBasicShape(OSlot, TEXT("Cube"));
			GameForgeVisuals::Tint(OSlot, FLinearColor(0.85f, 0.25f, 0.2f, 1.f));
			OpponentLaneSlotVisuals.Add(OSlot);
		}
	}
	RefreshSlotVisuals();
}

void AGameForgeCardTable::RefreshSlotVisuals()
{
	if (!MatchComponent)
	{
		return;
	}
	for (int32 i = 0; i < PlayerLaneSlotVisuals.Num(); ++i)
	{
		if (UStaticMeshComponent* S = PlayerLaneSlotVisuals[i])
		{
			const bool bOccupied = MatchComponent->PlayerLanes.IsValidIndex(i) && MatchComponent->PlayerLanes[i].CardId > 0;
			S->SetWorldScale3D(bOccupied ? FVector(0.95f, 0.7f, 0.25f) : FVector(0.95f, 0.7f, 0.06f));
			GameForgeVisuals::Tint(S, bOccupied
				? FLinearColor(0.25f, 0.75f, 1.0f, 1.f)
				: FLinearColor(0.18f, 0.30f, 0.45f, 1.f));
		}
	}
	for (int32 i = 0; i < OpponentLaneSlotVisuals.Num(); ++i)
	{
		if (UStaticMeshComponent* S = OpponentLaneSlotVisuals[i])
		{
			const bool bOccupied = MatchComponent->OpponentLanes.IsValidIndex(i) && MatchComponent->OpponentLanes[i].CardId > 0;
			S->SetWorldScale3D(bOccupied ? FVector(0.95f, 0.7f, 0.25f) : FVector(0.95f, 0.7f, 0.06f));
			GameForgeVisuals::Tint(S, bOccupied
				? FLinearColor(1.0f, 0.35f, 0.25f, 1.f)
				: FLinearColor(0.45f, 0.20f, 0.20f, 1.f));
		}
	}
}

void AGameForgeCardTable::OnSelected(APlayerController* PC)
{
	if (!MatchComponent)
	{
		return;
	}

	const int32 NumLanes = FMath::Max(1, MatchComponent->PlayerLanes.Num());
	// Play as many affordable cards from Hand as possible into open/available lanes, then resolve the turn
	bool bPlayedAny = false;
	for (int32 Lane = 0; Lane < NumLanes; ++Lane)
	{
		for (int32 CardIdx = 0; CardIdx < MatchComponent->Hand.Num(); ++CardIdx)
		{
			if (MatchComponent->Hand[CardIdx].Cost <= MatchComponent->CurrentEnergy)
			{
				if (MatchComponent->PlayerLanes[Lane].CardId == 0 || bPlayedAny == false)
				{
					MatchComponent->PlayCard(CardIdx, Lane);
					bPlayedAny = true;
					break;
				}
			}
		}
	}
	MatchComponent->EndTurn();
}
