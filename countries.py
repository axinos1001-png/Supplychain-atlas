"""Small lookup table of countries used for the map view.

Each entry is: name -> (ISO-3 code, latitude, longitude).
The coordinates are rough country centre points, good enough for a
network-style map. Keeping this table inside the project means the map works
offline and does not depend on any external geocoding service.

Countries that are missing from this table are still counted everywhere in the
dashboard; they are only left off the map (the app tells the user how many).
"""

from typing import Optional

INDIA_NAME = "India"
INDIA_COORDS = (22.0, 79.0)

COUNTRIES: dict[str, tuple[str, float, float]] = {
    "Australia": ("AUS", -25.0, 134.0),
    "Bangladesh": ("BGD", 23.7, 90.4),
    "Belgium": ("BEL", 50.6, 4.7),
    "Brazil": ("BRA", -10.0, -52.0),
    "Canada": ("CAN", 56.0, -106.0),
    "Chile": ("CHL", -33.0, -71.0),
    "China": ("CHN", 35.0, 103.0),
    "France": ("FRA", 46.6, 2.5),
    "Germany": ("DEU", 51.0, 10.4),
    "Indonesia": ("IDN", -2.5, 118.0),
    "Italy": ("ITA", 42.8, 12.5),
    "Japan": ("JPN", 36.5, 138.0),
    "Malaysia": ("MYS", 3.8, 102.0),
    "Nepal": ("NPL", 28.4, 84.1),
    "Netherlands": ("NLD", 52.2, 5.5),
    "Norway": ("NOR", 61.0, 9.0),
    "Peru": ("PER", -9.2, -75.0),
    "Philippines": ("PHL", 12.8, 122.0),
    "Russia": ("RUS", 61.0, 99.0),
    "Saudi Arabia": ("SAU", 24.0, 45.0),
    "Singapore": ("SGP", 1.35, 103.8),
    "South Africa": ("ZAF", -29.0, 24.0),
    "South Korea": ("KOR", 36.5, 127.8),
    "Spain": ("ESP", 40.0, -3.7),
    "Sri Lanka": ("LKA", 7.9, 80.7),
    "Taiwan": ("TWN", 23.7, 121.0),
    "Tanzania": ("TZA", -6.4, 34.9),
    "Thailand": ("THA", 15.0, 101.0),
    "Turkey": ("TUR", 39.0, 35.0),
    "Ukraine": ("UKR", 49.0, 32.0),
    "United Arab Emirates": ("ARE", 24.0, 54.0),
    "United Kingdom": ("GBR", 54.0, -2.0),
    "United States": ("USA", 39.5, -98.5),
    "Vietnam": ("VNM", 16.0, 107.8),
    "Zambia": ("ZMB", -13.5, 27.8),
    # A few extra partners so a real Comtrade CSV maps well too.
    "Argentina": ("ARG", -34.0, -64.0),
    "Egypt": ("EGY", 26.8, 30.8),
    "Iran": ("IRN", 32.4, 53.7),
    "Kuwait": ("KWT", 29.3, 47.5),
    "Mexico": ("MEX", 23.6, -102.5),
    "Oman": ("OMN", 21.5, 55.9),
    "Poland": ("POL", 52.0, 19.1),
    "Qatar": ("QAT", 25.3, 51.2),
    "Switzerland": ("CHE", 46.8, 8.2),
    "Hong Kong": ("HKG", 22.3, 114.2),
    "Kazakhstan": ("KAZ", 48.0, 68.0),
    "Mozambique": ("MOZ", -18.7, 35.5),
    "Nigeria": ("NGA", 9.1, 8.7),
}

# Different sources spell country names differently; map common variants.
ALIASES: dict[str, str] = {
    "usa": "United States",
    "us": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "uae": "United Arab Emirates",
    "russian federation": "Russia",
    "republic of korea": "South Korea",
    "rep. of korea": "South Korea",
    "korea, republic of": "South Korea",
    "viet nam": "Vietnam",
    "türkiye": "Turkey",
    "turkiye": "Turkey",
    "china, hong kong sar": "Hong Kong",
}


def normalise_country(name: str) -> str:
    """Return a cleaned, consistently spelled country name."""
    cleaned = " ".join(str(name).split())
    return ALIASES.get(cleaned.lower(), cleaned)


def get_country_info(name: str) -> Optional[tuple[str, float, float]]:
    """Return (iso3, lat, lon) for a country, or None if we don't know it."""
    return COUNTRIES.get(normalise_country(name))
