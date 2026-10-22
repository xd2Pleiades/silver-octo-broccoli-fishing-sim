"""Seabird flight model, fishing-ground cues and top-down bird sprite wiring (headless, no pygame)."""
from __future__ import annotations

import ast
import math
from collections import OrderedDict
from pathlib import Path
from unittest import mock
import unittest

from fishing_sim.systems import seabirds as sb
from fishing_sim.systems.hotspot_visuals import slick_visible, baitfish_fleck_count, boil_count

GAME = (Path(__file__).resolve().parents[1] / "core" / "game.py").read_text(encoding="utf-8")
METHODS = {n.name: n for n in ast.walk(ast.parse(GAME)) if isinstance(n, ast.FunctionDef)}
CUE_R = 540.0


def src(name):
    n = METHODS[name]
    return "\n".join(GAME.splitlines()[n.lineno - 1:n.end_lineno])


def run_flock(strength, secs=120.0, count=20, seed=3):
    flock, dt = sb.SeabirdFlock(seed), 0.05
    samples, dives, prev = [], 0, {}
    for _ in range(int(secs / dt)):
        flock.update(dt, 0.0, 0.0, CUE_R, strength, count)
        for b in flock.birds:
            samples.append(math.hypot(b.x, b.y))
            if prev.get(id(b)) != sb.DIVE and b.state == sb.DIVE:
                dives += 1
            prev[id(b)] = b.state
    return flock, samples, dives


