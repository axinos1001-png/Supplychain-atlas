"""Load and validate trade data from CSV.

Responsibility of this module: turn "whatever CSV the user gives us" into a
clean pandas DataFrame with the project schema, or raise a DataValidationError
with a message a human can act on. It never touches the database or the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Union

import pandas as pd

from countries import normalise_country

REQUIRED_COLUMNS = [
    "year",
    "material",
    "commodity_code",
    "trade_flow",
    "partner_country",
    "trade_value_usd",
]
OPTIONAL_COLUMNS = ["net_weight_kg"]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Spellings we accept for the trade flow, mapped to the two allowed values.
FLOW_ALIASES = {
    "import": "Import",
    "imports": "Import",
    "m": "Import",
    "export": "Export",
    "exports": "Export",
    "x": "Export",
}

# Rows that are totals, not real partner countries. Keeping them would
# double-count trade, so they are removed (and reported).
AGGREGATE_PARTNERS = {"world", "total", "all countries", "areas, nes"}

DEMO_CSV_PATH = Path(__file__).parent / "data" / "demo_trade_data.csv"

CsvSource = Union[str, Path, IO]


class DataValidationError(Exception):
    """Raised when a file cannot be used. The message is shown to the user."""


@dataclass
class ValidationReport:
    """Summary of what happened during cleaning, shown in the UI."""

    rows_in: int = 0
    rows_kept: int = 0
    dropped_reasons: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def rows_dropped(self) -> int:
        return self.rows_in - self.rows_kept

    def drop(self, reason: str, count: int) -> None:
        if count > 0:
            self.dropped_reasons[reason] = self.dropped_reasons.get(reason, 0) + count


def read_csv(source: CsvSource) -> pd.DataFrame:
    """Read a CSV into a DataFrame (all text, so we control the conversion)."""
    try:
        # dtype=str keeps commodity codes such as "0710" from losing zeros.
        df = pd.read_csv(source, dtype=str, skipinitialspace=True)
    except FileNotFoundError:
        raise DataValidationError(f"File not found: {source}") from None
    except pd.errors.EmptyDataError:
        raise DataValidationError("The file is empty.") from None
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise DataValidationError(
            f"The file could not be read as a CSV ({exc.__class__.__name__}). "
            "Check that it is comma-separated, UTF-8 text."
        ) from None
    return df


def validate_and_clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, ValidationReport]:
    """Check the schema, fix what is fixable, drop what is not, and report."""
    report = ValidationReport(rows_in=len(raw))
    df = raw.copy()

    # Be forgiving about header capitalisation and stray spaces.
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError(
            "Missing required column(s): "
            + ", ".join(missing)
            + ". Expected columns: "
            + ", ".join(ALL_COLUMNS)
            + "."
        )
    if df.empty:
        raise DataValidationError("The file has a header but no data rows.")

    if "net_weight_kg" not in df.columns:
        df["net_weight_kg"] = pd.NA
    df = df[ALL_COLUMNS]

    # --- text columns -------------------------------------------------------
    for col in ["material", "commodity_code", "trade_flow", "partner_country"]:
        df[col] = df[col].astype("string").str.strip()

    # --- numeric columns: bad values become NaN, then get dropped -----------
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["trade_value_usd"] = pd.to_numeric(df["trade_value_usd"], errors="coerce")
    df["net_weight_kg"] = pd.to_numeric(df["net_weight_kg"], errors="coerce")

    # --- trade flow: map spellings, anything else is invalid -----------------
    df["trade_flow"] = df["trade_flow"].str.lower().map(FLOW_ALIASES)

    # --- drop invalid rows, one reason at a time so we can explain them -----
    def drop_where(mask: pd.Series, reason: str) -> None:
        nonlocal df
        mask = mask.fillna(True)
        report.drop(reason, int(mask.sum()))
        df = df[~mask]

    drop_where(df["year"].isna() | (df["year"] % 1 != 0), "year missing or not a whole number")
    drop_where(~df["year"].between(1900, 2100), "year outside 1900-2100")
    drop_where(df["trade_flow"].isna(), "trade_flow not Import/Export")
    drop_where(df["material"].isna() | (df["material"] == ""), "material missing")
    drop_where(df["commodity_code"].isna() | (df["commodity_code"] == ""), "commodity_code missing")
    drop_where(df["partner_country"].isna() | (df["partner_country"] == ""), "partner_country missing")
    drop_where(df["trade_value_usd"].isna(), "trade_value_usd missing or not a number")
    drop_where(df["trade_value_usd"] < 0, "trade_value_usd negative")

    # Remove "World"/"Total" rows that would double-count the partners.
    df["partner_country"] = df["partner_country"].map(normalise_country)
    is_aggregate = df["partner_country"].str.lower().isin(AGGREGATE_PARTNERS)
    drop_where(is_aggregate, "aggregate row (World/Total), not a partner country")

    # Negative or odd weights are not fatal: weight is optional, so blank it.
    bad_weight = df["net_weight_kg"] < 0
    if bad_weight.any():
        report.notes.append(f"{int(bad_weight.sum())} negative net_weight_kg value(s) were blanked.")
        df.loc[bad_weight, "net_weight_kg"] = pd.NA

    if df.empty:
        raise DataValidationError(
            "No usable rows remained after validation. Reasons: "
            + "; ".join(f"{k} ({v})" for k, v in report.dropped_reasons.items())
        )

    # --- duplicates ---------------------------------------------------------
    before = len(df)
    df = df.drop_duplicates()
    report.drop("exact duplicate row", before - len(df))

    key = ["year", "material", "commodity_code", "trade_flow", "partner_country"]
    dup_keys = int(df.duplicated(subset=key).sum())
    if dup_keys:
        # Same partner listed twice for the same slice: add them up and say so.
        report.notes.append(
            f"{dup_keys} row(s) shared the same year/material/code/flow/partner and were added together."
        )
        df = df.groupby(key, as_index=False, dropna=False).agg(
            trade_value_usd=("trade_value_usd", "sum"),
            net_weight_kg=("net_weight_kg", lambda s: s.sum(min_count=1)),
        )

    df["year"] = df["year"].astype(int)
    df["trade_value_usd"] = df["trade_value_usd"].astype(float)
    df = df[ALL_COLUMNS].reset_index(drop=True)

    report.rows_kept = len(df)
    return df, report


def load_trade_csv(source: CsvSource) -> tuple[pd.DataFrame, ValidationReport]:
    """Convenience wrapper: read a CSV and validate it in one call."""
    return validate_and_clean(read_csv(source))
