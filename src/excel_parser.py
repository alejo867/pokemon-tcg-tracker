"""
Excel parser for TCG Tracker_New_04.07.26.xlsx.

Reads the 'Tracking Collection' sheet:
  Column A: Number  → "#1", "#25", "#150"
  Column B: Quantity
  Column C: Quantity2 (duplicates / variants)

Ownership rule:
  collected  ←  Quantity >= 1  OR  Quantity2 >= 1
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd


@dataclass
class PokemonEntry:
    number: int
    quantity: int
    quantity2: int

    @property
    def collected(self) -> bool:
        return self.quantity >= 1 or self.quantity2 >= 1

    @property
    def has_duplicate(self) -> bool:
        return self.quantity2 >= 1


def _parse_qty(val) -> int:
    if val is None or (hasattr(val, '__class__') and val.__class__.__name__ == 'float'
                       and val != val):  # NaN check without importing math
        return 0
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return 0
        return max(0, int(float(str(val).strip())))
    except (ValueError, TypeError):
        return 0


def load_collection(source) -> Tuple[Dict[int, PokemonEntry], List[str]]:
    """
    Load the Tracking Collection sheet.

    source: str/Path (file path) or file-like object (Streamlit uploader)
    Returns (entries_dict keyed by int dex number, warnings_list)
    """
    warnings: List[str] = []
    entries: Dict[int, PokemonEntry] = {}

    try:
        df = pd.read_excel(
            source,
            sheet_name="Tracking Collection",
            header=None,
            dtype=str,
            engine="openpyxl",
        )
    except Exception as exc:
        raise ValueError(f"Failed to read Excel file: {exc}") from exc

    # Find first row whose column A starts with "#" followed by digits
    data_start = None
    for idx, row in df.iterrows():
        val = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if val.startswith("#") and val[1:].isdigit():
            data_start = idx
            break

    if data_start is None:
        raise ValueError(
            "Could not find Pokémon data rows. "
            "Expected '#N' format in column A of 'Tracking Collection'."
        )

    data_df = df.iloc[data_start:].reset_index(drop=True)
    seen: set = set()

    for row_idx, row in data_df.iterrows():
        raw = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if not raw.startswith("#"):
            continue

        num_str = raw.lstrip("#")
        if not num_str.isdigit():
            warnings.append(f"Row {data_start + row_idx}: invalid number '{raw}' — skipped")
            continue

        number = int(num_str)

        if number in seen:
            warnings.append(f"Duplicate row for #{number} at row {data_start + row_idx}")
        seen.add(number)

        qty = _parse_qty(row.iloc[1] if len(row) > 1 else None)
        qty2 = _parse_qty(row.iloc[2] if len(row) > 2 else None)

        entries[number] = PokemonEntry(number=number, quantity=qty, quantity2=qty2)

    # Check sequential integrity
    if entries:
        numbers = sorted(entries.keys())
        expected = set(range(numbers[0], numbers[-1] + 1))
        missing_rows = expected - set(numbers)
        if missing_rows:
            sample = sorted(missing_rows)[:5]
            tail = f" and {len(missing_rows) - 5} more" if len(missing_rows) > 5 else ""
            warnings.append(
                f"Excel is missing rows for: #{', #'.join(map(str, sample))}{tail}"
            )

    return entries, warnings
