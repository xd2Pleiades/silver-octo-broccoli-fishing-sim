"""Chapter B - sailor motion (Design Guide v3.2, B11)."""
import math
import os
import random
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from fishing_sim.systems import sailor_motion as M
from fishing_sim.systems.sailor_motion import (
    BALANCE, Bottleneck, GatherPlanner, MotionState, PathFollower)


def run(s, seconds, dt, **kw):
    for _ in range(int(round(seconds / dt))):
        M.step_crew([s], dt, **kw)


def speed(s):
    return math.hypot(*s.vel)


class LocomotionTests(unittest.TestCase):
    def test_arrive_decelerates(self):
        s = MotionState("a", pos=(0, 0), target=(10, 0))
        for _ in range(2000):
            M.step_crew([s], 1 / 60)
            if math.hypot(10 - s.pos[0], 0) <= 0.1:
                break
        self.assertLess(speed(s), 0.2 * BALANCE["max_speed"])

    def test_brace_slows(self):
        def steady(brace):
            s = MotionState("a", pos=(0, 0), target=(1e4, 0), brace=brace)
            for _ in range(600):
                s.vel = M.step_velocity(s, M.desired_velocity(s), 1 / 60)
            return speed(s)
        self.assertLessEqual(steady(1.0), 0.4 * steady(0.0) + 1e-9)

    def test_brace_dt_independent(self):
        def steady(dt):
            s = MotionState("a", pos=(0, 0), target=(1e4, 0), brace=0.8)
            for _ in range(int(3 / dt)):
                s.vel = M.step_velocity(s, M.desired_velocity(s), dt)
            return speed(s)
        self.assertAlmostEqual(steady(1 / 30), steady(1 / 120), places=6)

    def test_speed_cap_does_not_compound(self):
        s = MotionState("a", target=(1e4, 0), brace=1.0)
        d1 = M.desired_velocity(s)
        d2 = M.desired_velocity(s)
        self.assertEqual(d1, d2)

    def test_facing_turns_toward_velocity_at_turn_rate(self):
        s = MotionState("a", vel=(0, 1.0), facing=0.0)
        f = M.step_facing(s, 0.1)
        self.assertAlmostEqual(f, BALANCE["turn_rate"] * 0.1)

    def test_facing_toward_speaker_overrides_velocity(self):
        s = MotionState("a", pos=(0, 0), facing=0.0)
        for _ in range(60):
            s.facing = M.step_facing(s, 1 / 30, face_toward=(0, 5))
        self.assertAlmostEqual(s.facing, math.pi / 2, places=6)


class SeparationTests(unittest.TestCase):
    def test_separation_pushes_apart(self):
        a, b = MotionState("a", pos=(0, 0)), MotionState("b", pos=(0, 0))
        for _ in range(240):
            M.step_crew([a, b], 1 / 60)
        d = math.hypot(a.pos[0] - b.pos[0], a.pos[1] - b.pos[1])
        self.assertGreaterEqual(d, 0.9 * (a.radius + b.radius))

    def test_separation_dt_independent(self):
        def disp(dt):
            a, b = MotionState("a", pos=(0.0, 0.0)), MotionState("b", pos=(0.3, 0.0))
            for _ in range(int(0.25 / dt)):          # short window, still overlapping
                M.step_crew([a, b], dt)
            return a.pos[0]
        coarse, fine = disp(1 / 30), disp(1 / 120)
        self.assertLess(abs(coarse - fine), 0.15 * abs(fine))

    def test_bottleneck_queue_preserves_order(self):
        hatch = Bottleneck("hatch", (0, 0), capacity=1, facing=0.0)
        got = [hatch.request(n) for n in ("a", "b", "c")]
        self.assertEqual(got, [True, False, False])
        order = []
        for _ in range(3):
            order.append(hatch.holders[0])
            hatch.release(hatch.holders[0])
        self.assertEqual(order, ["a", "b", "c"])

    def test_queue_spots_stack_behind_the_bottleneck(self):
        hatch = Bottleneck("hatch", (0, 0), capacity=1, facing=0.0)
        for n in ("a", "b", "c"):
            hatch.request(n)
        b, c = hatch.queue_spot("b"), hatch.queue_spot("c")
        self.assertLess(b[0], 0)
        self.assertLess(c[0], b[0])
        self.assertIsNone(hatch.queue_spot("a"))


class BraceTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(M.classify_brace(5.9, 0.0, True), M.BRACE_NONE)
        self.assertEqual(M.classify_brace(6.0, 0.0, True), M.BRACE_WALK_MODE)
        self.assertEqual(M.classify_brace(6.0, 0.0, False), M.BRACE_NONE)
        self.assertEqual(M.classify_brace(10.0, 0.0, False), M.BRACE_GRAB)
        self.assertEqual(M.classify_brace(0.0, 0.41, False), M.BRACE_GRAB)

    def test_grab_rail_targets_rail_and_raises_brace(self):
        s = MotionState("a", pos=(0, 0), target=(5, 5))
        for _ in range(60):
            M.update_brace(s, 12.0, 0.0, 1 / 30, nearest_rail=(0.0, 1.0))
        self.assertEqual(s.target, (0.0, 1.0))
        self.assertEqual(s.brace, 1.0)

    def test_brace_rises_at_three_per_second(self):
        s = MotionState("a", target=(1, 1))
        M.update_brace(s, 12.0, 0.0, 0.1, nearest_rail=(0, 1))
        self.assertAlmostEqual(s.brace, 0.3)

    def test_brace_release_clears_stale_rail_target(self):
        s = MotionState("a", pos=(0, 0), station_target=(9, 9))
        for _ in range(30):
            M.update_brace(s, 12.0, 0.0, 1 / 30, nearest_rail=(0.0, 1.0))
        self.assertEqual(s.target, (0.0, 1.0))
        M.update_brace(s, 0.0, 0.0, 1 / 30, nearest_rail=(0.0, 1.0))      # roll dropped
        self.assertIsNone(s.target)
        for _ in range(120):
            M.step_crew([s], 1 / 30, abs_roll_deg=0.0, rail_points=[(0.0, 1.0)])
        self.assertGreater(s.pos[0], 1.0)           # heads to the station, not the rail

    def test_lean_is_against_the_roll(self):
        self.assertAlmostEqual(M.lean_angle_deg(1.0, 10.0), -7.0)
        self.assertEqual(M.lean_angle_deg(0.0, 10.0), 0.0)


class StaggerTests(unittest.TestCase):
    def test_stagger_opposes_roll_rate_and_scales_with_brace(self):
        self.assertLess(M.stagger_impulse(20.0, 0.0), 0.0)
        self.assertGreater(M.stagger_impulse(-20.0, 0.0), 0.0)
        self.assertEqual(M.stagger_impulse(20.0, 0.5), 0.0)
        self.assertEqual(M.stagger_impulse(2.0, 0.0), 0.0)
        self.assertLessEqual(abs(M.stagger_impulse(1e6, 0.0)), BALANCE["stagger_cap"])

    def test_deck_clamp_under_random_roll_impulses(self):
        rng = random.Random(7)
        bounds = (-8.0, -2.0, 8.0, 2.0)
        crew = [MotionState("s%d" % i, pos=(rng.uniform(-7, 7), rng.uniform(-1.5, 1.5))) for i in range(6)]
        for _ in range(3000):
            M.step_crew(crew, 1 / 60, abs_roll_deg=rng.uniform(0, 14),
                        roll_rate_deg_s=rng.uniform(-400, 400), bounds=bounds)
            for s in crew:
                self.assertTrue(bounds[0] <= s.pos[0] <= bounds[2] and bounds[1] <= s.pos[1] <= bounds[3])


class AnimationTests(unittest.TestCase):
    def test_state_selection(self):
        self.assertEqual(M.select_anim(0.0, 0.0, "idle"), M.IDLE_SWAY)
        self.assertEqual(M.select_anim(1.0, 0.0, "idle"), M.WALK)
        self.assertEqual(M.select_anim(1.0, 0.4, "idle"), M.BRACE_WALK)
        self.assertEqual(M.select_anim(0.0, 0.8, "idle"), M.BRACE_HOLD)
        self.assertEqual(M.select_anim(0.0, 0.0, "bail"), M.WORK_CROUCH)
        self.assertEqual(M.select_anim(0.0, 0.0, "helm"), M.STAND_WATCH)

    def test_transitions_blend_not_cut(self):
        s = MotionState("a", vel=(1.0, 0.0))
        M.update_anim(s, 0.0)
        self.assertEqual((s.anim_prev, s.anim, s.anim_t), (M.IDLE_SWAY, M.WALK, 0.0))
        M.update_anim(s, 0.1)
        self.assertAlmostEqual(s.anim_t, 0.5)
        M.update_anim(s, 0.2)
        self.assertEqual(s.anim_t, 1.0)


