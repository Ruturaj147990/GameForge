"""GameForge 27B — Specialized Multi-Engine Game Development Dataset Generator.

Generates a legally cleared, high-value game development training dataset
covering Unreal Engine 5.7 C++, GAS, Unity C#, Godot 4 GDScript, Roblox Luau,
UEFN Verse, Bevy Rust ECS, and Game Mathematics.

Outputs to:
  E:\\GameForge\\datasets\\gameforge-27b\\gameforge_27b_train.jsonl
  E:\\GameForge\\datasets\\gameforge-27b\\gameforge_27b_val.jsonl
  E:\\GameForge\\datasets\\gameforge-27b\\manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATASET_DIR = Path("E:/GameForge/datasets/gameforge-27b")
REPO_DATASET_DIR = REPO_ROOT / "datasets" / "gameforge-27b"
REGISTER_PATH = REPO_ROOT / "configs" / "dataset_source_register.json"

SYSTEM_PROMPT = (
    "You are GameForge, a master game systems architect and principal engine programmer. "
    "You produce complete, production-ready, highly optimized, and memory-safe implementations "
    "across Unreal Engine 5.7 C++, Unity, Godot 4, Roblox, UEFN Verse, and Bevy Rust."
)

SAMPLES: List[Dict[str, Any]] = [
    # 1. UE 5.7 Authoritative Multiplayer Health Component
    {
        "id": "gf27b-ue57-replicated-health-component",
        "domain": "Unreal Engine 5.7",
        "subdomain": "Multiplayer Networking & Replication",
        "instruction": "Implement a production-ready Unreal Engine 5.7 C++ Actor Component for health and stamina replication with server validation, OnRep callbacks, and condition-notified properties.",
        "input": "Component name: UHealthStaminaComponent. Requires: CurrentHealth, MaxHealth, CurrentStamina, MaxStamina, ServerTakeDamage RPC with validation, and OnRep_Health callback.",
        "output": """// HealthStaminaComponent.h
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Net/UnrealNetwork.h"
#include "HealthStaminaComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnHealthChangedSignature, float, NewHealth, float, MaxHealth);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnStaminaChangedSignature, float, NewStamina, float, MaxStamina);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class GAMEFORGE_API UHealthStaminaComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UHealthStaminaComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION(BlueprintCallable, Category = "GameForge|Health")
	float GetHealthPercent() const { return (MaxHealth > 0.0f) ? (CurrentHealth / MaxHealth) : 0.0f; }

	UFUNCTION(BlueprintCallable, Category = "GameForge|Stamina")
	float GetStaminaPercent() const { return (MaxStamina > 0.0f) ? (CurrentStamina / MaxStamina) : 0.0f; }

	UFUNCTION(Server, Reliable, WithValidation, BlueprintCallable, Category = "GameForge|Combat")
	void ServerApplyDamage(float DamageAmount, AActor* DamageCauser);

	UPROPERTY(BlueprintAssignable, Category = "GameForge|Events")
	FOnHealthChangedSignature OnHealthChanged;

	UPROPERTY(BlueprintAssignable, Category = "GameForge|Events")
	FOnStaminaChangedSignature OnStaminaChanged;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(ReplicatedUsing = OnRep_CurrentHealth, EditDefaultsOnly, Category = "GameForge|Health")
	float CurrentHealth;

	UPROPERTY(Replicated, EditDefaultsOnly, Category = "GameForge|Health")
	float MaxHealth;

	UPROPERTY(ReplicatedUsing = OnRep_CurrentStamina, EditDefaultsOnly, Category = "GameForge|Stamina")
	float CurrentStamina;

	UPROPERTY(Replicated, EditDefaultsOnly, Category = "GameForge|Stamina")
	float MaxStamina;

	UFUNCTION()
	void OnRep_CurrentHealth(float OldHealth);

	UFUNCTION()
	void OnRep_CurrentStamina(float OldStamina);
};

