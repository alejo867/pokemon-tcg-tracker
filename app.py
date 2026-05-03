"""
Pokémon TCG Collection Tracker — Streamlit dashboard.

Data backend: Supabase (PostgreSQL).
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
from src.database import bulk_upsert, fetch_all, upsert
from src.excel_parser import PokemonEntry, load_collection
from src.pokeapi import check_new_pokemon, get_authoritative_total, invalidate_total_cache
from src.state import load_state, save_state

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
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"]          { background: #111827; border-right: 1px solid #1f2937; }
h1, h2, h3, h4 { color: #e6f1ff !important; }
.stTabs [data-baseweb="tab-list"] { background: #111827; border-radius: 8px; }
.stTabs [data-baseweb="tab"]      { color: #94a3b8; }
.stTabs [aria-selected="true"]    { color: #ef4444 !important; }

.kpi-card {
    background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 12px;
    padding: 18px 14px 14px; text-align: center; min-height: 100px;
}
.kpi-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 8px; }
.kpi-value { font-size: 26px; font-weight: 800; color: #e6f1ff; line-height: 1.1; }
.kpi-sub   { font-size: 11px; color: #475569; margin-top: 5px; }
.kpi-green  .kpi-value { color: #4ade80; }
.kpi-red    .kpi-value { color: #f87171; }
.kpi-yellow .kpi-value { color: #fbbf24; }
.kpi-blue   .kpi-value { color: #60a5fa; }
.kpi-purple .kpi-value { color: #c084fc; }

.prog-track { background: #1f2937; border-radius: 999px; height: 24px; overflow: hidden; border: 1px solid #374151; margin: 6px 0 4px; }
.prog-fill  {
    height: 24px; border-radius: 999px;
    background: linear-gradient(90deg, #dc2626 0%, #ef4444 20%, #fb923c 50%, #fbbf24 75%, #4ade80 100%);
    display: flex; align-items: center; justify-content: flex-end;
    padding-right: 12px; font-size: 12px; font-weight: 700; color: #fff; min-width: 48px;
}
.prog-labels { display: flex; justify-content: space-between; font-size: 11px; color: #374151; margin-top: 2px; }

.gen-row    { background: #161b27; border: 1px solid #1e293b; border-radius: 8px; padding: 8px 14px; margin-bottom: 6px; }
.gen-meta   { display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; margin-bottom: 5px; }
.gen-track  { background: #0d1117; border-radius: 4px; height: 7px; overflow: hidden; }
.gen-fill   { height: 7px; border-radius: 4px; background: linear-gradient(90deg, #ef4444, #fbbf24 60%, #4ade80); }

.pdx-grid {
    display: flex; flex-wrap: wrap; gap: 3px;
    max-height: 560px; overflow-y: auto; padding: 10px;
    background: #0a0f1a; border-radius: 10px; border: 1px solid #1e293b;
}
.pt { width: 26px; height: 26px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 6.5px; color: rgba(255,255,255,0.55); cursor: default; transition: transform 0.12s; position: relative; }
.pt:hover { transform: scale(1.45); filter: brightness(1.4); z-index: 20; }
.pt-c  { background: #14532d; border: 1px solid #22c55e; }
.pt-m  { background: #1a1f2e; border: 1px solid #1e293b; }
.pt-n  { background: #3b0764; border: 1px solid #9333ea; }
.pt-hi { outline: 3px solid #fbbf24 !important; transform: scale(1.5) !important; z-index: 30; }

.gap-wrap { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.gap-chip    { background: #1a0f0f; border: 1px solid #7f1d1d; border-radius: 6px; padding: 4px 10px; font-size: 12px; color: #fca5a5; white-space: nowrap; }
.gap-chip-lg { border-color: #dc2626; background: #2d0f0f; color: #fecaca; font-weight: 600; }

.warn-banner  { background: #1c1408; border: 1px solid #b45309; border-radius: 8px; padding: 11px 15px; color: #fcd34d; font-size: 13px; margin-bottom: 14px; }
.new-banner   { background: #150a2e; border: 1px solid #7c3aed; border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.new-banner-title { color: #c4b5fd; font-size: 15px; font-weight: 700; margin-bottom: 8px; }
.new-chip { display: inline-block; background: #2e1065; border-radius: 4px; padding: 2px 8px; margin: 2px; font-size: 12px; color: #e9d5ff; }

.cx-card  { background: #1a1a2e; border: 1px solid #2d2d44; border-radius: 12px; padding: 18px 10px; text-align: center; min-height: 130px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.cx-num   { font-size: 10px; color: #475569; margin-bottom: 3px; }
.cx-icon  { font-size: 44px; margin-bottom: 6px; }
.cx-name  { font-size: 14px; font-weight: 700; color: #fbbf24; }
.cx-qty   { font-size: 11px; color: #4ade80; margin-top: 4px; }

.sec-hdr  { font-size: 15px; font-weight: 700; color: #e6f1ff; margin: 22px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #ef4444; }
.legend   { display: flex; gap: 18px; margin: 8px 0 6px; font-size: 12px; color: #64748b; }
.legend-dot { display: inline-block; width: 13px; height: 13px; border-radius: 3px; vertical-align: middle; margin-right: 5px; }
.small-muted { font-size: 11px; color: #374151; }
.phase2-notice { background: #1e1b2e; border: 1px dashed #4338ca; border-radius: 8px; padding: 12px 16px; color: #818cf8; font-size: 13px; margin-bottom: 16px; }

/* Quick update panel */
.update-panel { background: #111827; border: 1px solid #1e293b; border-radius: 10px; padding: 14px; margin-top: 12px; }
.update-title { font-size: 12px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
</style>
"""

