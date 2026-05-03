"""
One-time fetch: pull every Pokémon's details from PokéAPI → store in Supabase.

Uses 15 concurrent threads. ~1025 Pokémon × 2 endpoints ≈ 60-90 seconds.
Safe to re-run — upserts only fetch what's missing.

Usage:
    python fetch_pokemon_details.py
    python fetch_pokemon_details.py 151        # only Gen 1
"""

import concurrent.futures
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import toml
from supabase import create_client

# ── Credentials ───────────────────────────────────────────────────────────────
secrets = toml.load(Path(__file__).parent / ".streamlit" / "secrets.toml")
client  = create_client(secrets["supabase"]["url"], secrets["supabase"]["key"])

BASE = "https://pokeapi.co/api/v2"
STAT_MAP = {
    "hp": "hp", "attack": "attack", "defense": "defense",
    "special-attack": "sp_attack", "special-defense": "sp_defense", "speed": "speed",
}


def fetch_one(num: int) -> Optional[dict]:
    try:
        r_poke = requests.get(f"{BASE}/pokemon/{num}", timeout=12)
        if r_poke.status_code != 200:
            return None
        poke = r_poke.json()

        r_spec = requests.get(f"{BASE}/pokemon-species/{num}", timeout=12)
        spec   = r_spec.json() if r_spec.status_code == 200 else {}

        types = [t["type"]["name"] for t in poke.get("types", [])]
        stats = {
            STAT_MAP[s["stat"]["name"]]: s["base_stat"]
            for s in poke.get("stats", [])
            if s["stat"]["name"] in STAT_MAP
        }

        return {
            "pokemon_number": num,
            "name":           poke["name"],
            "type1":          types[0] if len(types) > 0 else None,
            "type2":          types[1] if len(types) > 1 else None,
            "height_dm":      poke.get("height"),
            "weight_hg":      poke.get("weight"),
            "is_legendary":   bool(spec.get("is_legendary", False)),
            "is_mythical":    bool(spec.get("is_mythical",  False)),
            **stats,
        }
    except Exception as exc:
        print(f"  ⚠  #{num}: {exc}")
        return None


def run(total: int = 1025, workers: int = 15) -> None:
    # Find out what's already stored
    existing_resp = (
        client.table("pokemon_details")
        .select("pokemon_number")
        .execute()
    )
    existing = {r["pokemon_number"] for r in (existing_resp.data or [])}
    to_fetch  = [n for n in range(1, total + 1) if n not in existing]

    if not to_fetch:
        print(f"✅ All {total} Pokémon details already in Supabase — nothing to do.")
        return

    print(f"Fetching {len(to_fetch)} Pokémon (skipping {len(existing)} already stored)…")
    t0      = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(fetch_one, n): n for n in to_fetch}
        done = 0
        for future in concurrent.futures.as_completed(future_map):
            done += 1
            data = future.result()
            if data:
                results.append(data)
            if done % 100 == 0 or done == len(to_fetch):
                elapsed = time.time() - t0
                print(f"  {done}/{len(to_fetch)}  ({elapsed:.0f}s)")

    # Upsert in batches of 200
    chunk = 200
    for i in range(0, len(results), chunk):
        client.table("pokemon_details").upsert(
            results[i : i + chunk], on_conflict="pokemon_number"
        ).execute()

    print(f"\n✅ Done — {len(results)} records stored in {time.time() - t0:.0f}s.")
    fails = len(to_fetch) - len(results)
    if fails:
        print(f"   ⚠  {fails} failed (likely form/variant Pokémon without species entry).")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 1025
    run(total=limit)