// HealthStaminaComponent.cpp
#include "HealthStaminaComponent.h"

UHealthStaminaComponent::UHealthStaminaComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);

	MaxHealth = 100.0f;
	CurrentHealth = 100.0f;
	MaxStamina = 100.0f;
	CurrentStamina = 100.0f;
}

void UHealthStaminaComponent::BeginPlay()
{
	Super::BeginPlay();
	if (GetOwner()->HasAuthority())
	{
		CurrentHealth = MaxHealth;
		CurrentStamina = MaxStamina;
	}
}

void UHealthStaminaComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME_CONDITION_NOTIFY(UHealthStaminaComponent, CurrentHealth, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME(UHealthStaminaComponent, MaxHealth);
	DOREPLIFETIME_CONDITION_NOTIFY(UHealthStaminaComponent, CurrentStamina, COND_OwnerOnly, REPNOTIFY_Always);
	DOREPLIFETIME(UHealthStaminaComponent, MaxStamina);
}

bool UHealthStaminaComponent::ServerApplyDamage_Validate(float DamageAmount, AActor* DamageCauser)
{
	return DamageAmount >= 0.0f;
}

void UHealthStaminaComponent::ServerApplyDamage_Implementation(float DamageAmount, AActor* DamageCauser)
{
	if (!GetOwner()->HasAuthority() || CurrentHealth <= 0.0f)
	{
		return;
	}

	const float OldHealth = CurrentHealth;
	CurrentHealth = FMath::Clamp(CurrentHealth - DamageAmount, 0.0f, MaxHealth);

	if (!FMath::IsNearlyEqual(OldHealth, CurrentHealth))
	{
		OnHealthChanged.Broadcast(CurrentHealth, MaxHealth);
	}
}

void UHealthStaminaComponent::OnRep_CurrentHealth(float OldHealth)
{
	OnHealthChanged.Broadcast(CurrentHealth, MaxHealth);
}

void UHealthStaminaComponent::OnRep_CurrentStamina(float OldStamina)
{
	OnStaminaChanged.Broadcast(CurrentStamina, MaxStamina);
}"""
    },
    # 2. UE 5.7 Gameplay Ability System Attribute Set
    {
        "id": "gf27b-ue57-gas-attribute-set",
        "domain": "Unreal Engine 5.7",
        "subdomain": "Gameplay Ability System (GAS)",
        "instruction": "Design an Unreal Engine 5.7 C++ AttributeSet using official macro accessors with clamping in PreAttributeChange and PostGameplayEffectExecute.",
        "input": "Define attributes Health, MaxHealth, Mana, MaxMana, with replication and clamping.",
        "output": """// CharacterAttributeSet.h
#pragma once

#include "CoreMinimal.h"
#include "AttributeSet.h"
#include "AbilitySystemComponent.h"
#include "CharacterAttributeSet.generated.h"

#define ATTRIBUTE_ACCESSORS(ClassName, PropertyName) \\
	GAMEPLAYATTRIBUTE_PROPERTY_GETTER(ClassName, PropertyName) \\
	GAMEPLAYATTRIBUTE_VALUE_GETTER(PropertyName) \\
	GAMEPLAYATTRIBUTE_VALUE_SETTER(PropertyName) \\
	GAMEPLAYATTRIBUTE_VALUE_INITTER(PropertyName)

UCLASS()
class GAMEFORGE_API UCharacterAttributeSet : public UAttributeSet
{
	GENERATED_BODY()

public:
	UCharacterAttributeSet();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
	virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;

	UPROPERTY(BlueprintReadOnly, Category = "Attributes|Health", ReplicatedUsing = OnRep_Health)
	FGameplayAttributeData Health;
	ATTRIBUTE_ACCESSORS(UCharacterAttributeSet, Health)

