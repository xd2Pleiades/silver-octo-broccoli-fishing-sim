"""Contracts for integrating the older ship redesign into the v13.2.13 systems base."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "core" / "game.py"


def class_node(tree, name):
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


def method_source(source, tree, class_name, method_name):
    cls = class_node(tree, class_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return ast.get_source_segment(source, node)


def layout_below(source, tree):
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "LAYOUT" for t in n.targets))
    value = next(v for k, v in zip(assignment.value.keys, assignment.value.values)
                 if isinstance(k, ast.Constant) and k.value == "below")
    return ast.literal_eval(value)


class ShipOverhaulMergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GAME.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.below = layout_below(cls.source, cls.tree)

    def test_hull_is_human_scale_and_lower_deck_spans_the_hull(self):
        init = next(n for n in class_node(self.tree, "Ship").body
                    if isinstance(n, ast.FunctionDef) and n.name == "__init__")
        defaults = {arg.arg: value for arg, value in zip(init.args.args[-len(init.args.defaults):], init.args.defaults)}
        self.assertEqual(ast.literal_eval(defaults["length"]), 1650.0)
        self.assertEqual(ast.literal_eval(defaults["beam"]), 420.0)
        zones = [self.below[k] for k in ("aft_stores", "engine_room", "ice_hold", "crew_quarters", "forepeak")]
        self.assertLessEqual(min(r[0] for r in zones), -0.44)
        self.assertGreaterEqual(max(r[0] + r[2] for r in zones), 0.45)

    def test_ship_geometry_helpers_are_static_methods(self):
        ship = class_node(self.tree, "Ship")
        methods = {n.name: n for n in ship.body if isinstance(n, ast.FunctionDef)}
        for name in ("_inset_poly", "_clip_x", "_spans"):
            with self.subTest(method=name):
                self.assertIn("staticmethod", [ast.unparse(d) for d in methods[name].decorator_list])

    def test_bulkheads_create_separate_rooms_and_companionway(self):
        bulkheads = self.below["bulkheads"]
        self.assertEqual(len(bulkheads), 4)
        self.assertIsNone(bulkheads[1][1])
        self.assertIsNone(bulkheads[2][1])
        layout_assignment = next(n for n in self.tree.body if isinstance(n, ast.Assign)
                                and any(isinstance(t, ast.Name) and t.id == "LAYOUT" for t in n.targets))
        values = {k.value: ast.literal_eval(v) for k, v in zip(layout_assignment.value.keys, layout_assignment.value.values)
                  if isinstance(k, ast.Constant) and k.value == "companionway"}
        self.assertEqual(values["companionway"], (0.022, -0.085, 0.050, 0.170))
        self.assertIn("crew companionway", ast.get_source_segment(self.source, layout_assignment))
        nav = method_source(self.source, self.tree, "Ship", "_build_nav")
        self.assertIn("below_walls.append((V(bx, -reach), V(bx, reach)))", nav)
        self.assertIn("door_y - door_w * 0.5", nav)

    def test_engine_room_equipment_and_bunks_are_real_solids(self):
        layout = method_source(self.source, self.tree, "Ship", "_layout")
        self.assertIn('self.below_generator = rect(bl["generator"])', layout)
        self.assertIn('self.below_switchboard = rect(bl["switchboard"])', layout)
        self.assertIn("self.ice_bins", layout)
        self.assertIn("self.stores_racks", layout)
        self.assertIn("self.ice_bins + self.stores_racks + self.bunks", layout)
        art = method_source(self.source, self.tree, "Ship", "_draw_lower_deck")
        for cue in ("for bx, door_y, door_w in self.bulkheads", "self.below_generator", "self.below_switchboard", "CREW CABIN"):
            self.assertIn(cue, art)
        self.assertNotIn("hallway =", art)

    def test_latest_water_and_rescue_systems_remain_wired(self):
        ship_init = method_source(self.source, self.tree, "Ship", "__init__")
        for cue in ("self.deck_foam = []", "self.last_flood_report = None", "FloodingModel.attach(self)", "self._build_art()"):
            self.assertIn(cue, ship_init)
        ship = class_node(self.tree, "Ship")
        ship_methods = {n.name for n in ship.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"spawn_wash", "splash_out", "update_water", "draw_water"}.issubset(ship_methods))
        game = class_node(self.tree, "Game")
        game_methods = {n.name for n in game.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"_start_player_rescue_mission", "_update_player_rescue_mission", "save_career", "load_career"}.issubset(game_methods))

    def test_engine_watch_hysteresis_and_bunk_blanket_survived_the_merge(self):
        duty = method_source(self.source, self.tree, "Sailor", "_do_task")
        self.assertIn("was_at_engine", duty)
        self.assertIn("hysteresis", duty)
        sleep_art = method_source(self.source, self.tree, "Sailor", "_draw_sleeping_in_bunk")
        self.assertIn("A wool blanket", sleep_art)


if __name__ == "__main__":
    unittest.main(verbosity=2)
