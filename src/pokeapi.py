"""
PokéAPI client with 24-hour file-based cache.

Endpoints used:
  GET /pokemon-species?limit=1      → authoritative total count
  GET /pokemon-species?offset=N&limit=M  → delta species list
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

_CACHE_DIR = Path(__file__).parent.parent / "cache"
_CACHE_TTL = 86_400  # 24 hours
_BASE = "https://pokeapi.co/api/v2"
_TIMEOUT = 12


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"pokeapi_{key}.json"


def _load(key: str) -> Optional[dict]:
    fp = _cache_path(key)
    if not fp.exists():
        return None
    try:
        with open(fp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if time.time() - data.get("_ts", 0) < _CACHE_TTL:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save(key: str, payload: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload["_ts"] = time.time()
    with open(_cache_path(key), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def get_authoritative_total() -> Tuple[int, float]:
    """
    Return (total_species_count, cached_at_timestamp).
    Reads from cache if fresh; otherwise hits PokéAPI.
    """
    cached = _load("species_total")
    if cached:
        return int(cached["count"]), float(cached["_ts"])

    resp = requests.get(
        f"{_BASE}/pokemon-species",
        params={"limit": 1},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    count = int(resp.json()["count"])
    _save("species_total", {"count": count})
    return count, time.time()


def _fetch_species_range(offset: int, limit: int) -> List[Dict]:
    """Fetch a page of species entries, with caching."""
    key = f"species_{offset}_{limit}"
    cached = _load(key)
    if cached:
        return cached["results"]

    resp = requests.get(
        f"{_BASE}/pokemon-species",
        params={"offset": offset, "limit": limit},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    _save(key, {"results": results})
    return results


def check_new_pokemon(last_seen_total: int, current_total: int) -> List[Dict]:
    """
    Return list of {id, name} for Pokémon that appeared since last_seen_total.
    Returns empty list if nothing new or last_seen_total == 0 (first run).
    """
    if last_seen_total == 0 or current_total <= last_seen_total:
        return []

    delta = current_total - last_seen_total
    results = _fetch_species_range(last_seen_total, delta)

    new_list = []
    for item in results:
        url_parts = item.get("url", "").rstrip("/").split("/")
        try:
            poke_id = int(url_parts[-1])
        except (ValueError, IndexError):
            poke_id = None
        new_list.append({"id": poke_id, "name": item.get("name", "unknown")})

    return new_list


def invalidate_total_cache() -> None:
    """Force a fresh API fetch next time get_authoritative_total is called."""
    fp = _cache_path("species_total")
    if fp.exists():
        fp.unlink()