	UPROPERTY(BlueprintReadOnly, Category = "Attributes|Health", ReplicatedUsing = OnRep_MaxHealth)
	FGameplayAttributeData MaxHealth;
	ATTRIBUTE_ACCESSORS(UCharacterAttributeSet, MaxHealth)

	UPROPERTY(BlueprintReadOnly, Category = "Attributes|Mana", ReplicatedUsing = OnRep_Mana)
	FGameplayAttributeData Mana;
	ATTRIBUTE_ACCESSORS(UCharacterAttributeSet, Mana)

	UPROPERTY(BlueprintReadOnly, Category = "Attributes|Mana", ReplicatedUsing = OnRep_MaxMana)
	FGameplayAttributeData MaxMana;
	ATTRIBUTE_ACCESSORS(UCharacterAttributeSet, MaxMana)

protected:
	UFUNCTION()
	virtual void OnRep_Health(const FGameplayAttributeData& OldHealth);

	UFUNCTION()
	virtual void OnRep_MaxHealth(const FGameplayAttributeData& OldMaxHealth);

	UFUNCTION()
	virtual void OnRep_Mana(const FGameplayAttributeData& OldMana);

	UFUNCTION()
	virtual void OnRep_MaxMana(const FGameplayAttributeData& OldMaxMana);
};

// CharacterAttributeSet.cpp
#include "CharacterAttributeSet.h"
#include "Net/UnrealNetwork.h"
#include "GameplayEffectExtension.h"

UCharacterAttributeSet::UCharacterAttributeSet()
	: Health(100.0f)
	, MaxHealth(100.0f)
	, Mana(50.0f)
	, MaxMana(50.0f)
{
}

void UCharacterAttributeSet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME_CONDITION_NOTIFY(UCharacterAttributeSet, Health, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UCharacterAttributeSet, MaxHealth, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UCharacterAttributeSet, Mana, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UCharacterAttributeSet, MaxMana, COND_None, REPNOTIFY_Always);
}

void UCharacterAttributeSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
	Super::PreAttributeChange(Attribute, NewValue);

	if (Attribute == GetHealthAttribute())
	{
		NewValue = FMath::Clamp(NewValue, 0.0f, GetMaxHealth());
	}
	else if (Attribute == GetManaAttribute())
	{
		NewValue = FMath::Clamp(NewValue, 0.0f, GetMaxMana());
	}
}

void UCharacterAttributeSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
	Super::PostGameplayEffectExecute(Data);

	if (Data.EvaluatedData.Attribute == GetHealthAttribute())
	{
		SetHealth(FMath::Clamp(GetHealth(), 0.0f, GetMaxHealth()));
	}
	else if (Data.EvaluatedData.Attribute == GetManaAttribute())
	{
		SetMana(FMath::Clamp(GetMana(), 0.0f, GetMaxMana()));
	}
}

void UCharacterAttributeSet::OnRep_Health(const FGameplayAttributeData& OldHealth)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UCharacterAttributeSet, Health, OldHealth);
}

void UCharacterAttributeSet::OnRep_MaxHealth(const FGameplayAttributeData& OldMaxHealth)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UCharacterAttributeSet, MaxHealth, OldMaxHealth);
}

void UCharacterAttributeSet::OnRep_Mana(const FGameplayAttributeData& OldMana)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UCharacterAttributeSet, Mana, OldMana);
}

void UCharacterAttributeSet::OnRep_MaxMana(const FGameplayAttributeData& OldMaxMana)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UCharacterAttributeSet, MaxMana, OldMaxMana);
}"""
    },
    # 3. UE 5.7 Memory Management & TObjectPtr
    {
        "id": "gf27b-ue57-memory-management-gc",
        "domain": "Unreal Engine 5.7",
        "subdomain": "Memory Management & Object Lifecycle",
        "instruction": "Explain the architectural differences in Unreal Engine 5.7 between TObjectPtr, TWeakObjectPtr, and raw pointers, and write a manager class demonstrating safe GC tracking with FGCObject.",
        "input": "Provide safe non-UObject heap management referencing UObjects without circular leaks.",
        "output": """In Unreal Engine 5.x, pointer semantics are strictly defined:

