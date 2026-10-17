"""Tests for the non-UI parts. Run with:  python -m pytest -q"""

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import analysis  # noqa: E402
import charts  # noqa: E402
from data_loader import DataValidationError, load_trade_csv  # noqa: E402
from database import DEMO, TradeDatabase  # noqa: E402

HEADER = "year,material,commodity_code,trade_flow,partner_country,trade_value_usd,net_weight_kg\n"


def table_from(values: dict[str, float]) -> pd.DataFrame:
    df = pd.DataFrame({"partner_country": list(values), "trade_value_usd": list(values.values())})
    return analysis.build_partner_table(df)


# --- analysis ------------------------------------------------------------------
def test_shares_sum_to_100_and_rank_order():
    t = table_from({"A": 50, "B": 30, "C": 20})
    assert t["share_pct"].sum() == pytest.approx(100)
    assert list(t["partner_country"]) == ["A", "B", "C"]
    assert list(t["rank"]) == [1, 2, 3]


def test_hhi_known_values():
    assert analysis.hhi(table_from({"A": 50, "B": 30, "C": 20})) == pytest.approx(3800)
    assert analysis.hhi(table_from({"A": 1})) == pytest.approx(10000)
    assert analysis.hhi(table_from({str(i): 1 for i in range(10)})) == pytest.approx(1000)


def test_top_three_share():
    t = table_from({"A": 40, "B": 30, "C": 20, "D": 10})
    assert analysis.top_n_share(t, 3) == pytest.approx(90)
    assert analysis.top_n_share(table_from({"A": 5, "B": 5}), 3) == pytest.approx(100)


def test_summary_is_calculated_not_hardcoded():
    s = analysis.summarise(table_from({"Zed": 90, "Amy": 10}))
    assert s.top_partner == "Zed" and s.partner_count == 2
    assert s.total_value_usd == 100 and s.top_partner_share_pct == pytest.approx(90)


def test_empty_inputs_do_not_crash():
    empty = analysis.build_partner_table(pd.DataFrame(columns=["partner_country", "trade_value_usd"]))
    assert empty.empty
    assert analysis.summarise(empty).top_partner is None
    assert analysis.hhi(empty) == 0 and analysis.top_n_share(empty) == 0


def test_scenario_reduces_only_top_partner_and_can_change_ranking():
    t = table_from({"A": 100, "B": 90, "C": 10})
    after = analysis.simulate_top_partner_drop(t, 25)
    a = after.set_index("partner_country")
    assert a.loc["A", "value_after"] == pytest.approx(75)
    assert a.loc["B", "value_after"] == pytest.approx(90)
    assert a.loc["B", "rank_after"] == 1 and a.loc["A", "rank_after"] == 2
    assert after["share_after_pct"].sum() == pytest.approx(100)


def test_compare_handles_partner_missing_on_one_side():
    a, b = table_from({"X": 10, "Y": 10}), table_from({"X": 5, "Z": 15})
    cmp = analysis.compare_tables(a, b, "A", "B").set_index("partner_country")
    assert cmp.loc["Y", "value_b"] == 0 and cmp.loc["Z", "value_a"] == 0
    assert cmp.loc["X", "change_usd"] == -5


def test_format_usd():
    assert analysis.format_usd(2_500_000_000) == "$2.50B"
    assert analysis.format_usd(-3_200_000) == "-$3.2M"


# --- data loader -----------------------------------------------------------------
def test_good_csv_loads():
    csv = HEADER + "2022,Copper,74,Import,Chile,1000,500\n2022,Copper,74,Export,Japan,2000,\n"
    df, report = load_trade_csv(io.StringIO(csv))
    assert len(df) == 2 and report.rows_dropped == 0
    assert df["net_weight_kg"].isna().sum() == 1  # weight is optional


def test_malformed_rows_are_dropped_with_reasons():
    csv = HEADER + "\n".join([
        "2022,Copper,74,Import,Chile,1000,500",   # good
        "abcd,Copper,74,Import,Chile,1000,500",   # bad year
        "2022,Copper,74,Sideways,Chile,1000,500",  # bad flow
        "2022,Copper,74,Import,Chile,notanumber,5",  # bad value
        "2022,Copper,74,Import,Chile,-50,5",      # negative value
        "2022,Copper,74,Import,,100,5",           # missing partner
        "2022,Copper,74,Import,World,9999,5",     # aggregate row
    ]) + "\n"
    df, report = load_trade_csv(io.StringIO(csv))
    assert len(df) == 1
    assert report.rows_dropped == 6 and len(report.dropped_reasons) >= 5


