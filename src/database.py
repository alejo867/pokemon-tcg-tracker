"""
Supabase backend — all read/write operations for the collection.

Credentials come from st.secrets["supabase"]["url"] and ["key"].
The Supabase client is cached at resource level (one connection per session).
"""

from typing import Dict, List

import streamlit as st


@st.cache_resource
def _client():
    from supabase import create_client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


def fetch_all() -> Dict[int, dict]:
    """Return full collection as {pokemon_number: row_dict}."""
    resp = (
        _client()
        .table("collection")
        .select("pokemon_number,quantity,quantity2,updated_at")
        .execute()
    )
    return {r["pokemon_number"]: r for r in (resp.data or [])}


def upsert(number: int, quantity: int, quantity2: int = 0) -> None:
    """Insert or update a single Pokémon's quantities."""
    _client().table("collection").upsert(
        {"pokemon_number": number, "quantity": quantity, "quantity2": quantity2},
        on_conflict="pokemon_number",
    ).execute()


def load_all_details() -> List[dict]:
    """Return all rows from pokemon_details, ordered by number."""
    resp = (
        _client()
        .table("pokemon_details")
        .select("*")
        .order("pokemon_number")
        .execute()
    )
    return resp.data or []


def bulk_upsert(rows: List[dict]) -> None:
    """
    Upsert many rows at once.
    Each row must have: pokemon_number, quantity, quantity2
    """
    if not rows:
        return
    # Supabase upsert has a practical limit; batch in chunks of 500
    chunk = 500
    for i in range(0, len(rows), chunk):
        _client().table("collection").upsert(
            rows[i : i + chunk],
            on_conflict="pokemon_number",
        ).execute()