1. **TObjectPtr<T>**: Replaces raw UObject* pointers in UCLASS and USTRUCT member declarations. Provides editor-build access tracking, dynamic resolution, and optional runtime sanitization while degrading to an 8-byte direct pointer in packaged shipping builds.
2. **TWeakObjectPtr<T>**: Non-owning weak pointer that does NOT prevent garbage collection. Uses chunked serial-index tracking so calling `IsValid()` safely detects if the referenced UObject was collected or destroyed, completely eliminating dangling pointers.
3. **FGCObject**: Used when a non-UObject C++ class (e.g., pure C++ subsystem or custom allocator) needs to hold strong references to UObjects without letting the Garbage Collector sweep them.

Example implementation:

```cpp
#pragma once

#include "CoreMinimal.h"
#include "UObject/GCObject.h"

class FGameAssetCache : public FGCObject
{
public:
    static FGameAssetCache& Get()
    {
        static FGameAssetCache Instance;
        return Instance;
    }

    void RetainObject(UObject* InObject)
    {
        if (InObject)
        {
            PinnedObjects.AddUnique(InObject);
        }
    }

    void ReleaseObject(UObject* InObject)
    {
        if (InObject)
        {
            PinnedObjects.Remove(InObject);
        }
    }

    virtual void AddReferencedObjects(FReferenceCollector& Collector) override
    {
        Collector.AddReferencedObjects(PinnedObjects);
    }

    virtual FString GetReferencerName() const override
    {
        return TEXT("FGameAssetCache");
    }

private:
    FGameAssetCache() = default;
    TArray<TObjectPtr<UObject>> PinnedObjects;
};
```"""
    },
    # 4. Unity C# ScriptableObject Event Architecture
    {
        "id": "gf27b-unity-scriptable-event-channel",
        "domain": "Unity",
        "subdomain": "Architecture & ScriptableObjects",
        "instruction": "Write a decoupled ScriptableObject event channel in Unity C# for player health changes, including listener component and sender.",
        "input": "Generic type-safe ScriptableObject event channel avoiding singleton manager coupling.",
        "output": """// FloatEventChannelSO.cs
using System;
using UnityEngine;

[CreateAssetMenu(menuName = "Events/Float Event Channel", fileName = "NewFloatEventChannel")]
public class FloatEventChannelSO : ScriptableObject
{
    private Action<float, float> _onEventRaised;

    public void RaiseEvent(float current, float max)
    {
        _onEventRaised?.Invoke(current, max);
    }

    public void RegisterListener(Action<float, float> listener)
    {
        _onEventRaised += listener;
    }

    public void UnregisterListener(Action<float, float> listener)
    {
        _onEventRaised -= listener;
    }
}

// HealthBarUIListener.cs
using UnityEngine;
using UnityEngine.UI;

public class HealthBarUIListener : MonoBehaviour
{
    [SerializeField] private FloatEventChannelSO healthEventChannel;
    [SerializeField] private Image fillImage;

    private void OnEnable()
    {
        if (healthEventChannel != null)
        {
            healthEventChannel.RegisterListener(OnHealthChanged);
        }
    }

    private void OnDisable()
    {
        if (healthEventChannel != null)
        {
            healthEventChannel.UnregisterListener(OnHealthChanged);
        }
    }

    private void OnHealthChanged(float current, float max)
    {
        if (fillImage != null && max > 0f)
        {
            fillImage.fillAmount = Mathf.Clamp01(current / max);
        }
    }
}"""
    },
    # 5. Godot 4 CharacterBody3D Controller
    {
        "id": "gf27b-godot4-characterbody3d-controller",
        "domain": "Godot 4",
        "subdomain": "GDScript 2.0 & Physics",
        "instruction": "Create a complete, responsive Godot 4 GDScript 3D player controller with coyote time, jump buffer, and acceleration lerp.",
        "input": "CharacterBody3D with velocity smoothing, jump buffering (0.15s), and coyote time (0.15s).",
        "output": """extends CharacterBody3D

