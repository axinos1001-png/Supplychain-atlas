"""SQLite storage for SupplyChain Atlas.

Responsibility of this module: create the database on first run, store
validated data, and answer queries. It knows nothing about charts or Streamlit.

Two datasets can live side by side in one table, told apart by the `dataset`
column:
    "demo" - the illustrative sample data shipped with the project
    "user" - data the user explicitly imported (e.g. a UN Comtrade CSV)
Keeping them separate means importing real data can never silently overwrite
the demo data (or the other way round).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd

from data_loader import DEMO_CSV_PATH, load_trade_csv

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "atlas.db"

DEMO = "demo"
USER = "user"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trade (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset          TEXT    NOT NULL,
    year             INTEGER NOT NULL,
    material         TEXT    NOT NULL,
    commodity_code   TEXT    NOT NULL,
    trade_flow       TEXT    NOT NULL CHECK (trade_flow IN ('Import', 'Export')),
    partner_country  TEXT    NOT NULL,
    trade_value_usd  REAL    NOT NULL CHECK (trade_value_usd >= 0),
    net_weight_kg    REAL
);
CREATE INDEX IF NOT EXISTS idx_trade_filters
    ON trade (dataset, material, year, trade_flow);

CREATE TABLE IF NOT EXISTS dataset_info (
    dataset      TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    is_demo      INTEGER NOT NULL,
    source_name  TEXT,
    row_count    INTEGER NOT NULL,
    loaded_at    TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class DatasetInfo:
    dataset: str
    label: str
    is_demo: bool
    source_name: Optional[str]
    row_count: int
    loaded_at: str


class TradeDatabase:
    """A small wrapper around one SQLite file.

    A class fits here because every method needs the same piece of state (the
    database path), and grouping them keeps SQL out of the rest of the app.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    # --- connection helpers ------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create tables if they do not exist (safe to call every run)."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # --- writing -----------------------------------------------------------
    def replace_dataset(
        self,
        dataset: str,
        df: pd.DataFrame,
        label: str,
        is_demo: bool,
        source_name: str = "",
    ) -> int:
        """Replace ONE dataset ('demo' or 'user') with the rows in `df`.

        Delete + insert run in a single transaction, so a failure part-way
        leaves the old data untouched.
        """
        rows = df.assign(dataset=dataset)[
            [
                "dataset", "year", "material", "commodity_code",
                "trade_flow", "partner_country", "trade_value_usd", "net_weight_kg",
            ]
        ]
        # NaN -> None so SQLite stores NULL for a missing weight.
        records = [
            tuple(None if pd.isna(v) else v for v in row)
            for row in rows.itertuples(index=False, name=None)
        ]
        with self._connect() as conn:
            conn.execute("DELETE FROM trade WHERE dataset = ?", (dataset,))
            conn.executemany(
                "INSERT INTO trade (dataset, year, material, commodity_code, "
                "trade_flow, partner_country, trade_value_usd, net_weight_kg) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(r[0], int(r[1]), *r[2:]) for r in records],
            )
            conn.execute(
                "INSERT OR REPLACE INTO dataset_info VALUES (?, ?, ?, ?, ?, ?)",
                (
                    dataset, label, int(is_demo), source_name, len(records),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        return len(records)

    def ensure_demo_loaded(self, csv_path: Path = DEMO_CSV_PATH) -> None:
        """Load the demo CSV on first run (when no demo dataset exists yet)."""
        if self.get_dataset_info(DEMO) is not None:
            return
        df, _report = load_trade_csv(csv_path)
        self.replace_dataset(
            DEMO, df,
            label="Illustrative demo data (NOT official statistics)",
            is_demo=True,
            source_name=csv_path.name,
        )

    # --- reading -----------------------------------------------------------
    def get_dataset_info(self, dataset: str) -> Optional[DatasetInfo]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT dataset, label, is_demo, source_name, row_count, loaded_at "
                "FROM dataset_info WHERE dataset = ?",
                (dataset,),
            ).fetchone()
        if row is None:
            return None
        return DatasetInfo(row[0], row[1], bool(row[2]), row[3], row[4], row[5])

    def list_datasets(self) -> list[DatasetInfo]:
        return [
            info for info in (self.get_dataset_info(DEMO), self.get_dataset_info(USER))
            if info is not None
        ]

    def get_filter_options(self, dataset: str) -> dict[str, list]:
        """Distinct materials, years and flows available in a dataset."""
        with self._connect() as conn:
            def distinct(column: str) -> list:
                # `column` is chosen from a fixed list below, never from user input.
                cur = conn.execute(
                    f"SELECT DISTINCT {column} FROM trade WHERE dataset = ? ORDER BY {column}",
                    (dataset,),
                )
                return [r[0] for r in cur.fetchall()]

            return {
                "materials": distinct("material"),
                "years": distinct("year"),
                "flows": distinct("trade_flow"),
            }

    def get_partner_totals(
        self, dataset: str, material: str, year: int, trade_flow: str
    ) -> pd.DataFrame:
        """Total trade per partner for one material / year / flow.

        Returns columns: partner_country, trade_value_usd, net_weight_kg.
        An empty DataFrame (not an error) means "no records match".
        """
        query = """
            SELECT partner_country,
                   SUM(trade_value_usd) AS trade_value_usd,
                   SUM(net_weight_kg)   AS net_weight_kg
            FROM trade
            WHERE dataset = ? AND material = ? AND year = ? AND trade_flow = ?
            GROUP BY partner_country
            HAVING SUM(trade_value_usd) > 0
            ORDER BY trade_value_usd DESC
        """
        with self._connect() as conn:
            return pd.read_sql_query(
                query, conn, params=(dataset, material, int(year), trade_flow)
            )