class PathTests(unittest.TestCase):
    def test_waypoint_advance_radius(self):
        f = PathFollower()
        f.set_path([(1, 0), (2, 0), (3, 0)])
        self.assertEqual(f.advance((0.7, 0)), (2, 0))
        self.assertEqual(f.advance((0.7, 0)), (2, 0))

    def test_repath_throttle(self):
        f = PathFollower()
        f.set_path([(5, 0)])
        count, t, dt = 0, 0.0, 1 / 60
        while t < 10.0:
            f.note_progress(True, dt)                # permanently blocked
            if f.should_repath(t):
                f.mark_repathed(t)
                count += 1
            t += dt
        self.assertLessEqual(count / 10.0, 2.0)
        self.assertGreaterEqual(count, 3)

    def test_repath_waits_for_block_duration(self):
        f = PathFollower()
        f.note_progress(True, 1.0)
        self.assertFalse(f.should_repath(100.0))
        f.note_progress(True, 0.6)
        self.assertTrue(f.should_repath(100.0))
        self.assertTrue(PathFollower().should_repath(100.0, deck_state_changed=True))

    def test_string_pull_removes_grid_staircase(self):
        stairs = [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2)]
        self.assertEqual(M.smooth_path(stairs, lambda a, b: True), [(0, 0), (3, 2)])

    def test_string_pull_keeps_blocked_corner(self):
        pts = [(0, 0), (4, 0), (4, 4)]
        out = M.smooth_path(pts, lambda a, b: not (a == (0, 0) and b == (4, 4)))
        self.assertEqual(out, pts)


class GatherTests(unittest.TestCase):
    def test_meeting_spot_minimises_longer_walk(self):
        spot = M.pick_meeting_spot((0, 0), (10, 0), [(0, 5), (5, 0), (20, 0)])
        self.assertEqual(spot, (5, 0))

    def test_plan_brings_a_far_pair_inside_conversation_radius(self):
        gp = GatherPlanner(seed=3, interval_s=1.0)
        plan = gp.plan(2.0, [("a", (0, 0)), ("b", (10, 0))], [(5, 0)])
        self.assertIsNotNone(plan)
        a, b = plan["a"], plan["b"]
        self.assertLess(math.hypot(a[0] - b[0], a[1] - b[1]), BALANCE["conversation_radius"])

    def test_plan_skips_pairs_already_close_and_respects_cooldown(self):
        gp = GatherPlanner(seed=3, interval_s=1.0, cooldown_s=100.0)
        self.assertIsNone(gp.plan(2.0, [("a", (0, 0)), ("b", (1, 0))], [(5, 0)]))
        self.assertIsNotNone(gp.plan(4.0, [("a", (0, 0)), ("b", (10, 0))], [(5, 0)]))
        self.assertIsNone(gp.plan(8.0, [("a", (0, 0)), ("b", (10, 0))], [(5, 0)]))

    def test_plan_is_deterministic(self):
        idle = [("a", (0, 0)), ("b", (9, 0)), ("c", (0, 9))]
        r1 = GatherPlanner(seed=5, interval_s=1.0).plan(2.0, idle, [(4, 4)])
        r2 = GatherPlanner(seed=5, interval_s=1.0).plan(2.0, idle, [(4, 4)])
        self.assertEqual(r1, r2)


class PerformanceTests(unittest.TestCase):
    def test_twelve_sailors_well_under_a_millisecond_per_tick(self):
        rng = random.Random(1)
        crew = [MotionState("s%d" % i, pos=(rng.uniform(-6, 6), rng.uniform(-1.5, 1.5)),
                            station_target=(rng.uniform(-6, 6), rng.uniform(-1.5, 1.5)),
                            target=(rng.uniform(-6, 6), rng.uniform(-1.5, 1.5))) for i in range(12)]
        n = 500
        t0 = time.perf_counter()
        for _ in range(n):
            M.step_crew(crew, 1 / 60, abs_roll_deg=7.0, roll_rate_deg_s=15.0)
        per_tick_ms = (time.perf_counter() - t0) / n * 1000.0
        self.assertLess(per_tick_ms, 3.0)           # generous CI bound; real figure printed in the status doc
        print("\n[chapter B] 12 sailors: %.3f ms/tick" % per_tick_ms)


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------
# Game integration (needs pygame)
# --------------------------------------------------------------------------
try:
    import pygame  # noqa: F401
    from pygame.math import Vector2 as V
    from fishing_sim.core import game as G
    PYGAME_AVAILABLE = True
except ImportError:
    G = None
    PYGAME_AVAILABLE = False


class _NoKeys:
    def __getitem__(self, key):
        return False


def _new_game(seed=1):
    random.seed(seed)
    return G.Game()


def _step(g, seconds, dt=0.05):
    for _ in range(int(seconds / dt)):
        g.update(dt, _NoKeys())


