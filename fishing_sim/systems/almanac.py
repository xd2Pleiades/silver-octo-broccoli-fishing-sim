"""Ship's calendar and deterministic seasonal coastal outlook.

The game is set on a fictional fishing route using Hakodate/North Pacific as a
climate analogue. These forecasts are simulated, date-seeded outlooks, not a live
meteorological feed or a prediction of actual 1962 weather.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import random

START_DATE = date(1962, 4, 1)
SECONDS_PER_DAY = 600.0

MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
MONTH_ABBR = tuple(name[:3].upper() for name in MONTH_NAMES)

# Japan Meteorological Agency Hakodate monthly climate normals (1991–2020),
# rounded to one decimal place. Used as a regional baseline rather than a hard
# weather guarantee for a specific simulated day.
HAKODATE_MEAN_TEMP_C = (-2.4, -1.8, 1.9, 7.3, 12.3, 16.2, 20.3, 22.1, 18.8, 12.5, 6.0, -0.1)
HAKODATE_PRECIP_MM = (77.4, 64.5, 64.1, 71.9, 88.9, 79.8, 123.6, 156.5, 150.5, 105.6, 110.8, 94.6)

# Relative likelihood of broad daily regimes, not point forecasts. Late-summer
# and early-autumn coastal storms are more common; spring is cool and changeable;
# early summer allows more fog; late autumn/winter favour wind and frontal rain.
MONTH_WEATHER_WEIGHTS = {
    1: {"clear": 19, "cloudy": 23, "fog": 3, "drizzle": 7, "rain": 23, "storm": 25},
    2: {"clear": 20, "cloudy": 24, "fog": 3, "drizzle": 8, "rain": 22, "storm": 23},
    3: {"clear": 20, "cloudy": 27, "fog": 7, "drizzle": 16, "rain": 17, "storm": 13},
    4: {"clear": 20, "cloudy": 29, "fog": 8, "drizzle": 19, "rain": 15, "storm": 9},
    5: {"clear": 21, "cloudy": 28, "fog": 15, "drizzle": 16, "rain": 14, "storm": 6},
    6: {"clear": 18, "cloudy": 29, "fog": 20, "drizzle": 14, "rain": 14, "storm": 5},
    7: {"clear": 20, "cloudy": 25, "fog": 9, "drizzle": 12, "rain": 18, "storm": 16},
    8: {"clear": 18, "cloudy": 22, "fog": 7, "drizzle": 11, "rain": 18, "storm": 24},
    9: {"clear": 18, "cloudy": 20, "fog": 8, "drizzle": 11, "rain": 20, "storm": 23},
    10: {"clear": 21, "cloudy": 26, "fog": 7, "drizzle": 14, "rain": 18, "storm": 14},
    11: {"clear": 20, "cloudy": 26, "fog": 5, "drizzle": 14, "rain": 20, "storm": 15},
    12: {"clear": 20, "cloudy": 24, "fog": 4, "drizzle": 9, "rain": 19, "storm": 24},
}

CONDITION_NAMES = {
    "clear": "Clear spells", "cloudy": "Overcast", "fog": "Coastal fog",
    "drizzle": "Drizzle", "rain": "Rain / squalls", "storm": "Gales / storm risk",
}

SEASON_NOTES = {
    "winter": "Cold westerlies and rough frontal seas; snow is not modelled as a separate precipitation type.",
    "spring": "Cool, changeable fronts; chilly nights and occasional coastal fog.",
    "summer": "Milder air, more humid cloud and fog; convective showers become more likely.",
    "autumn": "Longer frontal spells and elevated late-summer / early-autumn storm risk.",
}


def game_date(day_number: int, start_date: date = START_DATE) -> date:
    """Map game Day 1 to 1 April 1962 and handle month/year rollovers."""
    day_number = max(1, int(day_number))
    return start_date + timedelta(days=day_number - 1)


def game_date_from_elapsed(elapsed_seconds: float, day_len: float = SECONDS_PER_DAY,
                           start_date: date = START_DATE) -> date:
    """Convert simulated seconds to the calendar date; time scaling is handled by caller."""
    day_len = max(1e-6, float(day_len))
    day_number = int(max(0.0, float(elapsed_seconds)) // day_len) + 1
    return game_date(day_number, start_date)


def season_name(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


@dataclass(frozen=True)
class DailyForecast:
    day: date
    condition: str
    temp_low_c: int
    temp_high_c: int
    wind_min_kt: int
    wind_max_kt: int
    rain_chance_pct: int
    sea_state: float
    confidence_pct: int

    @property
    def label(self) -> str:
        return CONDITION_NAMES[self.condition]

    def notebook_line(self) -> str:
        return (f"{self.day.strftime('%a %d %b')}: {self.label}; {self.temp_low_c}–{self.temp_high_c} C; "
                f"wind {self.wind_min_kt}–{self.wind_max_kt} kt; rain {self.rain_chance_pct}%; "
                f"sea {self.sea_state:.1f}")

    def radio_line(self) -> str:
        return (f"{self.day.strftime('%d %b')}: {self.label.lower()}, {self.temp_low_c} to "
                f"{self.temp_high_c} Celsius; wind {self.wind_min_kt} to {self.wind_max_kt} knots; "
                f"rain probability {self.rain_chance_pct} percent; sea state about {self.sea_state:.1f}.")


def forecast_for_date(day: date) -> DailyForecast:
    """Return a stable, seasonal daily outlook so forecasts and weather share a model.

    Date-seeded variation makes repeated radio reports consistent for a day while
    monthly weights keep the broad seasonal pattern. Confidence is deliberately
    lower beyond one day in the notebook presentation.
    """
    seed = (day.toordinal() * 1_000_003) ^ 0x19620401
    rng = random.Random(seed)
    weights = MONTH_WEATHER_WEIGHTS[day.month]
    condition = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]

    mean_temp = HAKODATE_MEAN_TEMP_C[day.month - 1]
    # The day-by-day spread is much smaller than seasonal change; daytime range
    # expands slightly under clear skies and contracts beneath thick cloud/rain.
    temp_anomaly = rng.uniform(-3.5, 3.5)
    mean_today = mean_temp + temp_anomaly
    diurnal_range = {"clear": 7.0, "cloudy": 5.0, "fog": 3.0,
                     "drizzle": 4.0, "rain": 4.0, "storm": 5.0}[condition]
    low = round(mean_today - diurnal_range * 0.48)
    high = round(mean_today + diurnal_range * 0.52)

    wind_ranges = {
        "clear": (3, 12), "cloudy": (5, 16), "fog": (2, 10),
        "drizzle": (6, 17), "rain": (8, 23), "storm": (18, 38),
    }
    wind_min, wind_max = wind_ranges[condition]
    # Modest seasonal wind floor, reflecting colder-season frontal weather.
    if day.month in (11, 12, 1, 2, 3) and condition in ("rain", "storm"):
        wind_max += 4
    # Relative monthly precipitation compared with annual daily average nudges wet
    # regime probabilities without overriding their primary condition.
    precip_factor = HAKODATE_PRECIP_MM[day.month - 1] / (sum(HAKODATE_PRECIP_MM) / 12.0)
    base_rain = {"clear": 8, "cloudy": 24, "fog": 12, "drizzle": 65, "rain": 88, "storm": 94}[condition]
    rain_chance = int(max(2, min(99, round(base_rain * (0.8 + 0.2 * precip_factor)))))
    sea_base = {"clear": 0.20, "cloudy": 0.34, "fog": 0.22,
                "drizzle": 0.38, "rain": 0.55, "storm": 0.86}[condition]
    sea_state = max(0.05, min(1.0, sea_base + (wind_max - 12) / 100.0 + rng.uniform(-0.06, 0.06)))
    return DailyForecast(day, condition, low, high, wind_min, wind_max,
                         rain_chance, round(sea_state, 2), 75)


def forecast_range(start_day: date, count: int = 5) -> list[DailyForecast]:
    count = max(1, min(10, int(count)))
    results = []
    for i in range(count):
        item = forecast_for_date(start_day + timedelta(days=i))
        confidence = max(45, 84 - 7 * i)
        results.append(DailyForecast(item.day, item.condition, item.temp_low_c, item.temp_high_c,
                                     item.wind_min_kt, item.wind_max_kt, item.rain_chance_pct,
                                     item.sea_state, confidence))
    return results


def season_note(day: date) -> str:
    return SEASON_NOTES[season_name(day.month)]