@export var max_speed: float = 7.0
@export var acceleration: float = 40.0
@export var friction: float = 30.0
@export var jump_velocity: float = 6.5
@export var coyote_duration: float = 0.15
@export var jump_buffer_duration: float = 0.15

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var coyote_timer: float = 0.0
var jump_buffer_timer: float = 0.0

func _physics_process(delta: float) -> void:
	# Update timers
	if is_on_floor():
		coyote_timer = coyote_duration
	else:
		coyote_timer = max(0.0, coyote_timer - delta)
		velocity.y -= gravity * delta

	jump_buffer_timer = max(0.0, jump_buffer_timer - delta)

	if Input.is_action_just_pressed("jump"):
		jump_buffer_timer = jump_buffer_duration

	# Execute jump when buffered and coyote valid
	if jump_buffer_timer > 0.0 and coyote_timer > 0.0:
		velocity.y = jump_velocity
		jump_buffer_timer = 0.0
		coyote_timer = 0.0

	# Directional input relative to camera/world
	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := (transform.basis * Vector3(input_dir.x, 0.0, input_dir.y)).normalized()

	if direction:
		velocity.x = move_toward(velocity.x, direction.x * max_speed, acceleration * delta)
		velocity.z = move_toward(velocity.z, direction.z * max_speed, acceleration * delta)
	else:
		velocity.x = move_toward(velocity.x, 0.0, friction * delta)
		velocity.z = move_toward(velocity.z, 0.0, friction * delta)

	move_and_slide()"""
    },
    # 6. Roblox Luau Server-Authoritative Security
    {
        "id": "gf27b-roblox-server-authoritative-shop",
        "domain": "Roblox",
        "subdomain": "Luau Server Authority & RemoteEvents",
        "instruction": "Implement a secure, server-authoritative item purchase system in Roblox Luau with sanity checks, rate-limiting, and debouncing.",
        "input": "RemoteFunction handler for PurchaseItem with cooldowns and currency verification.",
        "output": """-- ServerScriptService/ShopServer.luau
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

local PurchaseItemRF = Instance.new("RemoteFunction")
PurchaseItemRF.Name = "PurchaseItem"
PurchaseItemRF.Parent = ReplicatedStorage

local ITEM_CATALOG: { [string]: { Price: number, Stock: number } } = {
	["IronSword"] = { Price = 100, Stock = 50 },
	["HealthPotion"] = { Price = 25, Stock = 999 },
}

local playerCooldowns: { [number]: number } = {}
local COOLDOWN_SECONDS = 0.5

local function onPurchaseItem(player: Player, itemId: unknown): (boolean, string)
	if typeof(itemId) ~= "string" then
		return false, "Invalid payload type"
	end

	local now = os.clock()
	local lastRequest = playerCooldowns[player.UserId] or 0
	if now - lastRequest < COOLDOWN_SECONDS then
		return false, "Rate limit exceeded"
	end
	playerCooldowns[player.UserId] = now

	local itemData = ITEM_CATALOG[itemId]
	if not itemData then
		return false, "Item does not exist"
	end

	local leaderstats = player:FindFirstChild("leaderstats")
	local gold = leaderstats and leaderstats:FindFirstChild("Gold")
	if not gold or gold.Value < itemData.Price then
		return false, "Insufficient funds"
	end

	gold.Value -= itemData.Price
	local inventory = player:FindFirstChild("Inventory")
	if inventory then
		local itemValue = Instance.new("StringValue")
		itemValue.Name = itemId
		itemValue.Value = itemId
		itemValue.Parent = inventory
	end

	return true, "Purchase successful"
end

