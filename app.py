"""SupplyChain Atlas - Streamlit interface.

Run with:  streamlit run app.py

This file only handles layout and user interaction. Loading/validating data,
SQL, maths and chart-building each live in their own module.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import analysis
import charts
from comtrade_refresh import RefreshError, fetch_comtrade
from data_loader import DataValidationError, load_trade_csv
from database import DEFAULT_DB_PATH, DEMO, USER, TradeDatabase

st.set_page_config(
    page_title="SupplyChain Atlas",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

PLOT_CONFIG = {"displaylogo": False, "responsive": True}
DEMO_LABEL = "Illustrative demo data - not official statistics"

CSS = """
<style>
  .block-container { padding-top: 2rem; max-width: 1400px; }
  .atlas-hero { padding: 1.6rem 1.8rem; border-radius: 16px; margin-bottom: 1.2rem;
    background: radial-gradient(1200px 300px at 0% 0%, rgba(45,212,191,.16), transparent 60%),
                linear-gradient(135deg, #111a2e 0%, #0d1526 100%);
    border: 1px solid #22304a; }
  .atlas-kicker { letter-spacing: .18em; text-transform: uppercase; font-size: .8rem;
    color: #2dd4bf; font-weight: 700; margin-bottom: .3rem; }
  .atlas-title { font-size: 2.6rem; line-height: 1.1; font-weight: 800; margin: 0; color: #f2f6fc; }
  .atlas-sub { font-size: 1.15rem; color: #b6c4d9; margin-top: .6rem; max-width: 62rem; }
  .atlas-badge { display: inline-block; padding: .35rem .8rem; border-radius: 999px;
    font-weight: 700; font-size: .85rem; margin-top: 1rem; }
  .badge-demo { background: rgba(245,158,11,.15); color: #fbbf24; border: 1px solid #f59e0b; }
  .badge-user { background: rgba(45,212,191,.12); color: #5eead4; border: 1px solid #2dd4bf; }
  .atlas-note { font-size: .95rem; color: #9fb0c8; margin-top: .8rem; }
  .atlas-card { background: #111a2e; border: 1px solid #22304a; border-radius: 14px;
    padding: 1.1rem 1.3rem; height: 100%; }
  .atlas-card .label { font-size: .85rem; letter-spacing: .08em; text-transform: uppercase; color: #9fb0c8; }
  .atlas-card .value { font-size: 2.2rem; font-weight: 800; color: #f2f6fc; line-height: 1.15; }
  .atlas-card .hint { font-size: .95rem; color: #9fb0c8; }
  .atlas-empty { background: #111a2e; border: 1px dashed #3b4f73; border-radius: 14px;
    padding: 2rem; text-align: center; color: #b6c4d9; }
  .atlas-warn { background: rgba(245,158,11,.08); border-left: 4px solid #f59e0b;
    padding: .8rem 1rem; border-radius: 6px; color: #e6edf7; margin: .5rem 0 1rem 0; }
  .hhi-track { position: relative; height: 12px; border-radius: 6px; margin-top: .6rem;
    background: linear-gradient(90deg, #134e4a 0%, #134e4a 15%, #0f766e 15%, #0f766e 25%, #2dd4bf 25%, #2dd4bf 100%); }
  .hhi-marker { position: absolute; top: -5px; width: 4px; height: 22px; background: #f2f6fc; border-radius: 2px; }
  .atlas-footer { color: #7f93b3; font-size: .9rem; border-top: 1px solid #22304a;
    margin-top: 2.5rem; padding-top: 1rem; }
  button[role="tab"] p { font-size: 1.05rem !important; font-weight: 600; }
</style>
"""


# --- setup ---------------------------------------------------------------------
@st.cache_resource
def get_database() -> TradeDatabase:
    """Create the database (and load the demo data) on first run."""
    db_path = Path(os.environ.get("ATLAS_DB_PATH", DEFAULT_DB_PATH))
    db = TradeDatabase(db_path)
    db.ensure_demo_loaded()
    return db


@st.cache_data(show_spinner=False)
def load_partner_table(
    db_path: str, dataset: str, material: str, year: int, flow: str, loaded_at: str
) -> pd.DataFrame:
    """Cached query. `loaded_at` is in the key so importing new data refreshes it."""
    db = TradeDatabase(db_path)
    totals = db.get_partner_totals(dataset, material, year, flow)
    return analysis.build_partner_table(totals)


def partner_table_for(db: TradeDatabase, info, material: str, year: int, flow: str) -> pd.DataFrame:
    return load_partner_table(str(db.db_path), info.dataset, material, int(year), flow, info.loaded_at)


# --- small UI helpers ----------------------------------------------------------
def card(label: str, value: str, hint: str = "") -> str:
    return (
        f'<div class="atlas-card"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div>'
        f'<div class="hint">{html.escape(hint)}</div></div>'
    )


def selection_title(material: str, year: int, flow: str) -> str:
    verb = "imports of" if flow == "Import" else "exports of"
    return f"India's {verb} {material}, {year}"


def show_empty_state(material: str, year: int, flow: str) -> None:
    st.markdown(
        '<div class="atlas-empty"><h3>No records match these filters</h3>'
        f"<p>This dataset has no {html.escape(flow.lower())} records for "
        f"<b>{html.escape(material)}</b> in <b>{year}</b>.<br>"
        "Try another year, material or trade direction in the sidebar.</p></div>",
        unsafe_allow_html=True,
    )


def show_hero(info) -> None:
    badge = (
        '<span class="atlas-badge badge-demo">DEMO DATA &middot; illustrative values, not official statistics</span>'
        if info.is_demo
        else f'<span class="atlas-badge badge-user">Imported data &middot; {html.escape(info.source_name or "user file")}</span>'
    )
    st.markdown(
        f"""
        <div class="atlas-hero">
          <div class="atlas-kicker">Trade-network explorer</div>
          <h1 class="atlas-title">SupplyChain Atlas</h1>
          <div class="atlas-sub">Explore which countries appear as India's reported trade partners for
          engineering materials, how large each partner's share is, and how concentrated that trade is.</div>
          {badge}
          <div class="atlas-note"><b>Data limitations:</b> figures are <i>reported trade between countries</i>.
          They do not trace individual products through factories, suppliers or shipping routes, and the
          scenario on the What-if tab is an illustration, not a forecast.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hhi_bar(value: float) -> str:
    position = min(max(value / 10000, 0), 1) * 100
    return (
        '<div class="hhi-track">'
        f'<div class="hhi-marker" style="left: calc({position:.1f}% - 2px)"></div></div>'
        '<div class="hint" style="display:flex;justify-content:space-between;color:#9fb0c8;font-size:.8rem">'
        "<span>0 (spread out)</span><span>10,000 (one partner)</span></div>"
    )


# --- sidebar --------------------------------------------------------------------
def sidebar_dataset_picker(db: TradeDatabase):
    st.sidebar.header("Data")
    available = db.list_datasets()
    names = {d.dataset: d for d in available}
    choice_labels = {DEMO: "Demo data (illustrative)", USER: "My imported data"}
    options = [d.dataset for d in available]
    dataset = st.sidebar.radio(
        "Dataset", options, format_func=lambda k: choice_labels[k], key="dataset_choice"
    )
    return names[dataset]


def sidebar_filters(db: TradeDatabase, info):
    options = db.get_filter_options(info.dataset)
    st.sidebar.header("Filters")
    material = st.sidebar.selectbox("Material", options["materials"])
    years = options["years"]
    year = st.sidebar.selectbox("Year", years, index=len(years) - 1)
    # Import first: it is the more natural default for a supply-chain question.
    flows = sorted(options["flows"], key=lambda f: f != "Import")
    flow = st.sidebar.radio("Trade direction", flows, horizontal=True)
    top_n = st.sidebar.slider("Partners shown in charts", 5, 20, 12)
    return options, material, int(year), flow, top_n


def sidebar_import(db: TradeDatabase) -> None:
    """Import your own CSV (e.g. from UN Comtrade). Validated before saving."""
    with st.sidebar.expander("Import my own CSV"):
        st.caption(
            "Use the same columns as the demo file (see README). Your data is stored "
            "separately and never replaces the demo data."
        )
        uploaded = st.file_uploader("CSV file", type="csv", key="upload")
        if uploaded is None:
            return
        try:
            clean, report = load_trade_csv(uploaded)
        except DataValidationError as exc:
            st.error(str(exc))
            return
        st.success(f"{report.rows_kept} of {report.rows_in} rows are valid.")
        for reason, count in report.dropped_reasons.items():
            st.warning(f"{count} row(s) skipped: {reason}")
        for note in report.notes:
            st.info(note)
        if st.button("Import as 'My imported data'"):
            db.replace_dataset(USER, clean, label="Imported by user", is_demo=False,
                               source_name=uploaded.name)
            st.success("Imported. Choose 'My imported data' under Dataset.")
            st.rerun()


def sidebar_refresh(db: TradeDatabase, material: str) -> None:
    """Optional UN Comtrade download. Separate from the main flow; never auto-imports."""
    with st.sidebar.expander("Optional: fetch from UN Comtrade"):
        st.caption(
            "Needs internet. Uses the public preview API (max 500 rows per request, may be "
            "rate limited). Not tested against the live service here. Nothing is saved or "
            "replaced unless you choose to import it."
        )
        hs_code = st.text_input("HS chapter code", value="72", max_chars=6)
        year = st.number_input("Year", min_value=2000, max_value=2100, value=2022, step=1)
        flows = st.multiselect("Direction", ["Import", "Export"], default=["Import"])
        label = st.text_input("Material label", value=material)
        if st.button("Download preview"):
            if not flows or not hs_code.strip() or not label.strip():
                st.error("Enter an HS code, a material label and at least one direction.")
                return
            try:
                with st.spinner("Contacting UN Comtrade..."):
                    raw = fetch_comtrade(label.strip(), hs_code.strip(), [int(year)], flows)
                clean, report = load_trade_csv_from_frame(raw)
                st.session_state["comtrade_df"] = clean
                st.session_state["comtrade_name"] = f"comtrade_{hs_code.strip()}_{int(year)}.csv"
            except (RefreshError, DataValidationError) as exc:
                st.error(str(exc))
        fetched = st.session_state.get("comtrade_df")
        if fetched is not None:
            st.write(f"{len(fetched)} rows downloaded.")
            st.download_button("Save as CSV", fetched.to_csv(index=False),
                               file_name=st.session_state["comtrade_name"], mime="text/csv")
            if st.button("Import as 'My imported data'", key="import_fetched"):
                db.replace_dataset(USER, fetched, label="UN Comtrade download", is_demo=False,
                                   source_name=st.session_state["comtrade_name"])
                st.success("Imported. Choose 'My imported data' under Dataset.")
                st.rerun()


def load_trade_csv_from_frame(df: pd.DataFrame):
    """Run downloaded rows through the same validation as an uploaded CSV."""
    from data_loader import validate_and_clean
    return validate_and_clean(df.astype("string"))


# --- tabs -----------------------------------------------------------------------
def tab_explore(table: pd.DataFrame, material: str, year: int, flow: str, top_n: int) -> None:
    title = selection_title(material, year, flow)
    st.plotly_chart(
        charts.partner_bar(table, f"{title}: trade value by partner", top_n),
        width="stretch", config=PLOT_CONFIG,
    )
    left, right = st.columns([1, 1])
    with left:
        st.plotly_chart(
            charts.share_treemap(table, "Share of selected trade by partner (%)"),
            width="stretch", config=PLOT_CONFIG,
        )
    with right:
        view = table[["rank", "partner_country", "trade_value_usd", "share_pct"]]  # cumulative % is in the CSV download
        st.markdown("**Partner shares**")
        st.dataframe(
            view, hide_index=True, width="stretch", height=410,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", width="small"),
                "partner_country": "Partner",
                "trade_value_usd": st.column_config.NumberColumn("Trade value (USD)", format="localized"),
                "share_pct": st.column_config.ProgressColumn(
                    "Share", format="%.1f%%", min_value=0, max_value=100),
            },
        )
    st.download_button("Download this table (CSV)", table.to_csv(index=False),
                       file_name=f"partners_{material}_{year}_{flow}.csv".replace(" ", "_"),
                       mime="text/csv")


def tab_map(table: pd.DataFrame, material: str, year: int, flow: str, top_n: int) -> None:
    fig, unmapped = charts.network_map(
        table, f"{selection_title(material, year, flow)}: partner network", flow, top_n
    )
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
    if unmapped:
        st.caption(
            f"{len(unmapped)} partner(s) among those shown are not on the map because their "
            f"coordinates are not in the built-in list: {', '.join(unmapped)}. "
            "They are still counted everywhere else."
        )
    direction = "partners into India" if flow == "Import" else "India to partners"
    st.caption(
        f"Line width and marker size = trade value ({direction}). Shaded countries are partners; "
        "darker shading = larger value. Positions are approximate country centres, and lines show "
        "who trades with India, not shipping routes. Only the 8 largest partners are labelled; hover for the rest."
    )


def tab_concentration(table: pd.DataFrame) -> None:
    top3 = analysis.top_n_share(table, 3)
    hhi_value = analysis.hhi(table)
    label = analysis.hhi_label(hhi_value)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(card("Top-three partner share", f"{top3:.1f}%",
                         "of the selected trade value"), unsafe_allow_html=True)
    with c2:
        st.markdown(card("HHI (0 - 10,000)", f"{hhi_value:,.0f}", label), unsafe_allow_html=True)
        st.markdown(hhi_bar(hhi_value), unsafe_allow_html=True)

    st.markdown("#### What do these numbers mean?")
    e1, e2 = st.columns(2)
    with e1:
        st.markdown(
            "**Top-three share**  \n"
            "Add up the percentage shares of the three biggest partners. If the answer is 80%, "
            "three countries account for four-fifths of the selected trade value. "
            "A higher number means trade depends on fewer partners."
        )
    with e2:
        st.markdown(
            "**HHI (Herfindahl-Hirschman Index)**  \n"
            "Square each partner's percentage share, then add the squares. Example: shares of "
            "50%, 30% and 20% give 2,500 + 900 + 400 = 3,800. One partner alone gives 10,000; "
            "ten equal partners give 1,000. Squaring makes big partners count extra."
        )
    st.caption(analysis.HHI_NOTE)
    st.caption("Concentration here describes how reported trade value is spread across partners. "
               "It is not a measure of supply risk by itself.")


def tab_scenario(table: pd.DataFrame, material: str, year: int, flow: str) -> None:
    top_name = table.iloc[0]["partner_country"]
    drop_pct = st.slider("Reduction in the largest partner's trade value (%)", 5, 50, 25, step=5)
    st.markdown(f"### What if {top_name}'s trade fell by {drop_pct}%?")
    st.markdown(
        '<div class="atlas-warn"><b>Illustrative calculation, not a prediction.</b> '
        "This only re-does the arithmetic after reducing one number. It assumes nothing about why "
        "trade would fall, whether other partners would fill the gap, or what would really happen.</div>",
        unsafe_allow_html=True,
    )
    after = analysis.simulate_top_partner_drop(table, drop_pct)

    # Rebuild a share table from the "after" values to reuse the same metrics.
    after_for_metrics = after.rename(
        columns={"value_after": "trade_value_usd", "share_after_pct": "share_pct"}
    ).sort_values("trade_value_usd", ascending=False).reset_index(drop=True)
    m1, m2, m3 = st.columns(3)
    before_top3, after_top3 = analysis.top_n_share(table, 3), analysis.top_n_share(after_for_metrics, 3)
    before_hhi, after_hhi = analysis.hhi(table), analysis.hhi(after_for_metrics)
    total_before = table["trade_value_usd"].sum()
    total_after = after["value_after"].sum()
    m1.metric("Total trade value", analysis.format_usd(total_after),
              f"{analysis.format_usd(total_after - total_before)}", delta_color="off")
    m2.metric("Top-three share", f"{after_top3:.1f}%", f"{after_top3 - before_top3:+.1f} pts", delta_color="off")
    m3.metric("HHI", f"{after_hhi:,.0f}", f"{after_hhi - before_hhi:+,.0f}", delta_color="off")

    st.plotly_chart(
        charts.scenario_chart(after, f"{selection_title(material, year, flow)}: partner shares before vs after (illustrative)"),
        width="stretch", config=PLOT_CONFIG,
    )
    moved = after[after["rank_change"] != 0]
    if moved.empty:
        st.info("In this scenario the ranking does not change.")
    else:
        st.markdown("**Ranking changes**")
        view = moved[["partner_country", "rank_before", "rank_after", "share_before_pct", "share_after_pct"]]
        st.dataframe(
            view, hide_index=True, width="stretch",
            column_config={
                "partner_country": "Partner", "rank_before": "Rank before", "rank_after": "Rank after",
                "share_before_pct": st.column_config.NumberColumn("Share before", format="%.1f%%"),
                "share_after_pct": st.column_config.NumberColumn("Share after", format="%.1f%%"),
            },
        )


def tab_compare(db: TradeDatabase, info, options: dict, material: str, year: int, flow: str, top_n: int) -> None:
    mode = st.radio("Compare", ["Two years (same material)", "Two materials (same year)"], horizontal=True)
    years, materials = options["years"], options["materials"]

    if mode.startswith("Two years"):
        others = [y for y in years if y != year]
        if not others:
            st.info("This dataset has only one year, so there is nothing to compare.")
            return
        year_b = st.selectbox("Compare with year", others, index=len(others) - 1)
        table_a = partner_table_for(db, info, material, year, flow)
        table_b = partner_table_for(db, info, material, int(year_b), flow)
        label_a, label_b = str(year), str(year_b)
        title = f"India's {flow.lower()}s of {material}: {label_a} vs {label_b}"
    else:
        others = [m for m in materials if m != material]
        if not others:
            st.info("This dataset has only one material, so there is nothing to compare.")
            return
        material_b = st.selectbox("Compare with material", others)
        table_a = partner_table_for(db, info, material, year, flow)
        table_b = partner_table_for(db, info, material_b, year, flow)
        label_a, label_b = material, material_b
        title = f"India's {flow.lower()}s in {year}: {label_a} vs {label_b}"

    if table_a.empty or table_b.empty:
        empty_side = label_a if table_a.empty else label_b
        st.markdown(
            '<div class="atlas-empty"><h3>One side has no records</h3>'
            f"<p>No matching records for <b>{html.escape(empty_side)}</b>. Pick a different comparison.</p></div>",
            unsafe_allow_html=True,
        )
        return

    sa, sb = analysis.summarise(table_a), analysis.summarise(table_b)
    change = (sb.total_value_usd - sa.total_value_usd)
    pct = f"{change / sa.total_value_usd * 100:+.1f}%" if sa.total_value_usd else "n/a"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Total: {label_a}", analysis.format_usd(sa.total_value_usd))
    c2.metric(f"Total: {label_b}", analysis.format_usd(sb.total_value_usd), pct, delta_color="off")
    c3.metric(f"Top partner: {label_a}", f"{sa.top_partner} ({sa.top_partner_share_pct:.1f}%)")
    c4.metric(f"Top partner: {label_b}", f"{sb.top_partner} ({sb.top_partner_share_pct:.1f}%)")
    h1, h2 = st.columns(2)
    h1.metric(f"HHI: {label_a}", f"{analysis.hhi(table_a):,.0f} - {analysis.hhi_label(analysis.hhi(table_a))}")
    h2.metric(f"HHI: {label_b}", f"{analysis.hhi(table_b):,.0f} - {analysis.hhi_label(analysis.hhi(table_b))}")

    cmp = analysis.compare_tables(table_a, table_b, label_a, label_b)
    st.plotly_chart(charts.comparison_bar(cmp, title, top_n), width="stretch", config=PLOT_CONFIG)
    st.dataframe(
        cmp[["partner_country", "value_a", "value_b", "change_usd", "share_a_pct", "share_b_pct"]],
        hide_index=True, width="stretch",
        column_config={
            "partner_country": "Partner",
            "value_a": st.column_config.NumberColumn(f"Value: {label_a}", format="localized"),
            "value_b": st.column_config.NumberColumn(f"Value: {label_b}", format="localized"),
            "change_usd": st.column_config.NumberColumn("Change (B - A)", format="localized"),
            "share_a_pct": st.column_config.NumberColumn(f"Share: {label_a}", format="%.1f%%"),
            "share_b_pct": st.column_config.NumberColumn(f"Share: {label_b}", format="%.1f%%"),
        },
    )
    if not mode.startswith("Two years"):
        st.caption("Different materials differ greatly in price and volume, so compare shares and "
                   "concentration rather than expecting similar totals.")


def tab_about(info) -> None:
    st.markdown("### About SupplyChain Atlas")
    st.markdown(
        "A college mini-project that explores **reported trade** between India and its partner "
        "countries for a few engineering materials (iron & steel, aluminium, copper, nickel)."
    )
    st.markdown(f"**Dataset in use:** {info.label} &middot; {info.row_count:,} rows &middot; loaded {info.loaded_at}")
    if info.is_demo:
        st.markdown(
            '<div class="atlas-warn"><b>The demo values are invented for illustration.</b> '
            "They are not official statistics and must not be quoted as real trade figures.</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "**Intended source for real data:** [UN Comtrade](https://comtradeplus.un.org/) - export a CSV "
        "with the columns described in the README and import it from the sidebar."
    )
    st.markdown(
        "**What this tool cannot tell you:** which factory, supplier or shipping route a product "
        "took; re-exports and mirror-data differences; or what will happen in the future. "
        "The what-if scenario is arithmetic on the selected numbers, not a forecast."
    )


# --- main ------------------------------------------------------------------------
def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)

    try:
        db = get_database()
    except (DataValidationError, OSError) as exc:
        st.error(f"The database could not be prepared: {exc}")
        st.stop()

    info = sidebar_dataset_picker(db)
    options, material, year, flow, top_n = sidebar_filters(db, info)
    sidebar_import(db)
    sidebar_refresh(db, material)

    show_hero(info)

    table = partner_table_for(db, info, material, year, flow)

    # Summary cards (shown for every selection; zeros if nothing matches).
    summary = analysis.summarise(table)
    c1, c2, c3 = st.columns(3)
    c1.markdown(card("Total trade value", analysis.format_usd(summary.total_value_usd),
                     selection_title(material, year, flow)), unsafe_allow_html=True)
    c2.markdown(card("Partner countries", str(summary.partner_count),
                     "reporting trade in this selection"), unsafe_allow_html=True)
    c3.markdown(card("Top partner", summary.top_partner or "-",
                     f"{summary.top_partner_share_pct:.1f}% of selected trade" if summary.top_partner else "no data"),
                unsafe_allow_html=True)
    st.write("")

    explore, map_tab, conc, whatif, compare, about = st.tabs(
        ["Partners", "Network map", "Concentration", "What-if (illustrative)", "Compare", "About"]
    )
    has_data = not table.empty
    with explore:
        if has_data:
            tab_explore(table, material, year, flow, top_n)
        else:
            show_empty_state(material, year, flow)
    with map_tab:
        if has_data:
            tab_map(table, material, year, flow, top_n)
        else:
            show_empty_state(material, year, flow)
    with conc:
        if has_data:
            tab_concentration(table)
        else:
            show_empty_state(material, year, flow)
    with whatif:
        if has_data:
            tab_scenario(table, material, year, flow)
        else:
            show_empty_state(material, year, flow)
    with compare:
        tab_compare(db, info, options, material, year, flow, top_n)
    with about:
        tab_about(info)

    st.markdown(
        '<div class="atlas-footer">SupplyChain Atlas &middot; college mini-project &middot; '
        "Intended future data source: UN Comtrade (comtradeplus.un.org). "
        + ("<b>Currently showing illustrative demo data, not official statistics.</b>" if info.is_demo
           else "Currently showing data you imported; check it against the original source.")
        + "</div>",
        unsafe_allow_html=True,
    )


main()
