"""Behavioural (headless) tests for v13.1.32: crew no longer pile into the engine room, the engine watch holds steady,
sleepers are handled sensibly, and the captain's own orders (3-day fishing trip / return to port) live in the context menu."""
import os
import random
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

try:
    import pygame  # noqa: E402,F401
    from fishing_sim.core import game as G  # noqa: E402
    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None
    G = None
    PYGAME_AVAILABLE = False

if PYGAME_AVAILABLE:
    Level, Sailor, Longline = G.Level, G.Sailor, G.Longline
else:
    Level = Sailor = Longline = None
SRC = (ROOT / "core" / "game.py").read_text(encoding="utf-8")


class NoKeys:
    def __getitem__(self, key):
        return False


KEYS = NoKeys()


def new_game(seed=1):
    random.seed(seed)
    return G.Game()


def step(g, seconds, dt=0.05):
    for _ in range(int(seconds / dt)):
        g.update(dt, KEYS)


def by_name(g, name):
    return next(s for s in g.sailors if s.name == name)


def captain(g):
    return next(s for s in g.sailors if s.role == Sailor.CAPTAIN)


@unittest.skipUnless(PYGAME_AVAILABLE, "requires pygame runtime dependencies")
class CrewStayOutOfTheEngineRoomTests(unittest.TestCase):
    def test_idle_man_below_deck_goes_back_up(self):
        g = new_game()
        step(g, 5)
        y = by_name(g, "Yamamoto")
        ladder = next(l for l in g.ship.links if l.name == "engine ladder").pos(Level.BELOW)
        y.level, y.pos, y.task = Level.BELOW, G.V(ladder) + G.V(40, 0), "idle"
        step(g, 30)
        self.assertEqual(y.level, Level.MAIN)

    def test_chat_partner_is_on_the_same_level_and_awake(self):
        g = new_game()
        step(g, 5)
        vet = by_name(g, "Takeda")
        vet.level = Level.BELOW                                  # the veteran's mentor bonus used to draw everyone down to him
        deckhand = by_name(g, "Yamamoto")
        deckhand.level = Level.MAIN
        self.assertIsNot(deckhand._find_partner(), vet)
        sleeper = by_name(g, "Sato")
        sleeper.level, sleeper.sleeping_in_bunk = Level.BELOW, True
        self.assertIsNot(deckhand._find_partner(), sleeper)

    def test_engine_watch_holds_steady_and_the_crew_do_not_crowd_below(self):
        g = new_game()
        step(g, 15)
        g.world.set_destination(g.world.ship_pos + G.V(60000, 0))
        step(g, 5)
        captain(g).fatigue = 0.85                                # the veteran takes the helm; a hand must keep the engine
        holders, last = 0, None
        for _ in range(int(150 / 0.05)):
            g.update(0.05, KEYS)
            now = tuple(s.name for s in g.sailors if s.at_engine)
            if now != last:
                holders, last = holders + 1, now
        below = [s for s in g.sailors if s.mode == Sailor.ABOARD and s.level == Level.BELOW
                 and not s.sleeping_in_bunk and s.task != "engine"]
        self.assertLess(holders, 20, "engine watch flickered %d times (crowd shoving the engineer off his station)" % holders)
        self.assertLessEqual(len(below), 1, "idle hands are loitering below deck: %s" % [s.name for s in below])


@unittest.skipUnless(PYGAME_AVAILABLE, "requires pygame runtime dependencies")
class SleepTests(unittest.TestCase):
    def test_tired_deckhand_sleeps_below_and_comes_back_up(self):
        g = new_game()
        step(g, 10)
        y = by_name(g, "Yamamoto")
        y.fatigue = 0.9
        slept = False
        for _ in range(int(120 / 0.05)):
            g.update(0.05, KEYS)
            slept = slept or y.sleeping_in_bunk
        self.assertTrue(slept)
        self.assertLess(y.fatigue, 0.2)
        self.assertEqual(y.level, Level.MAIN, "rested hands go back up to the deck")

    def test_captain_hands_over_to_the_veteran_and_takes_the_helm_back(self):
        g = new_game()
        step(g, 15)
        g.world.set_destination(g.world.ship_pos + G.V(60000, 0))
        step(g, 5)
        cap = captain(g)
        cap.fatigue = 0.85
        slept = False
        for _ in range(int(150 / 0.05)):
            g.update(0.05, KEYS)
            slept = slept or cap.sleeping_in_bunk
        self.assertTrue(slept)
        self.assertFalse(g.captain_resting)
        self.assertIs(g.helm_operator, cap)
        self.assertEqual(cap.level, Level.WHEELHOUSE)

    def test_bunk_rest_is_better_than_deck_rest_and_a_sleeper_hears_late(self):
        self.assertIn("0.045 if asleep else 0.028", SRC)
        self.assertIn("delay += 1.2 + (1.8 if o.sleeping_in_bunk else 0.0)", SRC)


