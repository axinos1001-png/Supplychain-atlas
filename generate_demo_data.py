"""Generate the ILLUSTRATIVE demo dataset for SupplyChain Atlas.

Every number written by this script is INVENTED for demonstration.
It is NOT official trade data and must never be quoted as real statistics.

Run:  python generate_demo_data.py
Output: data/demo_trade_data.csv

The script uses a fixed random seed so the CSV is reproducible. The partner
weights below are arbitrary sample weights chosen only to make the charts
interesting; they do not describe any real trade relationship.
"""

import csv
import random
from pathlib import Path

SEED = 2024
OUTPUT = Path(__file__).parent / "data" / "demo_trade_data.csv"

YEARS = [2021, 2022, 2023]

# material -> (HS chapter code, invented price in USD per kg used to derive weights)
MATERIALS = {
    "Iron & Steel": ("72", 0.85),
    "Aluminium": ("76", 2.60),
    "Copper": ("74", 8.20),
    "Nickel": ("75", 19.00),
}

# Invented total trade size (million USD) per material and flow, for year 2021.
BASE_TOTAL_MUSD = {
    ("Iron & Steel", "Import"): 9000,
    ("Iron & Steel", "Export"): 12000,
    ("Aluminium", "Import"): 4500,
    ("Aluminium", "Export"): 3200,
    ("Copper", "Import"): 3800,
    ("Copper", "Export"): 2100,
    ("Nickel", "Import"): 900,
    ("Nickel", "Export"): 150,
}

# Invented growth factor per year (relative to 2021), per material.
YEAR_FACTOR = {
    "Iron & Steel": {2021: 1.00, 2022: 1.12, 2023: 1.05},
    "Aluminium": {2021: 1.00, 2022: 1.18, 2023: 1.09},
    "Copper": {2021: 1.00, 2022: 1.10, 2023: 1.15},
    "Nickel": {2021: 1.00, 2022: 1.30, 2023: 1.02},
}

# Arbitrary sample weights per (material, flow). Higher = bigger sample share.
PARTNER_WEIGHTS = {
    ("Iron & Steel", "Import"): {
        "China": 22, "Japan": 16, "South Korea": 14, "Russia": 9, "Vietnam": 6,
        "Germany": 6, "Indonesia": 5, "Australia": 4, "Italy": 3, "Taiwan": 3,
        "Ukraine": 2, "Brazil": 2,
    },
    ("Iron & Steel", "Export"): {
        "Italy": 12, "Belgium": 10, "United Arab Emirates": 10, "Vietnam": 9,
        "Nepal": 8, "Spain": 7, "United States": 7, "Germany": 6,
        "Saudi Arabia": 5, "Bangladesh": 5, "Turkey": 4, "Netherlands": 4,
        "United Kingdom": 3,
    },
    ("Aluminium", "Import"): {
        "China": 24, "United Arab Emirates": 14, "Russia": 10, "Australia": 8,
        "Malaysia": 7, "Saudi Arabia": 6, "Indonesia": 6, "Japan": 5,
        "Germany": 4, "Vietnam": 4, "South Korea": 3,
    },
    ("Aluminium", "Export"): {
        "United States": 18, "Italy": 9, "United Arab Emirates": 8, "Germany": 8,
        "United Kingdom": 7, "Netherlands": 6, "Saudi Arabia": 5, "Belgium": 5,
        "Bangladesh": 4, "Sri Lanka": 3, "France": 3,
    },
    ("Copper", "Import"): {
        "Chile": 15, "Japan": 12, "Tanzania": 8, "Indonesia": 8, "Malaysia": 8,
        "China": 7, "Singapore": 6, "South Africa": 5, "Zambia": 5,
        "United Arab Emirates": 4, "Thailand": 4, "Peru": 3,
    },
    ("Copper", "Export"): {
        "China": 20, "Germany": 10, "United States": 9, "Saudi Arabia": 7,
        "Italy": 7, "United Arab Emirates": 6, "Malaysia": 5, "South Korea": 5,
        "Singapore": 4, "Turkey": 3, "Taiwan": 3,
    },
    ("Nickel", "Import"): {
        "Indonesia": 20, "China": 14, "Russia": 12, "Australia": 9, "Canada": 8,
        "Philippines": 7, "Norway": 6, "South Africa": 5, "Brazil": 3,
    },
    ("Nickel", "Export"): {
        "United Arab Emirates": 15, "Germany": 12, "United States": 11,
        "Italy": 8, "Singapore": 7, "France": 6, "Japan": 5, "United Kingdom": 4,
    },
}


def build_rows(rng: random.Random) -> list[dict]:
    """Turn the sample weights into CSV rows with a little random wobble."""
    rows: list[dict] = []
    for (material, flow), weights in PARTNER_WEIGHTS.items():
        code, price_per_kg = MATERIALS[material]
        total_weight = sum(weights.values())
        for year in YEARS:
            year_total_usd = (
                BASE_TOTAL_MUSD[(material, flow)]
                * 1_000_000
                * YEAR_FACTOR[material][year]
            )
            for partner, weight in weights.items():
                # +/- 15% wobble so each year looks a little different.
                wobble = rng.uniform(0.85, 1.15)
                value = year_total_usd * (weight / total_weight) * wobble
                # Invented price wobble gives a net weight; kept optional in schema.
                kg = value / (price_per_kg * rng.uniform(0.9, 1.1))
                rows.append(
                    {
                        "year": year,
                        "material": material,
                        "commodity_code": code,
                        "trade_flow": flow,
                        "partner_country": partner,
                        "trade_value_usd": round(value),
                        "net_weight_kg": round(kg),
                    }
                )
    return rows


def main() -> None:
    rng = random.Random(SEED)
    rows = build_rows(rng)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "year", "material", "commodity_code", "trade_flow",
        "partner_country", "trade_value_usd", "net_weight_kg",
    ]
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} ILLUSTRATIVE rows to {OUTPUT}")


if __name__ == "__main__":
    main()
