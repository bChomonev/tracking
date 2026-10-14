"""Canonical definition of the 12 team rate metrics and the 4 tactical stacks.

Vector dimension order is the order of ``TEAM_METRICS``. Changing order, weights or
directions invalidates every stored ``stats_vector`` — recalibrate after editing.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricDef:
    key: str
    label: str
    stack: str
    direction: int  # +1 higher is better, -1 lower is better
    weight: float
    unit: str


@dataclass(frozen=True, slots=True)
class StackDef:
    stack_id: str
    name: str
    score_column: str


STACKS: tuple[StackDef, ...] = (
    StackDef("STACK_01", "Work Rate & Press", "stack_01_work_rate_score"),
    StackDef("STACK_02", "Progression & Territory", "stack_02_progression_score"),
    StackDef("STACK_03", "Attacking Execution", "stack_03_attacking_score"),
    StackDef("STACK_04", "Defensive & Transition", "stack_04_defensive_score"),
)

TEAM_METRICS: tuple[MetricDef, ...] = (
    MetricDef("distance_per_90_km", "Team Distance Covered", "STACK_01", +1, 1.0, "km"),
    MetricDef(
        "sprints_per_min_oop", "Sprints / Min Out of Possession", "STACK_01", +1, 1.2, "sprints/min"
    ),
    MetricDef("ppda", "Pressing Intensity (PPDA)", "STACK_01", -1, 1.4, "passes/action"),
    MetricDef("field_tilt_pct", "Field Tilt", "STACK_02", +1, 1.4, "%"),
    MetricDef(
        "line_breaks_per_100_touches",
        "Line Breaks / 100 Touches",
        "STACK_02",
        +1,
        1.2,
        "per 100 touches",
    ),
    MetricDef("box_touches_per_90", "Box Touches", "STACK_02", +1, 1.2, "touches"),
    MetricDef("npxg_created", "Non-Penalty xG Created", "STACK_03", +1, 1.8, "xG"),
    MetricDef("npxg_per_shot", "npxG per Shot", "STACK_03", +1, 1.4, "xG/shot"),
    MetricDef("finishing_delta", "Finishing Delta (xGOT − npxG)", "STACK_03", +1, 1.0, "xG"),
    MetricDef("npxg_conceded", "Non-Penalty xG Conceded", "STACK_04", -1, 1.8, "xG"),
    MetricDef("npxga_per_shot_faced", "npxG per Shot Faced", "STACK_04", -1, 1.4, "xG/shot"),
    MetricDef("gk_goals_prevented", "GK Goals Prevented", "STACK_04", +1, 1.0, "goals"),
)

METRIC_KEYS: tuple[str, ...] = tuple(m.key for m in TEAM_METRICS)
N_DIMS = len(TEAM_METRICS)

DIRECTIONS = [m.direction for m in TEAM_METRICS]
WEIGHTS = [m.weight for m in TEAM_METRICS]

# Dimension indices belonging to each stack, in vector order.
STACK_DIMS: dict[str, tuple[int, ...]] = {
    s.stack_id: tuple(i for i, m in enumerate(TEAM_METRICS) if m.stack == s.stack_id)
    for s in STACKS
}

Z_CLIP = 4.5
