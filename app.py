"""
Pokémon TCG Collection Tracker — Streamlit dashboard.

Entry point: streamlit run app.py
"""

import csv
import io
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.analytics import GENERATIONS, compute_kpis, find_gaps, get_generation_stats
from src.excel_parser import PokemonEntry, load_collection
from src.pokeapi import (
    check_new_pokemon,
    get_authoritative_total,
    invalidate_total_cache,
)
from src.state import load_state, save_state

DEFAULT_EXCEL = Path(__file__).parent / "data" / "TCG Tracker_New_04.07.26.xlsx"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pokédex TCG Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"]          { background: #111827; border-right: 1px solid #1f2937; }
h1, h2, h3, h4 { color: #e6f1ff !important; }
.stTabs [data-baseweb="tab-list"] { background: #111827; border-radius: 8px; }
.stTabs [data-baseweb="tab"]      { color: #94a3b8; }
.stTabs [aria-selected="true"]    { color: #ef4444 !important; }

/* ── KPI cards ── */
.kpi-card {
    background: #1a1a2e;
    border: 1px solid #2d2d44;
    border-radius: 12px;
    padding: 18px 14px 14px;
    text-align: center;
    min-height: 100px;
}
.kpi-label {
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 26px;
    font-weight: 800;
    color: #e6f1ff;
    line-height: 1.1;
}
.kpi-sub { font-size: 11px; color: #475569; margin-top: 5px; }
.kpi-green  .kpi-value { color: #4ade80; }
.kpi-red    .kpi-value { color: #f87171; }
.kpi-yellow .kpi-value { color: #fbbf24; }
.kpi-blue   .kpi-value { color: #60a5fa; }
.kpi-purple .kpi-value { color: #c084fc; }

/* ── Overall progress bar ── */
.prog-track {
    background: #1f2937;
    border-radius: 999px;
    height: 24px;
    overflow: hidden;
    border: 1px solid #374151;
    margin: 6px 0 4px;
}
.prog-fill {
    height: 24px;
    border-radius: 999px;
    background: linear-gradient(90deg, #dc2626 0%, #ef4444 20%, #fb923c 50%, #fbbf24 75%, #4ade80 100%);
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding-right: 12px;
    font-size: 12px;
    font-weight: 700;
    color: #fff;
    min-width: 48px;
    transition: width 0.6s cubic-bezier(.4,0,.2,1);
}
.prog-labels {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #374151;
    margin-top: 2px;
}

/* ── Generation bars ── */
.gen-row {
    background: #161b27;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 8px 14px;
    margin-bottom: 6px;
}
.gen-meta {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 5px;
}
.gen-track {
    background: #0d1117;
    border-radius: 4px;
    height: 7px;
    overflow: hidden;
}
.gen-fill {
    height: 7px;
    border-radius: 4px;
    background: linear-gradient(90deg, #ef4444, #fbbf24 60%, #4ade80);
}

/* ── Pokédex grid ── */
.pdx-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    max-height: 560px;
    overflow-y: auto;
    padding: 10px;
    background: #0a0f1a;
    border-radius: 10px;
    border: 1px solid #1e293b;
}
.pt {
    width: 26px; height: 26px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 6.5px;
    color: rgba(255,255,255,0.55);
    cursor: default;
    transition: transform 0.12s, filter 0.12s;
    position: relative;
}
.pt:hover { transform: scale(1.45); filter: brightness(1.4); z-index: 20; }
.pt-c { background: #14532d; border: 1px solid #22c55e; }
.pt-m { background: #1a1f2e; border: 1px solid #1e293b; }
.pt-n { background: #3b0764; border: 1px solid #9333ea; }
.pt-hi { outline: 3px solid #fbbf24 !important; transform: scale(1.5) !important; z-index: 30; }

/* ── Gap chips ── */
.gap-wrap { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.gap-chip {
    background: #1a0f0f;
    border: 1px solid #7f1d1d;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    color: #fca5a5;
    white-space: nowrap;
}
.gap-chip-lg { border-color: #dc2626; background: #2d0f0f; color: #fecaca; font-weight: 600; }

/* ── Banners ── */
.warn-banner {
    background: #1c1408;
    border: 1px solid #b45309;
    border-radius: 8px;
    padding: 11px 15px;
    color: #fcd34d;
    font-size: 13px;
    margin-bottom: 14px;
}
.new-banner {
    background: #150a2e;
    border: 1px solid #7c3aed;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 16px;
}
.new-banner-title { color: #c4b5fd; font-size: 15px; font-weight: 700; margin-bottom: 8px; }
.new-chip {
    display: inline-block;
    background: #2e1065;
    border-radius: 4px;
    padding: 2px 8px;
    margin: 2px;
    font-size: 12px;
    color: #e9d5ff;
}

/* ── Carousel cards ── */
.cx-card {
    background: #1a1a2e;
    border: 1px solid #2d2d44;
    border-radius: 12px;
    padding: 18px 10px;
    text-align: center;
    min-height: 130px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.cx-num  { font-size: 10px; color: #475569; margin-bottom: 3px; }
.cx-icon { font-size: 44px; margin-bottom: 6px; }
.cx-name { font-size: 14px; font-weight: 700; color: #fbbf24; }
.cx-qty  { font-size: 11px; color: #4ade80; margin-top: 4px; }

/* ── Section headers ── */
.sec-hdr {
    font-size: 15px;
    font-weight: 700;
    color: #e6f1ff;
    margin: 22px 0 10px;
    padding-bottom: 6px;
    border-bottom: 2px solid #ef4444;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Legend ── */
.legend {
    display: flex; gap: 18px; margin: 8px 0 6px;
    font-size: 12px; color: #64748b;
}
.legend-dot {
    display: inline-block;
    width: 13px; height: 13px;
    border-radius: 3px;
    vertical-align: middle;
    margin-right: 5px;
}

/* ── Misc ── */
.small-muted { font-size: 11px; color: #374151; }
.phase2-notice {
    background: #1e1b2e;
    border: 1px dashed #4338ca;
    border-radius: 8px;
    padding: 12px 16px;
    color: #818cf8;
    font-size: 13px;
    margin-bottom: 16px;
}
</style>
"""

# ── Cached helpers (session-level) ────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _cached_api_total():
    return get_authoritative_total()


@st.cache_data(show_spinner=False)
def _cached_load_collection(source_key, source):
    return load_collection(source)


# ── Rendering helpers ─────────────────────────────────────────────────────────

def kpi_card(label: str, value: str, sub: str = "", variant: str = "") -> str:
    cls = f"kpi-card kpi-{variant}" if variant else "kpi-card"
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f'<div class="{cls}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>{sub_html}</div>'


def render_progress(pct: float, collected: int, total: int) -> str:
    safe_pct = min(100.0, max(0.0, pct))
    return f"""
    <div class="prog-track">
      <div class="prog-fill" style="width:{safe_pct:.2f}%">{safe_pct:.1f}%</div>
    </div>
    <div class="prog-labels"><span>0</span><span>{collected:,} collected</span><span>{total:,} total</span></div>
    """


def render_gen_bars(gen_stats: dict) -> str:
    rows = []
    for name, d in gen_stats.items():
        pct = d["pct"]
        rows.append(f"""
        <div class="gen-row">
          <div class="gen-meta">
            <span>{name}</span>
            <span>{d['collected']}/{d['total']} &nbsp;·&nbsp; {pct:.0f}%</span>
          </div>
          <div class="gen-track">
            <div class="gen-fill" style="width:{pct:.2f}%"></div>
          </div>
        </div>""")
    return "".join(rows)


def render_grid(entries: dict, display_start: int, display_end: int,
                new_ids: set, highlight: Optional[int] = None) -> str:
    tiles = []
    for num in range(display_start, display_end + 1):
        entry = entries.get(num)
        if num in new_ids:
            cls, lbl = "pt pt-n", "★"
        elif entry and entry.collected:
            cls, lbl = "pt pt-c", "✓"
        else:
            cls, lbl = "pt pt-m", ""

        extra = ' class="pt pt-c pt-hi"' if num == highlight else f' class="{cls}"'
        tiles.append(f'<div{extra} title="#{num}">{lbl}</div>')

    return f'<div class="pdx-grid">{"".join(tiles)}</div>'


def gaps_csv(gaps) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["start", "end", "count", "label"])
    for g in gaps:
        w.writerow([g.start, g.end, g.size, g.label])
    return buf.getvalue().encode()


def fmt_ts(ts) -> str:
    if ts is None:
        return "Never"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


POKEBALL_ICONS = ["⚡", "🔴", "🌊", "🌿", "🔥", "❄️", "🌙", "☀️", "💜", "⭐"]


# ── Tab renderers ─────────────────────────────────────────────────────────────

def tab_overview(kpis: dict, gen_stats: dict, entries: dict) -> None:
    # KPIs
    cols = st.columns(6, gap="small")
    gap = kpis["largest_gap"]
    st_start, st_end, st_len = kpis["longest_streak"]

    kpi_defs = [
        ("Total Pokémon",  f"{kpis['effective_total']:,}", "Authoritative (API)", "blue"),
        ("Collected",      f"{kpis['collected']:,}",       "In your Excel",       "green"),
        ("Missing",        f"{kpis['missing']:,}",         "Not yet owned",       "red"),
        ("% Complete",     f"{kpis['pct_complete']:.1f}%", "Of all known",        "yellow"),
        ("Largest Gap",    gap.label if gap else "—",
                           f"{gap.size} Pokémon" if gap else "", ""),
        ("Best Streak",    f"{st_len:,}",
                           f"#{st_start}–#{st_end}" if st_len else "", "purple"),
    ]
    for col, (label, value, sub, var) in zip(cols, kpi_defs):
        with col:
            st.markdown(kpi_card(label, value, sub, var), unsafe_allow_html=True)

    # Progress bar
    st.markdown('<div class="sec-hdr">🎯 Collection Progress</div>', unsafe_allow_html=True)
    st.markdown(
        render_progress(kpis["pct_complete"], kpis["collected"], kpis["effective_total"]),
        unsafe_allow_html=True,
    )

    # Generation breakdown
    st.markdown('<div class="sec-hdr">📚 By Generation</div>', unsafe_allow_html=True)
    st.markdown(render_gen_bars(gen_stats), unsafe_allow_html=True)

    # Carousel
    st.markdown('<div class="sec-hdr">✨ Collected Spotlight</div>', unsafe_allow_html=True)
    collected_nums = [n for n, e in entries.items() if e.collected]

    if not collected_nums:
        st.info("No collected Pokémon yet.")
        return

    if "carousel_sample" not in st.session_state:
        st.session_state.carousel_sample = random.sample(collected_nums, min(5, len(collected_nums)))

    col_shuffle, _ = st.columns([1, 5])
    with col_shuffle:
        if st.button("🔀 Shuffle", key="shuffle_carousel"):
            st.session_state.carousel_sample = random.sample(
                collected_nums, min(5, len(collected_nums))
            )

    cx_cols = st.columns(5)
    for col, num in zip(cx_cols, st.session_state.carousel_sample):
        icon = POKEBALL_ICONS[num % len(POKEBALL_ICONS)]
        entry = entries[num]
        qty_text = f"×{entry.quantity}" if entry.quantity > 1 else ""
        with col:
            st.markdown(
                f'<div class="cx-card">'
                f'<div class="cx-num">#{num:04d}</div>'
                f'<div class="cx-icon">{icon}</div>'
                f'<div class="cx-name">Pokémon #{num}</div>'
                f'<div class="cx-qty">{qty_text if qty_text else "Collected ✓"}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def tab_grid(entries: dict, api_total: int, new_ids: set) -> None:
    legend_html = """
    <div class="legend">
      <span><span class="legend-dot" style="background:#14532d;border:1px solid #22c55e"></span>Collected</span>
      <span><span class="legend-dot" style="background:#1a1f2e;border:1px solid #1e293b"></span>Missing</span>
      <span><span class="legend-dot" style="background:#3b0764;border:1px solid #9333ea"></span>New (not in Excel)</span>
    </div>
    """
    st.markdown(legend_html, unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    with c1:
        gen_options = ["All Generations"] + list(GENERATIONS.keys())
        selected_gen = st.selectbox("Filter by Generation", gen_options)
    with c2:
        jump = st.number_input("Highlight #", min_value=1, max_value=api_total, value=1, step=1)

    if selected_gen == "All Generations":
        g_start, g_end = 1, api_total
    else:
        g_start, g_end = GENERATIONS[selected_gen]
        g_end = min(g_end, api_total)

    count = g_end - g_start + 1
    highlight_num = jump if g_start <= jump <= g_end else None
    st.caption(f"Showing #{g_start}–#{g_end} · {count:,} Pokémon")

    st.markdown(
        render_grid(entries, g_start, g_end, new_ids, highlight=highlight_num),
        unsafe_allow_html=True,
    )


def tab_missing(gaps, api_total: int) -> None:
    if not gaps:
        st.success("🎉 Perfect collection — no missing Pokémon!")
        return

    total_missing = sum(g.size for g in gaps)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Gaps", len(gaps))
    c2.metric("Missing Pokémon", total_missing)
    c3.metric("Largest Gap", f"{max(g.size for g in gaps)} Pokémon")

    st.download_button(
        "📥 Export Shopping List (CSV)",
        data=gaps_csv(gaps),
        file_name="missing_pokemon_shopping_list.csv",
        mime="text/csv",
        use_container_width=False,
    )

    st.markdown("---")
    sort_opt = st.radio(
        "Sort by",
        ["Largest gap first", "Number ascending"],
        horizontal=True,
        key="gap_sort",
    )
    sorted_gaps = (
        sorted(gaps, key=lambda g: -g.size)
        if sort_opt.startswith("Largest")
        else sorted(gaps, key=lambda g: g.start)
    )

    # Group into large (≥5) and small (<5)
    large = [g for g in sorted_gaps if g.size >= 5]
    small = [g for g in sorted_gaps if g.size < 5]

    if large:
        st.markdown('<div class="sec-hdr">🔴 Large Gaps (≥5 missing)</div>', unsafe_allow_html=True)
        chips = "".join(
            f'<span class="gap-chip gap-chip-lg">{g.label} &nbsp;<em style="font-weight:300">{g.size}</em></span>'
            for g in large
        )
        st.markdown(f'<div class="gap-wrap">{chips}</div>', unsafe_allow_html=True)

    if small:
        st.markdown('<div class="sec-hdr">🟡 Individual Missing</div>', unsafe_allow_html=True)
        chips = "".join(
            f'<span class="gap-chip">{g.label}</span>' for g in small[:200]
        )
        st.markdown(f'<div class="gap-wrap">{chips}</div>', unsafe_allow_html=True)
        if len(small) > 200:
            st.caption(f"… and {len(small) - 200} more")


def tab_duplicates(entries: dict) -> None:
    st.markdown(
        '<div class="phase2-notice">🔧 <strong>Phase 2 Feature</strong> — '
        'Schema is finalized; full UI coming in the next release. '
        'The <em>Duplicates</em> sheet in your Excel is reserved for this data.</div>',
        unsafe_allow_html=True,
    )

    dupes = [e for e in entries.values() if e.has_duplicate]
    if dupes:
        st.markdown(f"**{len(dupes)} Pokémon** have a Quantity2 value (current Excel data):")
        st.dataframe(
            pd.DataFrame([{"#": e.number, "Qty": e.quantity, "Qty2": e.quantity2} for e in dupes]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No Quantity2 values in the current Excel file.")

    st.markdown("""
### Phase 2 Duplicates Schema

The `Duplicates` sheet will use these columns:

| Column | Type | Description |
|---|---|---|
| `pokemon_number` | int | National Dex # |
| `variant_name` | str | Card set / illustration ID |
| `quantity` | int | Copies owned |
| `notes` | str | `keep` · `sell` · `trade` |

**Phase 2 Dashboard panels:**
- Cards available to trade or sell
- Total duplicate count by Pokémon
- Export "trade binder" as CSV
- Value estimation hook (future Phase 3)
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    state = load_state()

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚡ Pokédex TCG Tracker")
        st.markdown("---")

        st.markdown("**📁 Excel File**")
        has_default = DEFAULT_EXCEL.exists()
        uploaded = None

        if has_default:
            st.success(f"✓ `{DEFAULT_EXCEL.name}`")
        else:
            uploaded = st.file_uploader(
                "Upload your TCG Tracker Excel",
                type=["xlsx", "xls"],
                help="Drag and drop or click to upload",
            )
            if not uploaded:
                st.caption(f"Or place it at:\n`data/{DEFAULT_EXCEL.name}`")

        st.markdown("---")
        st.markdown("**⚙️ Settings**")
        count_untracked = st.toggle(
            "Count new Pokémon as missing",
            value=True,
            help="Pokémon found in PokéAPI but absent from Excel are treated as missing.",
        )

        st.markdown("---")
        st.markdown("**🌐 PokéAPI**")

        if st.button("🔄 Force Refresh API", use_container_width=True):
            invalidate_total_cache()
            _cached_api_total.clear()
            st.rerun()

        api_ts = state.get("last_api_check")
        st.markdown(
            f'<div class="small-muted">Last checked: {fmt_ts(api_ts)}</div>',
            unsafe_allow_html=True,
        )

    # ── Determine source ──────────────────────────────────────────────────────
    source = None
    source_key = None
    if has_default:
        source = str(DEFAULT_EXCEL)
        source_key = DEFAULT_EXCEL.name
    elif uploaded:
        source = uploaded
        source_key = uploaded.name

    if source is None:
        st.markdown("""
        <div style="text-align:center;padding:80px 20px;color:#374151">
          <div style="font-size:72px">📋</div>
          <h2 style="color:#64748b;margin:16px 0 8px">No Collection Loaded</h2>
          <p style="color:#475569">
            Upload your <strong>TCG Tracker Excel</strong> in the sidebar,<br>
            or place it at <code>data/TCG Tracker_New_04.07.26.xlsx</code>
          </p>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Load collection ───────────────────────────────────────────────────────
    try:
        with st.spinner("Reading Excel…"):
            entries, parse_warnings = _cached_load_collection(source_key, source)
    except ValueError as exc:
        st.error(f"Excel parse error: {exc}")
        return

    # ── PokéAPI total ─────────────────────────────────────────────────────────
    api_total: int
    api_cached_at: Optional[float] = None
    api_offline = False

    try:
        with st.spinner("Checking PokéAPI…"):
            api_total, api_cached_at = _cached_api_total()
    except Exception as exc:
        api_offline = True
        cached_total = state.get("api_total")
        if cached_total:
            api_total = int(cached_total)
            st.warning(f"⚠️ PokéAPI unreachable ({exc}). Using cached total: {api_total:,}")
        else:
            api_total = max(entries.keys(), default=1025)
            st.warning(f"⚠️ PokéAPI unreachable. Falling back to Excel max: {api_total:,}")

    # ── New Pokémon detection ─────────────────────────────────────────────────
    last_seen = state.get("last_seen_total", 0)
    new_pokemon: List[dict] = []

    if not api_offline and api_total > last_seen and last_seen > 0:
        try:
            new_pokemon = check_new_pokemon(last_seen, api_total)
        except Exception:
            pass

    if not api_offline:
        state["api_total"] = api_total
        state["last_api_check"] = time.time()
        if last_seen == 0:
            state["last_seen_total"] = api_total
        elif new_pokemon:
            state["last_seen_total"] = api_total
            state["known_new_pokemon"] = new_pokemon
        save_state(state)

    new_ids = {p["id"] for p in new_pokemon if p.get("id")}

    # ── Compute analytics ─────────────────────────────────────────────────────
    kpis = compute_kpis(entries, api_total, count_untracked)
    gen_stats = get_generation_stats(entries)

    # ── Sidebar status ────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        st.markdown(
            f'<div class="small-muted">API total: <strong style="color:#60a5fa">{api_total:,}</strong></div>',
            unsafe_allow_html=True,
        )
        if api_offline:
            st.error("API offline — using cache")
        if parse_warnings:
            with st.expander(f"⚠️ {len(parse_warnings)} data warning(s)"):
                for w in parse_warnings:
                    st.caption(w)

    # ── Page title ────────────────────────────────────────────────────────────
    st.markdown(
        f"# ⚡ Pokédex TCG Tracker"
        f"<span style='font-size:14px;color:#475569;font-weight:400;margin-left:14px'>"
        f"{kpis['collected']:,} / {kpis['effective_total']:,} · {kpis['pct_complete']:.1f}% complete"
        f"</span>",
        unsafe_allow_html=True,
    )

    # ── Excel vs API banner ───────────────────────────────────────────────────
    excel_max = max(entries.keys(), default=0)
    if excel_max < api_total:
        st.markdown(
            f'<div class="warn-banner">⚠️ Your Excel covers up to <strong>#{excel_max}</strong>, '
            f'but PokéAPI reports <strong>{api_total:,}</strong> species. '
            f'Pokémon #{excel_max + 1}–#{api_total} are counted as missing. '
            f'Use "Export Updated Excel" (sidebar · Phase 2) to extend your tracker.</div>',
            unsafe_allow_html=True,
        )

    # ── New Pokémon banner ────────────────────────────────────────────────────
    if new_pokemon:
        items_html = "".join(
            f'<span class="new-chip">#{p["id"]} {p["name"].replace("-", " ").title()}</span>'
            for p in new_pokemon[:24]
        )
        more = f"<em style='color:#7c3aed;font-size:11px'> +{len(new_pokemon) - 24} more</em>" \
               if len(new_pokemon) > 24 else ""
        st.markdown(
            f'<div class="new-banner">'
            f'<div class="new-banner-title">🆕 {len(new_pokemon)} New Pokémon Detected!</div>'
            f'<div>{items_html}{more}</div>'
            f'<div style="font-size:11px;color:#7c3aed;margin-top:8px">'
            f'Counted as missing until added to your Excel.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    t_overview, t_grid, t_missing, t_dupes = st.tabs(
        ["📊 Overview", "🔲 Pokédex Grid", "❌ Missing", "🔄 Duplicates"]
    )

    with t_overview:
        tab_overview(kpis, gen_stats, entries)

    with t_grid:
        tab_grid(entries, api_total, new_ids)

    with t_missing:
        tab_missing(kpis["gaps"], api_total)

    with t_dupes:
        tab_duplicates(entries)


if __name__ == "__main__":
    main()
