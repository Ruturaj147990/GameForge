# P5 — Gameplay Kit v2: a data-driven runtime (handover)

**Branch:** `phase/P5-kit`. **Depends on:** P3 accepted (event bus, scenario runner, kit player). **Decision:** AD-10.
**Estimate:** 5–7 weeks, in four increments (K1–K4). Each increment ends with a plugin build, the kit testbed and
scenarios. **Read first:** `../01_ARCHITECTURE.md` §3.2–3.3, §3.6; `P03_scenario_qa.md`; `../06_ENGINE_NOTES_UE57.md`.

## Objective

Generated games should contain **no generated gameplay C++** except `custom_code` rules. The kit in `GameForgeRuntime`
plus a validated runtime definition (`gfdef/1`) must express everything the GDS can say: stats, rules, win/lose,
feedback, HUD, menus, save, and the entity modules in `design/events_catalog.MODULE_EVENTS`.

## Conventions (binding for every kit class)

1. **Entity identity.** Every kit actor has `UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="GameForge") FName EntityId;`
   (the GDS `entity_id`) and the actor tag `GF_E_<entity_id>`. Events carry it in `FGameForgeEvent::Entity` (added in P3). `EventRef.source` in a GDS **always means the entity id**, never an actor name.
2. **Events** only through `UGameForgeEventBus::Emit`, with names from `GameForgeEventNames.h`.
3. **Health and damage** only through GAS (`UGameForgeAttributeSet`). There is no second health system.
   `UGameForgeGameplayStateComponent` (M4) stays for the UMG demos and is marked legacy.
4. **No editor-only dependencies** in `GameForgeRuntime`. Everything must cook.
5. **Data-driven:** behaviour parameters are `UPROPERTY(EditAnywhere)` so the composer can set them through
   `set_actor_property`. Their names are listed in the Python kit module's `PROPERTY_MAP`.
6. **Determinism:** randomness uses `FRandomStream` seeded from `gfdef.seed` + the entity index.

**From P3:** `FGameForgeEvent::Entity`, `Emit(..., FName Entity)` and `Count(Name, Entity)` already exist, and
`AGameForgePickup`, `AGameForgeGuard` and `AGameForgeQuestGiver` already have `EntityId`. Every new kit actor below
follows the same pattern.

---

## The runtime definition `gfdef/1` (contract with P6's `composer/runtime_def.py`)

```json
{
  "schema": "gfdef/1",
  "title": "Relic Run",
  "seed": 2026,
  "player": {"camera": "third_person", "move_speed": 600, "jump_velocity": 650, "max_health": 100,
             "lives": 0, "kill_z": -2000},
  "input": [{"action": "IA_Move", "type": "axis2d",
             "bindings": [{"key": "W", "mods": ["swizzle"]}, {"key": "S", "mods": ["swizzle", "negate"]},
                          {"key": "D", "mods": []}, {"key": "A", "mods": ["negate"]}]}],
  "stats": {"player.health": {"initial": 100, "min": 0, "max": 100}, "game.score": {"initial": 0},
            "game.counter.waves_cleared": {"initial": 0}},
  "entities": {"pickups": {"class": "/Script/GameForgeRuntime.GameForgePickup", "spawn_tag": "GF_SP_pickups"}},
  "rules": [{"id": "score", "when": {"e": "pickup.collected", "ent": null},
             "if": [], "do": [{"kind": "add_stat", "stat": "game.score", "delta": 10}]}],
  "win":  [{"kind": "count_at_least", "event": "pickup.collected", "n": 5}],
  "lose": [{"kind": "stat", "stat": "player.health", "op": "<=", "value": 0}],
  "feedback": [{"e": "pickup.collected", "vfx": "/Game/GameForge/VFX/NS_Sparkle", "sfx": "/Game/GameForge/SFX/S_Chime",
                "shake": 0.0, "msg": null}],
  "hud": [{"id": "health", "kind": "bar", "stat": "player.health", "label": "Health"},
          {"id": "relics", "kind": "counter", "stat": "entity.pickups.collected", "label": "Relics", "of": 5}],
  "menus": {"main": true, "pause": true, "end": true},
  "custom_rules": [{"id": "custom_0", "class": "/Script/RelicRun.Custom0Rule"}]
}
```

