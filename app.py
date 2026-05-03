"""
Pokémon TCG Collection Tracker — Streamlit dashboard.
Backend: Supabase.  Entry point: streamlit run app.py
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
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from src.analytics import GENERATIONS, compute_kpis, find_gaps, get_generation_stats
from src.database import bulk_upsert, fetch_all, load_all_details, upsert
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

# ── Sprite helpers ────────────────────────────────────────────────────────────
def sprite_url(dex_num: int) -> str:
    """Official artwork hosted by PokéAPI (public, no auth)."""
    return (
        f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
        f"/sprites/pokemon/other/official-artwork/{dex_num}.png"
    )

def mini_sprite_url(dex_num: int) -> str:
    """Small pixel sprite for compact use."""
    return (
        f"https://raw.githubusercontent.com/PokeAPI/sprites/master"
        f"/sprites/pokemon/{dex_num}.png"
    )

# ── Type colors (official Pokémon palette) ────────────────────────────────────
TYPE_COLORS = {
    "normal":   "#A8A878", "fire":     "#F08030", "water":    "#6890F0",
    "electric": "#F8D030", "grass":    "#78C850", "ice":      "#98D8D8",
    "fighting": "#C03028", "poison":   "#A040A0", "ground":   "#E0C068",
    "flying":   "#A890F0", "psychic":  "#F85888", "bug":      "#A8B820",
    "rock":     "#B8A038", "ghost":    "#705898", "dragon":   "#7038F8",
    "dark":     "#705848", "steel":    "#B8B8D0", "fairy":    "#EE99AC",
}

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
<style>
/* ── Base ── */
[data-testid="stAppViewContainer"] {
    background: #FEF6EC;
}
[data-testid="stSidebar"] {
    background: #FFFFFF;
    border-right: 2px solid #F3E0CC;
}
[data-testid="stSidebar"] * { color: #1a1a2a !important; }
h1,h2,h3,h4 { color: #1a1a2a !important; }
.stTabs [data-baseweb="tab-list"] {
    background: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #F3E0CC;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] { color: #8B7355; border-radius: 8px; }
.stTabs [aria-selected="true"] {
    background: #CC0000 !important;
    color: #FFFFFF !important;
}

/* ── KPI cards ── */
.kpi-card {
    background: #FFFFFF;
    border: 1px solid #F3E0CC;
    border-radius: 16px;
    padding: 20px 16px 16px;
    text-align: center;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    min-height: 110px;
}
.kpi-label {
    font-size: 11px;
    color: #A08060;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 8px;
    font-weight: 600;
}
.kpi-value { font-size: 28px; font-weight: 800; color: #1a1a2a; line-height: 1.1; }
.kpi-sub   { font-size: 11px; color: #B0A090; margin-top: 5px; }
.kpi-red    .kpi-value { color: #CC0000; }
.kpi-green  .kpi-value { color: #2E7D32; }
.kpi-blue   .kpi-value { color: #1565C0; }
.kpi-yellow .kpi-value { color: #F57F17; }
.kpi-purple .kpi-value { color: #6A1B9A; }

/* ── Progress bar ── */
.prog-wrap  {
    background: #F3E0CC;
    border-radius: 999px;
    height: 28px;
    overflow: hidden;
    margin: 8px 0 4px;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.08);
}
.prog-fill  {
    height: 28px;
    border-radius: 999px;
    background: linear-gradient(90deg, #CC0000 0%, #FF6F00 40%, #F9A825 70%, #2E7D32 100%);
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding-right: 14px;
    font-size: 13px;
    font-weight: 800;
    color: #fff;
    min-width: 54px;
    text-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.prog-labels { display: flex; justify-content: space-between; font-size: 11px; color: #A08060; margin-top: 3px; }

/* ── Pokédex grid ── */
.pdx-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    max-height: 540px;
    overflow-y: auto;
    padding: 12px;
    background: #FFF8F2;
    border-radius: 12px;
    border: 1px solid #F3E0CC;
}
.pt {
    width: 27px; height: 27px;
    border-radius: 5px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 7px;
    cursor: default;
    transition: transform 0.1s;
    position: relative;
}
.pt:hover { transform: scale(1.5); z-index: 20; }
.pt-c  { background: #C8E6C9; border: 1px solid #43A047; color: #1B5E20; font-weight: 700; }
.pt-m  { background: #F5F5F5; border: 1px solid #DDDDDD; color: #BBBBBB; }
.pt-n  { background: #E1BEE7; border: 1px solid #8E24AA; color: #4A148C; }
.pt-hi { outline: 3px solid #FF6F00 !important; transform: scale(1.6) !important; z-index: 30; }

/* ── Legend ── */
.legend { display: flex; gap: 18px; margin: 8px 0 6px; font-size: 12px; color: #8B7355; }
.legend-dot { display: inline-block; width: 13px; height: 13px; border-radius: 3px; vertical-align: middle; margin-right: 5px; }

/* ── Carousel cards ── */
.cx-card {
    background: #FFFFFF;
    border: 1px solid #F3E0CC;
    border-radius: 16px;
    padding: 16px 10px 12px;
    text-align: center;
    box-shadow: 0 4px 16px rgba(0,0,0,0.07);
    transition: transform 0.15s, box-shadow 0.15s;
}
.cx-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
.cx-sprite { width: 96px; height: 96px; object-fit: contain; margin: 0 auto; display: block; }
.cx-num  { font-size: 10px; color: #A08060; margin-bottom: 2px; font-weight: 600; letter-spacing: 1px; }
.cx-name { font-size: 14px; font-weight: 800; color: #CC0000; margin-top: 6px; }
.cx-qty  { font-size: 11px; color: #2E7D32; margin-top: 3px; font-weight: 600; }

/* ── Gap chips ── */
.gap-wrap { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.gap-chip    { background: #FFF3F3; border: 1px solid #FFCDD2; border-radius: 8px; padding: 4px 12px; font-size: 12px; color: #C62828; font-weight: 600; }
.gap-chip-lg { background: #FFEBEE; border: 1.5px solid #E53935; color: #B71C1C; font-size: 13px; }

/* ── Banners ── */
.warn-banner {
    background: #FFF8E1;
    border: 1px solid #FFB300;
    border-radius: 10px;
    padding: 12px 16px;
    color: #7A5800;
    font-size: 13px;
    margin-bottom: 14px;
}
.new-banner {
    background: #F3E5F5;
    border: 1.5px solid #8E24AA;
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 16px;
}
.new-banner-title { color: #6A1B9A; font-size: 15px; font-weight: 800; margin-bottom: 8px; }
.new-chip {
    display: inline-block;
    background: #E1BEE7;
    border-radius: 6px;
    padding: 3px 10px;
    margin: 2px;
    font-size: 12px;
    color: #4A148C;
    font-weight: 600;
}

/* ── Section headers ── */
.sec-hdr {
    font-size: 16px;
    font-weight: 800;
    color: #1a1a2a;
    margin: 24px 0 12px;
    padding-bottom: 8px;
    border-bottom: 3px solid #CC0000;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Update panel ── */
.phase2-notice {
    background: #EDE7F6;
    border: 1px dashed #7E57C2;
    border-radius: 10px;
    padding: 12px 16px;
    color: #4527A0;
    font-size: 13px;
    margin-bottom: 16px;
}
.small-muted { font-size: 11px; color: #A08060; }

/* ── Pokéball divider ── */
.pokeball-divider {
    text-align: center;
    color: #F3E0CC;
    font-size: 20px;
    margin: 4px 0;
    letter-spacing: 8px;
}

/* ── Page title ── */
.page-title {
    font-size: 32px;
    font-weight: 900;
    color: #CC0000;
    letter-spacing: -0.5px;
}
.page-subtitle { font-size: 14px; color: #A08060; font-weight: 500; margin-top: 2px; }

/* ── Featured Pokémon strip ── */
.feat-strip {
    background: linear-gradient(135deg, #CC0000 0%, #FF6F00 100%);
    border-radius: 16px;
    padding: 16px 20px;
    color: white;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 4px 20px rgba(204,0,0,0.25);
    margin-bottom: 16px;
}
.feat-strip-text h3 { color: white !important; margin: 0; font-size: 18px; }
.feat-strip-text p  { color: rgba(255,255,255,0.85); margin: 4px 0 0; font-size: 13px; }
</style>
"""

