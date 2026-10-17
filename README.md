# SupplyChain Atlas: India's Engineering Materials Trade Network

An interactive dashboard for exploring **India's reported trade** in selected engineering materials (iron & steel, aluminium, copper, nickel): who the trade partners are, how big each partner's share is, and how concentrated that trade is.

> ## Important: the included data is illustrative, not official
> The dataset in `data/demo_trade_data.csv` is **invented sample data** created by `generate_demo_data.py` so the dashboard works offline. **The values are illustrative, not official statistics**, and must not be quoted as real trade figures. The interface shows a "DEMO DATA" badge whenever it is loaded.

> ## What this project is, and is not
> Trade statistics show *reported trade between countries*. They do **not** trace individual products through factories, suppliers or shipping routes. This is a **trade-network explorer**. Anything labelled "what-if" is an **illustrative calculation, not a forecast**.

---

## Features

- Filters for **material**, **year** and **trade direction** (import / export)
- Summary cards: total trade value, number of partner countries, top partner (all calculated from the selected data)
- Ranked, interactive **bar chart** of partner trade values
- **Network map**: India linked to its partners, partner countries shaded, line width and marker size = trade value
- **Partner-share view** (treemap + table with percentage shares)
- **Concentration indicators**: top-three share and Herfindahl-Hirschman Index (HHI), explained in plain language in the app
- **Compare mode**: two years (same material) or two materials (same year)
- **What-if scenario** (optional tab): reduce the largest partner's value by 25% (adjustable) and see how shares, ranking, top-three share and HHI change, clearly labelled illustrative
- Clear **empty state** when no records match, and friendly **error messages** for malformed CSV files
- **Import your own CSV** (stored separately, never overwrites the demo data)
- Optional, separate **UN Comtrade download** helper (needs internet)
- Fully **offline** core: no API key, no network calls, no external map tiles or CDN files

## Technology stack

| Tool | Used for |
|---|---|
| Python 3.10+ | everything |
| Streamlit | the dashboard interface |
| pandas | cleaning, validation, ranking and shares |
| SQLite (`sqlite3`, built into Python) | local storage and queries |
| Plotly | interactive charts and the map |
| requests | **only** the optional Comtrade download helper |
| pytest | automated tests |

## Project structure

```
supplychain_atlas/
├── app.py                    Streamlit interface (layout and user interaction only)
├── data_loader.py            Read + validate CSV files; clear errors for bad data
├── database.py               TradeDatabase class: SQLite setup, storage, queries
├── analysis.py               Maths: shares, top-3, HHI, scenario, comparison
├── charts.py                 Plotly figure builders and the shared dark theme
├── countries.py              Country name spellings + approximate map coordinates
├── comtrade_refresh.py       OPTIONAL UN Comtrade download (separate from the core)
├── generate_demo_data.py     Creates the illustrative demo CSV (fixed random seed)
├── data/
│   ├── demo_trade_data.csv   The illustrative demo dataset (261 invented rows)
│   └── world_outline.json    Country outlines for the map (Natural Earth, public domain)
├── tools/build_world_outline.py   One-off helper that made world_outline.json (not needed to run)
├── tests/test_core.py        Automated tests
├── .streamlit/config.toml    Dark theme
├── requirements.txt
└── README.md
```

**Why it is split this way:** each file has one job. `app.py` never contains SQL or maths; `analysis.py` never touches the database or the screen. That makes each part easy to test and easy to explain.

The SQLite file `data/atlas.db` is **created automatically on first run** (and the demo data loaded into it). It is rebuilt if you delete it.

## Installation and running

```bash
# 1. (Recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the dashboard
streamlit run app.py
```