POKEBALL_ICONS = ["⚡", "🔴", "🌊", "🌿", "🔥", "❄️", "🌙", "☀️", "💜", "⭐"]


# ── Session-state helpers ─────────────────────────────────────────────────────

def _load_db_into_session() -> None:
    """Fetch DB once per session; skip if already loaded."""
    if "db_entries" not in st.session_state:
        with st.spinner("Loading collection from database…"):
            st.session_state.db_entries = fetch_all()
            st.session_state.db_loaded_at = time.time()


def _session_to_pokemon_entries(api_total: int) -> Dict[int, PokemonEntry]:
    """Convert session DB rows → PokemonEntry objects for analytics."""
    rows = st.session_state.get("db_entries", {})
    return {
        num: PokemonEntry(
            number=num,
            quantity=rows.get(num, {}).get("quantity", 0),
            quantity2=rows.get(num, {}).get("quantity2", 0),
        )
        for num in range(1, api_total + 1)
    }


def _update_entry(number: int, quantity: int, quantity2: int = 0) -> None:
    """Persist to Supabase + update session state immediately."""
    upsert(number, quantity, quantity2)
    if "db_entries" not in st.session_state:
        st.session_state.db_entries = {}
    st.session_state.db_entries[number] = {
        "pokemon_number": number,
        "quantity": quantity,
        "quantity2": quantity2,
    }


