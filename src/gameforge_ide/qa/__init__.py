"""Scenario QA package: schemas, manifest, generator, runner, and game-specific acceptance tests."""
from .game_spec_tests import (
    AcceptanceTestSpec,
    acceptance_tests_to_scenarios,
    generate_acceptance_tests,
)
from .runner import run_editor_game, run_packaged
from .scenario import Scenario, ScenarioResult
