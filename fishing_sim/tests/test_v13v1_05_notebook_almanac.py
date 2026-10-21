"""Headless checks for V13V1-05 notebook, dated radio, seasonal forecasts and market response."""
import ast
from datetime import date
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems.almanac import (
    START_DATE, HAKODATE_MEAN_TEMP_C, MONTH_WEATHER_WEIGHTS,
    forecast_for_date, forecast_range, game_date, game_date_from_elapsed, season_name,
)
from fishing_sim.systems.market_weather import (
    add_storm_surge, decay_storm_surge, storm_price_index,
)


class CalendarAndForecastTests(unittest.TestCase):
    def test_campaign_starts_on_first_april_1962_and_rolls_by_game_day(self):
        self.assertEqual(START_DATE, date(1962, 4, 1))
        self.assertEqual(game_date(1), date(1962, 4, 1))
        self.assertEqual(game_date(2), date(1962, 4, 2))
        self.assertEqual(game_date(31), date(1962, 5, 1))
        self.assertEqual(game_date(275), date(1962, 12, 31))

    def test_elapsed_time_advances_calendar_on_exact_day_length(self):
        self.assertEqual(game_date_from_elapsed(0), date(1962, 4, 1))
        self.assertEqual(game_date_from_elapsed(599.99), date(1962, 4, 1))
        self.assertEqual(game_date_from_elapsed(600), date(1962, 4, 2))

    def test_daily_forecast_is_repeatable_for_a_given_date(self):
        day = date(1962, 8, 19)
        self.assertEqual(forecast_for_date(day), forecast_for_date(day))

    def test_forecast_range_has_consecutive_dates_and_lower_confidence(self):
        outlook = forecast_range(date(1962, 4, 1), 5)
        self.assertEqual([x.day for x in outlook], [date(1962, 4, n) for n in range(1, 6)])
        self.assertEqual(len(outlook), 5)
        self.assertGreater(outlook[0].confidence_pct, outlook[-1].confidence_pct)

    def test_forecast_fields_are_physical_and_bounded(self):
        for month in range(1, 13):
            report = forecast_for_date(date(1962, month, 15))
            self.assertGreaterEqual(report.rain_chance_pct, 0)
            self.assertLessEqual(report.rain_chance_pct, 100)
            self.assertGreaterEqual(report.wind_min_kt, 0)
            self.assertGreaterEqual(report.wind_max_kt, report.wind_min_kt)
            self.assertGreaterEqual(report.sea_state, 0.05)
            self.assertLessEqual(report.sea_state, 1.0)
            self.assertLessEqual(report.temp_low_c, report.temp_high_c)

    def test_north_pacific_seasonal_climate_is_not_constant(self):
        self.assertLess(HAKODATE_MEAN_TEMP_C[1], HAKODATE_MEAN_TEMP_C[7])
        self.assertGreater(MONTH_WEATHER_WEIGHTS[8]["storm"], MONTH_WEATHER_WEIGHTS[4]["storm"])
        self.assertEqual(season_name(4), "spring")
        self.assertEqual(season_name(8), "summer")
        self.assertEqual(season_name(10), "autumn")
        self.assertEqual(season_name(1), "winter")


class StormMarketTests(unittest.TestCase):
    def test_storm_increases_effective_index_above_base(self):
        base = 1.0
        surge = add_storm_surge(0.0, 0.9)
        self.assertGreater(storm_price_index(base, surge), base)
        self.assertGreaterEqual(surge, 0.22)
        self.assertLessEqual(storm_price_index(base, surge), 1.85)

    def test_repeated_storms_are_capped(self):
        surge = 0.0
        for _ in range(20):
            surge = add_storm_surge(surge, 1.0)
        self.assertLessEqual(surge, 0.65)
        self.assertLessEqual(storm_price_index(1.3, surge), 1.85)

    def test_market_premium_decays_without_becoming_negative(self):
        surge = 0.4
        after_day = decay_storm_surge(surge, 600)
        self.assertGreater(after_day, 0.0)
        self.assertLess(after_day, surge)
        self.assertEqual(decay_storm_surge(after_day, -5), after_day)
        self.assertEqual(decay_storm_surge(0.0, 500), 0.0)


