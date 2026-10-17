"""OPTIONAL: download India's trade data from the UN Comtrade public preview API.

This module is deliberately separate from the core app:
  * The dashboard works fully without it (no key, no internet needed).
  * It never writes to the database and never replaces the demo data. It only
    returns a DataFrame; the user decides whether to download or import it.

Known limits (please read before relying on it):
  * It uses the public *preview* endpoint, which needs no key but returns at
    most 500 rows per request and may be rate limited or change without notice.
  * It was written from the public API documentation. It has NOT been tested
    against the live service from the development environment, so treat it as
    a starting point and check the output against comtradeplus.un.org.
  * Reported values are as published by India and/or its partners; revisions,
    re-exports and mirror-data differences mean they will not match other
    sources exactly.
"""

from __future__ import annotations

import pandas as pd
import requests

from data_loader import ALL_COLUMNS

PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
INDIA_REPORTER_CODE = 699  # UN Comtrade numeric code for India
FLOW_CODES = {"Import": "M", "Export": "X"}


class RefreshError(Exception):
    """Raised when the download fails; the message is shown to the user."""


def fetch_comtrade(
    material: str,
    hs_code: str,
    years: list[int],
    flows: list[str],
    timeout: int = 30,
) -> pd.DataFrame:
    """Fetch partner-level annual trade for one HS chapter (e.g. '72').

    Returns a DataFrame in the project schema. Raises RefreshError on any
    network or format problem instead of crashing the app.
    """
    frames: list[pd.DataFrame] = []
    for year in years:
        for flow in flows:
            params = {
                "reporterCode": INDIA_REPORTER_CODE,
                "period": year,
                "cmdCode": hs_code,
                "flowCode": FLOW_CODES[flow],
            }
            try:
                response = requests.get(PREVIEW_URL, params=params, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
            except requests.exceptions.Timeout:
                raise RefreshError("The request timed out. Check your connection and try again.") from None
            except requests.exceptions.ConnectionError:
                raise RefreshError("Could not reach UN Comtrade. Are you offline?") from None
            except requests.exceptions.HTTPError as exc:
                raise RefreshError(
                    f"UN Comtrade returned an error ({exc.response.status_code}). "
                    "The preview service may be rate limiting you; wait and retry."
                ) from None
            except ValueError:
                raise RefreshError("UN Comtrade sent a reply that was not valid JSON.") from None

            records = payload.get("data") if isinstance(payload, dict) else None
            if not records:
                continue  # nothing for this year/flow; not an error
            frames.append(_to_schema(pd.DataFrame(records), material, hs_code, year, flow))

    if not frames:
        raise RefreshError("UN Comtrade returned no rows for that selection.")
    return pd.concat(frames, ignore_index=True)


def _to_schema(raw: pd.DataFrame, material: str, hs_code: str, year: int, flow: str) -> pd.DataFrame:
    """Map Comtrade's field names onto the project schema."""
    needed = {"partnerDesc", "primaryValue"}
    if not needed.issubset(raw.columns):
        raise RefreshError(
            "The reply did not have the expected fields (partnerDesc, primaryValue); "
            "the API format may have changed."
        )
    df = raw
    # Keep the plain "partner, all transport modes, all customs" rows only, so
    # the same trade is not counted several times. Skip a filter if the field
    # is absent.
    if "partnerCode" in df.columns:
        df = df[pd.to_numeric(df["partnerCode"], errors="coerce") != 0]  # 0 = World total
    if "partner2Code" in df.columns:
        df = df[pd.to_numeric(df["partner2Code"], errors="coerce").fillna(0) == 0]
    if "motCode" in df.columns:
        df = df[pd.to_numeric(df["motCode"], errors="coerce").fillna(0) == 0]

    out = pd.DataFrame(
        {
            "year": year,
            "material": material,
            "commodity_code": hs_code,
            "trade_flow": flow,
            "partner_country": df["partnerDesc"],
            "trade_value_usd": df["primaryValue"],
            "net_weight_kg": df["netWgt"] if "netWgt" in df.columns else pd.NA,
        }
    )
    return out[ALL_COLUMNS]