def _parse_number_input(text: str) -> List[int]:
    """Parse '1, 5, 10-15, 25' → [1, 5, 10, 11, 12, 13, 14, 15, 25]."""
    nums: List[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                nums.extend(range(int(a.strip()), int(b.strip()) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            nums.append(int(part))
    return sorted(set(nums))


# ── Cached API call ───────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _cached_api_total():
    return get_authoritative_total()


# ── Rendering helpers ─────────────────────────────────────────────────────────

def kpi_card(label, value, sub="", variant=""):
    cls = f"kpi-card kpi-{variant}" if variant else "kpi-card"
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f'<div class="{cls}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>{sub_html}</div>'


def render_progress(pct, collected, total):
    safe = min(100.0, max(0.0, pct))
    return (
        f'<div class="prog-track"><div class="prog-fill" style="width:{safe:.2f}%">{safe:.1f}%</div></div>'
        f'<div class="prog-labels"><span>0</span><span>{collected:,} collected</span><span>{total:,} total</span></div>'
    )


def render_gen_bars(gen_stats):
    rows = []
    for name, d in gen_stats.items():
        p = d["pct"]
        rows.append(
            f'<div class="gen-row"><div class="gen-meta"><span>{name}</span>'
            f'<span>{d["collected"]}/{d["total"]} &nbsp;·&nbsp; {p:.0f}%</span></div>'
            f'<div class="gen-track"><div class="gen-fill" style="width:{p:.2f}%"></div></div></div>'
        )
    return "".join(rows)


def render_grid(entries, start, end, new_ids, highlight=None):
    tiles = []
    for num in range(start, end + 1):
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


def gaps_csv(gaps):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["start", "end", "count", "label"])
    for g in gaps:
        w.writerow([g.start, g.end, g.size, g.label])
    return buf.getvalue().encode()


def entries_to_excel_bytes(entries: Dict[int, PokemonEntry]) -> bytes:
    """Export current collection state as Excel in the original format."""
    rows = [["Number", "Quantity", "Quantity2"]]
    for num in sorted(entries.keys()):
        e = entries[num]
        rows.append([f"#{num}", e.quantity, e.quantity2])
    buf = io.BytesIO()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df.to_excel(buf, index=False, sheet_name="Tracking Collection")
    return buf.getvalue()


def fmt_ts(ts):
    if ts is None:
        return "Never"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


# ── Tab renderers ─────────────────────────────────────────────────────────────

def tab_overview(kpis, gen_stats, entries):
    cols = st.columns(6, gap="small")
    gap = kpis["largest_gap"]
    s_start, s_end, s_len = kpis["longest_streak"]
    kpi_defs = [
        ("Total Pokémon",  f"{kpis['effective_total']:,}", "Authoritative (API)", "blue"),
        ("Collected",      f"{kpis['collected']:,}",       "In your collection",  "green"),
        ("Missing",        f"{kpis['missing']:,}",         "Not yet owned",       "red"),
        ("% Complete",     f"{kpis['pct_complete']:.1f}%", "Of all known",        "yellow"),
        ("Largest Gap",    gap.label if gap else "—",       f"{gap.size} Pokémon" if gap else "", ""),
        ("Best Streak",    f"{s_len:,}",                    f"#{s_start}–#{s_end}" if s_len else "", "purple"),
    ]
    for col, (label, value, sub, var) in zip(cols, kpi_defs):
        with col:
            st.markdown(kpi_card(label, value, sub, var), unsafe_allow_html=True)

    st.markdown('<div class="sec-hdr">🎯 Collection Progress</div>', unsafe_allow_html=True)
    st.markdown(render_progress(kpis["pct_complete"], kpis["collected"], kpis["effective_total"]), unsafe_allow_html=True)

    st.markdown('<div class="sec-hdr">📚 By Generation</div>', unsafe_allow_html=True)
    st.markdown(render_gen_bars(gen_stats), unsafe_allow_html=True)

    st.markdown('<div class="sec-hdr">✨ Collected Spotlight</div>', unsafe_allow_html=True)
    collected_nums = [n for n, e in entries.items() if e.collected]
    if not collected_nums:
        st.info("No collected Pokémon yet.")
        return

    if "carousel_sample" not in st.session_state:
        st.session_state.carousel_sample = random.sample(collected_nums, min(5, len(collected_nums)))

    c_btn, _ = st.columns([1, 5])
    if c_btn.button("🔀 Shuffle", key="shuffle"):
        st.session_state.carousel_sample = random.sample(collected_nums, min(5, len(collected_nums)))

    for col, num in zip(st.columns(5), st.session_state.carousel_sample):
        icon = POKEBALL_ICONS[num % len(POKEBALL_ICONS)]
        with col:
            st.markdown(
                f'<div class="cx-card"><div class="cx-num">#{num:04d}</div>'
                f'<div class="cx-icon">{icon}</div>'
                f'<div class="cx-name">Pokémon #{num}</div>'
                f'<div class="cx-qty">Collected ✓</div></div>',
                unsafe_allow_html=True,
            )


def tab_grid(entries, api_total, new_ids):
    st.markdown("""
    <div class="legend">
      <span><span class="legend-dot" style="background:#14532d;border:1px solid #22c55e"></span>Collected</span>
      <span><span class="legend-dot" style="background:#1a1f2e;border:1px solid #1e293b"></span>Missing</span>
      <span><span class="legend-dot" style="background:#3b0764;border:1px solid #9333ea"></span>New (not yet in collection)</span>
    </div>""", unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    with c1:
        selected_gen = st.selectbox("Filter by Generation", ["All Generations"] + list(GENERATIONS.keys()))
    with c2:
        jump = st.number_input("Highlight #", min_value=1, max_value=api_total, value=1, step=1)

    g_start, g_end = (1, api_total) if selected_gen == "All Generations" else GENERATIONS[selected_gen]
    g_end = min(g_end, api_total)
    highlight_num = jump if g_start <= jump <= g_end else None

    st.caption(f"Showing #{g_start}–#{g_end} · {g_end - g_start + 1:,} Pokémon")
    st.markdown(render_grid(entries, g_start, g_end, new_ids, highlight=highlight_num), unsafe_allow_html=True)


def tab_missing(gaps, api_total):
    if not gaps:
        st.success("🎉 Perfect collection — no missing Pokémon!")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Gaps", len(gaps))
    c2.metric("Missing Pokémon", sum(g.size for g in gaps))
    c3.metric("Largest Gap", f"{max(g.size for g in gaps)} Pokémon")

    st.download_button("📥 Export Shopping List (CSV)", data=gaps_csv(gaps),
                       file_name="missing_pokemon_shopping_list.csv", mime="text/csv")

    st.markdown("---")
    sort_opt = st.radio("Sort by", ["Largest gap first", "Number ascending"], horizontal=True)
    sorted_gaps = sorted(gaps, key=lambda g: -g.size if sort_opt.startswith("Largest") else g.start)

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
        chips = "".join(f'<span class="gap-chip">{g.label}</span>' for g in small[:200])
        st.markdown(f'<div class="gap-wrap">{chips}</div>', unsafe_allow_html=True)
        if len(small) > 200:
            st.caption(f"… and {len(small) - 200} more")


def tab_update(entries, api_total):
    st.markdown("Update your collection by entering Pokémon numbers below. Changes save instantly.")

    # ── Single update ─────────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">🎯 Single Pokémon</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        num = st.number_input("Pokémon #", min_value=1, max_value=api_total, value=1, step=1, key="single_num")

    entry = entries.get(num)
    current_status = "✅ Collected" if (entry and entry.collected) else "❌ Missing"
    st.caption(f"Current status: **{current_status}**")

    with c2:
        if st.button("✅ Mark Collected", use_container_width=True, key="btn_collect"):
            _update_entry(num, 1)
            st.success(f"#{num} marked as collected!")
            st.rerun()
    with c3:
        if st.button("❌ Mark Missing", use_container_width=True, key="btn_missing"):
            _update_entry(num, 0)
            st.info(f"#{num} marked as missing.")
            st.rerun()

    st.markdown("---")

    # ── Bulk update ───────────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">📋 Bulk Update</div>', unsafe_allow_html=True)
    st.caption("Enter a mix of individual numbers and ranges, e.g. `1, 5, 10-15, 25`")

    bulk_input = st.text_input("Pokémon numbers / ranges", placeholder="e.g. 152, 155, 200-210", key="bulk_input")
    if bulk_input.strip():
        parsed = _parse_number_input(bulk_input)
        valid = [n for n in parsed if 1 <= n <= api_total]
        st.caption(f"Parsed: **{len(valid)}** valid Pokémon numbers")

        bc1, bc2 = st.columns(2)
        if bc1.button("✅ Mark All Collected", use_container_width=True, key="bulk_collect"):
            rows = [{"pokemon_number": n, "quantity": 1, "quantity2": 0} for n in valid]
            bulk_upsert(rows)
            for n in valid:
                if "db_entries" not in st.session_state:
                    st.session_state.db_entries = {}
                st.session_state.db_entries[n] = {"pokemon_number": n, "quantity": 1, "quantity2": 0}
            st.success(f"Marked {len(valid)} Pokémon as collected!")
            st.rerun()

        if bc2.button("❌ Mark All Missing", use_container_width=True, key="bulk_missing"):
            rows = [{"pokemon_number": n, "quantity": 0, "quantity2": 0} for n in valid]
            bulk_upsert(rows)
            for n in valid:
                if "db_entries" not in st.session_state:
                    st.session_state.db_entries = {}
                st.session_state.db_entries[n] = {"pokemon_number": n, "quantity": 0, "quantity2": 0}
            st.info(f"Marked {len(valid)} Pokémon as missing.")
            st.rerun()

    st.markdown("---")

    # ── Import from Excel ─────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">📂 Import from Excel</div>', unsafe_allow_html=True)
    st.caption("Upload your Excel tracker to bulk-sync all quantity values into the database.")

    uploaded = st.file_uploader("Upload Excel tracker", type=["xlsx", "xls"], key="import_excel")
    if uploaded:
        try:
            import_entries, import_warnings = load_collection(uploaded)
            collected_count = sum(1 for e in import_entries.values() if e.collected)
            st.info(f"File contains **{len(import_entries)}** entries · **{collected_count}** collected")
            if import_warnings:
                with st.expander(f"⚠️ {len(import_warnings)} warning(s)"):
                    for w in import_warnings:
                        st.caption(w)

            if st.button("⬆️ Import into Database", type="primary", key="do_import"):
                rows = [
                    {"pokemon_number": e.number, "quantity": e.quantity, "quantity2": e.quantity2}
                    for e in import_entries.values()
                ]
                with st.spinner(f"Importing {len(rows)} entries…"):
                    bulk_upsert(rows)
                    # Refresh session state
                    st.session_state.db_entries = fetch_all()
                st.success(f"✅ Imported {len(rows)} entries. Dashboard will update now.")
                st.rerun()
        except Exception as exc:
            st.error(f"Failed to read file: {exc}")

    st.markdown("---")

    # ── Export as Excel ───────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">📥 Export Current State as Excel</div>', unsafe_allow_html=True)
    st.caption("Downloads your full collection in the original Excel format (Number, Quantity, Quantity2).")
    st.download_button(
        "⬇️ Download Excel",
        data=entries_to_excel_bytes(entries),
        file_name="TCG_Tracker_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def tab_duplicates(entries):
    st.markdown(
        '<div class="phase2-notice">🔧 <strong>Phase 2 Feature</strong> — '
        'Schema is finalized; full UI coming in the next release. '
        'The <em>duplicates</em> table in Supabase is already created.</div>',
        unsafe_allow_html=True,
    )
    dupes = [e for e in entries.values() if e.has_duplicate]
    if dupes:
        st.markdown(f"**{len(dupes)} Pokémon** have a Quantity2 value:")
        st.dataframe(
            pd.DataFrame([{"#": e.number, "Qty": e.quantity, "Qty2": e.quantity2} for e in dupes]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No Quantity2 values in current data.")

    st.markdown("""
### Phase 2 Schema (ready in Supabase)

| Column | Type | Description |
|---|---|---|
| `pokemon_number` | int | National Dex # |
| `variant_name` | str | Card set / illustration ID |
| `quantity` | int | Copies owned |
| `notes` | str | `keep` · `sell` · `trade` |
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.markdown(CSS, unsafe_allow_html=True)
    state = load_state()

    # ── Load DB into session ──────────────────────────────────────────────────
    try:
        _load_db_into_session()
    except Exception as exc:
        st.error(f"Cannot connect to Supabase: {exc}\n\nCheck your secrets configuration.")
        st.stop()

    # ── PokéAPI total ─────────────────────────────────────────────────────────
    api_total: int
    api_cached_at: Optional[float] = None
    api_offline = False

    try:
        api_total, api_cached_at = _cached_api_total()
    except Exception as exc:
        api_offline = True
        api_total = int(state.get("api_total") or 1025)
        st.warning(f"⚠️ PokéAPI unreachable. Using cached total: {api_total:,}")

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
        save_state(state)

    new_ids = {p["id"] for p in new_pokemon if p.get("id")}

    # ── Build entries from session state ──────────────────────────────────────
    entries = _session_to_pokemon_entries(api_total)
    kpis = compute_kpis(entries, api_total)
    gen_stats = get_generation_stats(entries)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚡ Pokédex TCG Tracker")
        st.markdown("---")

        # Quick Update
        st.markdown("**📝 Quick Update**")
        sb_num = st.number_input("Pokémon #", min_value=1, max_value=api_total, step=1, key="sb_num")
        sb_entry = entries.get(sb_num)
        sb_status = "✅ Collected" if (sb_entry and sb_entry.collected) else "❌ Missing"
        st.caption(sb_status)

        sc1, sc2 = st.columns(2)
        if sc1.button("✅ Got it", use_container_width=True, key="sb_got"):
            _update_entry(sb_num, 1)
            st.rerun()
        if sc2.button("❌ Missing", use_container_width=True, key="sb_miss"):
            _update_entry(sb_num, 0)
            st.rerun()

        st.markdown("---")
        st.markdown("**🌐 PokéAPI**")
        if st.button("🔄 Force Refresh", use_container_width=True):
            invalidate_total_cache()
            _cached_api_total.clear()
            st.rerun()
        st.markdown(
            f'<div class="small-muted">Last checked: {fmt_ts(api_cached_at)}</div>'
            f'<div class="small-muted">Total: {api_total:,}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown(
            f'<div class="small-muted">DB loaded: {fmt_ts(st.session_state.get("db_loaded_at"))}</div>',
            unsafe_allow_html=True,
        )
        if st.button("↺ Reload from DB", use_container_width=True):
            del st.session_state["db_entries"]
            st.rerun()

    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        f"# ⚡ Pokédex TCG Tracker "
        f"<span style='font-size:14px;color:#475569;font-weight:400;margin-left:12px'>"
        f"{kpis['collected']:,} / {kpis['effective_total']:,} · {kpis['pct_complete']:.1f}% complete"
        f"</span>",
        unsafe_allow_html=True,
    )

    # ── New Pokémon banner ────────────────────────────────────────────────────
    if new_pokemon:
        items = "".join(
            f'<span class="new-chip">#{p["id"]} {p["name"].replace("-", " ").title()}</span>'
            for p in new_pokemon[:24]
        )
        more = f"<em>+{len(new_pokemon)-24} more</em>" if len(new_pokemon) > 24 else ""
        st.markdown(
            f'<div class="new-banner"><div class="new-banner-title">🆕 {len(new_pokemon)} New Pokémon Detected!</div>'
            f'<div>{items}{more}</div>'
            f'<div style="font-size:11px;color:#7c3aed;margin-top:8px">Counted as missing until you mark them collected.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    t1, t2, t3, t4, t5 = st.tabs(
        ["📊 Overview", "🔲 Pokédex Grid", "❌ Missing", "✏️ Update", "🔄 Duplicates"]
    )
    with t1: tab_overview(kpis, gen_stats, entries)
    with t2: tab_grid(entries, api_total, new_ids)
    with t3: tab_missing(kpis["gaps"], api_total)
    with t4: tab_update(entries, api_total)
    with t5: tab_duplicates(entries)


if __name__ == "__main__":
    main()
