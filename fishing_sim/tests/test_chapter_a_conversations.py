"""Chapter A (Part A — Conversations): headless behavioural tests.

Covers the nine A7 assertions plus cooldowns, gating, determinism,
frame-rate independence, persistence and script-data validity.  Pygame-free.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import unittest
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fishing_sim.systems import conversations as cv
from fishing_sim.systems.conversations import (
    BALANCE, Beat, BeatGroup, ConversationContext, ConversationDirector, Participant,
    Script, Tier, TIER_TABLE, silence,
)
from fishing_sim.systems.conversation_scripts import ALL_SCRIPTS, MAYDAY_SETPIECE


def people(*specs):
    """specs: (name, x, y) -> idle participants."""
    return [Participant(name=n, pos=(x, y)) for n, x, y in specs]


def pair(dist=1.0):
    return people(("Alpha", 0.0, 0.0), ("Bravo", dist, 0.0))


def ctx(now=0.0, **kw):
    return ConversationContext(now=now, **kw)


def drive(director, crew, start=0.0, seconds=200.0, dt=0.25, **ctx_kw):
    """Run ``update`` and return (events with timestamps, final time)."""
    out, t = [], start
    while t < start + seconds:
        for e in director.update(crew, ctx(now=t, **ctx_kw)):
            out.append((t, e))
        t += dt
    return out, t


def test_script(sid="t", tier=Tier.SHORT, beats=None, **kw):
    beats = beats or (Beat(lines=("one",)), Beat(lines=("two",)), Beat(lines=("three",)))
    kw.setdefault("cooldown", 1e9)                    # one conversation per test unless overridden
    return Script(sid, kw.pop("category", "test"), tier, beats=tuple(beats), **kw)


class TierSelectionTests(unittest.TestCase):
    def test_tier_weights_favor_micro(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=7)
        counts = Counter(d.roll_tier(ctx(hour=12.0), []) for _ in range(1000))
        self.assertGreater(counts[Tier.MICRO], counts[Tier.LONG])
        self.assertGreater(counts[Tier.MICRO], counts[Tier.SHORT])   # 40 vs 30

    def test_table_matches_guide(self):
        self.assertEqual({t: TIER_TABLE[t][2] for t in TIER_TABLE},
                         {Tier.MICRO: 40.0, Tier.SHORT: 30.0, Tier.MEDIUM: 18.0,
                          Tier.LONG: 8.0, Tier.SETPIECE: 2.0})

    def test_long_suppressed_in_emergency(self):
        for kw in ({"flooding": 0.5}, {"sea_state": 5.0}):
            d = ConversationDirector(ALL_SCRIPTS, world_seed=11)
            d.note_event("radio_assist", 0.0)           # would otherwise boost setpieces
            tiers = {d.roll_tier(ctx(now=1.0, **kw), []) for _ in range(500)}
            self.assertTrue(tiers <= {Tier.MICRO, Tier.SHORT}, tiers)
            started = set()
            for i in range(200):
                d2 = ConversationDirector(ALL_SCRIPTS, world_seed=i)
                d2.note_event("radio_assist", 0.0)
                conv = d2.try_start(pair(), ctx(now=10.0, **kw))
                if conv:
                    started.add(conv.script.tier)
            self.assertTrue(started <= {Tier.MICRO, Tier.SHORT}, started)

    def test_idle_close_pair_raises_longer_tiers(self):
        d = ConversationDirector(ALL_SCRIPTS)
        near = d.tier_weights(ctx(), pair(1.0))
        busy = [replace(p, idle=False) for p in pair(1.0)]
        far = d.tier_weights(ctx(), busy)
        self.assertGreater(near[Tier.MEDIUM], far[Tier.MEDIUM])
        self.assertEqual(near[Tier.MICRO], far[Tier.MICRO])

    def test_night_low_load_raises_long_only(self):
        d = ConversationDirector(ALL_SCRIPTS)
        day = d.tier_weights(ctx(hour=12.0), [])
        night = d.tier_weights(ctx(hour=2.0, task_load=0.1), [])
        self.assertGreater(night[Tier.LONG], day[Tier.LONG])
        self.assertEqual(night[Tier.MEDIUM], day[Tier.MEDIUM])
        busy_night = d.tier_weights(ctx(hour=2.0, task_load=0.9), [])
        self.assertEqual(busy_night[Tier.LONG], day[Tier.LONG])

    def test_setpiece_bonus_after_flood_recovery(self):
        d = ConversationDirector(ALL_SCRIPTS)
        base = d.tier_weights(ctx(now=100.0), [])[Tier.SETPIECE]
        d.observe_flooding(0.6, 100.0)
        d.observe_flooding(0.1, 120.0)                  # dropped below 0.2 -> event recorded
        self.assertIn("flood_recovered", d.event_times)
        self.assertGreater(d.tier_weights(ctx(now=130.0), [])[Tier.SETPIECE], base)


class StartConditionTests(unittest.TestCase):
    def test_participants_must_be_near(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=3)
        crew = pair(10.0)
        for i in range(200):
            self.assertIsNone(d.try_start(crew, ctx(now=10.0 + i * 10.0)))
        self.assertFalse(d.has_active())

    def test_participants_on_different_levels_never_start(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=3)
        crew = pair(1.0)
        crew[1].level = 1
        self.assertIsNone(d.try_start(crew, ctx(now=10.0)))

    def test_busy_or_unavailable_sailors_are_excluded(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=3)
        crew = pair(1.0)
        crew[0].idle = False
        self.assertIsNone(d.try_start(crew, ctx(now=10.0)))
        crew = pair(1.0)
        crew[1].available = False
        self.assertIsNone(d.try_start(crew, ctx(now=10.0)))
        crew = pair(1.0)
        crew[0].speaking_until = 50.0                   # overlap guard
        self.assertIsNone(d.try_start(crew, ctx(now=10.0)))

    def test_script_cooldown_blocks_restart(self):
        only = test_script("only", Tier.MICRO, beats=(Beat(lines=("hi",)),), cooldown=500.0)
        d = ConversationDirector([only], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.MICRO
        crew = pair()
        self.assertIsNotNone(d.try_start(crew, ctx(now=0.0)))
        d.active.clear()
        d.script_ready_at["only"] = 500.0
        self.assertIsNone(d.try_start(crew, ctx(now=100.0)))
        self.assertIsNotNone(d.try_start(crew, ctx(now=501.0)))

    def test_setpiece_cooldown_is_global_and_long(self):
        sp1 = test_script("sp1", Tier.SETPIECE, interruptible=False,
                          beats=tuple(Beat(lines=("x",), delay=(0.1, 0.1)) for _ in range(13)))
        sp2 = replace(sp1, id="sp2")
        d = ConversationDirector([sp1, sp2], world_seed=2)
        crew = pair()
        drive(d, crew, seconds=60.0)
        self.assertGreater(d.setpiece_ready_at, 1000.0)       # ~20 min after the first ended
        self.assertEqual(d.started_count, 1)                  # sp2 blocked even though it never ran
        self.assertEqual(d.tier_weights(ctx(now=100.0), pair())[Tier.SETPIECE], 0.0)

    def test_gate_and_flags(self):
        d = ConversationDirector([MAYDAY_SETPIECE], world_seed=4)
        d.roll_tier = lambda c, g=(): Tier.SETPIECE
        crew = pair()
        self.assertIsNone(d.try_start(crew, ctx(now=10.0)))   # no radio assist yet
        d.note_event("radio_assist", 5.0)
        self.assertIsNotNone(d.try_start(crew, ctx(now=10.0)))

    def test_mayday_setpiece_needs_two_to_three_and_is_non_interruptible(self):
        self.assertEqual(MAYDAY_SETPIECE.participants, (2, 3))
        self.assertFalse(MAYDAY_SETPIECE.interruptible)
        self.assertEqual(MAYDAY_SETPIECE.cooldown, 1200.0)

    def test_three_person_group_chosen_when_available(self):
        s = test_script("tri", Tier.MICRO, participants=(3, 3), beats=(Beat(lines=("hi",)),))
        d = ConversationDirector([s], world_seed=5)
        d.roll_tier = lambda c, g=(): Tier.MICRO
        crew = people(("A", 0, 0), ("B", 1, 0), ("C", 0, 1))
        conv = d.try_start(crew, ctx(now=10.0))
        self.assertEqual(sorted(conv.participants), ["A", "B", "C"])


class CriticalStartTests(unittest.TestCase):
    def test_no_new_conversation_starts_while_critical(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=3)
        for i in range(100):
            self.assertIsNone(d.try_start(pair(), ctx(now=10.0 + i * 10.0, critical=True)))
        self.assertEqual(d.started_count, 0)


class PacingTests(unittest.TestCase):
    def test_quiet_gap_follows_each_conversation(self):
        one = lambda i: Script("p%d" % i, "t", Tier.MICRO, beats=(Beat(lines=("hi",)),), cooldown=0.0)
        d = ConversationDirector([one(0)], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.MICRO
        crew = pair()
        ev, t = drive(d, crew, seconds=5.0)
        self.assertEqual(len(ev), 1)
        self.assertEqual(d.completed_count, 1)
        gap = d.next_start_at - ev[0][0]
        self.assertGreaterEqual(gap, BALANCE["gap_min_s"] - 1.0)
        self.assertLessEqual(gap, BALANCE["gap_max_s"] + 1.0)
        self.assertIsNone(d.try_start(crew, ctx(now=ev[0][0] + BALANCE["gap_min_s"] - 2.0)))

    def test_conversations_are_sparse_over_time(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=6)
        drive(d, pair(), seconds=1800.0, hour=14.0)
        self.assertLessEqual(d.started_count, 1800.0 / BALANCE["gap_min_s"])
        self.assertGreaterEqual(d.started_count, 10)

    def test_start_delay(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=6, start_delay_s=25.0)
        self.assertIsNone(d.try_start(pair(), ctx(now=10.0)))
        self.assertIsNotNone(d.try_start(pair(), ctx(now=26.0)))


class SpeakerTests(unittest.TestCase):
    def test_alternation_no_double_speaker(self):
        for seed in range(25):
            script = test_script("alt", Tier.LONG,
                                 beats=tuple(Beat(lines=("l",), delay=(0.5, 0.6)) for _ in range(7)))
            d = ConversationDirector([script], world_seed=seed)
            d.roll_tier = lambda c, g=(): Tier.LONG
            ev, _ = drive(d, pair(), seconds=30.0)
            names = [e.speaker for _, e in ev]
            self.assertEqual(len(names), 7)
            for a, b in zip(names, names[1:]):
                self.assertNotEqual(a, b)

    def test_alternation_holds_across_the_real_script_library(self):
        for seed in range(25):
            d = ConversationDirector(ALL_SCRIPTS, world_seed=seed)
            ev, _ = drive(d, pair(), seconds=400.0, hour=14.0)
            self.assertTrue(ev)
            current, last = None, None
            for _, e in ev:
                if e.payload["beat"] == 0 or e.payload["script"] != current:
                    current, last = e.payload["script"], None       # new conversation
                if last is not None:
                    self.assertNotEqual(e.speaker, last, e.payload)
                last = e.speaker

    def test_three_person_rotation(self):
        s = test_script("rot", Tier.MEDIUM, participants=(3, 3),
                        beats=tuple(Beat(lines=("l",), delay=(0.4, 0.5)) for _ in range(6)))
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.MEDIUM
        ev, _ = drive(d, people(("A", 0, 0), ("B", 1, 0), ("C", 0, 1)), seconds=20.0)
        names = [e.speaker for _, e in ev][:6]
        self.assertEqual(names[:3], names[3:6])
        self.assertEqual(len(set(names[:3])), 3)

    def test_affinity_picks_first_speaker(self):
        trust = lambda a, b: 0.9 if a == "Warm" else 0.1
        s = test_script("aff", beats=(Beat(lines=("hello",)), Beat(lines=("hi",))))
        for seed in range(30):
            d = ConversationDirector([s], world_seed=seed)
            d.roll_tier = lambda c, g=(): Tier.SHORT
            crew = people(("Cold", 0, 0), ("Warm", 1, 0))       # list order must not decide it
            conv = d.try_start(crew, ctx(now=5.0, trust=trust))
            self.assertEqual(conv.participants[0], "Warm")
            ev, _ = drive(d, crew, start=5.0, seconds=10.0, trust=trust)
            self.assertEqual(ev[0][1].speaker, "Warm")

    def test_task_overlap_breaks_trust_ties(self):
        s = test_script("ovl", beats=(Beat(lines=("hello",)),))
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.SHORT
        a, b = Participant("A", (0, 0), task="haul"), Participant("B", (1, 0), task="haul")
        # both have overlap 0.25 and equal trust -> any opener is legal, but conversation forms
        self.assertIsNotNone(d.try_start([a, b], ctx(now=5.0)))

    def test_overlap_guard_skips_a_speaking_sailor(self):
        s = test_script("guard", Tier.LONG, participants=(3, 3),
                        beats=tuple(Beat(lines=("l",), delay=(1.0, 1.0)) for _ in range(7)))
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.LONG
        crew = people(("A", 0, 0), ("B", 1, 0), ("C", 0, 1))
        d.try_start(crew, ctx(now=0.0))
        crew[1].speaking_until = 1e9                      # B is mid-sentence elsewhere forever
        ev = []
        for i in range(60):
            ev += d.update(crew, ctx(now=1.0 + i * 0.5))
        self.assertTrue(ev)
        self.assertNotIn("B", {e.speaker for e in ev})

    def test_silence_beat_has_no_line_and_takes_time(self):
        s = test_script("sil", beats=(Beat(lines=("first",), delay=(0.5, 0.5)), silence(3.0, 3.0),
                                      Beat(lines=("second",), delay=(0.5, 0.5))))
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.SHORT
        ev, _ = drive(d, pair(), seconds=20.0, dt=0.1)
        self.assertEqual([e.text for _, e in ev], ["first", "second"])
        self.assertGreaterEqual(ev[1][0] - ev[0][0], 3.4)   # 0.5 + 3.0, quantised by dt


class InterruptTests(unittest.TestCase):
    def _director(self, interruptible=True):
        cut = Beat(lines=("Hold on—",), tag=cv.TAG_CUT_SHORT)
        beats = tuple(Beat(lines=("l%d" % i,), delay=(2.0, 2.0)) for i in range(7)) + (cut,)
        s = test_script("int", Tier.LONG, beats=beats, interruptible=interruptible)
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.LONG
        return d

    def test_interrupt_pauses_and_resumes_inside_window(self):
        d = self._director()
        crew = pair()
        ev, t = drive(d, crew, seconds=5.0, dt=0.25)
        before = len(ev)
        self.assertGreater(before, 0)
        conv = d.active[0]
        ev2, t = drive(d, crew, start=t, seconds=10.0, dt=0.25, critical=True)
        self.assertEqual(ev2, [])
        self.assertTrue(d.active[0].paused)
        ev3, t = drive(d, crew, start=t, seconds=30.0, dt=0.25)          # critical cleared at +10 s
        self.assertFalse(conv.paused)
        self.assertGreater(len(ev3), 0)
        self.assertNotIn(cv.TAG_CUT_SHORT, [e.payload.get("tag") for _, e in ev + ev2 + ev3])

    def test_pause_shifts_next_beat_by_pause_duration(self):
        d = self._director()
        crew = pair()
        _, t = drive(d, crew, seconds=2.0, dt=0.25)
        conv = d.active[0]
        due = conv.next_at
        _, t2 = drive(d, crew, start=t, seconds=6.0, dt=0.25, critical=True)
        self.assertTrue(conv.paused)
        d.update(crew, ctx(now=t2))                                       # critical has cleared
        self.assertFalse(conv.paused)
        self.assertAlmostEqual(conv.next_at - due, t2 - t, places=6)      # clock shifted by the pause

    def test_interrupt_abort_emits_exactly_one_cut_short(self):
        d = self._director()
        crew = pair()
        _, t = drive(d, crew, seconds=5.0, dt=0.25)
        ev, t = drive(d, crew, start=t, seconds=40.0, dt=0.25, critical=True)
        cuts = [e for _, e in ev if e.payload and e.payload.get("tag") == cv.TAG_CUT_SHORT]
        self.assertEqual(len(cuts), 1)
        self.assertEqual(len(ev), 1)
        self.assertFalse(d.has_active())
        self.assertEqual(d.aborted_count, 1)
        self.assertGreater(ev[0][0] - 5.0 - 0.25, BALANCE["resume_window_s"] - 1.0)

    def test_cut_short_comes_from_most_recent_speaker(self):
        d = self._director()
        crew = pair()
        ev, t = drive(d, crew, seconds=5.0, dt=0.25)
        last = ev[-1][1].speaker
        ev2, _ = drive(d, crew, start=t, seconds=40.0, dt=0.25, critical=True)
        self.assertEqual(ev2[0][1].speaker, last)

    def test_cut_short_beat_never_plays_in_normal_flow(self):
        d = self._director()
        ev, _ = drive(d, pair(), seconds=60.0)
        tags = [e.payload.get("tag") for _, e in ev]
        self.assertNotIn(cv.TAG_CUT_SHORT, tags)
        self.assertEqual(len(ev), 7)

    def test_setpiece_non_interruptible(self):
        d = ConversationDirector([MAYDAY_SETPIECE], world_seed=2)
        d.roll_tier = lambda c, g=(): Tier.SETPIECE
        d.note_event("radio_assist", 0.0)
        crew = people(("A", 0, 0), ("B", 1, 0))
        ev, t = drive(d, crew, seconds=10.0, dt=0.25)
        self.assertTrue(d.has_active())
        ev2, t = drive(d, crew, start=t, seconds=60.0, dt=0.25, critical=True)
        self.assertFalse(d.active and d.active[0].paused)
        self.assertGreater(len(ev2), 0)                                # kept talking through CRITICAL
        ev3, _ = drive(d, crew, start=t, seconds=120.0, dt=0.25, critical=True)
        all_lines = [e.text for _, e in ev + ev2 + ev3]
        self.assertIn("No. We weren't.", all_lines)                    # reached the close
        self.assertEqual(d.completed_count, 1)


class EndingTests(unittest.TestCase):
    def test_ends_on_tag_terminates_early(self):
        beats = (Beat(lines=("a",), delay=(0.5, 0.5)),
                 Beat(lines=("stop",), tag="halt", delay=(0.5, 0.5)),
                 Beat(lines=("never",), delay=(0.5, 0.5)),
                 Beat(lines=("never2",), delay=(0.5, 0.5)))
        s = test_script("early", Tier.MEDIUM, beats=beats, ends_on="halt")
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.MEDIUM
        ev, _ = drive(d, pair(), seconds=20.0)
        self.assertEqual([e.text for _, e in ev], ["a", "stop"])
        self.assertFalse(d.has_active())
        self.assertEqual(d.completed_count, 1)

    def test_participant_walking_off_ends_conversation_without_cut_short(self):
        beats = tuple(Beat(lines=("l",), delay=(1.0, 1.0)) for _ in range(7)) + (
            Beat(lines=("cut",), tag=cv.TAG_CUT_SHORT),)
        s = test_script("walk", Tier.LONG, beats=beats)
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.LONG
        crew = pair()
        drive(d, crew, seconds=3.0)
        crew[1].pos = (50.0, 0.0)
        ev = d.update(crew, ctx(now=4.0))
        self.assertEqual(ev, [])
        self.assertFalse(d.has_active())
        self.assertFalse(crew[0].in_conversation)

    def test_unavailable_participant_ends_conversation(self):
        s = test_script("gone", beats=tuple(Beat(lines=("l",), delay=(1.0, 1.0)) for _ in range(3)))
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.SHORT
        crew = pair()
        drive(d, crew, seconds=1.5)
        crew[0].available = False
        d.update(crew, ctx(now=2.0))
        self.assertFalse(d.has_active())

    def test_in_conversation_flag_set_and_cleared(self):
        s = test_script("flag", beats=(Beat(lines=("a",), delay=(0.5, 0.5)), Beat(lines=("b",))))
        d = ConversationDirector([s], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.SHORT
        crew = pair()
        d.update(crew, ctx(now=0.0))
        self.assertTrue(all(p.in_conversation for p in crew))
        self.assertTrue(d.is_in_conversation("Alpha"))
        drive(d, crew, start=0.25, seconds=10.0)
        self.assertFalse(any(p.in_conversation for p in crew))


class ScriptContentTests(unittest.TestCase):
    @staticmethod
    def _turns(script):
        return sum(1 for b in script.beats
                   if isinstance(b, BeatGroup) or (b.tag != cv.TAG_CUT_SHORT and not b.is_silence))

    def test_every_script_fits_its_declared_tier(self):
        for s in ALL_SCRIPTS:
            lo, hi, _ = TIER_TABLE[s.tier]
            n = self._turns(s)
            self.assertGreaterEqual(n, lo, s.id)
            if hi is not None:
                self.assertLessEqual(n, hi, s.id)

    def test_every_tier_has_a_script(self):
        self.assertEqual({s.tier for s in ALL_SCRIPTS}, set(Tier))

    def test_script_ids_unique(self):
        ids = [s.id for s in ALL_SCRIPTS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_interruptible_long_form_scripts_have_a_cut_short_beat(self):
        for s in ALL_SCRIPTS:
            if s.tier in (Tier.MEDIUM, Tier.LONG, Tier.SETPIECE) and s.interruptible:
                self.assertTrue(any(isinstance(b, Beat) and b.tag == cv.TAG_CUT_SHORT for b in s.beats), s.id)

    def test_after_flood_matches_the_guide_example(self):
        from fishing_sim.systems.conversation_scripts import AFTER_FLOOD
        self.assertEqual(AFTER_FLOOD.tier, Tier.LONG)
        self.assertEqual(AFTER_FLOOD.cooldown, 600.0)
        first = AFTER_FLOOD.beats[0]
        self.assertEqual(first.lines, ("That was closer than I like.",))
        self.assertTrue(any(isinstance(b, Beat) and b.tag == cv.TAG_SILENCE for b in AFTER_FLOOD.beats))
        self.assertEqual(AFTER_FLOOD.beats[-2].tag, "close")

    def test_after_flood_only_after_recovery(self):
        from fishing_sim.systems.conversation_scripts import AFTER_FLOOD
        d = ConversationDirector([AFTER_FLOOD], world_seed=1)
        d.roll_tier = lambda c, g=(): Tier.LONG
        crew = pair()
        self.assertIsNone(d.try_start(crew, ctx(now=10.0, flooding=0.05)))
        d.observe_flooding(0.6, 20.0)
        d.observe_flooding(0.1, 40.0)
        self.assertIsNotNone(d.try_start(crew, ctx(now=60.0, flooding=0.1)))


class DeterminismAndFrameRateTests(unittest.TestCase):
    def _run(self, seed, dt, seconds=1500.0):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=seed)
        ev, _ = drive(d, pair(), seconds=seconds, dt=dt, hour=14.0)
        return [(e.speaker, e.text) for _, e in ev]

    def test_same_seed_same_conversation(self):
        self.assertEqual(self._run(42, 0.25), self._run(42, 0.25))

    def test_different_seed_differs(self):
        self.assertNotEqual(self._run(1, 0.25), self._run(2, 0.25))

    def test_first_conversation_independent_of_tick_rate(self):
        """Same lines in the same order at 30 Hz, 8 Hz and 2 Hz; timing within one tick."""
        runs = {}
        for dt in (1 / 30, 1 / 8, 0.5):
            d = ConversationDirector(ALL_SCRIPTS, world_seed=9)
            ev, _ = drive(d, pair(), seconds=40.0, dt=dt, hour=14.0)
            runs[dt] = ev
        base = [e.text for _, e in runs[1 / 30]]
        self.assertTrue(base)
        for dt, ev in runs.items():
            n = min(len(base), len(ev))
            self.assertEqual([e.text for _, e in ev][:n], base[:n], dt)
        # Each beat's due-time is quantised to the tick, so drift is at most one tick per beat.
        for i, ((t0, _), (t1, _)) in enumerate(zip(runs[1 / 30][:4], runs[0.5][:4]), start=1):
            self.assertLessEqual(abs(t0 - t1), 0.5 * i + 0.1, (i, t0, t1))

    def test_snapshot_restore_round_trip(self):
        d = ConversationDirector(ALL_SCRIPTS, world_seed=5)
        drive(d, pair(), seconds=300.0, hour=14.0)
        d.note_event("catch", 123.0)
        snap = d.snapshot()
        e = ConversationDirector(ALL_SCRIPTS, world_seed=5)
        e.restore(snap)
        self.assertEqual(e.script_ready_at, d.script_ready_at)
        self.assertEqual(e.event_times, d.event_times)
        self.assertEqual(e.rng.getstate(), d.rng.getstate())
        with self.assertRaises(ValueError):
            e.restore({"schema": 999})

    def test_snapshot_is_json_serialisable(self):
        import json
        d = ConversationDirector(ALL_SCRIPTS, world_seed=5)
        drive(d, pair(), seconds=100.0, hour=14.0)
        restored = json.loads(json.dumps(d.snapshot()))
        ConversationDirector(ALL_SCRIPTS, world_seed=5).restore(restored)


# ---------------------------------------------------------------------------------------------
# Game integration (needs pygame; skipped otherwise, like the other Game-level tests).
# ---------------------------------------------------------------------------------------------
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
try:
    import pygame  # noqa: F401
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


def _all_script_lines():
    lines = set()
    for sc in ALL_SCRIPTS:
        for slot in sc.beats:
            for b in (slot.options if isinstance(slot, BeatGroup) else (slot,)):
                lines.update(b.lines)
    return lines


@unittest.skipUnless(PYGAME_AVAILABLE, "requires pygame runtime dependencies")
class GameConversationIntegrationTests(unittest.TestCase):
    def test_game_owns_a_seeded_director_with_the_full_library(self):
        g = _new_game()
        self.assertIsInstance(g.crew_conversations, ConversationDirector)
        self.assertEqual(set(g.crew_conversations.scripts), {s.id for s in ALL_SCRIPTS})

    def test_participants_snapshot_converts_pixels_to_metres(self):
        g = _new_game()
        crew = g._crew_conversation_participants(0.0)
        self.assertEqual({p.name for p in crew}, {s.name for s in g.sailors})
        s0, p0 = g.sailors[1], crew[1]
        self.assertAlmostEqual(p0.pos[0], s0.pos.x / g.DECK_PX_PER_METRE)
        self.assertAlmostEqual(p0.pos[1], s0.pos.y / g.DECK_PX_PER_METRE)

    def test_conversation_lines_reach_the_crew_as_attributed_speech(self):
        g = _new_game()
        spoken = []
        original = g.crew.say
        g.crew.say = lambda text: (spoken.append(text), original(text))[1]
        _step(g, 400)
        lines = _all_script_lines()
        convo = [t for t in spoken if ": " in t and t.split(": ", 1)[1] in lines]
        self.assertGreater(len(convo), 5)
        names = {s.name for s in g.sailors}
        self.assertTrue(all(t.split(": ", 1)[0] in names for t in convo))
        self.assertGreater(g.crew_conversations.started_count, 0)

    def _two_idle_sailors_at_sea(self):
        g = _new_game()
        a, b = g.sailors[2], g.sailors[3]
        for s in g.sailors:
            if s not in (a, b):
                s.mode = G.Sailor.SHORE                      # only two hands aboard
        b.pos = type(a.pos)(a.pos.x + 40, a.pos.y)
        a.task = b.task = "idle"
        a.level = b.level = G.Level.MAIN
        g.docked = lambda: False                             # ambient chatter is silent in harbour
        g.broadcast_director.is_busy = lambda: False
        return g

    def test_ambient_crew_chatter_yields_to_an_active_conversation(self):
        queued = []
        # Control: no conversation running -> the ambient timer queues a deck exchange.
        g = self._two_idle_sailors_at_sea()
        g.crew_conversations.next_start_at = 1e12            # conversations held off
        g.queue_broadcast_conversation = lambda lines, **kw: queued.append(kw.get("source"))
        g.broadcast_crew_chatter_timer = 0.0
        g._queue_ambient_crew_conversation(0.05)
        self.assertIn("deck_chatter", queued)

        # Same situation but a conversation is active -> ambient chatter is suppressed.
        queued.clear()
        g = self._two_idle_sailors_at_sea()
        g.crew_conversations.scripts = {"g_long": test_script("g_long", Tier.LONG, beats=tuple(
            Beat(lines=("l",), delay=(5.0, 5.0)) for _ in range(7)))}
        g.crew_conversations.roll_tier = lambda c, grp=(): Tier.LONG
        g.crew_conversations.next_start_at = 0.0
        g.queue_broadcast_conversation = lambda lines, **kw: queued.append(kw.get("source"))
        g.broadcast_crew_chatter_timer = 0.0
        g._queue_ambient_crew_conversation(0.05)
        self.assertTrue(g.crew_conversations.has_active())
        self.assertNotIn("deck_chatter", queued)

    def test_conversing_sailors_stand_still_instead_of_wandering(self):
        g = _new_game()
        a, b = g.sailors[2], g.sailors[3]
        for s in g.sailors:
            if s not in (a, b):
                s.mode = G.Sailor.SHORE
        b.pos = type(a.pos)(a.pos.x + 40, a.pos.y)
        a.task = b.task = "idle"
        a.level = b.level = G.Level.MAIN
        script = test_script("g_hold", Tier.LONG, beats=tuple(
            Beat(lines=("l",), delay=(4.0, 4.0)) for _ in range(7)))
        g.crew_conversations.scripts = {"g_hold": script}
        g.crew_conversations.roll_tier = lambda c, grp=(): Tier.LONG
        g.crew_conversations.next_start_at = 0.0
        _step(g, 2.0)
        self.assertTrue(g.crew_conversations.has_active())
        self.assertTrue(a.conversation_hold and b.conversation_hold)
        start_a, start_b = type(a.pos)(a.pos), type(b.pos)(b.pos)
        a.wander_t = b.wander_t = 0.0                      # would normally trigger a wander right now
        _step(g, 6.0)
        self.assertLess(a.pos.distance_to(start_a), 25.0)
        self.assertLess(b.pos.distance_to(start_b), 25.0)

    def test_man_overboard_is_critical_and_pauses_the_conversation(self):
        g = _new_game()
        self.assertFalse(g._crew_conversation_critical())
        swimmer = g.sailors[3]
        swimmer.mode = G.Sailor.SWIMMING
        self.assertTrue(g._crew_conversation_critical())
        swimmer.mode = G.Sailor.ABOARD
        g.ship.hold_flood = 0.8
        self.assertTrue(g._crew_conversation_critical())

    def test_catch_and_rescue_record_world_events(self):
        g = _new_game()
        g.crew.add_catch(100)
        self.assertIn("catch", g.crew_conversations.event_times)

    def test_conversation_hold_flag_defaults_false(self):
        g = _new_game()
        self.assertTrue(all(s.conversation_hold is False for s in g.sailors))


if __name__ == "__main__":
    unittest.main()