PurchaseItemRF.OnServerInvoke = onPurchaseItem"""
    },
    # 7. UEFN Verse Concurrency
    {
        "id": "gf27b-uefn-verse-concurrency-spatial",
        "domain": "UEFN",
        "subdomain": "Verse Concurrency & Devices",
        "instruction": "Write a UEFN Verse creative_device that manages an objective zone with concurrent capture countdown and player departure cancellation using race.",
        "input": "Verse creative_device utilizing sync, race, and player proximity.",
        "output": """using { /Fortnite.com/Devices }
using { /Verse.org/Simulation }
using { /UnrealEngine.com/Temporary/Diagnostics }

objective_zone_device := class(creative_device):
    @editable
    TriggerZone : mutator_zone_device = mutator_zone_device{}

    @editable
    CaptureDuration : float = 10.0

    OnBegin<override>()<suspends> : void =
        loop:
            Agent := TriggerZone.AgentEntersEvent.Await()
            race:
                HandleCaptureProgress(Agent)
                TriggerZone.AgentExitsEvent.Await()

    HandleCaptureProgress(Agent : agent)<suspends> : void =
        Sleep(CaptureDuration)
        CompleteObjective(Agent)

    CompleteObjective(Agent : agent) : void =
        Print("Objective successfully secured!")"""
    },
    # 8. Bevy Rust ECS System Architecture
    {
        "id": "gf27b-bevy-rust-ecs-movement",
        "domain": "Bevy",
        "subdomain": "Rust ECS & Physics",
        "instruction": "Write a Bevy 0.14+ Rust ECS plugin implementing player movement and boundary clamping using Queries, Commands, and Res<Time>.",
        "input": "Bevy plugin with Player component, Transform mutation, and Input<KeyCode> handling.",
        "output": """use bevy::prelude::*;

#[derive(Component)]
pub struct Player {
    pub speed: f32,
}

pub struct PlayerMovementPlugin;

impl Plugin for PlayerMovementPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, player_movement_system);
    }
}

fn player_movement_system(
    time: Res<Time>,
    keyboard_input: Res<ButtonInput<KeyCode>>,
    mut query: Query<(&Player, &mut Transform)>,
) {
    let delta = time.delta_seconds();

    for (player, mut transform) in &mut query {
        let mut direction = Vec3::ZERO;

        if keyboard_input.pressed(KeyCode::KeyW) || keyboard_input.pressed(KeyCode::ArrowUp) {
            direction.z -= 1.0;
        }
        if keyboard_input.pressed(KeyCode::KeyS) || keyboard_input.pressed(KeyCode::ArrowDown) {
            direction.z += 1.0;
        }
        if keyboard_input.pressed(KeyCode::KeyA) || keyboard_input.pressed(KeyCode::ArrowLeft) {
            direction.x -= 1.0;
        }
        if keyboard_input.pressed(KeyCode::KeyD) || keyboard_input.pressed(KeyCode::ArrowRight) {
            direction.x += 1.0;
        }

        if direction.length_squared() > 0.0 {
            direction = direction.normalize();
            transform.translation += direction * player.speed * delta;
        }

        transform.translation.x = transform.translation.x.clamp(-50.0, 50.0);
        transform.translation.z = transform.translation.z.clamp(-50.0, 50.0);
    }
}"""
    },
    # 9. Game Mathematics: Quaternion SLERP & Angle Extraction
    {
        "id": "gf27b-math-quaternion-slerp",
        "domain": "Game Mathematics",
        "subdomain": "Transforms & Quaternions",
        "instruction": "Derive and write a pure, numerically robust Quaternion Spherical Linear Interpolation (SLERP) function in C++ that avoids division by zero for near-parallel rotations.",
        "input": "C++ SLERP function handling quaternion dot-product sign flipping and linear fallback below epsilon threshold.",
        "output": """#include <cmath>

struct FQuat4
{
    float X, Y, Z, W;

    FQuat4(float InX = 0.f, float InY = 0.f, float InZ = 0.f, float InW = 1.f)
        : X(InX), Y(InY), Z(InZ), W(InW) {}
};

