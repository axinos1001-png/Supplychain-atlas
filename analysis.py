"""Metrics and calculations. Pure pandas, no database and no UI.

Every function takes a DataFrame of partner totals (columns: partner_country,
trade_value_usd, ...) and returns plain numbers or DataFrames. That makes them
easy to test and easy to explain in a viva.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

HHI_NOTE = (
    "Reading aid only: competition regulators often treat HHI below about "
    "1,500 as low concentration, 1,500-2,500 as moderate and above 2,500 as "
    "high. Exact thresholds differ between authorities, and these bands were "
    "designed for company market shares, so treat them as a rough guide here."
)


@dataclass(frozen=True)
class Summary:
    """The headline numbers shown in the summary cards."""

    total_value_usd: float
    partner_count: int
    top_partner: Optional[str]
    top_partner_share_pct: float


def build_partner_table(partner_totals: pd.DataFrame) -> pd.DataFrame:
    """Rank partners and add share % and cumulative share %.

    Input:  partner_country, trade_value_usd (any order)
    Output: same plus rank, share_pct, cumulative_share_pct, sorted by value.
    """
    if partner_totals.empty:
        return partner_totals.assign(rank=[], share_pct=[], cumulative_share_pct=[])

    table = (
        partner_totals.sort_values(
            ["trade_value_usd", "partner_country"], ascending=[False, True]
        )
        .reset_index(drop=True)
    )
    total = table["trade_value_usd"].sum()
    table["rank"] = table.index + 1
    table["share_pct"] = table["trade_value_usd"] / total * 100
    table["cumulative_share_pct"] = table["share_pct"].cumsum()
    return table


def summarise(table: pd.DataFrame) -> Summary:
    """Total value, partner count and top partner, all computed from the data."""
    if table.empty:
        return Summary(0.0, 0, None, 0.0)
    top = table.iloc[0]
    return Summary(
        total_value_usd=float(table["trade_value_usd"].sum()),
        partner_count=int(len(table)),
        top_partner=str(top["partner_country"]),
        top_partner_share_pct=float(top["share_pct"]),
    )


def top_n_share(table: pd.DataFrame, n: int = 3) -> float:
    """Combined share (%) of the n largest partners. 0 for an empty table."""
    if table.empty:
        return 0.0
    return float(table["share_pct"].head(n).sum())


def hhi(table: pd.DataFrame) -> float:
    """Herfindahl-Hirschman Index on a 0-10,000 scale.

    HHI = sum of (share in %) squared.
      * One partner with 100% share -> 100^2 = 10,000 (fully concentrated)
      * N equal partners            -> 10,000 / N
    """
    if table.empty:
        return 0.0
    return float((table["share_pct"] ** 2).sum())


def hhi_label(value: float) -> str:
    """Plain-language band for an HHI value (see HHI_NOTE for the caveat)."""
    if value < 1500:
        return "Low concentration"
    if value <= 2500:
        return "Moderate concentration"
    return "High concentration"


def format_usd(value: float) -> str:
    """Short human-friendly money string, e.g. 1.2B, 340.5M."""
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 1e9:
        return f"{sign}${abs_value / 1e9:,.2f}B"
    if abs_value >= 1e6:
        return f"{sign}${abs_value / 1e6:,.1f}M"
    if abs_value >= 1e3:
        return f"{sign}${abs_value / 1e3:,.1f}K"
    return f"{sign}${abs_value:,.0f}"


# --- illustrative scenario ---------------------------------------------------
def simulate_top_partner_drop(table: pd.DataFrame, drop_pct: float = 25.0) -> pd.DataFrame:
    """ILLUSTRATIVE what-if: cut the largest partner's value by drop_pct %.

    This is plain arithmetic on the selected numbers. It assumes nothing about
    why trade might fall, whether other partners would make up the gap, or
    what would really happen. It is not a forecast.

    Returns a table with before/after values, shares and ranks.
    """
    if table.empty:
        return table.copy()

    before = table[["partner_country", "trade_value_usd", "share_pct", "rank"]].rename(
        columns={
            "trade_value_usd": "value_before",
            "share_pct": "share_before_pct",
            "rank": "rank_before",
        }
    )
    after = before.copy()
    top_name = before.iloc[0]["partner_country"]
    factor = 1 - drop_pct / 100
    after["value_after"] = after["value_before"]
    after.loc[after["partner_country"] == top_name, "value_after"] *= factor

    total_after = after["value_after"].sum()
    after["share_after_pct"] = after["value_after"] / total_after * 100
    # Rank by the new value; ties broken by name so results are stable.
    after = after.sort_values(
        ["value_after", "partner_country"], ascending=[False, True]
    ).reset_index(drop=True)
    after["rank_after"] = after.index + 1
    after["rank_change"] = after["rank_before"] - after["rank_after"]  # + means moved up
    after["is_reduced"] = after["partner_country"] == top_name
    return after


# --- comparison mode -----------------------------------------------------------
def compare_tables(
    table_a: pd.DataFrame, table_b: pd.DataFrame, label_a: str, label_b: str
) -> pd.DataFrame:
    """Side-by-side partner values for two selections (years or materials).

    Partners missing from one side get 0 on that side. `change_usd` is B - A.
    """
    a = table_a[["partner_country", "trade_value_usd", "share_pct"]].rename(
        columns={"trade_value_usd": "value_a", "share_pct": "share_a_pct"}
    )
    b = table_b[["partner_country", "trade_value_usd", "share_pct"]].rename(
        columns={"trade_value_usd": "value_b", "share_pct": "share_b_pct"}
    )
    merged = a.merge(b, on="partner_country", how="outer").fillna(0.0)
    merged["change_usd"] = merged["value_b"] - merged["value_a"]
    merged["share_change_pts"] = merged["share_b_pct"] - merged["share_a_pct"]
    merged["larger_of_two"] = merged[["value_a", "value_b"]].max(axis=1)
    merged = merged.sort_values(
        ["larger_of_two", "partner_country"], ascending=[False, True]
    ).reset_index(drop=True)
    merged.attrs["label_a"] = label_a
    merged.attrs["label_b"] = label_b
    return merged