@unittest.skipUnless(PYGAME_AVAILABLE, "requires pygame runtime dependencies")
class CaptainOrdersTests(unittest.TestCase):
    def _menu(self, g, who):
        g.select(who)
        p = g.SS(who.pos)
        self.assertTrue(g._open_context_menu_at((int(p.x), int(p.y)), who.pos))
        return g.context_menu

    def test_captain_menu_offers_trip_and_port_but_crew_menu_is_unchanged(self):
        g = new_game()
        step(g, 3)
        labels = [o["label"] for o in self._menu(g, captain(g))["options"]]
        self.assertIn("Fish: 3-day trip", labels)
        self.assertIn("Return to port", labels)
        g.context_menu = None
        crew = [o["label"] for o in self._menu(g, by_name(g, "Yamamoto"))["options"]]
        self.assertIn("Assign: haul line", crew)
        self.assertNotIn("Return to port", crew)

    def test_fish_order_starts_a_three_day_trip(self):
        g = new_game()
        step(g, 3)
        menu = self._menu(g, captain(g))
        option = next(o for o in menu["options"] if o["action"] == "captain_fish")
        g._perform_context_action(option)
        ln = g.line
        self.assertTrue(ln.auto)
        self.assertEqual(ln.trip_days, 3)
        self.assertAlmostEqual(ln.trip_end - ln.trip_start, 3 * G.DAY_LEN)
        self.assertTrue(ln.trip_hud().startswith("TRIP"))

    def test_after_a_haul_the_trip_sets_again_until_something_says_go_home(self):
        g = new_game()
        g.start_fishing_trip()
        ln, w = g.line, g.world
        for b in g.bait:
            g.bait[b] = 500.0                                    # plenty of bait, so only time, fuel and ice matter
        ln.phase, ln.stage = Longline.IDLE, "haul"
        ln._auto(0.05)
        self.assertEqual(ln.stage, "off", "mid-trip: carry on fishing, the catch stays in the hold")
        ln.stage = "haul"
        ln.trip_end = w.time - 1                                 # the days are up
        ln._auto(0.05)
        self.assertEqual(ln.stage, "return")

    def test_reasons_to_head_home(self):
        g = new_game()
        ln, w = g.line, g.world
        for b in g.bait:
            g.bait[b] = 500.0
        ln.trip_start, ln.trip_days, ln.trip_end = w.time, 3, w.time + 3 * G.DAY_LEN
        self.assertFalse(ln._trip_over())
        g.fuel = 10.0
        self.assertTrue(ln._trip_over())
        g.fuel = G.FUEL_CAP
        for b in g.bait:
            g.bait[b] = 0.0
        self.assertTrue(ln._trip_over())
        for b in g.bait:
            g.bait[b] = 500.0
        g.hold.append(object())
        g.ice = 5.0
        self.assertTrue(ln._trip_over())
        g.hold.clear()
        g.ice = G.ICE_CAP
        ln.trip_end = w.time - 1
        self.assertTrue(ln._trip_over())

    def test_standing_down_by_hand_ends_the_trip(self):
        g = new_game()
        g.start_fishing_trip()
        g.line.toggle_auto()
        g.line._auto(0.05)
        self.assertIsNone(g.line.trip_end)

    def test_return_to_port_refused_when_alongside_or_line_out_by_hand(self):
        g = new_game()
        step(g, 3)
        g.world.ship_pos, g.world.speed = G.V(g.world.berth), 0.0
        self.assertFalse(g.order_return_to_port(), "alongside the quay: nothing to do")
        g.world.ship_pos = g.world.ship_pos + G.V(9000, 0)       # now at sea, the line out under manual control
        g.line.phase, g.line.auto = Longline.SOAKING, False
        self.assertFalse(g.order_return_to_port())

    def test_return_with_the_line_out_hauls_first_then_goes_home(self):
        g = new_game()
        step(g, 3)
        g.start_fishing_trip()
        g.world.ship_pos = g.world.ship_pos + G.V(9000, 0)
        g.line.phase, g.line.stage = Longline.SOAKING, "soak"
        self.assertTrue(g.order_return_to_port())
        self.assertLessEqual(g.line.trip_end, g.world.time)
        g.line.phase, g.line.stage = Longline.IDLE, "haul"
        g.line._auto(0.05)
        self.assertEqual(g.line.stage, "return")

    def test_a_trip_really_runs_set_haul_set_haul_home(self):
        g = new_game()
        step(g, 3)
        for b in g.bait:
            g.bait[b] = 500.0
        g.start_fishing_trip(days=1)
        ln, sets, last = g.line, 0, None
        for _ in range(int(2400 / 0.05)):
            g.update(0.05, KEYS)
            if ln.stage == "set" and last != "set":
                sets += 1
            last = ln.stage
            if ln.stage == "return":
                break
        self.assertGreaterEqual(sets, 2, "a trip should set more than once before heading in")
        self.assertEqual(ln.stage, "return")


@unittest.skipUnless(PYGAME_AVAILABLE, "requires pygame runtime dependencies")
class WheelhouseCutawayStillWorksTests(unittest.TestCase):
    def test_every_level_view_draws(self):
        g = new_game()
        step(g, 5)
        for lv in (Level.MAIN, Level.WHEELHOUSE, Level.BELOW, None):
            g.peek = lv
            g.draw()


if __name__ == "__main__":
    unittest.main()