# ── Plotly chart helpers ──────────────────────────────────────────────────────

def plotly_gen_chart(gen_stats: dict) -> go.Figure:
    names      = list(gen_stats.keys())
    collected  = [d["collected"] for d in gen_stats.values()]
    missing    = [d["missing"]   for d in gen_stats.values()]
    pcts       = [f'{d["pct"]:.0f}%' for d in gen_stats.values()]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Collected", y=names, x=collected, orientation="h",
        marker=dict(color="#43A047", line=dict(width=0)),
        text=pcts, textposition="inside", insidetextanchor="middle",
        textfont=dict(color="white", size=11, family="sans-serif"),
        hovertemplate="%{y}: %{x} collected<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Missing", y=names, x=missing, orientation="h",
        marker=dict(color="#FFCDD2", line=dict(width=0)),
        hovertemplate="%{y}: %{x} missing<extra></extra>",
    ))
    fig.update_layout(
        barmode="stack",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=300,
        margin=dict(l=10, r=20, t=10, b=10),
        legend=dict(
            orientation="h", y=-0.15, x=0.5, xanchor="center",
            font=dict(size=12, color="#8B7355"),
        ),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, tickfont=dict(size=12, color="#5D4037")),
        font=dict(family="sans-serif"),
        hoverlabel=dict(bgcolor="white", bordercolor="#F3E0CC"),
    )
    return fig