Streamlit prints a local address (normally http://localhost:8501) and opens it in your browser. No API keys or internet connection are needed.

Run the tests:

```bash
python -m pytest -q
```

Regenerate the demo CSV (optional; it is already included):

```bash
python generate_demo_data.py
```

## How the demo dataset works

- `generate_demo_data.py` writes `data/demo_trade_data.csv` using arbitrary sample weights and a fixed random seed. Totals, shares, partners and years are **invented**: 4 materials x 2 trade directions x 3 years (2021-2023) x 8-13 partners each.
- On first start, `database.py` loads this CSV into SQLite as the dataset named `demo` and flags it as demo data. The interface then shows the DEMO DATA badge.
- Imported data goes in a **separate** dataset named `user`. Switching between them is always an explicit choice in the sidebar; one never silently replaces the other.
- Which country is the "top partner" is **calculated from whatever data is selected**, never hard-coded.

## CSV schema (for replacing demo data with real data)

One row per year / material / commodity code / direction / partner.

| Column | Required | Type | Notes |
|---|---|---|---|
| `year` | yes | whole number | e.g. `2022` |
| `material` | yes | text | label shown in the app, e.g. `Copper` |
| `commodity_code` | yes | text | HS code, e.g. `74`. Kept as text so `0710` stays `0710` |
| `trade_flow` | yes | `Import` or `Export` | also accepts `imports`, `exports`, `M`, `X` (any case) |
| `partner_country` | yes | text | e.g. `China`. Common variants (`USA`, `Russian Federation`...) are tidied |
| `trade_value_usd` | yes | number >= 0 | trade value in US dollars |
| `net_weight_kg` | no | number >= 0 | may be blank or the column may be absent |

Example:

```csv
year,material,commodity_code,trade_flow,partner_country,trade_value_usd,net_weight_kg
2022,Copper,74,Import,Chile,1500000000,170000000
```

**To use it:** open the sidebar, expand **Import my own CSV**, upload the file, check the validation summary, then press **Import**. Then choose **My imported data** under *Dataset*.

**What the validator does:** header names are matched ignoring case and spaces; rows with a bad year, unknown direction, missing partner, or non-numeric/negative value are skipped and counted with the reason; "World"/"Total" rows are removed so nothing is double-counted; exact duplicate rows are dropped; rows with the same year/material/code/direction/partner are added together (and you are told). If the file is empty, unreadable, missing required columns, or has no usable rows, you get an explanatory message instead of a crash.

A UN Comtrade export has different column names (`refYear`, `partnerDesc`, `primaryValue`...), so rename or reshape them to the schema above first.

## Data source and API limitations

- **Intended source for real data: [UN Comtrade](https://comtradeplus.un.org/).** Trade is whatever India (the reporter) and/or its partners reported to the UN. Revisions, re-exports, valuation differences and gaps between importer and exporter ("mirror") reports mean figures can differ from other sources.
- The sidebar's **Optional: fetch from UN Comtrade** section uses Comtrade's public *preview* endpoint:
  - it needs internet, and is **kept completely separate** from the offline core;
  - it returns at most 500 rows per request and may be rate limited or change;
  - it was written from the public documentation and **has not been tested against the live service** in the environment where this project was built. Check any download against comtradeplus.un.org;
  - it only *downloads* into memory. You may save it as CSV or import it as "My imported data". It **never** replaces the demo data automatically.
- Country positions on the map are approximate centres. Lines on the map show who trades with India, not shipping routes. A few small partners (for example Singapore, Hong Kong) are missing from the 1:110m outline, so they appear as markers but are not shaded. Partners missing from `countries.py` are listed under the map and still counted everywhere else.
- Map outlines: Natural Earth (public domain).

## Top-three share and HHI in beginner-friendly terms

**Top-three share.** Take the three biggest partners and add their percentage shares. If the answer is 80%, three countries account for four-fifths of the selected trade value. Higher = trade is concentrated in fewer partners.

**HHI (Herfindahl-Hirschman Index).** Square each partner's percentage share, then add up the squares.

- Shares of 50%, 30%, 20% give 50² + 30² + 20² = 2,500 + 900 + 400 = **3,800**
- One partner with 100% gives 100² = **10,000** (maximum)
- Ten equal partners (10% each) give 10 x 10² = **1,000**

Squaring makes large partners count extra, so HHI reacts more to one dominant partner than top-three share does. The app's "low / moderate / high" labels use common competition-policy rules of thumb (about 1,500 and 2,500). Those were designed for company market shares and different authorities use different cut-offs, so treat them as a reading aid only. **Concentration describes how reported trade value is spread; it is not a measure of supply risk by itself.**

## The what-if scenario

It takes the largest partner (found from the data), multiplies its value by 0.75 (the slider allows 5-50%), recalculates every partner's share, re-ranks, and recomputes top-three share and HHI. That is **only arithmetic on the selected numbers.** It says nothing about why trade might fall, whether other partners would fill the gap, or what would really happen. It is not a forecast.

---

## Suggested viva explanation (about 1 minute)

> "SupplyChain Atlas is a trade-network explorer for India's reported trade in four engineering materials. It stores data in SQLite, cleans and validates CSV input with pandas, and shows it in a Streamlit dashboard with Plotly charts. I separated the code by responsibility: `data_loader` validates, `database` stores and queries through a `TradeDatabase` class, `analysis` does the maths, `charts` draws, and `app` only arranges the screen. The bundled data is invented demo data, clearly labelled, so the app works offline; real UN Comtrade data can be imported with the same CSV schema. For each selection it ranks partners and computes each partner's share, then measures concentration using the top-three share and the Herfindahl-Hirschman Index. The what-if tab is illustrative arithmetic, not a forecast, and the app cannot trace individual products through supply chains because trade statistics don't contain that information."

## Questions to be ready for

1. Why is this a "trade-network explorer" and not a supply-chain tracker? What can't the data tell you?
2. Why SQLite instead of just reading the CSV each time? (Queries with filters, persistence, indexes, separate demo/user datasets.)
3. What does `TradeDatabase` do, and why is a class a sensible choice here? What is `self.db_path` for?
4. What is a parameterised SQL query (the `?` placeholders), and what attack does it prevent? (SQL injection)
5. Walk through `validate_and_clean`: what happens to a row with a negative value? A "World" row? Why remove "World"?
6. Why is `commodity_code` read as text? (Leading zeros.)
7. Define top-three share. Compute HHI by hand for shares 50/30/20. What are its minimum and maximum?
8. Why does HHI square the shares? How do top-three share and HHI differ in what they show?
9. Can high concentration be harmless, or low concentration risky? (It only describes value shares, not supply risk.)
10. How is the "top partner" found? Why is it never hard-coded?
11. Explain the what-if calculation step by step. Why isn't it a prediction?
12. Why does the demo data exist, and how do you know it is not real? How would you switch to real data?
13. What are the limits of the Comtrade data (reporter vs partner, revisions, re-exports) and of the optional download helper?
14. Why did you draw the map from a bundled outline file? (Plotly's own map layer downloads files from the internet; this app must work offline.)
15. What does `@st.cache_data` do, and why does the cache key include `loaded_at`?
16. How would you test `analysis.py`? (Pure functions: see `tests/test_core.py`.)
17. What would you improve next? (More materials/years, partner-country groups, trade-unit-value analysis, mirror-data checks.)
18. How does the project use Git well? (Small modules, `.gitignore` for the database and personal data, tests, reproducible demo data.)

## Git-friendly notes

`.gitignore` excludes the generated database (`data/*.db`), virtual environments, caches and your personal downloads (`data/user_*.csv`). The demo CSV is committed so a fresh clone works immediately. Suggested first commits: data + loader, database, analysis, charts, app, README.

---

*SupplyChain Atlas is a college mini-project. Demo values are illustrative, not official statistics. Intended future data source: UN Comtrade.*