class V13V1_05SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "core" / "game.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def method(self, class_name, name):
        cls = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        node = next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        return ast.get_source_segment(self.source, node)

    def test_world_clock_is_calendar_based_and_first_day_is_not_shortened(self):
        day_number = self.method("World", "day_number")
        calendar_date = self.method("World", "calendar_date")
        self.assertIn("self.time) // DAY_LEN", day_number)
        self.assertIn("game_date(self.day_number(), START_DATE)", calendar_date)

    def test_weather_uses_date_seeded_outlook_and_seasonal_temperature(self):
        init = self.method("Weather", "__init__")
        pick = self.method("Weather", "pick_next")
        temp = self.method("Weather", "air_temp")
        self.assertIn("forecast_for_date(self.outlook_date)", init)
        self.assertIn("self.day_outlook.condition", pick)
        self.assertIn("HAKODATE_MEAN_TEMP_C", temp)

    def test_crew_dialogue_is_recorded_to_a_long_form_log(self):
        say = self.method("Crew", "say")
        recorder = self.method("Game", "record_log_entry")
        self.assertIn("recorder(text)", say)
        self.assertIn("self.radio_log_entries.append(entry)", recorder)
        self.assertIn("self.crew_log_entries.append(entry)", recorder)
        self.assertIn('getattr(self, "log_entry_limit", 600)', recorder)

    def test_notebook_has_four_pages_and_arrow_navigation(self):
        draw = self.method("Game", "draw_notebook")
        handle = self.method("Game", "handle")
        render = self.method("Game", "draw")
        for label in ("CREW LOG", "RADIO LOG", "CALENDAR", "FORECAST", "< PREV", "NEXT >"):
            self.assertIn(label, draw)
        self.assertIn("pygame.K_F9", handle)
        self.assertIn("pygame.K_LEFT", handle)
        self.assertIn("pygame.K_RIGHT", handle)
        self.assertIn("self.draw_notebook()", render)

    def test_radio_notebook_pages_keep_each_exchange_in_spoken_order(self):
        entries = self.method("Game", "_notebook_entries")
        draw = self.method("Game", "draw_notebook")
        self.assertIn("return list(self.radio_log_entries)", entries)
        self.assertIn("end = max(0, len(entries) - self.notebook_page * page_size)", draw)
        self.assertIn("selected = entries[begin:end]", draw)

    def test_weather_radio_call_sends_future_daily_forecasts_as_transcript_turns(self):
        start = self.method("Game", "_start_radio_call")
        update = self.method("Game", "_update_radio")
        self.assertIn("self.weather.forecast(4)[1:4]", start)
        self.assertIn('"reply_lines": reply_lines', start)
        self.assertIn("[VESSEL]", start)
        self.assertIn('("COAST STATION", "Roger, fishing vessel.', update)
        self.assertIn('("VESSEL", "Received, coast station.', update)
        self.assertIn("self.radio_transcript_queue.extend(turns)", update)
        self.assertIn("speaker, line = self.radio_transcript_queue.pop(0)", update)
        self.assertIn('"Radio: [%s]: %s" % (speaker, line)', update)
        self.assertIn("self.radio_transcript_queue", self.method("Game", "radio_call"))

    def test_weather_storm_transition_and_price_decay_are_connected(self):
        transition = self.method("Game", "on_weather_transition")
        decay = self.method("Game", "_update_market_surge")
        open_auction = self.method("Game", "_open_auction")
        offers = self.method("Game", "_auction_build_offers")
        self.assertIn('new_kind == "storm" and old_kind != "storm"', transition)
        self.assertIn("add_storm_surge", transition)
        self.assertIn("decay_storm_surge", decay)
        self.assertIn("self.market_base", open_auction)
        self.assertIn("* self.market", offers)

    def test_market_storm_surge_updates_during_live_weather(self):
        update = self.method("Game", "update")
        self.assertIn("self.weather.update(dt)", update)
        self.assertIn("self._update_market_surge(dt)", update)

    def test_date_is_visible_and_key_is_documented(self):
        hud = self.method("Game", "draw_hud")
        self.assertIn("self.world.calendar_date_text()", hud)
        self.assertIn("F9 notebook", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
