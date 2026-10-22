"""Regression contracts for the v13.1.21 full-length lower-deck refit."""
from pathlib import Path
import ast
import math
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


def method_src(source, cls_name, method_name):
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(source, node)


def layout_below(source):
    tree = ast.parse(source)
    layout = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "LAYOUT" for t in n.targets))
    value = next(v for k, v in zip(layout.keys, layout.values)
                 if isinstance(k, ast.Constant) and k.value == "below")
    return ast.literal_eval(value)


class LowerDeckLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = GAME.read_text(encoding="utf-8")
        cls.below = layout_below(cls.src)

    def test_lower_deck_zones_span_nearly_the_full_ship_length(self):
        zones = [self.below[k] for k in ("aft_stores", "ice_hold", "engine_room", "crew_quarters", "forepeak")]
        xmin = min(r[0] for r in zones)
        xmax = max(r[0] + r[2] for r in zones)
        self.assertLessEqual(xmin, -0.44)
        self.assertGreaterEqual(xmax, 0.45)
        self.assertGreater(xmax - xmin, 0.90)

    def test_engine_room_and_its_hatch_are_aft_of_the_ice_hold(self):
        engine = self.below["engine_room"]
        ice = self.below["ice_hold"]
        layout = ast.parse(self.src)
        assignment = next(n.value for n in layout.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "LAYOUT" for t in n.targets))
        values = {k.value: ast.literal_eval(v) for k, v in zip(assignment.keys, assignment.values)
                  if isinstance(k, ast.Constant) and k.value in ("engine_hatch", "hatches")}
        self.assertLessEqual(round(engine[0] + engine[2], 6), round(ice[0], 6))   # they share a bulkhead
        eh = values["engine_hatch"]
        self.assertGreaterEqual(eh[0], engine[0] - 0.02)
        self.assertLessEqual(eh[0] + eh[2], engine[0] + engine[2])
        self.assertEqual(len(values["hatches"]), 2)
        for hatch in values["hatches"]:
            self.assertGreaterEqual(hatch[0], ice[0] - 0.01)
            self.assertLessEqual(hatch[0] + hatch[2], ice[0] + ice[2] + 0.01)

    def test_crew_cabin_is_forward_and_has_six_sailor_sized_berths(self):
        cabin = self.below["crew_quarters"]
        self.assertGreater(cabin[0], 0.0)
        self.assertEqual(len(self.below["bunks"]), 6)
        # At the standard 1650 x 420 hull a sleeping sailor is ~90 px long and ~31 px wide, so every
        # berth must be at least 110 x 56 px (the old 82 x 32 berths were shorter than the sleeper).
        for x, y, w, h in self.below["bunks"]:
            self.assertGreaterEqual(w * 1650, 110)
            self.assertGreaterEqual(h * 420, 56)
            self.assertGreaterEqual(x, cabin[0])
            self.assertLessEqual(x + w, cabin[0] + cabin[2])

    def test_no_alleyway_runs_through_the_engine_room_or_ice_hold(self):
        # Solid athwartships bulkheads (door None) close the engine room off from the ice hold and
        # the ice hold off from the crew cabin; the old full-length hallway is gone.
        walls = {round(x, 3): door for x, door, _ in self.below["bulkheads"]}
        engine, ice = self.below["engine_room"], self.below["ice_hold"]
        self.assertIsNone(walls[round(engine[0] + engine[2], 3)])      # engine | ice hold
        self.assertIsNone(walls[round(ice[0] + ice[2], 3)])            # ice hold | cabin
        self.assertNotIn("hallway", method_src(self.src, "Ship", "_draw_lower_deck"))

    def test_engine_casing_and_ladder_well_leave_a_walkable_gap(self):
        casing = self.below["casing"]
        # The main engine is to port; the engine ladder (y = 0) must clear it by more than a sailor's body.
        self.assertLess(casing[1] + casing[3], 0.0)
        self.assertGreaterEqual((0.0 - (casing[1] + casing[3])) * 420, 34.0)

    def test_engine_gauges_sit_on_the_switchboard_not_in_a_walkway(self):
        renderer = method_src(self.src, "Ship", "_draw_lower_deck")
        self.assertIn("sb = self.below_switchboard", renderer)
        self.assertIn('("OIL", g.engine_oil)', renderer)
        self.assertIn('("SEAL", g.shaft_seal)', renderer)

    def test_bunk_approaches_are_six_unique_points_in_the_aisle(self):
        stands = self.below["bunk_stands"]
        bunks = self.below["bunks"]
        self.assertEqual(len(stands), 6)
        self.assertEqual(len(set(stands)), 6)
        for (sx, sy), (x, y, w, h) in zip(stands, bunks):
            self.assertLessEqual(abs(sy), 0.08)                       # inside the aisle, clear of the berths
            self.assertTrue(x <= sx <= x + w)                         # level with its own berth
            self.assertEqual(sy < 0, y < 0)                           # on the same side

    def test_ladder_wells_are_as_wide_as_a_sailor(self):
        art = method_src(self.src, "Ship", "_draw_lower_deck")
        self.assertIn("self._ladder(g, lk.pos(Level.BELOW), 66, 54)", art)
        self.assertIn("length * 0.5", method_src(self.src, "Ship", "_ladder"))

    def test_lower_nav_uses_real_bulkhead_walls_with_door_gaps(self):
        nav = method_src(self.src, "Ship", "_build_nav")
        self.assertIn("below_walls.append((V(bx, -reach), V(bx, reach)))", nav)
        self.assertIn("door_y - door_w * 0.5", nav)
        self.assertIn("Level.BELOW: NavMap((L, B), below_inside, below_walls, self.below_solids, 17.0)", nav)
        self.assertIn("if t not in came:\n            return []", method_src(self.src, "NavMap", "find_path"))

    def test_every_room_is_reachable_from_its_own_ladder_and_rooms_are_separate(self):
        try:
            from fishing_sim.core import game as G
        except ImportError:
            self.skipTest("requires pygame")
        ship = G.Ship()
        nav = ship.maps[G.Level.BELOW]
        comp = lambda p: nav.comp.get(nav.nearest_cell(G.V(p)))
        link = {lk.name: lk.pos(G.Level.BELOW) for lk in ship.links if G.Level.BELOW in lk.ends}
        L = ship.length
        engine = {comp(link["engine ladder"]), comp(ship.markers["engine"]), comp(G.V(-0.43 * L, 0))}
        hold = {comp(link["hold ladder"]), comp(G.V(-0.0225 * L, 0))}
        cabin = {comp(link["crew companionway"]), comp(G.V(0.42 * L, 0))} | {comp(p) for p in ship.bunk_stands}
        for group in (engine, hold, cabin):
            self.assertEqual(len(group), 1)
        self.assertEqual(len(engine | hold | cabin), 3, "engine room, ice hold and cabin must be separate compartments")
        for point in list(ship.bunk_stands) + [ship.markers["engine"]] + list(link.values()):
            self.assertTrue(nav.point_safe(point))

    def test_failed_route_does_not_make_sailor_walk_straight_through_solids(self):
        move = method_src(self.src, "Sailor", "_move")
        self.assertIn("if not self.path:", move)
        self.assertIn("self.vel *= math.exp(-8.0 * dt)", move)
        self.assertIn("self.path = self._plan_path(self.pos, self.target, self.level)", move)

    def test_sleeping_bunk_occupant_is_exempt_from_bed_and_crew_collisions(self):
        move = method_src(self.src, "Sailor", "_move")
        separate = method_src(self.src, "Game", "separate_crew")
        enter = method_src(self.src, "Sailor", "_enter")
        draw = method_src(self.src, "Sailor", "draw")
        self.assertIn('if self.sleeping_in_bunk and self.task == "rest"', move)
        self.assertIn('not (s.sleeping_in_bunk and s.task == "rest")', separate)
        self.assertIn("self.sleeping_in_bunk = False", enter)
        self.assertIn("return self._draw_sleeping_in_bunk(g)", draw)

    def test_sleeper_moves_to_mattress_only_after_reaching_aisle_approach(self):
        task = method_src(self.src, "Sailor", "_do_task")
        self.assertIn("approach = self.g.rest_bunk_approach_for(self)", task)
        self.assertIn("elif self._go_to(approach, 10, Level.BELOW):", task)
        self.assertIn("self.pos = V(rest_pos)", task)
        self.assertIn("self.sleeping_in_bunk = True", task)

    def test_sleep_pose_fills_bunk_length_and_width(self):
        pose = method_src(self.src, "Sailor", "_draw_sleeping_in_bunk")
        self.assertIn("* 16.0", pose)
        self.assertIn("* 6.2", pose)
        self.assertIn("head = P(16.0, 0.0)", pose)


if __name__ == "__main__":
    unittest.main(verbosity=2)