class FlightModelTests(unittest.TestCase):
    def test_birds_circle_and_stay_over_the_school(self):
        flock, dist, _ = run_flock(1.0)
        dist.sort()
        self.assertEqual(len(flock.birds), 20)
        self.assertLess(dist[int(len(dist) * 0.95)], CUE_R * 1.2)

    def test_birds_really_wheel_rather_than_sit_on_a_fixed_ellipse(self):
        flock, dt, wound, prev = sb.SeabirdFlock(5), 0.05, {}, {}
        for _ in range(int(60 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 0.8, 12)
            for b in flock.birds:
                if id(b) in prev:
                    wound[id(b)] = wound.get(id(b), 0.0) + sb.wrap_angle(b.heading - prev[id(b)])
                prev[id(b)] = b.heading
        # Every bird completed several full loops in a minute.
        self.assertTrue(all(abs(v) > 3 * math.tau for v in wound.values()))

    def test_turn_rate_is_bounded(self):
        flock, dt, prev, worst = sb.SeabirdFlock(9), 0.05, {}, 0.0
        for _ in range(int(60 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 1.0, 16)
            for b in flock.birds:
                if id(b) in prev:
                    worst = max(worst, abs(sb.wrap_angle(b.heading - prev[id(b)])) / dt)
                prev[id(b)] = b.heading
        self.assertLessEqual(worst, sb.DIVE_TURN_RATE + 1e-6)

    def test_strong_schools_get_more_plunge_dives_and_each_leaves_a_splash(self):
        strong, _, strong_dives = run_flock(1.0, secs=240.0)
        _, _, weak_dives = run_flock(0.2, secs=240.0)
        self.assertGreater(strong_dives, weak_dives * 2)
        self.assertGreater(strong_dives, 20)
        flock, dt, seen = sb.SeabirdFlock(3), 0.05, 0
        for _ in range(int(120 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 1.0, 20)
            seen = max(seen, len(flock.splashes))
        self.assertGreater(seen, 0)
        self.assertLessEqual(seen, sb.MAX_SPLASHES)

    def test_altitude_and_speed_stay_physical(self):
        flock, dt = sb.SeabirdFlock(11), 0.05
        for _ in range(int(90 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 0.9, 20)
            for b in flock.birds:
                self.assertTrue(0.0 <= b.alt <= 1.0)
                self.assertTrue(0.0 <= b.speed <= 600.0)
                self.assertTrue(-1.0 <= b.bank <= 1.0)

    def test_flock_arrives_when_school_strengthens_and_leaves_when_it_fades(self):
        flock, dt = sb.SeabirdFlock(2), 0.05
        for _ in range(int(20 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 0.3, 6)
        self.assertEqual(len(flock.birds), 6)
        for _ in range(int(60 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 1.0, 20)
        self.assertEqual(len([b for b in flock.birds if b.state != sb.LEAVE]), 20)
        for _ in range(int(120 / dt)):
            flock.update(dt, 0.0, 0.0, CUE_R, 0.05, 0)
        self.assertEqual(len(flock.birds), 0)

    def test_flock_follows_a_drifting_school(self):
        flock, dt, x = sb.SeabirdFlock(4), 0.05, 0.0
        for _ in range(int(120 / dt)):
            x += 20.0 * dt                                     # the school drifts 2400 units
            flock.update(dt, x, 0.0, CUE_R, 1.0, 12)
        near = sum(1 for b in flock.birds if math.hypot(b.x - x, b.y) < CUE_R * 1.5)
        self.assertGreaterEqual(near, 10)

    def test_sprite_frame_poses(self):
        b = sb.Seabird(0, 0, 0, 100, 100, 200, 1.0)
        b.glide, b.state = False, sb.CIRCLE
        self.assertIn(sb.sprite_frame(b), range(sb.FLAP_FRAMES))
        b.glide = True
        self.assertEqual(sb.sprite_frame(b), sb.FRAME_GLIDE)
        b.state = sb.DIVE
        self.assertEqual(sb.sprite_frame(b), sb.FRAME_FOLD)


class CueRuleTests(unittest.TestCase):
    def test_ground_cue_thresholds(self):
        self.assertFalse(slick_visible(0.1))
        self.assertTrue(slick_visible(0.5))
        self.assertEqual(baitfish_fleck_count(0.05), 0)
        self.assertGreater(baitfish_fleck_count(1.0), baitfish_fleck_count(0.3))
        self.assertEqual(boil_count(0.2), 0)
        self.assertGreater(boil_count(1.0), boil_count(0.4))


class SpriteAndWiringTests(unittest.TestCase):
    def _namespace(self):
        pg = mock.MagicMock()
        ns = dict(pygame=pg, math=math, OrderedDict=OrderedDict, TAU=math.tau,
                  FLAP_FRAMES=sb.FLAP_FRAMES, FRAME_GLIDE=sb.FRAME_GLIDE, FRAME_FOLD=sb.FRAME_FOLD)
        a = GAME.index("# ------------------------------------------------------------------ seabird art")
        b = GAME.index('\n\nDECK = hexc("#6b5640")')
        exec(GAME[a:b], ns)
        return ns, pg

    def test_every_pose_renders_and_draw_cache_is_bounded(self):
        ns, _ = self._namespace()
        for kind in ("gull", "shearwater"):
            for frame in range(sb.FLAP_FRAMES + 2):
                for bank in (-1, 0, 1):
                    ns["_render_seabird"](kind, frame, bank)
        surf = mock.MagicMock()
        for i in range(2000):
            ns["draw_seabird"](surf, "gull", (10, 10), i * 0.01, 20 + (i % 40) * 0.5, i % 10, 0.0)
        self.assertLessEqual(len(ns["_bird_rotation_cache"]), ns["_BIRD_ROTATION_CACHE_LIMIT"])
        before = surf.blit.call_count
        ns["draw_seabird"](surf, "gull", (0, 0), 0.0, 0.1, 0)       # too small to draw
        self.assertEqual(surf.blit.call_count, before)

    def test_world_draws_birds_from_flocks_not_a_fixed_orbit(self):
        cues = src("draw_hotspot_cues")
        self.assertIn("draw_seabird(self.screen", cues)
        self.assertIn("sprite_frame(bird)", cues)
        self.assertIn("self.seabird_flocks", cues)
        self.assertNotIn("random.random()", cues)
        self.assertNotIn("self.world.time * (0.19", cues)          # old rigid-orbit formula is gone
        for marker in ("slick_visible(strength)", "baitfish_fleck_count(strength)", "boil_count(strength)", "flock.splashes"):
            self.assertIn(marker, cues)

    def test_flocks_update_with_the_simulation_and_follow_live_spots(self):
        self.assertIn("self._update_seabird_flocks(dt)", src("update"))
        upd = src("_update_seabird_flocks")
        self.assertIn("working_bird_count(strength)", upd)
        self.assertIn("flock.spot is not spot", upd)

    def test_follow_birds_use_the_sprite(self):
        self.assertIn('draw_seabird(self.screen, "shearwater"', src("draw_follow_birds"))


if __name__ == "__main__":
    unittest.main()
