"""
Persistent state stored in cache/state.json.

Tracks:
  last_api_check      – unix timestamp of last PokéAPI call
  last_seen_total     – species count as of last successful API check
  api_total           – most recent authoritative count
  known_new_pokemon   – list of {id, name} discovered since last check
"""

import json
from pathlib import Path
from typing import Any, Dict

STATE_FILE = Path(__file__).parent.parent / "cache" / "state.json"

_DEFAULTS: Dict[str, Any] = {
    "last_api_check": None,
    "last_seen_total": 0,
    "api_total": None,
    "known_new_pokemon": [],
}


def load_state() -> Dict[str, Any]:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key, default in _DEFAULTS.items():
                data.setdefault(key, default)
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return dict(_DEFAULTS)


def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, default=str)