def test_flow_spellings_and_header_case_accepted():
    csv = "Year,Material,Commodity_Code,Trade_Flow,Partner_Country,Trade_Value_USD\n2022,Copper,74,imports,USA,10\n"
    df, _ = load_trade_csv(io.StringIO(csv))
    assert df.iloc[0]["trade_flow"] == "Import" and df.iloc[0]["partner_country"] == "United States"


def test_missing_column_gives_clear_error():
    with pytest.raises(DataValidationError, match="Missing required column"):
        load_trade_csv(io.StringIO("year,material\n2022,Copper\n"))


def test_all_rows_bad_gives_clear_error():
    with pytest.raises(DataValidationError, match="No usable rows"):
        load_trade_csv(io.StringIO(HEADER + "x,Copper,74,Import,Chile,1,1\n"))


def test_empty_and_missing_files():
    with pytest.raises(DataValidationError):
        load_trade_csv(io.StringIO(""))
    with pytest.raises(DataValidationError, match="not found"):
        load_trade_csv("definitely_not_here.csv")


def test_duplicate_partner_rows_are_added_together():
    csv = HEADER + "2022,Copper,74,Import,Chile,100,\n2022,Copper,74,Import,Chile,50,\n"
    df, report = load_trade_csv(io.StringIO(csv))
    assert len(df) == 1 and df.iloc[0]["trade_value_usd"] == 150 and report.notes


def test_leading_zero_commodity_codes_survive():
    df, _ = load_trade_csv(io.StringIO(HEADER + "2022,Veg,0710,Import,Chile,10,\n"))
    assert df.iloc[0]["commodity_code"] == "0710"


# --- database ----------------------------------------------------------------------
def test_database_is_created_and_demo_loaded_automatically(tmp_path):
    db_file = tmp_path / "new" / "atlas.db"
    assert not db_file.exists()
    db = TradeDatabase(db_file)
    db.ensure_demo_loaded()
    assert db_file.exists()
    info = db.get_dataset_info(DEMO)
    assert info.is_demo and info.row_count > 0
    db.ensure_demo_loaded()  # second call must not duplicate rows
    assert db.get_dataset_info(DEMO).row_count == info.row_count


def test_every_demo_filter_combination_returns_data(tmp_path):
    db = TradeDatabase(tmp_path / "atlas.db")
    db.ensure_demo_loaded()
    opts = db.get_filter_options(DEMO)
    assert opts["flows"] == ["Export", "Import"] and len(opts["materials"]) >= 3
    for material in opts["materials"]:
        for year in opts["years"]:
            for flow in opts["flows"]:
                table = analysis.build_partner_table(db.get_partner_totals(DEMO, material, year, flow))
                assert not table.empty
                assert table["share_pct"].sum() == pytest.approx(100)
                # Every chart builds for every combination.
                charts.partner_bar(table, "t")
                charts.share_treemap(table, "t")
                charts.network_map(table, "t", flow)
                charts.scenario_chart(analysis.simulate_top_partner_drop(table, 25), "t")


def test_no_match_returns_empty_not_error(tmp_path):
    db = TradeDatabase(tmp_path / "atlas.db")
    db.ensure_demo_loaded()
    assert db.get_partner_totals(DEMO, "Unobtainium", 1999, "Import").empty


def test_sql_injection_text_is_just_text(tmp_path):
    db = TradeDatabase(tmp_path / "atlas.db")
    db.ensure_demo_loaded()
    assert db.get_partner_totals(DEMO, "x'; DROP TABLE trade;--", 2022, "Import").empty
    assert db.get_dataset_info(DEMO).row_count > 0


def test_user_dataset_is_separate_from_demo(tmp_path):
    db = TradeDatabase(tmp_path / "atlas.db")
    db.ensure_demo_loaded()
    demo_rows = db.get_dataset_info(DEMO).row_count
    df, _ = load_trade_csv(io.StringIO(HEADER + "2020,Zinc,79,Import,Peru,10,\n"))
    db.replace_dataset("user", df, "mine", is_demo=False, source_name="x.csv")
    assert db.get_dataset_info(DEMO).row_count == demo_rows
    assert db.get_filter_options("user")["materials"] == ["Zinc"]
    assert not db.get_dataset_info("user").is_demo


def test_map_reports_unmapped_partners():
    t = table_from({"China": 10, "Atlantis": 5})
    _, unmapped = charts.network_map(t, "t", "Import")
    assert unmapped == ["Atlantis"]
