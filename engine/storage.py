from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .utils import ensure_dir

RUNS_DIR = os.path.join(os.getcwd(), "runs")
EXPORTS_DIR = os.path.join(os.getcwd(), "exports")


def init_storage() -> None:
    ensure_dir(RUNS_DIR)
    ensure_dir(EXPORTS_DIR)


def run_path(run_id: str) -> str:
    return os.path.join(RUNS_DIR, f"{run_id}.json")


def save_run(run_id: str, payload: Dict[str, Any]) -> None:
    init_storage()
    with open(run_path(run_id), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)


def load_run(run_id: str) -> Dict[str, Any]:
    with open(run_path(run_id), "r", encoding="utf-8") as f:
        return json.load(f)


def list_runs(limit: int = 200) -> List[Dict[str, Any]]:
    init_storage()
    files = [x for x in os.listdir(RUNS_DIR) if x.endswith(".json")]
    files.sort(reverse=True)
    out: List[Dict[str, Any]] = []
    for fn in files[:limit]:
        path = os.path.join(RUNS_DIR, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out
