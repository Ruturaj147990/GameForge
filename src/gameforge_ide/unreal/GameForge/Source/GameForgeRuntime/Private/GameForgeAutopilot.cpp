#include "GameForgeAutopilot.h"

#include "Engine/LocalPlayer.h"
#include "EnhancedInputSubsystems.h"
#include "GameForgePlayer.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PawnMovementComponent.h"
#include "InputActionValue.h"
#include "NavigationPath.h"
#include "NavigationSystem.h"

UGameForgeAutopilotComponent::UGameForgeAutopilotComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
}

void UGameForgeAutopilotComponent::Finish(const FString& Result)
{
	bActive = false;
	Current.Result = Result;
	CompletedLegs.Add(Current);
}

bool UGameForgeAutopilotComponent::MoveTo(const FVector& Target, const FString& Label, float AcceptRadiusCm, float TimeoutS)
{
	APawn* Pawn = Cast<APawn>(GetOwner());
	if (!Pawn)
	{
		Current.Target = Label;
		Finish(TEXT("NO_CONTROLLER"));
		return false;
	}

	UNavigationPath* NavPath = UNavigationSystemV1::FindPathToLocationSynchronously(GetWorld(), Pawn->GetActorLocation(), Target, Pawn);
	if (!NavPath || !NavPath->IsValid() || NavPath->PathPoints.Num() == 0)
	{
		Current.Target = Label;
		Finish(TEXT("NO_PATH"));
		return false;
	}

	Path = NavPath->PathPoints;
	PathIndex = 0;
	Accept = AcceptRadiusCm;
	Timeout = TimeoutS;

	Current.Target = Label;
	Current.DistanceCm = 0.f;
	Current.Seconds = 0.f;
	Current.MaxStepCm = 0.f;
	Current.Result = TEXT("");

	LastPos = Pawn->GetActorLocation();
	StuckAnchor = LastPos;
	StuckTimer = 0.f;
	bActive = true;
	return true;
}

void UGameForgeAutopilotComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!bActive)
	{
		return;
	}

	APawn* Pawn = Cast<APawn>(GetOwner());
	AGameForgePlayerController* PC = Pawn ? Cast<AGameForgePlayerController>(Pawn->GetController()) : nullptr;
	if (!Pawn || !PC)
	{
		Finish(TEXT("NO_CONTROLLER"));
		return;
	}

	const FVector Pos = Pawn->GetActorLocation();
	const float Step = FVector::Dist2D(Pos, LastPos);
	Current.DistanceCm += Step;
	Current.MaxStepCm = FMath::Max(Current.MaxStepCm, Step);
	Current.Seconds += DeltaTime;
	LastPos = Pos;

	// 3. Teleport detection
	const float MaxSpeed = Pawn->GetMovementComponent() ? Pawn->GetMovementComponent()->GetMaxSpeed() : 600.f;
	if (Step > (MaxSpeed * DeltaTime * 1.5f + 50.f))
	{
		Finish(TEXT("TELEPORT_SUSPECTED"));
		return;
	}

	// 4. Stuck detection
	if (FVector::Dist2D(Pos, StuckAnchor) > 50.f)
	{
		StuckAnchor = Pos;
		StuckTimer = 0.f;
	}
	else
	{
		StuckTimer += DeltaTime;
	}
	if (StuckTimer > 3.0f)
	{
		Finish(TEXT("STUCK"));
		return;
	}

	// 5. Timeout
	if (Current.Seconds > Timeout)
	{
		Finish(TEXT("TIMEOUT"));
		return;
	}

	// 6. Advance PathIndex while the next point is within Accept (2D)
	while (PathIndex < Path.Num() && FVector::Dist2D(Pos, Path[PathIndex]) <= Accept)
	{
		PathIndex++;
	}
	if (PathIndex >= Path.Num())
	{
		Finish(TEXT("ARRIVED"));
		return;
	}

	// 7. Inject movement input
	const FVector Dir = (Path[PathIndex] - Pos).GetSafeNormal2D();
	const FRotator Yaw(0.f, PC->GetControlRotation().Yaw, 0.f);
	const FVector RightAxis = FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y);
	const FVector ForwardAxis = FRotationMatrix(Yaw).GetUnitAxis(EAxis::X);
	const FVector2D Input(FVector::DotProduct(Dir, RightAxis), FVector::DotProduct(Dir, ForwardAxis));

	if (ULocalPlayer* LP = PC->GetLocalPlayer())
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
		{
			if (UInputAction* MoveAct = PC->FindAction(TEXT("IA_Move")))
			{
				static const TArray<UInputModifier*> NoModifiers;
				static const TArray<UInputTrigger*> NoTriggers;
				Subsystem->InjectInputForAction(MoveAct, FInputActionValue(Input), NoModifiers, NoTriggers);
			}
		}
	}
}
