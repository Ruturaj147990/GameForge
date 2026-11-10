"""Builds the authoritative 50-task GameForge Engineering Benchmark.

Generates:
  E:\\GameForge\\reports\\gameforge-27b\\baseline_benchmark.json
  <REPO_ROOT>\\reports\\gameforge-27b\\baseline_benchmark.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BENCHMARK_TASKS: List[Dict[str, Any]] = [
    # --- UNREAL ENGINE 5.7 (30 Tasks) ---
    {
        "id": "GF-BENCH-01",
        "engine": "Unreal Engine 5.7",
        "category": "Reflection & Specifiers",
        "prompt": "Write a UCLASS definition in Unreal Engine 5.7 for a custom UGameSettingData asset inheriting from UDataAsset with Category, EditDefaultsOnly, and BlueprintReadOnly properties, plus an EditAnywhere array of gameplay tags.",
        "rubric": ["UCLASS(BlueprintType)", "UDataAsset", "GENERATED_BODY()", "UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category", "FGameplayTagContainer", "TArray"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-02",
        "engine": "Unreal Engine 5.7",
        "category": "Replication & RPCs",
        "prompt": "In Unreal Engine 5.7 C++, how do you declare and implement a server-reliable RPC with validation for requesting an item purchase? Show the header declaration and the _Validate and _Implementation functions.",
        "rubric": ["UFUNCTION(Server, Reliable, WithValidation)", "ServerRequestPurchase_Validate", "ServerRequestPurchase_Implementation", "bool", "GetOwner()->HasAuthority()"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-03",
        "engine": "Unreal Engine 5.7",
        "category": "Networking",
        "prompt": "Write the GetLifetimeReplicatedProps implementation for an AActor with two replicated variables: bIsStunned (replicated to all clients) and PlayerSecretToken (replicated only to the autonomous proxy owner with REPNOTIFY_Always).",
        "rubric": ["GetLifetimeReplicatedProps", "DOREPLIFETIME", "DOREPLIFETIME_CONDITION_NOTIFY", "COND_OwnerOnly", "REPNOTIFY_Always", "Net/UnrealNetwork.h"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-04",
        "engine": "Unreal Engine 5.7",
        "category": "Memory & Pointers",
        "prompt": "Explain the difference between TObjectPtr and raw pointers in Unreal Engine 5.7 C++ member variables, and state what macro or header enables TObjectPtr.",
        "rubric": ["TObjectPtr", "raw pointer", "editor access tracking", "shipping build degradation", "CoreMinimal.h"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-05",
        "engine": "Unreal Engine 5.7",
        "category": "Garbage Collection",
        "prompt": "How do you prevent a non-UObject C++ subsystem from having its referenced UObjects garbage collected in UE 5.7? Provide code inheriting from FGCObject.",
        "rubric": ["FGCObject", "AddReferencedObjects", "FReferenceCollector", "GetReferencerName"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-06",
        "engine": "Unreal Engine 5.7",
        "category": "Gameplay Ability System",
        "prompt": "Write the header definition of a custom UGameplayAbility in UE 5.7 that overrides ActivateAbility, CancelAbility, and EndAbility, specifying instancing policy InstancedPerActor.",
        "rubric": ["UGameplayAbility", "InstancedPerActor", "ActivateAbility", "CancelAbility", "EndAbility", "FGameplayAbilityActivationInfo"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-07",
        "engine": "Unreal Engine 5.7",
        "category": "Gameplay Ability System",
        "prompt": "Demonstrate the standard UE 5.7 macro block (ATTRIBUTE_ACCESSORS) for defining Getter, Setter, and Initter functions on an AttributeSet property.",
        "rubric": ["GAMEPLAYATTRIBUTE_PROPERTY_GETTER", "GAMEPLAYATTRIBUTE_VALUE_GETTER", "GAMEPLAYATTRIBUTE_VALUE_SETTER", "GAMEPLAYATTRIBUTE_VALUE_INITTER"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-08",
        "engine": "Unreal Engine 5.7",
        "category": "Blueprint Interoperability",
        "prompt": "Show how to declare a BlueprintNativeEvent in C++ named CalculateDamageMultiplier that returns a float and takes an FGameplayTag as input, and show the C++ fallback implementation function name.",
        "rubric": ["BlueprintNativeEvent", "CalculateDamageMultiplier", "CalculateDamageMultiplier_Implementation", "FGameplayTag"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-09",
        "engine": "Unreal Engine 5.7",
        "category": "Delegates",
        "prompt": "Declare a dynamic multicast delegate with two parameters (int32 PlayerID, float NewScore) that can be bound in Blueprints, and show the UPROPERTY declaration in a component.",
        "rubric": ["DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams", "BlueprintAssignable", "FOnPlayerScoreChanged", "UPROPERTY"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-10",
        "engine": "Unreal Engine 5.7",
        "category": "Enhanced Input",
        "prompt": "How do you bind an Enhanced Input Action to a character method in UE 5.7? Show the SetupPlayerInputComponent code with UEnhancedInputComponent.",
        "rubric": ["UEnhancedInputComponent", "BindAction", "ETriggerEvent", "UInputAction", "SetupPlayerInputComponent"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-11",
        "engine": "Unreal Engine 5.7",
        "category": "Subsystems",
        "prompt": "Create a UGameInstanceSubsystem in UE 5.7 that initializes persistent player session tokens across level transitions.",
        "rubric": ["UGameInstanceSubsystem", "Initialize", "Deinitialize", "FSubsystemCollectionBase"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-12",
        "engine": "Unreal Engine 5.7",
        "category": "AI & Navigation",
        "prompt": "Implement an AAIController in UE 5.7 that starts a BehaviorTree on Possess and sets up a BlackboardComponent.",
        "rubric": ["AAIController", "OnPossess", "RunBehaviorTree", "UBehaviorTree", "UBlackboardComponent"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-13",
        "engine": "Unreal Engine 5.7",
        "category": "Collision & Physics",
        "prompt": "Write a C++ function in UE 5.7 that performs an asynchronous multi-sphere trace for ECC_Pawn with debug sphere drawing.",
        "rubric": ["SphereTraceMulti", "ECC_Pawn", "FHitResult", "FCollisionQueryParams", "DrawDebugSphere"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-14",
        "engine": "Unreal Engine 5.7",
        "category": "Multiplayer Security",
        "prompt": "What security vulnerability occurs if an inventory drop item RPC takes an item pointer or struct directly from the client? How should it be refactored?",
        "rubric": ["Client spoofing", "server authority", "inventory slot index or GUID lookup", "server validation", "HasAuthority"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-15",
        "engine": "Unreal Engine 5.7",
        "category": "Build System & Modules",
        "prompt": "Write a Build.cs module rule adding GameplayAbilities, GameplayTags, and GameplayTasks to PublicDependencyModuleNames.",
        "rubric": ["ModuleRules", "PublicDependencyModuleNames.AddRange", "GameplayAbilities", "GameplayTags", "GameplayTasks"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-16",
        "engine": "Unreal Engine 5.7",
        "category": "Performance & Profiling",
        "prompt": "How do you add a custom CPU profiler cycle stat to a critical C++ gameplay tick function in UE 5.7?",
        "rubric": ["DECLARE_STATS_GROUP", "DECLARE_CYCLE_STAT", "SCOPE_CYCLE_COUNTER", "QUICK_SCOPE_CYCLE_COUNTER"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-17",
        "engine": "Unreal Engine 5.7",
        "category": "World Partition",
        "prompt": "How do you configure an AActor to be spatially loaded or non-spatially loaded in Unreal Engine 5.7 World Partition?",
        "rubric": ["SetIsSpatiallyLoaded", "bIsSpatiallyLoaded", "World Partition", "Data Layers"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-18",
        "engine": "Unreal Engine 5.7",
        "category": "Async Loading",
        "prompt": "Write a C++ function that uses FStreamableManager to asynchronously load a TSoftObjectPtr<UStaticMesh> with a completion delegate.",
        "rubric": ["FStreamableManager", "TSoftObjectPtr", "RequestAsyncLoad", "FStreamableDelegate"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-19",
        "engine": "Unreal Engine 5.7",
        "category": "Core Redirects",
        "prompt": "Provide the DefaultEngine.ini CoreRedirect entry to rename a moved UCLASS from OldGame.OldPlayerState to NewGame.NewPlayerState without breaking maps.",
        "rubric": ["[/Script/Engine.Engine]", "+ClassRedirects", "OldName", "NewName"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-20",
        "engine": "Unreal Engine 5.7",
        "category": "Niagara Integration",
        "prompt": "Show C++ code spawning a UNiagaraSystem attached to a character skeletal mesh socket with auto-destroy enabled.",
        "rubric": ["UNiagaraFunctionLibrary", "SpawnSystemAttached", "EAttachLocation", "bAutoDestroy", "SkeletalMeshComponent"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-21",
        "engine": "Unreal Engine 5.7",
        "category": "Animation & Montages",
        "prompt": "Write a C++ method on an ACharacter that plays a UAnimMontage and binds a dynamic delegate to OnMontageEnded.",
        "rubric": ["UAnimInstance", "Montage_Play", "OnMontageEnded", "UAnimMontage"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-22",
        "engine": "Unreal Engine 5.7",
        "category": "SaveGame System",
        "prompt": "How do you declare a USaveGame subclass in UE 5.7 with encrypted/compressed serialization support?",
        "rubric": ["USaveGame", "UGameplayStatics::SaveGameToSlot", "UGameplayStatics::LoadGameFromSlot", "SaveGame specifier"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-23",
        "engine": "Unreal Engine 5.7",
        "category": "Network Dormancy",
        "prompt": "Explain NetDormancy (DORM_Initial, DORM_DormantAll, FlushNetDormancy) in UE 5.7 and write code waking a dormant actor when state changes.",
        "rubric": ["NetDormancy", "DORM_DormantAll", "FlushNetDormancy", "SetNetDormancy"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-24",
        "engine": "Unreal Engine 5.7",
        "category": "Mass Entity & ECS",
        "prompt": "What is Mass Entity in Unreal Engine 5.7 and how does an FMassSharedFragment differ from an FMassFragment?",
        "rubric": ["MassEntity", "FMassFragment", "FMassSharedFragment", "data-oriented", "entity chunk"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-25",
        "engine": "Unreal Engine 5.7",
        "category": "Slate & CommonUI",
        "prompt": "Explain CommonUI in UE 5.7: How does UCommonActivatableWidget handle gamepad focus and back-action routing?",
        "rubric": ["CommonUI", "UCommonActivatableWidget", "ActivateWidget", "DeactivateWidget", "back handler"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-26",
        "engine": "Unreal Engine 5.7",
        "category": "Root Motion",
        "prompt": "How do you enable network-replicated root motion for montage-based character attacks in UE 5.7?",
        "rubric": ["Root Motion", "UCharacterMovementComponent", "Montage", "server prediction"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-27",
        "engine": "Unreal Engine 5.7",
        "category": "Sound & Audio",
        "prompt": "Write C++ code setting a continuous audio float parameter on a USoundBase using Audio Component and MetaSounds.",
        "rubric": ["UAudioComponent", "SetFloatParameter", "MetaSound", "PlaySoundAtLocation"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-28",
        "engine": "Unreal Engine 5.7",
        "category": "FastArraySerializer",
        "prompt": "Write the struct definitions for an FFastArraySerializer and FFastArraySerializerItem in UE 5.7 for replicating dynamic inventory items efficiently.",
        "rubric": ["FFastArraySerializer", "FFastArraySerializerItem", "NetDeltaSerialize", "MarkItemDirty", "PostReplicatedAdd"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-29",
        "engine": "Unreal Engine 5.7",
        "category": "Smart Pointers",
        "prompt": "When should you use TSharedPtr, TSharedRef, and TWeakPtr in non-UObject engine programming, and how do they handle thread safety?",
        "rubric": ["TSharedPtr", "TSharedRef", "TWeakPtr", "ESPMode::ThreadSafe", "reference counting"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-30",
        "engine": "Unreal Engine 5.7",
        "category": "Packaging & CI",
        "prompt": "Explain RunUAT BuildCookRun flags for shipping package generation with Pak and IoStore enabled.",
        "rubric": ["RunUAT.bat", "BuildCookRun", "-cook", "-stage", "-pak", "-iostore", "-clientconfig=Shipping"],
        "max_points": 10
    },

    # --- CROSS-ENGINE / GODOT / ROBLOX / UEFN / BEVY / MATH (20 Tasks) ---
    {
        "id": "GF-BENCH-31",
        "engine": "Cross-Engine Architecture",
        "category": "Data-Oriented Design",
        "prompt": "Explain Data-Oriented Design (DOD) principles in modern game engine architectures compared to traditional object-oriented scene hierarchies.",
        "rubric": ["Data-Oriented Design", "cache locality", "structure of arrays", "AOS vs SOA", "CPU cache lines"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-32",
        "engine": "Cross-Engine Architecture",
        "category": "State Synchronization",
        "prompt": "Explain lockstep deterministic simulation vs client-side prediction with server reconciliation in multiplayer action games.",
        "rubric": ["Lockstep", "deterministic simulation", "client-side prediction", "server reconciliation", "rollback"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-33",
        "engine": "Cross-Engine Architecture",
        "category": "Memory Management",
        "prompt": "Describe frame-based linear arena allocators and pool allocators in real-time game engines and why they avoid fragmentation.",
        "rubric": ["Arena allocator", "linear allocation", "pool allocator", "fragmentation", "O(1) reset"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-34",
        "engine": "Cross-Engine Architecture",
        "category": "Asset Pipelines",
        "prompt": "How do virtualized geometry asset pipelines (e.g. Nanite) dynamically determine cluster LODs based on projected screen pixels?",
        "rubric": ["Virtualized geometry", "cluster hierarchy", "screen-space error", "DAG traversal", "GPU culling"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-35",
        "engine": "Godot 4",
        "category": "CharacterBody3D",
        "prompt": "Write a complete Godot 4 GDScript for CharacterBody3D implementing horizontal acceleration, gravity, and floor sliding.",
        "rubric": ["CharacterBody3D", "move_and_slide()", "_physics_process", "velocity", "move_toward"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-36",
        "engine": "Godot 4",
        "category": "Signals & Decoupling",
        "prompt": "Show how to define and emit custom typed signals with parameters in Godot 4 GDScript, and connect via callable in code.",
        "rubric": ["signal health_changed(new_health: float)", "emit_signal or health_changed.emit", "connect", "Callable"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-37",
        "engine": "Godot 4",
        "category": "Multiplayer RPCs",
        "prompt": "Implement a server-reliable RPC in Godot 4 GDScript using @rpc('call_local', 'reliable') to sync score changes across peers.",
        "rubric": ["@rpc", "call_local", "reliable", "multiplayer.is_server()", "rpc_id"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-38",
        "engine": "Godot 4",
        "category": "Node Lifecycle",
        "prompt": "Explain the exact execution order in Godot 4 of _init, _enter_tree, _ready, and _exit_tree when instantiating a scene packed in code.",
        "rubric": ["_init", "_enter_tree", "_ready", "_exit_tree", "parent-first vs child-first order"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-39",
        "engine": "Roblox",
        "category": "RemoteEvent Security",
        "prompt": "Write a Luau server script that handles an EquipTool RemoteEvent, verifying that the tool is owned in player inventory and preventing spoofing.",
        "rubric": ["RemoteEvent.OnServerEvent", "player.Character", "player.Backpack", "server validation", "Humanoid:EquipTool"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-40",
        "engine": "Roblox",
        "category": "Task Scheduler",
        "prompt": "Explain why task.spawn and task.defer should be used instead of spawn() or delay() in modern Roblox Luau scripts.",
        "rubric": ["task.spawn", "task.defer", "engine step budget", "immediate execution vs deferred", "throttling in legacy spawn"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-41",
        "engine": "Roblox",
        "category": "DataStore2 / ProfileService",
        "prompt": "Describe session locking in Roblox DataStore architecture to prevent data duplication across rapid server hops.",
        "rubric": ["Session locking", "ProfileService or DataStore", "active session tag", "release on server exit", "BindToClose"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-42",
        "engine": "UEFN",
        "category": "Verse Concurrency",
        "prompt": "Write a Verse function using race and sync to wait for either an item to be picked up or a 30-second timer to expire.",
        "rubric": ["race", "sync", "Sleep", "Await", "suspends"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-43",
        "engine": "UEFN",
        "category": "Verse Spatial Math",
        "prompt": "Show how to linearly interpolate (lerp) the translation vector of a prop in UEFN Verse over a duration using Sleep in a loop.",
        "rubric": ["vector3", "Sleep", "loop", "transform", "MoveTo"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-44",
        "engine": "UEFN",
        "category": "Verse Devices",
        "prompt": "Implement a custom creative_device in Verse that tracks team scores and triggers an end_game_device when a threshold is met.",
        "rubric": ["creative_device", "@editable", "end_game_device", "team", "OnBegin"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-45",
        "engine": "Bevy",
        "category": "Rust ECS Query",
        "prompt": "Write a Bevy 0.14+ Rust system querying all entities with Position and Velocity components, mutating Position by Velocity * delta time.",
        "rubric": ["Query<(&mut Position, &Velocity)>", "Res<Time>", "delta_seconds()", "system function", "Component"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-46",
        "engine": "Bevy",
        "category": "Events & Commands",
        "prompt": "Demonstrate sending and reading custom Event in Bevy Rust ECS: An EventWriter in one system and EventReader in another.",
        "rubric": ["EventWriter", "EventReader", "add_event", "App", "read()"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-47",
        "engine": "Bevy",
        "category": "Resource Mutation",
        "prompt": "Explain the difference between Res<T> and ResMut<T> in Bevy Rust ECS and how system scheduling prevents data races.",
        "rubric": ["Res<T> immutable", "ResMut<T> mutable", "scheduler parallelization", "Rust borrow checker rules", "exclusive access"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-48",
        "engine": "Game Mathematics",
        "category": "Quaternions & Rotations",
        "prompt": "Write a C++ function calculating the shortest angular difference in radians between two 3D unit direction vectors.",
        "rubric": ["DotProduct", "FMath::Clamp", "acos", "CrossProduct", "radians"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-49",
        "engine": "Game Mathematics",
        "category": "Spatial Partitioning",
        "prompt": "Compare spatial hashing vs BVH (Bounding Volume Hierarchy) for dynamic multi-agent collision queries in games.",
        "rubric": ["Spatial hashing", "BVH", "grid cell lookup", "tree traversal", "O(1) average vs O(log N)"],
        "max_points": 10
    },
    {
        "id": "GF-BENCH-50",
        "engine": "Cross-Engine Architecture",
        "category": "Network Synchronization",
        "prompt": "Explain how tick-based snapshot interpolation buffers handle packet jitter in networked multiplayer action games.",
        "rubric": ["Snapshot buffer", "interpolation delay", "jitter buffer", "hermite or linear lerp", "render time offset"],
        "max_points": 10
    }
]


def _write_atomic_json(target_path: Path, data: Any) -> None:
    """Atomically write JSON data to file using a temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2)
        tf_name = tf.name
    os.replace(tf_name, target_path)


def build_benchmark(output_dirs: Optional[List[Path]] = None) -> List[Path]:
    written_files: List[Path] = []
    default_dirs = [
        REPO_ROOT / "reports" / "gameforge-27b",
    ]
    e_dir = Path("E:/GameForge/reports/gameforge-27b")
    if e_dir.parent.parent.exists():
        default_dirs.append(e_dir)

    target_dirs = output_dirs or default_dirs
    for d in target_dirs:
        out_file = d / "baseline_benchmark.json"
        _write_atomic_json(out_file, BENCHMARK_TASKS)
        written_files.append(out_file)
        print(f"Wrote {len(BENCHMARK_TASKS)} benchmark tasks to {out_file}")

    return written_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Build authoritative 50-task GameForge Engineering Benchmark")
    parser.add_argument("--output-dir", type=Path, default=None, help="Custom output directory")
    args = parser.parse_args()

    targets = [args.output_dir] if args.output_dir else None
    written = build_benchmark(targets)
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
