"""Physics Probes and Simulation Settle Time Verification for GameForge IDE.

Compliant with GameForge Master Blueprint:
- REQ-061: Physics Simulation Probes.
- Scope ladder Row 2: Drop tests with recorded settle time within tolerance.
- Evaluates collision response, restitution (bounciness), damping, and floor resting height.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class PhysicsProbeResult(BaseModel):
    """Structured evidence of a physical simulation test."""
    passed: bool
    initial_height: float
    floor_height: float
    resting_height: float
    expected_settle_time_s: float
    simulated_settle_time_s: float
    settle_time_error_pct: float
    bounce_count: int
    energy_decay_monotonic: bool
    final_velocity: float
    details: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class PhysicsDropProbe:
    """Simulates and verifies dynamic physical drop tests in Unreal Engine coordinate space."""

    GRAVITY_CM_S2 = 980.0  # Unreal Engine standard: 980 cm/s^2 (9.8 m/s^2)

    def __init__(
        self,
        time_step: float = 1.0 / 60.0,  # 60 Hz physics tick
        bounce_velocity_threshold: float = 40.0,  # Unreal Chaos BounceThreshold (cm/s)
        height_tolerance: float = 0.5,  # cm
    ):
        self.dt = time_step
        self.v_thresh = bounce_velocity_threshold
        self.h_tol = height_tolerance

    def calculate_theoretical_settle_time(
        self,
        initial_z: float,
        floor_z: float,
        restitution: float = 0.45,
        damping: float = 0.05,
    ) -> float:
        """Calculates expected theoretical settle time for a bouncing dynamic object under gravity."""
        drop_distance = max(0.0, initial_z - floor_z)
        if drop_distance <= 0:
            return 0.0

        # Time for first impact: sqrt(2 * h / g)
        t1 = math.sqrt(2.0 * drop_distance / self.GRAVITY_CM_S2)
        if restitution <= 0.0:
            return t1

        # Sum of geometric series of bounces: t_total = t1 * (1 + e) / (1 - e)
        settle_mult = (1.0 + restitution) / max(0.01, 1.0 - restitution)
        t_theoretical = t1 * settle_mult / (1.0 + damping)
        return t_theoretical

    def run_drop_probe(
        self,
        initial_z: float = 400.0,
        floor_z: float = 0.0,
        extent_z: float = 25.0,  # Half-height of prop
        mass_kg: float = 15.0,
        restitution: float = 0.40,
        linear_damping: float = 0.05,
        tolerance_pct: float = 15.0,
        max_duration_s: float = 10.0,
    ) -> PhysicsProbeResult:
        """Runs drop test simulation and verifies settle time and resting height."""
        errors: List[str] = []
        target_rest_z = floor_z + extent_z
        expected_settle = self.calculate_theoretical_settle_time(
            initial_z=initial_z,
            floor_z=target_rest_z,
            restitution=restitution,
            damping=linear_damping,
        )

        current_z = initial_z
        current_v = 0.0
        current_t = 0.0
        bounces = 0
        impact_energies: List[float] = []
        is_settled = False

        while current_t < max_duration_s:
            # Semi-implicit Euler integration (symplectic, energy-preserving)
            a = -self.GRAVITY_CM_S2 - (linear_damping * current_v)
            current_v += a * self.dt
            current_z += current_v * self.dt
            current_t += self.dt

            # Floor collision detection
            if current_z <= target_rest_z:
                current_z = target_rest_z
                impact_speed = abs(current_v)

                # Monotonically decaying impact kinetic energy
                ke = 0.5 * mass_kg * (impact_speed ** 2)
                impact_energies.append(ke)

                if impact_speed > self.v_thresh:
                    # Chaos physics bounce
                    bounces += 1
                    current_v = impact_speed * restitution
                    # Lift slightly above floor to prevent tick stickiness
                    current_z = target_rest_z + current_v * self.dt
                else:
                    # Inelastic settling: velocity below Chaos bounce threshold
                    current_v = 0.0
                    is_settled = True
                    break

        actual_settle = current_t

        # 1. Monotonic energy decay check across successive impacts
        monotonic_decay = True
        for i in range(1, len(impact_energies)):
            if impact_energies[i] > impact_energies[i - 1] * 1.01:
                monotonic_decay = False
                errors.append(f"Non-monotonic impact energy at bounce {i}: {impact_energies[i]:.2f} > {impact_energies[i-1]:.2f}")
                break

        # 2. Resting height check
        height_err = abs(current_z - target_rest_z)
        if height_err > self.h_tol:
            errors.append(
                f"Resting height {current_z:.2f}cm deviates from floor target {target_rest_z:.2f}cm by {height_err:.2f}cm"
            )

        # 3. Settle time within tolerance check
        settle_error_pct = (
            abs(actual_settle - expected_settle) / max(0.01, expected_settle)
        ) * 100.0

        if not is_settled:
            errors.append(f"Simulation failed to settle within {max_duration_s}s limit")
        elif settle_error_pct > tolerance_pct:
            errors.append(
                f"Settle time {actual_settle:.2f}s deviated by {settle_error_pct:.1f}% from expectation {expected_settle:.2f}s (tolerance {tolerance_pct}%)"
            )

        passed = len(errors) == 0 and is_settled and monotonic_decay

        return PhysicsProbeResult(
            passed=passed,
            initial_height=initial_z,
            floor_height=floor_z,
            resting_height=round(current_z, 2),
            expected_settle_time_s=round(expected_settle, 3),
            simulated_settle_time_s=round(actual_settle, 3),
            settle_time_error_pct=round(settle_error_pct, 2),
            bounce_count=bounces,
            energy_decay_monotonic=monotonic_decay,
            final_velocity=round(current_v, 4),
            details={
                "mass_kg": mass_kg,
                "restitution": restitution,
                "linear_damping": linear_damping,
                "target_rest_z": target_rest_z,
            },
            errors=errors,
        )