Condition and effect objects use **exactly** the GDS JSON shapes (`kind` discriminator, same field names), so the
composer copies them. The only renames are in `when` (`event` → `e`, `source` → `ent`).

---

## K1 — Core runtime (WI-5.1 … 5.5)

### WI-5.1 Definition asset + settings
```cpp
UCLASS(BlueprintType)
class GAMEFORGERUNTIME_API UGameForgeGameDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "GameForge") FString SchemaVersion = TEXT("gfdef/1");
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "GameForge", meta = (MultiLine = true)) FString DefinitionJson;
	/** Parsed once; nullptr if invalid (errors in ParseErrors). */
	TSharedPtr<FJsonObject> GetParsed() const;
	UPROPERTY(Transient, VisibleAnywhere, Category = "GameForge") mutable TArray<FString> ParseErrors;
private:
	mutable TSharedPtr<FJsonObject> Cached;
};

UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "GameForge Runtime"))
class GAMEFORGERUNTIME_API UGameForgeRuntimeSettings : public UDeveloperSettings
{
	GENERATED_BODY()
public:
	UPROPERTY(Config, EditAnywhere, Category = "GameForge") TSoftObjectPtr<UGameForgeGameDefinition> GameDefinition;
};
```
Build.cs: add `"DeveloperSettings"`, and `"Json"` moves to public dependencies. Add a new editor op
`gamedef_write {asset_path, json}`: create or update the asset, set `DefinitionJson`, save, then read back via
`gamedef_inspect`, which returns the parse errors computed **in the editor** by calling `GetParsed()` through a
`UFUNCTION(BlueprintCallable)` wrapper `ValidateDefinition() -> TArray<FString>`. The scaffolder writes:
```ini
; Config/DefaultGame.ini
[/Script/GameForgeRuntime.GameForgeRuntimeSettings]
GameDefinition=/Game/GameForge/GD_Main.GD_Main
[/Script/UnrealEd.ProjectPackagingSettings]
+DirectoriesToAlwaysCook=(Path="/Game/GameForge")
```

### WI-5.2 Stats in `AGameForgeGameState`
`TMap<FName, float> Stats` with `GetStat(FName)`, `SetStat(FName, float)` (clamped to definition min/max) and
`AddStat`. Every change emits **no event** (avoids feedback loops) but broadcasts `OnStatChanged(FName, float)` for
HUD binding. Derived stats are computed on read: `game.time_s` (world time since `game.started`),
`entity.<id>.remaining` (actors with tag `GF_E_<id>` that are not collected or dead), and
`entity.<id>.collected|killed` (bus counts of `pickup.collected`/`enemy.killed` with `Entity == id`).
`player.health` mirrors the player's GAS attribute (WI-5.6). Replication flags are prepared but unused until P10:
`bReplicates = true`, and the stats array is stored as a replicated `TArray<FGameForgeStat>`, because `TMap` does not
replicate.

### WI-5.3 The rule evaluator (pure C++, unit-testable without a world)
```cpp
/** Evaluates gfdef conditions against a stats + counts provider. No UObject dependencies. */
class GAMEFORGERUNTIME_API FGameForgeConditionEvaluator
{
public:
	struct FContext
	{
		TFunction<float(FName Stat)> GetStat;                   // returns NaN for unknown stats → condition false
		TFunction<int32(FName Event, FName Entity)> CountEvents;
		TFunction<bool(FName Event, FName Entity)> HasEvent;
		float ElapsedSeconds = 0.f;
	};
	/** false + Error set on malformed JSON (unknown kind, missing field, depth > 3). Never throws. */
	static bool Evaluate(const TSharedPtr<FJsonObject>& Condition, const FContext& Ctx, FString& Error, int32 Depth = 0);
};
```
Semantics (identical to the GDS docs; document them in the header):
- `count_at_least`: `CountEvents(event, source) >= n`. `stat`: compare with `op`, and NaN → false.
- `timer`: `ElapsedSeconds >= seconds`. `event`: `HasEvent(event, source)`.
- `all`: all items true. An empty `all` is malformed. `any`: any item true.
- Depth > 3 → malformed.

