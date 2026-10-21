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

    def test_crew_cabin_is_forward_and_has_six_sailor_sized_berths(self):
        cabin = self.below["crew_quarters"]
        self.assertGreater(cabin[0], 0.0)
        self.assertEqual(len(self.below["bunks"]), 6)
        # At the standard 1100 x 280 ship scale, berths are about 88 x 32 units.
        for x, y, w, h in self.below["bunks"]:
            self.assertGreaterEqual(w * 1100, 80)
            self.assertGreaterEqual(h * 280, 31)
            self.assertGreaterEqual(x, cabin[0])
            self.assertLessEqual(x + w, cabin[0] + cabin[2])

    def test_engine_casing_keeps_path_grid_clear_of_the_central_hall(self):
        casing = self.below["casing"]
        casing_top = casing[1] + casing[3]
        hallway_top = -0.09
        clearance = (hallway_top - casing_top) * 280
        self.assertLess(casing_top, hallway_top)
        self.assertGreaterEqual(clearance, 17.0)

    def test_bunk_approaches_are_six_unique_points_in_the_open_centre_hallway(self):
        stands = self.below["bunk_stands"]
        self.assertEqual(len(stands), 6)
        self.assertEqual(len(set(stands)), 6)
        self.assertTrue(all(abs(y) < 0.001 for _, y in stands))
        self.assertTrue(all(0.10 < x < 0.38 for x, _ in stands))

    def test_lower_nav_is_one_hull_wide_connected_walk_space_not_isolated_rooms(self):
        nav = method_src(self.src, "Ship", "_build_nav")
        self.assertIn("below_inside = lambda p: in_poly(p, self.hull)", nav)
        self.assertIn("Level.BELOW: NavMap((L, B), below_inside, below_walls, self.below_solids, 17.0)", nav)
        self.assertNotIn("rect_walls(r) for r in rooms", nav)
        self.assertIn("if t not in came:\n            return []", method_src(self.src, "NavMap", "find_path"))

    def test_engine_ice_cabin_bunks_and_forepeak_share_one_walkable_component(self):
        # Rebuild the lower NavMap's walk-cell geometry with the same 1100 x 280 scale,
        # 12-unit cells and 17-unit clearance. This catches room/casing changes that
        # visually look connected but split the actual path graph.
        L, B, cell, clear = 1100.0, 280.0, 12.0, 17.0

        def smoothstep(a, b, x):
            t = max(0.0, min(1.0, (x - a) / (b - a)))
            return t * t * (3.0 - 2.0 * t)

        def half_width(u):
            if u < 0.15:
                return (0.82 + 0.18 * smoothstep(0.0, 0.15, u)) * B * 0.5
            if u > 0.6:
                return (1.0 - ((u - 0.6) / 0.4) ** 1.8) * B * 0.5
            return B * 0.5

        hull = [(-L * 0.5 + i / 28 * L, half_width(i / 28)) for i in range(29)]
        hull += [(-L * 0.5 + i / 28 * L, -half_width(i / 28)) for i in range(27, -1, -1)]

        def in_hull(point):
            x, y = point
            inside, j = False, len(hull) - 1
            for i in range(len(hull)):
                a, b = hull[i], hull[j]
                if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                    inside = not inside
                j = i
            return inside

        def segment_distance(point, a, b):
            x, y = point
            dx, dy = b[0] - a[0], b[1] - a[1]
            length2 = dx * dx + dy * dy
            t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length2))
            return math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))

        def rect_distance(point, r):
            x, y = point
            dx = max(r[0] - x, 0.0, x - (r[0] + r[2]))
            dy = max(r[1] - y, 0.0, y - (r[1] + r[3]))
            return math.hypot(dx, dy)

        solids = [(L * self.below["casing"][0], B * self.below["casing"][1],
                   L * self.below["casing"][2], B * self.below["casing"][3])]
        solids.extend((L * x, B * y, L * w, B * h) for x, y, w, h in self.below["bunks"])
        nav = {}
        for i in range(int(-L / 2 / cell) - 1, int(L / 2 / cell) + 2):
            for j in range(int(-B / 2 / cell) - 1, int(B / 2 / cell) + 2):
                point = ((i + 0.5) * cell, (j + 0.5) * cell)
                if not in_hull(point) or not (-L * 0.47 < point[0] < L * 0.47):
                    continue
                if any(segment_distance(point, hull[k], hull[(k + 1) % len(hull)]) < clear for k in range(len(hull))):
                    continue
                if any(rect_distance(point, r) < clear for r in solids):
                    continue
                nav[(i, j)] = True

        neighbours = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        components = {}
        component_id = 0
        for start in nav:
            if start in components:
                continue
            component_id += 1
            components[start] = component_id
            stack = [start]
            while stack:
                current = stack.pop()
                for dx, dy in neighbours:
                    nxt = (current[0] + dx, current[1] + dy)
                    if nxt not in nav or nxt in components:
                        continue
                    if dx and dy and ((current[0] + dx, current[1]) not in nav or (current[0], current[1] + dy) not in nav):
                        continue
                    components[nxt] = component_id
                    stack.append(nxt)

        def nearest_component(point):
            c = (math.floor(point[0] / cell), math.floor(point[1] / cell))
            if c not in nav:
                c = min(nav, key=lambda k: ((k[0] + 0.5) * cell - point[0]) ** 2 + ((k[1] + 0.5) * cell - point[1]) ** 2)
            return components[c]

        targets = [
            (0.095 * L, 0.20 * B),                  # engine watch station
            (-0.1725 * L, 0.0),                    # centre of ice hold
            (self.below["bunk_stands"][0][0] * L, 0.0),
            (self.below["bunk_stands"][-1][0] * L, 0.0),
            (0.415 * L, 0.0),                      # forepeak passage
            (-0.40 * L, 0.0),                      # aft stores
        ]
        self.assertGreater(len(nav), 500)
        self.assertEqual(len({nearest_component(point) for point in targets}), 1)

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
