#pragma once
// Keep identical to src/gameforge_ide/design/events_catalog.py (tests/unit/test_event_names_parity.py).
#define GF_EVENT_NAMES(X) \
    X(GameStarted, "game.started") X(GameWon, "game.won") X(GameLost, "game.lost") X(GameRestarted, "game.restarted") \
    X(GamePaused, "game.paused") X(GameResumed, "game.resumed") \
    X(PlayerSpawned, "player.spawned") X(PlayerDamaged, "player.damaged") X(PlayerDied, "player.died") \
    X(PlayerRespawned, "player.respawned") X(PlayerJumped, "player.jumped") \
    X(PlayerDashed, "player.dashed") X(PlayerSprinted, "player.sprinted") X(WeaponSwitched, "weapon.switched") \
    X(PickupCollected, "pickup.collected") X(CheckpointReached, "checkpoint.reached") X(GoalReached, "goal.reached") \
    X(HazardTouched, "hazard.touched") X(EnemySpawned, "enemy.spawned") X(EnemyAttacked, "enemy.attacked") \
    X(EnemyKilled, "enemy.killed") X(WaveStarted, "wave.started") X(WaveCleared, "wave.cleared") \
    X(GuardState, "guard.state") X(GuardSpottedPlayer, "guard.spotted_player") X(GuardLostPlayer, "guard.lost_player") \
    X(DialogueLine, "dialogue.line") X(ObjectiveStarted, "objective.started") X(ObjectiveUpdated, "objective.updated") \
    X(ObjectiveCompleted, "objective.completed") X(SaveLoaded, "save.loaded") X(SaveWritten, "save.written") \
    X(InteractUsed, "interact.used") X(DoorOpened, "door.opened") X(DoorClosed, "door.closed") \
    X(SwitchToggled, "switch.toggled") X(SwitchActivated, "switch.activated") X(LandmarkDiscovered, "landmark.discovered") \
    X(BoardMove, "board.move") X(BoardWin, "board.win") X(BoardLose, "board.lose") X(BoardDraw, "board.draw") X(BoardWarp, "board.warp") \
    X(TurnEnded, "turn.ended") X(DiceRolled, "dice.rolled") X(TileRevealed, "tile.revealed") X(LineCleared, "line.cleared") \
    X(SnakeTransition, "snake.transition") X(LadderTransition, "ladder.transition") \
    X(CardPlayed, "card.played") X(LaneResolved, "lane.resolved") X(MatchWon, "match.won") X(MatchLost, "match.lost") \
    X(LapCompleted, "lap.completed") X(RaceFinished, "race.finished") \
    X(TowerAttacked, "tower.attacked") X(TowerBuilt, "tower.built") \
    X(BombsitePlanted, "bombsite.planted") X(BombsiteDefused, "bombsite.defused")

namespace GFEvent
{
#define GF_DECLARE_NAME(Id, Str) inline const FName Id(TEXT(Str));
    GF_EVENT_NAMES(GF_DECLARE_NAME)
#undef GF_DECLARE_NAME
}