**Automation tests** (`Private/Tests/GameForgeRulesTests.cpp`, `IMPLEMENT_SIMPLE_AUTOMATION_TEST`, filter
`GameForge.Kit.Rules.*`). Use an in-memory context and cover each kind, nesting, NaN stats, malformed input (unknown
kind, missing `n`, depth 4), and the operator table (`<`, `<=`, `==` with 1e-4 tolerance, `>=`, `>`).

### WI-5.4 `UGameForgeRulesSubsystem` (UWorldSubsystem)
- `OnWorldBeginPlay`: load the definition (settings → asset → `GetParsed()`). If it is missing or invalid, log an error,
  emit `game.started` with `{"definition":"invalid"}` and do nothing else: the scenario smoke test then fails visibly.
  Initialise the stats. Subscribe to the bus.
- On every event: append to the per-(event, entity) counters; then for each rule whose `when.e` equals the event and
  whose `when.ent` is null or equal to the entity → evaluate the `if` conditions → apply the `do` effects in order.
  Effects: `add_stat`/`set_stat` → GameState; `emit` → bus (re-entrancy guard: depth ≤ 4, then drop and log
  `RULE_LOOP`); `spawn` → `SpawnEntity(entity_id, count)` using `entities[id].class` at actors tagged `spawn_tag`
  (round-robin, seeded); `message` → feedback subsystem; `end_game` → GameMode `EndGame(outcome)`; `custom_code`
  → the custom rule instance's `OnEvent`.
- After every event and on a 0.25 s timer: evaluate `lose` first, then `win` (the documented tie-break). The first
  satisfied condition ends the game with `{"reason":"lose[<i>]"}` or `win[<i>]` in the event data. After the game ends,
  the subsystem stops evaluating.
- Custom rules: for each `custom_rules[i].class`, `LoadClass<UGameForgeCustomRule>(nullptr, *Path)` →
  `NewObject` → `Initialize(World)`. A missing class is an error (`game.started` data `{"custom_rule_missing": id}`).
  ```cpp
  UCLASS(Abstract, Blueprintable)
  class GAMEFORGERUNTIME_API UGameForgeCustomRule : public UObject
  {
  	GENERATED_BODY()
  public:
  	virtual void Initialize(UWorld* InWorld) { World = InWorld; }
  	virtual void OnEvent(const FGameForgeEvent& Event) {}
  	virtual void Tick(float DeltaSeconds) {}          // called by the rules subsystem every 0.25 s
  protected:
  	UPROPERTY() TObjectPtr<UWorld> World;
  	AGameForgeGameState* GameState() const;
  	void Emit(FName Name, const FString& DataJson = TEXT("{}"));
  };
  ```

### WI-5.5 `AGameForgeGameMode` + end/restart
It extends P3's `AGameForgeGameModeBase`. It reads `player` from the definition and applies it to the spawned
`AGameForgeCharacter` (camera mode, speeds, health initial). `EndGame(bool bWon, FString Reason)`: emit
`game.won`/`game.lost`, set `bEnded`, disable pawn input, show the end screen (WI-5.10) and save if save is enabled.
`IA_Restart` (R) or the end-screen button → emit `game.restarted` → `UGameplayStatics::OpenLevel(this,
GetWorld()->GetCurrentLevel ... )`, using the current map name from `UGameplayStatics::GetCurrentLevelName`. Player
death: if `player.lives` > 0 and a checkpoint exists, decrement lives, respawn at the checkpoint and emit
`player.respawned`. Otherwise do nothing extra: the lose conditions decide.