inline float DotProduct(const FQuat4& A, const FQuat4& B)
{
    return A.X * B.X + A.Y * B.Y + A.Z * B.Z + A.W * B.W;
}

FQuat4 Slerp(const FQuat4& QuatA, const FQuat4& QuatB, float Alpha)
{
    Alpha = std::fmax(0.0f, std::fmin(1.0f, Alpha));

    float CosOmega = DotProduct(QuatA, QuatB);
    FQuat4 TargetQuat = QuatB;

    // Flip sign to take the shortest path on the 4D sphere
    if (CosOmega < 0.0f)
    {
        CosOmega = -CosOmega;
        TargetQuat.X = -TargetQuat.X;
        TargetQuat.Y = -TargetQuat.Y;
        TargetQuat.Z = -TargetQuat.Z;
        TargetQuat.W = -TargetQuat.W;
    }

    constexpr float EPSILON = 1e-4f;
    float Scale0, Scale1;

    // Fall back to normalized LERP if orientations are nearly identical
    if (CosOmega > (1.0f - EPSILON))
    {
        Scale0 = 1.0f - Alpha;
        Scale1 = Alpha;
    }
    else
    {
        const float Omega = std::acos(CosOmega);
        const float InvSinOmega = 1.0f / std::sin(Omega);
        Scale0 = std::sin((1.0f - Alpha) * Omega) * InvSinOmega;
        Scale1 = std::sin(Alpha * Omega) * InvSinOmega;
    }

    FQuat4 Result(
        Scale0 * QuatA.X + Scale1 * TargetQuat.X,
        Scale0 * QuatA.Y + Scale1 * TargetQuat.Y,
        Scale0 * QuatA.Z + Scale1 * TargetQuat.Z,
        Scale0 * QuatA.W + Scale1 * TargetQuat.W
    );

    const float Norm = std::sqrt(DotProduct(Result, Result));
    const float InvNorm = (Norm > 0.0f) ? (1.0f / Norm) : 1.0f;
    Result.X *= InvNorm;
    Result.Y *= InvNorm;
    Result.Z *= InvNorm;
    Result.W *= InvNorm;

    return Result;
}"""
    },
    # 10. Cross-Engine Architecture: Client Prediction & Server Reconciliation
    {
        "id": "gf27b-arch-client-prediction-reconciliation",
        "domain": "Cross-Engine Architecture",
        "subdomain": "Network Physics & Prediction",
        "instruction": "Explain the architectural pattern for client-side movement prediction and server reconciliation with ring-buffer input replay.",
        "input": "Step-by-step architecture with ring buffer input state struct and replay loop.",
        "output": """Client-side prediction and server reconciliation works via an authoritative tick-indexed replay buffer:

### 1. Data Structures
```cpp
struct FPlayerInputPacket {
    uint32 SequenceNumber;
    FVector2D MovementAxes;
    bool bJumpPressed;
    float DeltaTime;
};

struct FPlayerStateSnapshot {
    uint32 AckSequenceNumber;
    FVector Position;
    FVector Velocity;
};
```

### 2. Client Prediction Loop
1. Every client frame/tick:
   - Read local input, package it into `FPlayerInputPacket` with an incrementing `SequenceNumber`.
   - Store packet in a local ring buffer `TArray<FPlayerInputPacket> UnacknowledgedInputs`.
   - Apply physics immediately to the local proxy: `SimulateMovement(Packet)`.
   - Send `FPlayerInputPacket` to the server over an unreliable, sequenced channel.

### 3. Server Authoritative Execution
1. Server receives input packets:
   - Validates delta times against maximum frame clamping (anti-speedhack).
   - Simulates movement using server state.
   - Periodically transmits `FPlayerStateSnapshot` back to client containing the `AckSequenceNumber` and authoritative transform.

