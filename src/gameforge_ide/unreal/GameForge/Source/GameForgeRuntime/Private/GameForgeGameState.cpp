#include "GameForgeGameState.h"
#include "GameForgeEvents.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"

AGameForgeGameState::AGameForgeGameState()
{
	bReplicates = true;
}

void AGameForgeGameState::BeginPlay()
{
	Super::BeginPlay();
	if (UWorld* W = GetWorld())
	{
		GameStartTime = W->GetTimeSeconds();
	}
}

void AGameForgeGameState::SetStatBounds(FName StatName, float MinVal, float MaxVal, bool bMin, bool bMax)
{
	FGameForgeStatBounds Bounds;
	Bounds.MinValue = MinVal;
	Bounds.MaxValue = MaxVal;
	Bounds.bHasMin = bMin;
	Bounds.bHasMax = bMax;
	StatBounds.Add(StatName, Bounds);
}

float AGameForgeGameState::GetStat(FName StatName) const
{
	FString NameStr = StatName.ToString();

	// Derived stat: game.time_s
	if (StatName == FName(TEXT("game.time_s")))
	{
		if (UWorld* W = GetWorld())
		{
			return static_cast<float>(W->GetTimeSeconds() - GameStartTime);
		}
		return 0.f;
	}

	// Derived stat: entity.<id>.collected
	if (NameStr.StartsWith(TEXT("entity.")) && NameStr.EndsWith(TEXT(".collected")))
	{
		TArray<FString> Parts;
		NameStr.ParseIntoArray(Parts, TEXT("."));
		if (Parts.Num() == 3)
		{
			FName EntityId(*Parts[1]);
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				return static_cast<float>(Bus->Count(FName(TEXT("pickup.collected")), EntityId));
			}
		}
		return 0.f;
	}

	// Derived stat: entity.<id>.killed
	if (NameStr.StartsWith(TEXT("entity.")) && NameStr.EndsWith(TEXT(".killed")))
	{
		TArray<FString> Parts;
		NameStr.ParseIntoArray(Parts, TEXT("."));
		if (Parts.Num() == 3)
		{
			FName EntityId(*Parts[1]);
			if (UGameForgeEventBus* Bus = UGameForgeEventBus::Get(this))
			{
				return static_cast<float>(Bus->Count(FName(TEXT("enemy.killed")), EntityId));
			}
		}
		return 0.f;
	}

	// Derived stat: entity.<id>.remaining
	if (NameStr.StartsWith(TEXT("entity.")) && NameStr.EndsWith(TEXT(".remaining")))
	{
		TArray<FString> Parts;
		NameStr.ParseIntoArray(Parts, TEXT("."));
		if (Parts.Num() == 3)
		{
			FName TagName(*(FString(TEXT("GF_E_")) + Parts[1]));
			TArray<AActor*> TaggedActors;
			UGameplayStatics::GetAllActorsWithTag(this, TagName, TaggedActors);
			int32 Remaining = 0;
			for (AActor* Act : TaggedActors)
			{
				if (Act && !Act->IsHidden() && Act->GetLifeSpan() <= 0.0f)
				{
					Remaining++;
				}
			}
			return static_cast<float>(Remaining);
		}
		return 0.f;
	}

	// Stored stat
	if (const float* Found = Stats.Find(StatName))
	{
		return *Found;
	}
	if (const int32* FoundCounter = Counters.Find(StatName))
	{
		return static_cast<float>(*FoundCounter);
	}

	return 0.f;
}

void AGameForgeGameState::SetStat(FName StatName, float Value)
{
	float ClampedVal = Value;
	if (const FGameForgeStatBounds* Bounds = StatBounds.Find(StatName))
	{
		if (Bounds->bHasMin)
		{
			ClampedVal = FMath::Max(ClampedVal, Bounds->MinValue);
		}
		if (Bounds->bHasMax)
		{
			ClampedVal = FMath::Min(ClampedVal, Bounds->MaxValue);
		}
	}

	const float* Existing = Stats.Find(StatName);
	if (!Existing || !FMath::IsNearlyEqual(*Existing, ClampedVal, 1e-4f))
	{
		Stats.Add(StatName, ClampedVal);
		if (StatName.ToString().StartsWith(TEXT("game.counter.")))
		{
			Counters.Add(StatName, FMath::RoundToInt(ClampedVal));
		}
		OnStatChanged.Broadcast(StatName, ClampedVal);
	}
}

void AGameForgeGameState::AddStat(FName StatName, float Delta)
{
	float Current = GetStat(StatName);
	SetStat(StatName, Current + Delta);
}

int32 AGameForgeGameState::IncrementCounter(FName CounterName, int32 Delta)
{
	const int32 Next = GetCounter(CounterName) + Delta;
	Counters.Add(CounterName, Next);
	SetStat(CounterName, static_cast<float>(Next));
	return Next;
}

int32 AGameForgeGameState::GetCounter(FName CounterName) const
{
	if (const int32* Found = Counters.Find(CounterName))
	{
		return *Found;
	}
	if (const float* FoundStat = Stats.Find(CounterName))
	{
		return FMath::RoundToInt(*FoundStat);
	}
	return 0;
}
