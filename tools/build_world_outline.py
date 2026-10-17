"""One-off helper that created data/world_outline.json. NOT needed to run the app.

Why it exists: Plotly's built-in map layer downloads its country outlines from
a CDN at view time, which would break the "works offline" requirement. Instead
the app draws the map itself from a small outline file shipped in data/.

Source of the outlines: Natural Earth 1:110m countries (public domain,
naturalearthdata.com). To rebuild:

    pip install pyshp
    python tools/build_world_outline.py path/to/ne_110m_admin_0_countries.shp

(Any Natural Earth 110m countries shapefile with NAME and ISO_A3 fields works,
including the older 'naturalearth_lowres' file bundled with geopandas < 1.0.)
"""

import json
import sys
from pathlib import Path

import shapefile  # pyshp

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "world_outline.json"

# Natural Earth leaves ISO codes as -99 for a few countries; patch by name.
ISO_FIXES = {"France": "FRA", "Norway": "NOR", "N. Cyprus": "", "Somaliland": "", "Kosovo": ""}


def main(shp_path: str) -> None:
    reader = shapefile.Reader(shp_path)
    fields = [f[0].lower() for f in reader.fields[1:]]
    countries = []
    for rec in reader.shapeRecords():
        attrs = dict(zip(fields, rec.record))
        name = attrs.get("name") or attrs.get("name_long") or ""
        iso3 = attrs.get("iso_a3") or ""
        if iso3 in ("-99", "") and name in ISO_FIXES:
            iso3 = ISO_FIXES[name]
        if iso3 == "-99":
            iso3 = ""
        if name == "Antarctica":
            continue  # keeps the map focused and shorter
        points = rec.shape.points
        parts = list(rec.shape.parts) + [len(points)]
        rings = [
            [[round(x, 1), round(y, 1)] for x, y in points[parts[i]:parts[i + 1]]]
            for i in range(len(parts) - 1)
        ]
        countries.append({"name": name, "iso3": iso3, "rings": rings})

    payload = {
        "source": "Natural Earth 1:110m countries, public domain (naturalearthdata.com)",
        "countries": countries,
    }
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(countries)} countries to {OUTPUT} ({OUTPUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
