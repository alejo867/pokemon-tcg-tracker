"""
One-time migration: import Excel collection data into Supabase.

Usage:
    python migrate_excel.py
    python migrate_excel.py path/to/your/file.xlsx

Reads the 'Tracking Collection' sheet and upserts every row into the
Supabase 'collection' table. Safe to re-run — uses upsert (no duplicates).
"""

import sys
from pathlib import Path

# Load secrets from .streamlit/secrets.toml before importing database module
import toml, os

secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
if secrets_path.exists():
    secrets = toml.load(secrets_path)
    os.environ["SUPABASE_URL"] = secrets["supabase"]["url"]
    os.environ["SUPABASE_KEY"] = secrets["supabase"]["key"]

from supabase import create_client

DEFAULT_EXCEL = Path(__file__).parent / "data" / "TCG Tracker_New_04.07.26.xlsx"


def run(excel_path: Path) -> None:
    # ── Load secrets ──────────────────────────────────────────────────────────
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("ERROR: Supabase credentials not found in .streamlit/secrets.toml")
        sys.exit(1)

    # ── Parse Excel ───────────────────────────────────────────────────────────
    sys.path.insert(0, str(Path(__file__).parent))
    from src.excel_parser import load_collection

    print(f"Reading: {excel_path}")
    entries, warnings = load_collection(str(excel_path))

    if warnings:
        print(f"  ⚠️  {len(warnings)} warning(s):")
        for w in warnings[:10]:
            print(f"    {w}")

    print(f"  Loaded {len(entries)} entries")

    # ── Build upsert payload ──────────────────────────────────────────────────
    rows = [
        {
            "pokemon_number": e.number,
            "quantity": e.quantity,
            "quantity2": e.quantity2,
        }
        for e in entries.values()
    ]

    # ── Upsert to Supabase ────────────────────────────────────────────────────
    client = create_client(url, key)
    chunk = 500
    total = len(rows)
    print(f"Upserting {total} rows to Supabase …")

    for i in range(0, total, chunk):
        batch = rows[i : i + chunk]
        client.table("collection").upsert(batch, on_conflict="pokemon_number").execute()
        print(f"  {min(i + chunk, total)}/{total}")

    print("✅ Migration complete.")

    collected = sum(1 for e in entries.values() if e.collected)
    print(f"   {collected} collected, {len(entries) - collected} missing")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXCEL
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    run(path)