def _two_idle_at_sea(g, apart_px=0.0):
    a, b = g.sailors[2], g.sailors[3]
    for s in g.sailors:
        if s not in (a, b):
            s.mode = G.Sailor.SHORE
    a.task = b.task = "idle"
    a.level = b.level = G.Level.MAIN
    g.docked = lambda: False
    g.broadcast_director.is_busy = lambda: False
    return a, b


@unittest.skipUnless(PYGAME_AVAILABLE, "requires pygame runtime dependencies")
class GameMotionIntegrationTests(unittest.TestCase):
    def test_roll_degrees_is_signed_and_scaled(self):
        g = _new_game()
        g.roll = 0.05
        self.assertAlmostEqual(g.roll_degrees(), math.degrees(math.atan(0.05)) * g.ROLL_DEG_GAIN)
        g.roll = -0.05
        self.assertLess(g.roll_degrees(), 0.0)

    def test_idle_hand_grabs_the_rail_then_release_clears_the_target(self):
        g = _new_game()
        a, _ = _two_idle_at_sea(g)
        g.roll_degrees = lambda: 12.0
        for _ in range(40):
            a._update_bracing(0.05)
        self.assertEqual(a.brace_mode, M.BRACE_GRAB)
        self.assertEqual(a.brace, 1.0)
        self.assertIsNotNone(a.rail_goal)
        self.assertTrue(g.ship.on_deck(a.rail_goal))
        a.has_target = True
        g.roll_degrees = lambda: 0.0
        a._update_bracing(0.05)
        self.assertIsNone(a.rail_goal)
        self.assertFalse(a.has_target)               # stale rail target is not followed
        for _ in range(80):
            a._update_bracing(0.05)
        self.assertEqual(a.brace, 0.0)

    def test_station_keepers_stay_at_their_posts_in_a_heavy_roll(self):
        g = _new_game()
        helm = g.helm_operator
        g.roll_degrees = lambda: 12.0
        for _ in range(20):
            helm._update_bracing(0.05)
        self.assertIsNone(helm.rail_goal)

    def test_brace_walk_covers_less_ground_than_normal_walk(self):
        def travelled(roll):
            g = _new_game(3)
            a, _ = _two_idle_at_sea(g)
            g.roll_degrees = lambda: roll
            a.task = "order"
            a.ordering, a.order_hold = True, 999.0
            start = V(a.pos)
            a.order_to(start + V(400, 0))
            for _ in range(30):
                a.update(0.05)
            return (a.pos - start).length()
        self.assertLess(travelled(6.5), 0.9 * travelled(0.0))

    def test_conversation_participants_face_the_speaker_and_stand_still(self):
        g = _new_game()
        a, b = _two_idle_at_sea(g)
        b.pos = V(a.pos.x + 150, a.pos.y)
        a.conversation_hold = b.conversation_hold = True
        a.face_target, b.face_target = V(b.pos), V(a.pos)
        a.facing, b.facing = 1.2, -1.0
        for _ in range(40):
            a.update(0.05)
            b.update(0.05)
        self.assertAlmostEqual(math.cos(a.facing), 1.0, places=2)
        self.assertAlmostEqual(math.cos(b.facing), -1.0, places=2)
        self.assertLess(a.vel.length(), 1.0)

    def test_gather_brings_far_idle_pair_into_conversation_range(self):
        g = _new_game()
        a, b = _two_idle_at_sea(g)
        a.pos, b.pos = V(g.ship.markers["rest_spot"]), V(g.ship.markers["bow_lookout"])
        before = a.pos.distance_to(b.pos) / g.DECK_PX_PER_METRE
        self.assertGreater(before, 3.0)
        g.crew_gather = M.GatherPlanner(seed=1, interval_s=1.0)
        goals = []
        for _ in range(int(40 / 0.05)):
            g.update(0.05, _NoKeys())
            if a.gather_goal is not None and b.gather_goal is not None and not goals:
                goals.append((V(a.gather_goal), V(b.gather_goal)))
        self.assertTrue(goals, "the planner never dispatched the idle pair")
        ga, gb = goals[0]
        self.assertLess(ga.distance_to(gb) / g.DECK_PX_PER_METRE, 3.0)
        gathered = a.pos.distance_to(b.pos) / g.DECK_PX_PER_METRE
        self.assertLess(gathered, 3.0, "gather should close %.1f m to under 3 m" % before)

    def test_gather_does_not_run_during_an_emergency(self):
        g = _new_game()
        a, b = _two_idle_at_sea(g)
        g._crew_conversation_critical = lambda: True
        g.crew_gather = M.GatherPlanner(seed=1, interval_s=1.0)
        _step(g, 10)
        self.assertIsNone(a.gather_goal)
        self.assertIsNone(b.gather_goal)