def plotly_completion_donut(collected: int, missing: int) -> go.Figure:
    fig = go.Figure(go.Pie(
        values=[collected, missing],
        labels=["Collected", "Missing"],
        hole=0.68,
        marker=dict(colors=["#43A047", "#FFCDD2"], line=dict(width=0)),
        textinfo="none",
        hovertemplate="%{label}: %{value}<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        height=180,
        margin=dict(l=0, r=0, t=0, b=0),
        annotations=[dict(
            text=f"<b>{collected/(collected+missing)*100:.1f}%</b>",
            x=0.5, y=0.5, font=dict(size=20, color="#CC0000", family="sans-serif"),
            showarrow=False,
        )],
    )
    return fig


# ── Session-state helpers ─────────────────────────────────────────────────────

def _load_db_into_session() -> None:
    if "db_entries" not in st.session_state:
        with st.spinner("Loading collection…"):
            st.session_state.db_entries   = fetch_all()
            st.session_state.db_loaded_at = time.time()


def _to_pokemon_entries(api_total: int) -> Dict[int, PokemonEntry]:
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
    upsert(number, quantity, quantity2)
    st.session_state.db_entries[number] = {
        "pokemon_number": number, "quantity": quantity, "quantity2": quantity2,
    }


def _parse_numbers(text: str) -> List[int]:
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


# ── Cached API ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def _cached_api_total():
    return get_authoritative_total()


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_details() -> pd.DataFrame:
    rows = load_all_details()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["hp","attack","defense","sp_attack","sp_defense","speed","height_dm","weight_hg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── Render helpers ────────────────────────────────────────────────────────────

def kpi_card(label, value, sub="", variant=""):
    cls = f"kpi-card kpi-{variant}" if variant else "kpi-card"
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="{cls}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{sub_html}</div>'
    )


def render_progress(pct, collected, total):
    safe = min(100.0, max(0.0, pct))
    return (
        f'<div class="prog-wrap">'
        f'<div class="prog-fill" style="width:{safe:.2f}%">{safe:.1f}%</div>'
        f'</div>'
        f'<div class="prog-labels">'
        f'<span>0</span><span>{collected:,} collected</span><span>{total:,} total</span>'
        f'</div>'
    )


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
        if num == highlight:
            tiles.append(f'<div class="pt pt-c pt-hi" title="#{num}">{lbl}</div>')
        else:
            tiles.append(f'<div class="{cls}" title="#{num}">{lbl}</div>')
    return f'<div class="pdx-grid">{"".join(tiles)}</div>'


def gaps_csv(gaps):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["start", "end", "count", "label"])
    for g in gaps:
        w.writerow([g.start, g.end, g.size, g.label])
    return buf.getvalue().encode()


def entries_to_excel_bytes(entries):
    buf = io.BytesIO()
    df = pd.DataFrame(
        [[f"#{e.number}", e.quantity, e.quantity2] for e in sorted(entries.values(), key=lambda e: e.number)],
        columns=["Number", "Quantity", "Quantity2"],
    )
    df.to_excel(buf, index=False, sheet_name="Tracking Collection")
    return buf.getvalue()


def fmt_ts(ts):
    if ts is None:
        return "Never"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%b %d, %Y %H:%M")
    except Exception:
        return str(ts)


# ── Tab renderers ─────────────────────────────────────────────────────────────