**K1 exit:** rules automation tests green. Kit testbed GDS v2 (hand-written gfdef): `collect_3` now also expects
`game.won`, and a new `lose_hazard` scenario expects `game.lost` (hazard from K2; until K2, use `set_stat` from a
debug-only scenario step `{"debug_set_stat": …}` compiled out in Shipping). Plugin build `GameForgePlugin_p5k1`.

---

## K2 — Player, health, world modules (WI-5.6 … 5.8)

### WI-5.6 GAS health
- Build.cs: `"GameplayAbilities", "GameplayTags", "GameplayTasks"`. The plugin enables `GameplayAbilities`.
- `UGameForgeAttributeSet`: `Health`, `MaxHealth`, `Stamina`, `MaxStamina`, and the meta attribute `Damage`. Use the
  standard `ATTRIBUTE_ACCESSORS` macro block. `PostGameplayEffectExecute`: if Damage → `Health = clamp(Health - Damage)`,
  `Damage = 0`, emit `player.damaged` or `enemy.attacked` (by owner type), and on Health ≤ 0 emit `player.died` or
  `enemy.killed` once (guard flag). Mirror `player.health` into GameState.
- A native tag via `UE_DEFINE_GAMEPLAY_TAG(TAG_GF_Data_Damage, "GameForge.Data.Damage")`.
- `UGameForgeDamageEffect : UGameplayEffect` (Instant; one modifier on `Damage`, magnitude SetByCaller
  `GameForge.Data.Damage`), configured in its constructor. A helper
  `UGameForgeDamageLibrary::ApplyDamage(AActor* Target, AActor* Instigator, float Amount)` builds the spec, sets the
  SetByCaller value and applies it.
- `AGameForgeCharacter` and `AGameForgeEnemy` own a `UAbilitySystemComponent` (`ReplicationMode::Minimal`) and the
  attribute set, and implement `IAbilitySystemInterface`.

### WI-5.7 World modules
| Class | Key UPROPERTYs (composer sets them) | Behaviour | Emits |
|---|---|---|---|
| `AGameForgePickup` (exists) | `Value`, `ObjectiveId`, `CollectVFX`, `CollectSound`, `EntityId`, `bRespawns`, `RespawnSeconds` | Overlap by the player pawn → collected (hidden, no collision) | `pickup.collected` `{value, objective}` |
| `AGameForgeHazard` | `DamagePerSecond`, `bInstantKill`, `ShapeExtent`, `EntityId` | Overlap → damage via GAS every 0.5 s, or kill | `hazard.touched` |
| `AGameForgeCheckpoint` | `EntityId`, `bActivateOnce` | Overlap → GameMode respawn transform | `checkpoint.reached` |
| `AGameForgeGoal` | `EntityId`, `RequiredStat` (optional FName), `RequiredValue` | Overlap → if the requirement is met, emit; otherwise HUD message "Not yet" | `goal.reached` |
| `AGameForgeLandmark` | `EntityId`, `DiscoverRadius` | First overlap | `landmark.discovered` |
| `AGameForgeMovingPlatform` | `EndOffset` (FVector), `Seconds`, `PauseSeconds` | Ping-pong interp on the server tick | — |
| KillZ | `AGameForgeCharacter::FellOutOfWorld` override | — | `player.died` `{"cause":"fell"}` |

### WI-5.8 Interaction
`IGameForgeInteractable` (UInterface) with BlueprintNativeEvents `CanInteract(AController*)` and
`Interact(AController*)`. `UGameForgeInteractionComponent` on the player: on `IA_Interact`, sphere-overlap 200 cm in
front of the pawn and call `Interact` on the nearest valid target, emitting `interact.used`.
`AGameForgeDoor` (`RequiredStat`, `RequiredValue`, `OpenOffset`, `Seconds`) and `AGameForgeSwitch` (`TargetTag`,
`bToggle`) implement the interface. `AGameForgeQuestGiver` gains `Interact` (talks on interact as well as on overlap,
configurable `bTalkOnOverlap`).

