# ⚡ Pokédex TCG Tracker

A personal dashboard to visualize and manage your Pokémon Trading Card Game collection.
Reads your Excel tracker, syncs live totals from PokéAPI, and shows exactly where your
collection stands — by generation, by gap, by streak.

---

## Stack

**Python + Streamlit** — chosen because:
- Excel → pandas is one line of code
- Streamlit handles all UI scaffolding with zero JavaScript
- Deployable in 5 minutes on Streamlit Community Cloud (free tier)
- Zero infrastructure to maintain for personal use

> **Next.js alternative** would be better if you want to share the app publicly,
> need offline PWA support, or want sub-100ms interactions on large datasets.
> Migrate when the Streamlit limits start to hurt.

---

## Quick Start

### 1. Clone / set up

```bash
cd ~/pokemon-tcg-tracker
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add your Excel file

Copy your tracker into the `data/` folder:

```bash
cp "~/path/to/TCG Tracker_New_04.07.26.xlsx" data/
```

The app auto-detects it. Alternatively, upload it via the sidebar file uploader.

### 3. Run

```bash
streamlit run app.py
```

Opens at [http://localhost:8501](http://localhost:8501).

---

## Project Structure

```
pokemon-tcg-tracker/
├── app.py                   # Main Streamlit dashboard (entry point)
├── requirements.txt
├── .streamlit/
│   └── config.toml          # Dark theme + server config
├── src/
│   ├── excel_parser.py      # Reads + validates Tracking Collection sheet
│   ├── pokeapi.py           # PokéAPI client with 24h file cache
│   ├── state.py             # Persistent state (last_seen_total, etc.)
│   └── analytics.py        # KPIs, gap analysis, generation stats, streaks
├── data/                    # Put your Excel here (gitignored)
└── cache/                   # Auto-generated API cache + state (gitignored)
```

---

## Excel Format Expected

**Sheet:** `Tracking Collection`

| Column | Format | Notes |
|--------|--------|-------|
| A | `#1`, `#25`, `#150` | National Dex number |
| B | `0` or `1` | Primary quantity |
| C | `0` or `1` | Secondary quantity / variant |

**Ownership rule:** collected if `Quantity >= 1` OR `Quantity2 >= 1`.

**Rows 1–N before the data:** any summary rows (Total, Collected, Left) are
automatically skipped. The parser finds the first `#N` row dynamically.

---

## Dashboard Features

### Overview Tab
- 6 KPI cards: Total, Collected, Missing, % Complete, Largest Gap, Best Streak
- Animated collection progress bar
- Per-generation breakdown bars (Gen 1–9)
- Random collected Pokémon carousel (shuffle button)

### Pokédex Grid Tab
- One tile per Pokémon (green = collected, dark = missing, purple = newly detected)
- Filter by Generation
- Highlight/jump to any number
- Hover tooltip shows `#N`

### Missing Tab
- Total gap count + missing Pokémon count
- Grouped by large gaps (≥5) and individual singles
- **Export shopping list as CSV** — ready to bring to a card show

### Duplicates Tab (Phase 2 shell)
- Shows any Quantity2 values from current Excel
- Schema documented and ready to implement

---

## PokéAPI Integration

On first run (and then at most once per 24h), the app calls:

```
GET https://pokeapi.co/api/v2/pokemon-species?limit=1
```

The `count` field becomes the authoritative total. Responses are cached in
`cache/pokeapi_species_total.json`.

**New Pokémon detection:** if the API total exceeds `last_seen_total` (stored in
`cache/state.json`), the delta is fetched and a banner appears showing the new
Pokémon. They are automatically counted as missing until added to your Excel.

**Force a fresh fetch:** click *🔄 Force Refresh API* in the sidebar.

---

## Updating Your Collection

1. Edit your Excel file normally (update Quantity / Quantity2 columns).
2. Reload the app (Streamlit hot-reloads, or press `R`).
3. All KPIs recompute automatically from the file.

No database to migrate. No sync step. The Excel **is** the database.

---

## Deployment (Streamlit Community Cloud — free)

1. Push this repo to GitHub (Excel file is gitignored — upload it via the sidebar
   after deploy, or add a Streamlit secret path).
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app.
3. Point to your repo + `app.py`.
4. Done. Public URL generated automatically.

> For private deployment: Streamlit Cloud supports private repos on the free tier
> for one app. Alternatively, run on a $5/mo Fly.io or Railway instance.

---

## Roadmap

### Phase 1 ✅ (current)
- Excel parsing with validation
- PokéAPI sync + new Pokémon detection
- KPI dashboard, generation bars, progress bar
- Pokédex grid with generation filter
- Gap analysis + CSV export
- Collected carousel

### Phase 2 (duplicates)
- Read `Duplicates` sheet (schema already defined)
- Per-Pokémon variant cards
- Trade/sell/keep tagging
- Export "trade binder" CSV
- Excel export with new rows appended

### Phase 3 (value + rarity)
- TCGPlayer price integration (read-only API)
- Rarity tags per card
- Collection value estimate
- "Best trades" suggestions based on duplicates

---

## Maintenance

| Task | How often | Action |
|------|-----------|--------|
| Update collection | After buying cards | Edit Excel Quantity column |
| New Pokémon released | Automatic | App detects via PokéAPI banner |
| Python deps | ~quarterly | `pip install -U -r requirements.txt` |
| Streamlit updates | ~monthly | Check [streamlit changelog](https://docs.streamlit.io/library/changelog) |

The only manual step is updating your Excel file. Everything else is automatic.
