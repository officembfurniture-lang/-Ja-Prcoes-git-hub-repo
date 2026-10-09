from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA = "horyzont.grid-flex-workload-passport/v0.1"


def _finite_number(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _strict_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


@dataclass(frozen=True)
class Task:
    id: str
    power_kw: float
    duration_slots: int
    earliest_slot: int
    latest_end_slot: int
    deferrable: bool
    priority: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Task":
        if not isinstance(payload, dict):
            raise ValueError("task must be an object")
        identifier = payload.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("task id must be a non-empty string")
        deferrable = payload.get("deferrable", True)
        if type(deferrable) is not bool:
            raise ValueError(f"task {identifier} deferrable must be boolean")
        value = cls(
            id=identifier,
            power_kw=_finite_number(payload.get("power_kw"), f"task {identifier} power_kw"),
            duration_slots=_strict_int(payload.get("duration_slots"), f"task {identifier} duration_slots"),
            earliest_slot=_strict_int(payload.get("earliest_slot"), f"task {identifier} earliest_slot"),
            latest_end_slot=_strict_int(payload.get("latest_end_slot"), f"task {identifier} latest_end_slot"),
            deferrable=deferrable,
            priority=_strict_int(payload.get("priority", 50), f"task {identifier} priority"),
        )
        if not value.id or value.power_kw <= 0 or value.duration_slots <= 0:
            raise ValueError("task id, power_kw and duration_slots must be positive/non-empty")
        if value.earliest_slot < 0 or value.latest_end_slot <= value.earliest_slot:
            raise ValueError(f"invalid scheduling window for task {value.id}")
        if value.earliest_slot + value.duration_slots > value.latest_end_slot:
            raise ValueError(f"task {value.id} cannot fit inside its scheduling window")
        if not 0 <= value.priority <= 100:
            raise ValueError(f"task {value.id} priority must be between 0 and 100")
        return value


def _candidate_starts(task: Task) -> range:
    if not task.deferrable:
        return range(task.earliest_slot, task.earliest_slot + 1)
    return range(task.earliest_slot, task.latest_end_slot - task.duration_slots + 1)


def _fits(load: list[float], task: Task, start: int, capacity: float) -> bool:
    return all(load[index] + task.power_kw <= capacity + 1e-9 for index in range(start, start + task.duration_slots))


def _place(load: list[float], task: Task, start: int) -> None:
    for index in range(start, start + task.duration_slots):
        load[index] += task.power_kw


def schedule(
    tasks: list[Task],
    grid_stress: list[float],
    site_capacity_kw: float,
    *,
    grid_aware: bool,
) -> tuple[dict[str, int], list[float]]:
    if not grid_stress or not math.isfinite(site_capacity_kw) or site_capacity_kw <= 0:
        raise ValueError("grid_stress must be non-empty and site_capacity_kw must be positive and finite")
    horizon = len(grid_stress)
    if any(not math.isfinite(value) or value < 0 for value in grid_stress):
        raise ValueError("grid_stress values must be finite and non-negative")
    if any(task.latest_end_slot > horizon for task in tasks):
        raise ValueError("a task scheduling window exceeds the grid_stress horizon")

    load = [0.0] * horizon
    starts: dict[str, int] = {}
    ordered = sorted(tasks, key=lambda task: (task.latest_end_slot, -task.priority, task.id))
    for task in ordered:
        feasible = [start for start in _candidate_starts(task) if _fits(load, task, start, site_capacity_kw)]
        if not feasible:
            raise ValueError(f"no feasible slot for task {task.id} under the declared capacity")
        if grid_aware and task.deferrable:
            start = min(
                feasible,
                key=lambda value: (
                    sum(grid_stress[value : value + task.duration_slots]) * task.power_kw,
                    max(load[value : value + task.duration_slots]),
                    value,
                ),
            )
        else:
            start = min(feasible)
        starts[task.id] = start
        _place(load, task, start)
    return starts, load


def analyze_workload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("workload must be an object")
    slot_minutes = _strict_int(payload.get("slot_minutes"), "slot_minutes")
    site_capacity_kw = _finite_number(payload.get("site_capacity_kw"), "site_capacity_kw")
    raw_stress = payload.get("grid_stress")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_stress, list) or not raw_stress:
        raise ValueError("grid_stress must be a non-empty list")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("tasks must be a non-empty list")
    grid_stress = [_finite_number(value, f"grid_stress[{index}]") for index, value in enumerate(raw_stress)]
    tasks = [Task.from_dict(item) for item in raw_tasks]
    if slot_minutes <= 0 or 60 % slot_minutes != 0:
        raise ValueError("slot_minutes must be a positive divisor of 60")
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("task ids must be unique")

    baseline_starts, baseline_load = schedule(tasks, grid_stress, site_capacity_kw, grid_aware=False)
    optimized_starts, optimized_load = schedule(tasks, grid_stress, site_capacity_kw, grid_aware=True)
    slot_hours = slot_minutes / 60
    moved = [task for task in tasks if baseline_starts[task.id] != optimized_starts[task.id]]
    baseline_weighted_stress = sum(load * stress * slot_hours for load, stress in zip(baseline_load, grid_stress))
    optimized_weighted_stress = sum(load * stress * slot_hours for load, stress in zip(optimized_load, grid_stress))
    return {
        "schema": SCHEMA,
        "slot_minutes": slot_minutes,
        "site_capacity_kw": site_capacity_kw,
        "baseline": {
            "task_start_slots": baseline_starts,
            "load_kw": baseline_load,
            "peak_kw": max(baseline_load, default=0.0),
            "weighted_grid_stress": round(baseline_weighted_stress, 6),
        },
        "grid_aware": {
            "task_start_slots": optimized_starts,
            "load_kw": optimized_load,
            "peak_kw": max(optimized_load, default=0.0),
            "weighted_grid_stress": round(optimized_weighted_stress, 6),
        },
        "planned_shifted_energy_kwh": round(
            sum(task.power_kw * task.duration_slots * slot_hours for task in moved), 6
        ),
        "moved_task_ids": sorted(task.id for task in moved),
        "truth_boundary": {
            "input_kind": payload.get("input_kind", "unspecified"),
            "physical_savings_claimed": False,
            "statement": "This is a deterministic scheduling plan. Only metered external operation can establish energy, grid or financial outcomes.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline and grid-aware AI workload schedules")
    parser.add_argument("input", help="Workload passport JSON")
    parser.add_argument("--output", help="Optional result JSON path")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rendered = json.dumps(analyze_workload(payload), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