**K2 exit:** kit testbed level v2 (hazard, checkpoint, goal, door + switch, moving platform). Scenarios:
`win_goal_after_relics`, `lose_hazard` (lives 0), `respawn_checkpoint` (lives 1 → `player.respawned` then win),
`door_requires_key`. All pass in Development and Shipping packages. Plugin build `p5k2`.

---

## K3 — Combat, AI, presentation (WI-5.9 … 5.11)

### WI-5.9 Enemies and spawner
- `AGameForgeEnemy : ACharacter` (+ ASC) with `AttackDamage`, `AttackRange`, `AttackCooldown`, `AggroRange`,
  `MoveSpeed`, `bRanged`, `ProjectileSpeed`, `EntityId`. `AGameForgeEnemyAIController`: AI Perception sight (reuse the
  guard's configuration code), states Idle → Chase → Attack → Dead. MoveTo goes through `MoveToActor` with an
  acceptance radius of `AttackRange * 0.8`. **Lesson from M15:** never issue MoveTo from `OnMoveCompleted`; schedule it
  on the next tick. Melee applies damage via `ApplyDamage` after an LOS line trace. Ranged spawns
  `AGameForgeProjectile` (sphere, `ProjectileMovementComponent`, damage on hit).
- `AGameForgeSpawner`: `EnemyClass` (soft class), `WaveCount`, `EnemiesPerWave`, `SecondsBetweenWaves`,
  `SpawnRadius`, `EntityId` (it spawns with the enemy entity id `EnemyEntityId`). It emits `wave.started {wave}`. It
  listens for `enemy.killed` with `EnemyEntityId`, and when its spawned set reaches 0 it emits `wave.cleared {wave}`.
  After the last wave it stops.
- The player attack (`IA_Attack`): a melee sweep (`AttackRange`, `AttackDamage`, cooldown) on `AGameForgeCharacter`,
  with values from gfdef `player` (`attack_damage`, `attack_range`, `attack_cooldown`; defaults 35/250/0.4).

### WI-5.10 HUD, menus and feedback (no Blueprint assets required)
- `UGameForgeHUDWidget : UUserWidget`: override `RebuildWidget()` to construct `UCanvasPanel` → a `UVerticalBox` (top-left)
  with one row per gfdef `hud` element: `bar` → `UProgressBar` + label; `counter` → `UTextBlock` "Label: v / of";
  `text`/`objective` → `UTextBlock`; `timer` → `UTextBlock` mm:ss. Then a centred message `UTextBlock` for feedback
  messages (fade after `seconds`). Bind to `AGameForgeGameState::OnStatChanged` (no tick polling) and refresh `timer`
  rows with a 0.25 s widget timer. Root construction:
  ```cpp
  TSharedRef<SWidget> UGameForgeHUDWidget::RebuildWidget()
  {
  	if (WidgetTree && !WidgetTree->RootWidget)
  	{
  		UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("Root"));
  		WidgetTree->RootWidget = Root;
  		BuildRows(Root);   // creates and slots the rows from the parsed definition
  	}
  	return Super::RebuildWidget();
  }
  ```
  Check in the 5.7.4 source (`UMG/Private/UserWidget.cpp`) that `WidgetTree` is non-null for native subclasses at
  `RebuildWidget` time. If it is null, create it with `NewObject<UWidgetTree>(this, TEXT("WidgetTree"))` before use, and
  note this in the commit.
- `UGameForgeMenuWidget`: the main menu (Play, Quit), pause (Resume, Restart, Quit) and end screen (title "You win!"
  or "Game over", the score if any, Restart, Quit). Buttons are `UButton` + `UTextBlock`, built the same way. Input:
  Esc → pause (`IA_Pause`, added to the default input). Mouse cursor is shown while menus are open. The main menu shows
  only if `menus.main` is true; otherwise play starts immediately. **Scenarios bypass the main menu**: the scenario
  subsystem calls `UGameForgeMenuWidget::StartGameForScenario()` when the menu is up.
- `UGameForgeFeedbackSubsystem` (WorldSubsystem): bus listener. For each matching `feedback` row: spawn Niagara at the
  event location (data `{"x","y","z"}`, else the source actor, else the player; emitters add a location to the data),
  play the sound at the location, start the camera shake (`UGameForgeCameraShake : UCameraShakeBase` with a
  `UWaveOscillatorCameraShakePattern` root set in its constructor, `Scale = shake`), and show `msg` through the HUD.
  Soft asset paths load **asynchronously** with `UAssetManager::GetStreamableManager()` on first use.

### WI-5.11 Save
`UGameForgeSaveSubsystem` (GameInstance): slot `GF_Save_<ProjectName>`, saving stats marked persistent (gfdef
`stats.<name>.persist: true`), objectives (delegates to the existing subsystem) and the checkpoint transform. Save on
`game.won`, on checkpoint and on quit; load on start when `persist` stats exist. Events `save.loaded`/`save.written`.

**K3 exit:** testbed level v3, an arena section: a spawner with 2 waves × 3 enemies, and a player attack scenario
`win_waves` (the autopilot navigates; a new scenario step `attack_until {entity, timeout_s}` injects `IA_Attack` every
0.4 s while facing the nearest enemy with that entity id). `lose_enemies` (the player idles until killed). HUD rows are
visible in captures (manual check, plus a pixel check that the bar region is not background). Pause/end menus work in
a Shipping package. Plugin build `p5k3`.

---

## K4 — Board and card logic modules; registry (WI-5.12 … 5.14)

### WI-5.12 `AGameForgeGridBoard`
Port the C++ logic from `recipes/grid_board_game/templates.py` (board state, win detection for N-in-a-row, gravity
drops, AI: perfect minimax for 3×3, alpha-beta depth-limited for larger boards, greedy, random). Render the template
output once with default params, copy the logic into kit classes, and remove the recipe-specific naming. Do not
invent new AI.
- Properties: `BoardSize`, `WinLength`, `bGravity`, `bVsAI`, `AILevel` (enum), `CellSizeCm`, the three colours, `EntityId`.
- Cells are child static-mesh components named `Cell_r_c`. Each cell implements selection through
  `IGameForgeSelectable::OnSelected(APlayerController*)`. The P3 `SelectAtScreenPosition` calls it.
- Events: `board.move {row,col,player}`, `turn.ended`, `board.win {winner:"player"|"ai"|"p2"}` (sets
  `game.counter.ai_won = 1` before emitting when the AI wins), `board.draw`.
- A scenario step `select_actor` with tag `GF_Cell_<r>_<c>` already works (P3). The generator's board strategy plays a
  scripted winning line against `AILevel=random` with a fixed seed, and a draw line against `perfect`.

### WI-5.13 `UGameForgeCardMatchComponent` + `AGameForgeCardTable`
Port from `recipes/card_battler/templates.py` (deck, shuffle with seeded stream, hand, energy, lanes, combat
resolution, opponent AI). The UI is drawn by `UGameForgeHUDWidget` extensions (`hud` kinds `hand`, `lanes`, `energy`;
add them to the GDS `HudElement.kind` literal **only after Claude approves**: raise it in QUESTIONS.md with the
proposed literal list). Events: `card.played`, `lane.resolved`, `turn.ended`, `match.won`, `match.lost`.

### WI-5.14 Python kit registry and parameter models
`src/gameforge_ide/kit/registry.py`:
```python
@dataclass(frozen=True)
class KitModule:
    module_id: str; version: str; runtime_class: str; entity_kinds: frozenset[str]
    params_model: type[BaseModel]; property_map: dict[str, str]
    required_plugins: tuple[str, ...] = (); game_module_deps: tuple[str, ...] = ()
    emits: tuple[str, ...] = (); automation_tests: tuple[str, ...] = (); status: str = "PLANNED"
    evidence: tuple[str, ...] = ()

KIT: dict[str, KitModule] = {}   # filled by kit/modules/*.py via register()
def register(m: KitModule) -> KitModule: ...
def module(module_id: str) -> KitModule: ...
def selectable(allow_partial: bool = False) -> list[KitModule]: ...
```
`kit/modules/pickup.py` (pattern for all modules):
```python
class PickupParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int = Field(1, ge=1, le=1000)
    objective_id: str | None = Field(None, pattern=r"^[a-z][a-z0-9_]{0,39}$")
    respawns: bool = False
    respawn_seconds: float = Field(10.0, ge=1, le=600)

register(KitModule(
    module_id="kit.pickup", version="2.0.0", runtime_class="/Script/GameForgeRuntime.GameForgePickup",
    entity_kinds=frozenset({"pickup"}), params_model=PickupParams,
    property_map={"value": "Value", "objective_id": "ObjectiveId", "respawns": "bRespawns",
                  "respawn_seconds": "RespawnSeconds"},
    emits=("pickup.collected",), automation_tests=("GameForge.Kit.Pickup",), status="PASS",
    evidence=("reports/P5/kit_scenarios_k2.json",)))
```
Tests: `KIT` keys equal `events_catalog.MODULE_EVENTS` keys; each module's `emits` equals the catalogue entry; every
`property_map` value is a `UPROPERTY` name that appears in the matching C++ header (regex over `Public/*.h`); and a
module's status may be `PASS` only if its evidence files exist.

**The GDS validator now also checks entity props:** `EntitySpec.props` validated against `KIT[module].params_model`.
Add this to `GameDesignSpec._cross_refs` behind a lazy import, so `design/` does not import `kit/` at module load.

## Phase exit gate
1. Plugin build `GameForgePlugin_p5` (all K1–K4 code) with 0 warnings in GameForge modules. SHA-256 recorded.
2. `GameForge.Kit.*` automation tests green in the testbed (`toolchain.run_automation_tests(…, "GameForge.Kit")`).
3. Kit scenario suite green in Development and Shipping packages: `reports/P5/kit_scenarios_final.json`
   (≥ 14 scenarios: collect, goal, hazard, respawn, door, waves win, enemy lose, board win, board draw, card win,
   quest, guard detect, plus the two P3 controls).
4. Every `kit/modules/*` row has `status` and `evidence`, and `docs/00_STATUS.md` kit rows are updated.
5. Packaged testbed size and startup time recorded (input to P10).

## Failure cases and prevention
- **GAS without an ASC init:** call `AbilitySystemComponent->InitAbilityActorInfo(this, this)` in `BeginPlay` for
  enemies and in `PossessedBy` for the player. Missing it silently drops effects.
- **The definition asset not cooked:** the `DirectoriesToAlwaysCook` line (WI-5.1). The Shipping smoke scenario
  catches it (`game.started` data `definition: invalid`).
- **Rule loops** (`emit` → rule → `emit`): depth guard plus a `RULE_LOOP` log, and a test with a self-triggering rule.
- **Pickups counted twice** (overlap begin fires per component): a guard flag `bCollected` plus collision disabled
  before the emit.
- **Native UMG trees** blank in Shipping: verify in the K3 exit capture. If they are blank, fall back to
  ops-authored WBP reparented to `UGameForgeHUDWidget` (M3/M4 path) and record the decision in QUESTIONS.md for
  Claude's approval.

## Progress
| WI | Status | Started | Finished | Evidence |
|---|---|---|---|---|
| 5.1–5.5 (K1) | TODO | | | |
| 5.6–5.8 (K2) | TODO | | | |
| 5.9–5.11 (K3) | TODO | | | |
| 5.12–5.14 (K4) | TODO | | | |

## Review log (Claude)
_empty_

## Revisions
- 2026-10-31: created (Claude).