def tab_overview(kpis, gen_stats, entries):
    collected_nums = [n for n, e in entries.items() if e.collected]

    # ── Featured strip ────────────────────────────────────────────────────────
    if collected_nums:
        featured = random.choice(collected_nums)
        st.markdown(
            f'<div class="feat-strip">'
            f'<img src="{mini_sprite_url(featured)}" width="64" style="image-rendering:pixelated">'
            f'<div class="feat-strip-text">'
            f'<h3>Your Collection · {kpis["pct_complete"]:.1f}% Complete</h3>'
            f'<p>{kpis["collected"]:,} of {kpis["effective_total"]:,} Pokémon collected · '
            f'{kpis["missing"]:,} still missing</p>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

    # ── KPI row ───────────────────────────────────────────────────────────────
    cols = st.columns(6, gap="small")
    gap = kpis["largest_gap"]
    s0, s1, s_len = kpis["longest_streak"]
    kpi_defs = [
        ("Total Pokémon",  f"{kpis['effective_total']:,}", "Authoritative",       "blue"),
        ("Collected",      f"{kpis['collected']:,}",       "In your collection",  "green"),
        ("Missing",        f"{kpis['missing']:,}",         "Not yet owned",       "red"),
        ("% Complete",     f"{kpis['pct_complete']:.1f}%", "Of all known",        "yellow"),
        ("Largest Gap",    gap.label if gap else "—",       f"{gap.size} Pokémon" if gap else "", ""),
        ("Best Streak",    f"{s_len:,}",                    f"#{s0}–#{s1}" if s_len else "", "purple"),
    ]
    for col, (label, value, sub, var) in zip(cols, kpi_defs):
        with col:
            st.markdown(kpi_card(label, value, sub, var), unsafe_allow_html=True)

    # ── Progress + donut side by side ─────────────────────────────────────────
    st.markdown('<div class="sec-hdr">🎯 Overall Progress</div>', unsafe_allow_html=True)
    pc1, pc2 = st.columns([3, 1])
    with pc1:
        st.markdown(render_progress(kpis["pct_complete"], kpis["collected"], kpis["effective_total"]), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.plotly_chart(plotly_gen_chart(gen_stats), use_container_width=True, config={"displayModeBar": False})
    with pc2:
        st.plotly_chart(
            plotly_completion_donut(kpis["collected"], kpis["missing"]),
            use_container_width=True, config={"displayModeBar": False},
        )
        st.markdown(
            f'<div style="text-align:center;font-size:11px;color:#A08060">'
            f'<b style="color:#43A047">{kpis["collected"]:,}</b> collected<br>'
            f'<b style="color:#E53935">{kpis["missing"]:,}</b> missing</div>',
            unsafe_allow_html=True,
        )

    # ── Carousel ──────────────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">✨ Collected Spotlight</div>', unsafe_allow_html=True)

    if not collected_nums:
        st.info("No collected Pokémon yet.")
        return

    if "carousel_sample" not in st.session_state:
        st.session_state.carousel_sample = random.sample(collected_nums, min(5, len(collected_nums)))

    c_btn, _ = st.columns([1, 5])
    if c_btn.button("🔀 Shuffle", key="shuffle"):
        st.session_state.carousel_sample = random.sample(collected_nums, min(5, len(collected_nums)))

    for col, num in zip(st.columns(5), st.session_state.carousel_sample):
        with col:
            st.markdown(
                f'<div class="cx-card">'
                f'<div class="cx-num">#{num:04d}</div>'
                f'<img class="cx-sprite" src="{sprite_url(num)}" alt="#{num}">'
                f'<div class="cx-name">Pokémon #{num}</div>'
                f'<div class="cx-qty">✓ Collected</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def tab_grid(entries, api_total, new_ids):
    st.markdown(
        '<div class="legend">'
        '<span><span class="legend-dot" style="background:#C8E6C9;border:1px solid #43A047"></span>Collected</span>'
        '<span><span class="legend-dot" style="background:#F5F5F5;border:1px solid #DDD"></span>Missing</span>'
        '<span><span class="legend-dot" style="background:#E1BEE7;border:1px solid #8E24AA"></span>New</span>'
        '</div>',
        unsafe_allow_html=True,
    )
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
        st.success("🎉 Complete collection — no missing Pokémon!")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Gaps",     len(gaps))
    c2.metric("Missing Pokémon", sum(g.size for g in gaps))
    c3.metric("Largest Gap",    f"{max(g.size for g in gaps)} Pokémon")

    st.download_button("📥 Export Shopping List (CSV)", data=gaps_csv(gaps),
                       file_name="missing_pokemon_shopping_list.csv", mime="text/csv")
    st.markdown("---")

    sort_opt = st.radio("Sort by", ["Largest gap first", "Number ascending"], horizontal=True)
    sorted_gaps = sorted(gaps, key=lambda g: (-g.size if sort_opt.startswith("Largest") else g.start))

    large = [g for g in sorted_gaps if g.size >= 5]
    small = [g for g in sorted_gaps if g.size < 5]

    if large:
        st.markdown('<div class="sec-hdr">🔴 Large Gaps (≥5 missing)</div>', unsafe_allow_html=True)
        chips = "".join(
            f'<span class="gap-chip gap-chip-lg">{g.label} <em style="font-weight:400">·{g.size}</em></span>'
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
    st.markdown("Changes save instantly to the database and reflect on all devices.")

    st.markdown('<div class="sec-hdr">🎯 Single Pokémon</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        num = st.number_input("Pokémon #", min_value=1, max_value=api_total, value=1, step=1, key="single_num")

    entry = entries.get(num)
    current = "✅ Collected" if (entry and entry.collected) else "❌ Missing"
    st.caption(f"Current status: **{current}**")

    # Show sprite preview
    sp_col, _ = st.columns([1, 3])
    with sp_col:
        st.image(sprite_url(num), width=100)

    with c2:
        if st.button("✅ Got it!", use_container_width=True, type="primary", key="btn_collect"):
            _update_entry(num, 1)
            st.success(f"#{num} marked collected!")
            st.rerun()
    with c3:
        if st.button("❌ Missing", use_container_width=True, key="btn_missing"):
            _update_entry(num, 0)
            st.info(f"#{num} marked missing.")
            st.rerun()

    st.markdown("---")
    st.markdown('<div class="sec-hdr">📋 Bulk Update</div>', unsafe_allow_html=True)
    st.caption("Mix numbers and ranges — e.g. `1, 5, 10-15, 25`")

    bulk_input = st.text_input("Pokémon numbers / ranges", placeholder="e.g. 152, 155, 200-210", key="bulk_input")
    if bulk_input.strip():
        parsed = [n for n in _parse_numbers(bulk_input) if 1 <= n <= api_total]
        st.caption(f"Parsed: **{len(parsed)}** valid numbers")
        bc1, bc2 = st.columns(2)
        if bc1.button("✅ Mark All Collected", use_container_width=True, key="bulk_collect", type="primary"):
            bulk_upsert([{"pokemon_number": n, "quantity": 1, "quantity2": 0} for n in parsed])
            for n in parsed:
                st.session_state.db_entries[n] = {"pokemon_number": n, "quantity": 1, "quantity2": 0}
            st.success(f"Marked {len(parsed)} Pokémon as collected!")
            st.rerun()
        if bc2.button("❌ Mark All Missing", use_container_width=True, key="bulk_missing"):
            bulk_upsert([{"pokemon_number": n, "quantity": 0, "quantity2": 0} for n in parsed])
            for n in parsed:
                st.session_state.db_entries[n] = {"pokemon_number": n, "quantity": 0, "quantity2": 0}
            st.info(f"Marked {len(parsed)} as missing.")
            st.rerun()

    st.markdown("---")
    st.markdown('<div class="sec-hdr">📂 Import from Excel</div>', unsafe_allow_html=True)
    st.caption("Bulk-sync your Excel tracker into the database.")
    uploaded = st.file_uploader("Upload Excel tracker", type=["xlsx", "xls"], key="import_excel")
    if uploaded:
        try:
            imp_entries, imp_warnings = load_collection(uploaded)
            st.info(f"**{len(imp_entries)}** entries · **{sum(1 for e in imp_entries.values() if e.collected)}** collected")
            if imp_warnings:
                with st.expander(f"⚠️ {len(imp_warnings)} warning(s)"):
                    for w in imp_warnings:
                        st.caption(w)
            if st.button("⬆️ Import into Database", type="primary", key="do_import"):
                rows = [{"pokemon_number": e.number, "quantity": e.quantity, "quantity2": e.quantity2}
                        for e in imp_entries.values()]
                with st.spinner(f"Importing {len(rows)} entries…"):
                    bulk_upsert(rows)
                    st.session_state.db_entries = fetch_all()
                st.success(f"✅ Imported {len(rows)} entries!")
                st.rerun()
        except Exception as exc:
            st.error(f"Failed to read file: {exc}")

    st.markdown("---")
    st.markdown('<div class="sec-hdr">📥 Export as Excel</div>', unsafe_allow_html=True)
    st.download_button(
        "⬇️ Download Excel",
        data=entries_to_excel_bytes(entries),
        file_name="TCG_Tracker_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def tab_analytics(entries: dict) -> None:
    details_df = _cached_details()

    if details_df.empty:
        st.info("Pokémon details not loaded yet. Run: `python fetch_pokemon_details.py`")
        return

    # Merge collection status into details
    df = details_df.copy()
    df["collected"] = df["pokemon_number"].apply(
        lambda n: bool(entries.get(n) and entries[n].collected)
    )
    cdf = df[df["collected"]].copy()   # collected subset
    n   = len(cdf)

    if n == 0:
        st.info("No collected Pokémon with details yet.")
        return

    n_leg  = int(cdf["is_legendary"].sum())
    n_myth = int(cdf["is_mythical"].sum())
    total_bs = (cdf[["hp","attack","defense","sp_attack","sp_defense","speed"]].sum(axis=1)).mean()

    st.markdown(
        f'<div style="color:#A08060;font-size:13px;margin-bottom:16px">'
        f'Analyzing <b style="color:#CC0000">{n}</b> collected Pokémon &nbsp;·&nbsp; '
        f'<b style="color:#F8D030">{n_leg}</b> Legendary &nbsp;·&nbsp; '
        f'<b style="color:#F85888">{n_myth}</b> Mythical &nbsp;·&nbsp; '
        f'Avg Base Stat Total: <b style="color:#6890F0">{total_bs:.0f}</b>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Champion cards ────────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">🏆 Your Champions</div>', unsafe_allow_html=True)
    champ_defs = [
        ("⚡ Fastest",      "speed",   "#F8D030"),
        ("⚔️ Strongest",    "attack",  "#F08030"),
        ("🛡️ Bulkiest",     "defense", "#6890F0"),
        ("❤️ Highest HP",   "hp",      "#78C850"),
        ("🏋️ Heaviest",     "weight_hg","#A8A878"),
    ]
    for col, (title, stat, color) in zip(st.columns(5), champ_defs):
        row = cdf.loc[cdf[stat].idxmax()]
        num = int(row["pokemon_number"])
        val = int(row[stat])
        label = f"{val/10:.1f} kg" if stat == "weight_hg" else str(val)
        with col:
            st.markdown(
                f'<div class="kpi-card" style="border-top:4px solid {color};padding-top:12px">'
                f'<div class="kpi-label">{title}</div>'
                f'<img src="{sprite_url(num)}" width="80" style="margin:6px auto 4px;display:block">'
                f'<div style="font-size:13px;font-weight:800;color:#1a1a2a;margin-top:4px">'
                f'{row["name"].replace("-"," ").title()}</div>'
                f'<div style="font-size:10px;color:#A08060">#{num}</div>'
                f'<div style="font-size:22px;font-weight:900;color:{color};margin-top:6px">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Type distribution + Legendary donut ──────────────────────────────────
    st.markdown('<div class="sec-hdr">🎨 Type Breakdown</div>', unsafe_allow_html=True)
    tc1, tc2 = st.columns([3, 2])

    with tc1:
        type_counts: dict = {}
        for _, row in cdf.iterrows():
            for t in [row.get("type1"), row.get("type2")]:
                if t and isinstance(t, str):
                    type_counts[t] = type_counts.get(t, 0) + 1

        type_series = (
            pd.DataFrame(list(type_counts.items()), columns=["type", "count"])
            .sort_values("count", ascending=True)
        )
        bar_colors = [TYPE_COLORS.get(t, "#888") for t in type_series["type"]]

        fig_types = go.Figure(go.Bar(
            y=type_series["type"].str.capitalize(),
            x=type_series["count"],
            orientation="h",
            marker=dict(color=bar_colors, line=dict(width=0)),
            text=type_series["count"],
            textposition="outside",
            hovertemplate="%{y}: %{x} Pokémon<extra></extra>",
        ))
        fig_types.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=440, margin=dict(l=10, r=40, t=10, b=10),
            xaxis=dict(showgrid=True, gridcolor="#F3E0CC", zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, tickfont=dict(size=12, color="#5D4037")),
            font=dict(family="sans-serif"),
        )
        st.plotly_chart(fig_types, use_container_width=True, config={"displayModeBar": False})

    with tc2:
        fig_leg = go.Figure(go.Pie(
            labels=["Regular", "Legendary", "Mythical"],
            values=[n - n_leg - n_myth, n_leg, n_myth],
            hole=0.55,
            marker=dict(colors=["#78C850", "#F8D030", "#F85888"], line=dict(width=0)),
            textinfo="label+percent",
            hovertemplate="%{label}: %{value}<extra></extra>",
        ))
        fig_leg.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", height=260,
            margin=dict(l=0, r=0, t=10, b=0),
            showlegend=False, font=dict(family="sans-serif"),
        )
        st.plotly_chart(fig_leg, use_container_width=True, config={"displayModeBar": False})

        # Type badge list (rarest in your collection)
        st.markdown("**Rarest types you own:**")
        for _, row in type_series.head(6).iterrows():
            color = TYPE_COLORS.get(row["type"], "#888")
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 10px;'
                f'border-radius:999px;font-size:12px;font-weight:700;display:inline-block;margin:2px">'
                f'{row["type"].capitalize()}</span> &nbsp;{int(row["count"])}',
                unsafe_allow_html=True,
            )

    # ── Attack vs Defense scatter ─────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">⚔️ Attack vs Defense — Your Collection</div>', unsafe_allow_html=True)

    fig_scatter = go.Figure()

    # Gray background: missing Pokémon
    mdf = df[~df["collected"]].dropna(subset=["attack","defense"])
    fig_scatter.add_trace(go.Scatter(
        x=mdf["attack"], y=mdf["defense"],
        mode="markers",
        name="Not collected",
        marker=dict(color="#E8E0D8", size=4, line=dict(width=0)),
        hovertemplate="#%{customdata[0]} %{customdata[1]}<extra></extra>",
        customdata=mdf[["pokemon_number","name"]].values,
    ))

    # Collected: one trace per type, colored
    for type_name, grp in cdf.dropna(subset=["attack","defense","type1"]).groupby("type1"):
        color = TYPE_COLORS.get(type_name, "#888")
        grp = grp.dropna(subset=["hp"])
        fig_scatter.add_trace(go.Scatter(
            x=grp["attack"], y=grp["defense"],
            mode="markers",
            name=type_name.capitalize(),
            marker=dict(
                color=color, opacity=0.85,
                size=grp["hp"].apply(lambda v: 5 + v / 18),
                line=dict(width=0.5, color="white"),
            ),
            hovertemplate=(
                "<b>#%{customdata[0]} %{customdata[1]}</b><br>"
                "Attack: %{x} &nbsp; Defense: %{y}<br>"
                "HP: %{customdata[2]}<extra></extra>"
            ),
            customdata=grp[["pokemon_number","name","hp"]].values,
        ))

    fig_scatter.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF7",
        height=460, margin=dict(l=20, r=20, t=10, b=60),
        xaxis=dict(title="Attack", showgrid=True, gridcolor="#F3E0CC", zeroline=False),
        yaxis=dict(title="Defense", showgrid=True, gridcolor="#F3E0CC", zeroline=False),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center", font=dict(size=11)),
        font=dict(family="sans-serif"),
        hoverlabel=dict(bgcolor="white", bordercolor="#F3E0CC"),
    )
    st.caption("Bubble size = HP. Gray = not yet collected.")
    st.plotly_chart(fig_scatter, use_container_width=True, config={"displayModeBar": False})

    # ── Your avg stats vs all Pokémon ─────────────────────────────────────────
    st.markdown('<div class="sec-hdr">📊 Your Collection vs All Pokémon — Average Stats</div>', unsafe_allow_html=True)

    stat_labels = ["HP", "Attack", "Defense", "Sp. Attack", "Sp. Defense", "Speed"]
    stat_cols   = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]

    your_avgs = [cdf[c].mean() for c in stat_cols]
    all_avgs  = [df[c].mean()  for c in stat_cols]

    fig_stats = go.Figure()
    fig_stats.add_trace(go.Bar(
        name="Your Collection", x=stat_labels, y=your_avgs,
        marker=dict(color="#CC0000", line=dict(width=0)),
        text=[f"{v:.0f}" for v in your_avgs], textposition="outside",
        hovertemplate="%{x}: %{y:.1f}<extra></extra>",
    ))
    fig_stats.add_trace(go.Bar(
        name="All 1025 Pokémon", x=stat_labels, y=all_avgs,
        marker=dict(color="#A8A878", opacity=0.75, line=dict(width=0)),
        text=[f"{v:.0f}" for v in all_avgs], textposition="outside",
        hovertemplate="%{x}: %{y:.1f}<extra></extra>",
    ))
    fig_stats.update_layout(
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=360, margin=dict(l=20, r=20, t=20, b=20),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#F3E0CC", zeroline=False, range=[0, max(max(your_avgs), max(all_avgs)) * 1.2]),
        legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        font=dict(family="sans-serif"),
        hoverlabel=dict(bgcolor="white"),
    )
    st.plotly_chart(fig_stats, use_container_width=True, config={"displayModeBar": False})

    # ── Stat leaders table ────────────────────────────────────────────────────
    st.markdown('<div class="sec-hdr">🥇 Your Top 10 by Base Stat Total</div>', unsafe_allow_html=True)
    cdf_display = cdf.copy()
    cdf_display["Base Total"] = cdf_display[stat_cols].sum(axis=1)
    cdf_display["Name"] = cdf_display["name"].str.replace("-", " ").str.title()
    cdf_display["Types"] = cdf_display.apply(
        lambda r: f'{r["type1"].capitalize()}' + (f' / {r["type2"].capitalize()}' if r.get("type2") else ""),
        axis=1,
    )
    top10 = (
        cdf_display[["pokemon_number","Name","Types","hp","attack","defense","sp_attack","sp_defense","speed","Base Total","is_legendary","is_mythical"]]
        .sort_values("Base Total", ascending=False)
        .head(10)
        .rename(columns={"pokemon_number":"#","hp":"HP","attack":"ATK","defense":"DEF",
                          "sp_attack":"SpATK","sp_defense":"SpDEF","speed":"SPD"})
    )
    top10["#"] = top10["#"].astype(int)
    top10["Leg."] = top10.apply(
        lambda r: "⭐ Legendary" if r["is_legendary"] else ("✨ Mythical" if r["is_mythical"] else ""), axis=1
    )
    st.dataframe(
        top10[["#","Name","Types","HP","ATK","DEF","SpATK","SpDEF","SPD","Base Total","Leg."]],
        use_container_width=True, hide_index=True,
    )


def tab_duplicates(entries):
    st.markdown(
        '<div class="phase2-notice">🔧 <strong>Phase 2</strong> — '
        'Duplicate tracking schema is ready in Supabase. Full UI coming next.</div>',
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.markdown(CSS, unsafe_allow_html=True)
    state = load_state()

    try:
        _load_db_into_session()
    except Exception as exc:
        st.error(f"Cannot connect to Supabase: {exc}")
        st.stop()

    # ── PokéAPI ───────────────────────────────────────────────────────────────
    api_total: int
    api_cached_at: Optional[float] = None
    api_offline = False

    try:
        api_total, api_cached_at = _cached_api_total()
    except Exception as exc:
        api_offline = True
        api_total = int(state.get("api_total") or 1025)
        st.warning(f"⚠️ PokéAPI unreachable. Using cached total: {api_total:,}")

    last_seen = state.get("last_seen_total", 0)
    new_pokemon: List[dict] = []
    if not api_offline and api_total > last_seen > 0:
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
    entries  = _to_pokemon_entries(api_total)
    kpis     = compute_kpis(entries, api_total)
    gen_stats = get_generation_stats(entries)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div style="text-align:center;padding:8px 0 4px">'
            '<span style="font-size:28px">⚡</span>'
            '<div style="font-size:18px;font-weight:900;color:#CC0000">Pokédex Tracker</div>'
            f'<div style="font-size:11px;color:#A08060;margin-top:2px">{kpis["pct_complete"]:.1f}% complete</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="pokeball-divider">· · ·</div>', unsafe_allow_html=True)

        st.markdown("**📝 Quick Update**")
        sb_num = st.number_input("Pokémon #", min_value=1, max_value=api_total, step=1, key="sb_num")
        sb_entry = entries.get(sb_num)
        sb_status = "✅ Collected" if (sb_entry and sb_entry.collected) else "❌ Missing"
        st.caption(sb_status)

        # Show mini sprite in sidebar
        st.image(mini_sprite_url(sb_num), width=72)

        sc1, sc2 = st.columns(2)
        if sc1.button("✅ Got it", use_container_width=True, type="primary", key="sb_got"):
            _update_entry(sb_num, 1)
            st.rerun()
        if sc2.button("❌ Missing", use_container_width=True, key="sb_miss"):
            _update_entry(sb_num, 0)
            st.rerun()

        st.markdown('<div class="pokeball-divider">· · ·</div>', unsafe_allow_html=True)
        st.markdown("**🌐 PokéAPI**")
        st.markdown(
            f'<div class="small-muted">Last checked: {fmt_ts(api_cached_at)}</div>'
            f'<div class="small-muted">Total species: {api_total:,}</div>',
            unsafe_allow_html=True,
        )
        if st.button("🔄 Force Refresh", use_container_width=True):
            invalidate_total_cache()
            _cached_api_total.clear()
            st.rerun()

        st.markdown('<div class="pokeball-divider">· · ·</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="small-muted">DB loaded: {fmt_ts(st.session_state.get("db_loaded_at"))}</div>',
            unsafe_allow_html=True,
        )
        if st.button("↺ Reload from DB", use_container_width=True):
            del st.session_state["db_entries"]
            st.rerun()

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="page-title">⚡ Pokédex TCG Tracker</div>'
        f'<div class="page-subtitle">'
        f'{kpis["collected"]:,} / {kpis["effective_total"]:,} Pokémon collected'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── New Pokémon banner ────────────────────────────────────────────────────
    if new_pokemon:
        items = "".join(
            f'<span class="new-chip">#{p["id"]} {p["name"].replace("-"," ").title()}</span>'
            for p in new_pokemon[:24]
        )
        more = f"<em>+{len(new_pokemon)-24} more</em>" if len(new_pokemon) > 24 else ""
        st.markdown(
            f'<div class="new-banner">'
            f'<div class="new-banner-title">🆕 {len(new_pokemon)} New Pokémon Detected!</div>'
            f'<div>{items}{more}</div>'
            f'<div style="font-size:11px;color:#6A1B9A;margin-top:8px">Counted as missing until marked collected.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    t1, t2, t3, t4, t5, t6 = st.tabs(
        ["📊 Overview", "🔲 Pokédex Grid", "❌ Missing", "🔬 Analytics", "✏️ Update", "🔄 Duplicates"]
    )
    with t1: tab_overview(kpis, gen_stats, entries)
    with t2: tab_grid(entries, api_total, new_ids)
    with t3: tab_missing(kpis["gaps"], api_total)
    with t4: tab_analytics(entries)
    with t5: tab_update(entries, api_total)
    with t6: tab_duplicates(entries)


if __name__ == "__main__":
    main()