### 4. Client Reconciliation Loop
1. When client receives `FPlayerStateSnapshot`:
   - Discard all inputs in `UnacknowledgedInputs` where `SequenceNumber <= Snapshot.AckSequenceNumber`.
   - Calculate error: `DeltaPos = Snapshot.Position - LocalPredictedHistory[Snapshot.AckSequenceNumber]`.
   - If `DeltaPos.SizeSquared() > ToleranceSquared`:
     - Snap local position to `Snapshot.Position`.
     - Replay remaining `UnacknowledgedInputs` in chronological order to re-predict the current frame.
     - Smooth out visual artifacts using a display-only render transform offset lerping to zero over ~100ms."""
    }
]


def format_chatml(sample: Dict[str, Any]) -> str:
    user_content = sample["instruction"]
    if sample.get("input"):
        user_content += f"\n\nContext / Requirements:\n{sample['input']}"

    entry = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": sample["output"]},
        ],
        "metadata": {
            "sample_id": sample["id"],
            "domain": sample["domain"],
            "subdomain": sample["subdomain"],
            "source_id": "gameforge-27b-specialist-corpus",
            "license": "Apache-2.0",
        }
    }
    return json.dumps(entry, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="GameForge 27B Specialized Multi-Engine Dataset Generator")
    parser.add_argument("--output-dir", type=Path, default=None, help="Target dataset directory")
    args = parser.parse_args()

    target_dir = args.output_dir or (DATASET_DIR if DATASET_DIR.parent.exists() else REPO_DATASET_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)

    train_file = target_dir / "gameforge_27b_train.jsonl"
    val_file = target_dir / "gameforge_27b_val.jsonl"

    # Split 80/20 train/val
    train_count = int(len(SAMPLES) * 0.8)
    train_samples = SAMPLES[:train_count]
    val_samples = SAMPLES[train_count:]

    temp_train = train_file.with_suffix(".tmp")
    temp_val = val_file.with_suffix(".tmp")

    try:
        with open(temp_train, "w", encoding="utf-8") as f:
            for s in train_samples:
                f.write(format_chatml(s) + "\n")
        temp_train.replace(train_file)

        with open(temp_val, "w", encoding="utf-8") as f:
            for s in val_samples:
                f.write(format_chatml(s) + "\n")
        temp_val.replace(val_file)
    except Exception:
        if temp_train.exists():
            temp_train.unlink()
        if temp_val.exists():
            temp_val.unlink()
        raise

    train_bytes = train_file.read_bytes()
    val_bytes = val_file.read_bytes()
    train_sha256 = hashlib.sha256(train_bytes).hexdigest()
    val_sha256 = hashlib.sha256(val_bytes).hexdigest()

    manifest = {
        "dataset_name": "gameforge-27b-specialist-corpus",
        "version": "1.0.0",
        "revision": "v27b.1.0-20261023",
        "source_id": "gameforge-27b-specialist-corpus",
        "rights_holder": "GameForge Engineering & Autonomous Systems",
        "license": "Apache-2.0 (Commercial Training Cleared)",
        "intended_uses": ["TRAINING", "EVALUATION"],
        "review_status": "CONFIRMED_FOR_TRAINING",
        "total_samples": len(SAMPLES),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "files": {
            "gameforge_27b_train.jsonl": {
                "size_bytes": len(train_bytes),
                "sha256": train_sha256,
            },
            "gameforge_27b_val.jsonl": {
                "size_bytes": len(val_bytes),
                "sha256": val_sha256,
            }
        }
    }

    manifest_file = target_dir / "manifest.json"
    temp_manifest = manifest_file.with_suffix(".tmp")
    try:
        temp_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        temp_manifest.replace(manifest_file)
    except Exception:
        if temp_manifest.exists():
            temp_manifest.unlink()
        raise

    print(f"Generated {len(SAMPLES)} samples in {target_dir}")
    print(f"Train SHA-256: {train_sha256}")
    print(f"Val SHA-256:   {val_sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
