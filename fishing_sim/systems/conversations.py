"""Part A — scripted crew conversations with a shape (opening, middle, ending).

Pure, Pygame-free and deterministic.  The director never touches Sailor/Game
objects directly: callers pass lightweight :class:`Participant` snapshots and a
:class:`ConversationContext`, and receive :class:`ChatterEvent` objects back.

Design reference: Sailor Systems Design Guide v3.2, Part A (A1-A7).

Conventions honoured here (section 0 of the guide):
  * positions are in metres (the Game adapter converts from deck pixels);
  * all randomness comes from one seeded ``random.Random`` per director, derived
    from the world seed with a system-specific salt;
  * the director is frame-rate independent: it only compares absolute ``now``
    timestamps (simulation seconds) and never counts frames.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
import random
from typing import Any, Callable, Optional, Sequence

from fishing_sim.world.seeding import stable_seed

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Tunables (guide section 0.5 says these belong in a balance profile; the repo
# has no profile loader yet, so they live in one dict that a loader can later
# override with ``BALANCE.update(profile["conversation"])``).
# --------------------------------------------------------------------------
BALANCE: dict[str, float] = {
    "conversation_radius_m": 3.0,        # A3: participants must be within ~3 m
    "abandon_radius_m": 6.0,             # a participant who walks this far off drops out
    "resume_window_s": 20.0,             # A3: pause -> resume window
    "setpiece_cooldown_s": 1200.0,       # A1: global, 20 min
    "flooding_emergency": 0.25,          # A1: no chat above short while flooding > 0.25
    "sea_emergency": 5.0,                # A1: ... or sea state >= 5
    "flood_recovered_threshold": 0.2,    # A1/A5: flooding just dropped below 0.2
    "flood_recovered_window_s": 600.0,   # "just recovered" context lasts 10 min
    "radio_assist_window_s": 600.0,      # A1/A5: radio assist within the last 10 min
    "catch_window_s": 120.0,             # A1: a catch "just came aboard"
    "idle_close_bonus": 1.6,             # A1 "+" both idle and within 3 m (above micro)
    "night_long_bonus": 2.5,             # A1 "+" night + low task load (long only)
    "setpiece_trigger_bonus": 12.0,      # A1 "+" setpiece after a big event
    "emergency_micro_factor": 1.0,       # micro/short are unaffected by emergencies
    "familiar_bonus": 1.3,               # D7.3 familiarity > 0.6
    "grievance_penalty": 0.6,            # D7.3 grievance > 0.4
    "night_start_hour": 21.0,
    "night_end_hour": 5.0,
    "low_task_load": 0.35,
    "gap_min_s": 35.0,                   # quiet pause after a conversation ends (random in range)
    "gap_max_s": 90.0,
    "first_beat_delay_s": 0.8,
}


class Tier(str, Enum):
    MICRO = "micro"
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    SETPIECE = "setpiece"


# A1 table: (min turns, max turns, base weight).  None max = open ended.
TIER_TABLE: dict[Tier, tuple[int, Optional[int], float]] = {
    Tier.MICRO: (1, 1, 40.0),
    Tier.SHORT: (2, 3, 30.0),
    Tier.MEDIUM: (4, 6, 18.0),
    Tier.LONG: (7, 12, 8.0),
    Tier.SETPIECE: (13, None, 2.0),
}
TIER_ORDER = (Tier.MICRO, Tier.SHORT, Tier.MEDIUM, Tier.LONG, Tier.SETPIECE)

TAG_ESCALATE, TAG_DEFUSE, TAG_END, TAG_SILENCE, TAG_CUT_SHORT = (
    "escalate", "defuse", "end", "silence", "cut_short")


# --------------------------------------------------------------------------
# Shared types (guide 0.6)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ChatterEvent:
    """A visible/delivered text bubble."""
    speaker: str
    text: str
    delay: float = 0.0
    category: str = "conversation"
    tier: str = "near"                    # "near" | "distant" (UI renders smaller)
    payload: Optional[dict] = None


@dataclass
class Participant:
    """Snapshot of one sailor as seen by the conversation system."""
    name: str
    pos: tuple[float, float]              # metres, ship-local
    idle: bool = True
    task: str = "idle"
    level: Any = 0                        # participants must share a deck level
    available: bool = True                # aboard, awake, not swimming/ashore
    in_conversation: bool = False         # managed by the director
    speaking_until: float = -1e9          # overlap guard (set by other systems/ambient)
    tags: frozenset = frozenset()         # e.g. {"veteran"} for gate use

    def distance_to(self, other: "Participant") -> float:
        return math.hypot(self.pos[0] - other.pos[0], self.pos[1] - other.pos[1])


@dataclass
class ConversationContext:
    """World state the director consults.  Built fresh each tick by the caller."""
    now: float = 0.0
    hour: float = 12.0
    flooding: float = 0.0
    sea_state: float = 2.0
    task_load: float = 0.0                # 0 (nothing to do) .. 1 (everyone busy)
    critical: bool = False                # flooding spike, abandon-ship, MAYDAY ...
    flags: frozenset = frozenset()        # free-form context flags usable by gates
    # D7 hooks; the relationship matrix does not exist yet, so these are optional.
    trust: Optional[Callable[[str, str], float]] = None
    familiarity: Optional[Callable[[str, str], float]] = None
    grievance: Optional[Callable[[str, str], float]] = None

    @property
    def is_night(self) -> bool:
        h = self.hour % 24.0
        return h >= BALANCE["night_start_hour"] or h < BALANCE["night_end_hour"]

    @property
    def emergency(self) -> bool:
        return (self.flooding > BALANCE["flooding_emergency"]
                or self.sea_state >= BALANCE["sea_emergency"])


Gate = Callable[[ConversationContext], bool]


# --------------------------------------------------------------------------
# Script data model (A2)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Beat:
    """One narrative slot: candidate lines, optional speaker slot, gate, tag.

    ``speaker`` is a participant *slot* (0 = the conversation's initiator, 1 =
    the next participant, ...).  ``None`` means "whoever's turn it is".  A beat
    with no lines is a silence beat (a pause that is part of the rhythm).
    """
    lines: tuple[str, ...] = ()
    speaker: Optional[int] = None
    gate: Optional[Gate] = None
    weight: float = 1.0
    delay: tuple[float, float] = (2.2, 3.6)
    tag: Optional[str] = None

    @property
    def is_silence(self) -> bool:
        return not self.lines


@dataclass(frozen=True)
class BeatGroup:
    """Alternate beats occupying one narrative slot; ``pick`` of them are used."""
    options: tuple[Beat, ...]
    pick: int = 1


@dataclass(frozen=True)
class Script:
    id: str
    category: str
    tier: Tier
    beats: tuple                          # Beat | BeatGroup
    participants: tuple[int, int] = (2, 2)
    gate: Optional[Gate] = None
    priority: int = 0
    cooldown: float = 300.0
    interruptible: bool = True
    ends_on: Optional[str] = None
    weight: float = 1.0                   # relative pick weight within its tier


def silence(lo: float = 2.5, hi: float = 3.5) -> Beat:
    return Beat(lines=(), delay=(lo, hi), tag=TAG_SILENCE)


# --------------------------------------------------------------------------
# Runtime
# --------------------------------------------------------------------------
@dataclass
class ActiveConversation:
    script: Script
    participants: list[str]               # ordered by slot; [0] is the initiator
    beat_index: int = 0
    next_at: float = 0.0
    paused: bool = False
    paused_at: float = 0.0
    log: list[ChatterEvent] = field(default_factory=list)
    emitted_tags: set = field(default_factory=set)
    last_speaker: Optional[str] = None
    turn_counter: int = 0                 # non-silent beats delivered so far
    pending: list = field(default_factory=list)   # extra beats from a pick>1 group
    started_at: float = 0.0
    ended: bool = False
    end_reason: str = ""


class ConversationDirector:
    """Starts, advances, interrupts and ends scripted conversations."""

    def __init__(self, scripts: Sequence[Script], world_seed: int = 1962, start_delay_s: float = 0.0):
        self.scripts: dict[str, Script] = {s.id: s for s in scripts}
        self.world_seed = int(world_seed)
        self.rng = random.Random(stable_seed(self.world_seed, "conversations"))
        self.active: list[ActiveConversation] = []
        self.script_ready_at: dict[str, float] = {}
        self.setpiece_ready_at = -1e12
        self.next_start_at = float(start_delay_s)
        self.event_times: dict[str, float] = {}
        self._flood_was_high = False
        self.started_count = 0
        self.completed_count = 0
        self.aborted_count = 0
        self.end_reasons: dict[str, int] = {}

    # -- world events -------------------------------------------------------
    def note_event(self, kind: str, now: float) -> None:
        """Record a world event ("radio_assist", "catch", "flood_recovered", ...)."""
        self.event_times[str(kind)] = float(now)

    def event_age(self, kind: str, now: float) -> Optional[float]:
        t = self.event_times.get(kind)
        return None if t is None else max(0.0, now - t)

    def observe_flooding(self, flooding: float, now: float) -> None:
        """Detect the flooding-just-dropped-below-0.2 edge used by A1/A5."""
        threshold = BALANCE["flood_recovered_threshold"]
        if flooding >= BALANCE["flooding_emergency"]:
            self._flood_was_high = True
        elif flooding < threshold and self._flood_was_high:
            self._flood_was_high = False
            self.note_event("flood_recovered", now)

    def with_event_flags(self, ctx: ConversationContext) -> ConversationContext:
        """Return ``ctx`` with flags derived from recorded world events (used by gates)."""
        derived = set(ctx.flags)
        for kind, window, flag in (
                ("flood_recovered", BALANCE["flood_recovered_window_s"], "flood_recovered"),
                ("radio_assist", BALANCE["radio_assist_window_s"], "radio_assist"),
                ("catch", BALANCE["catch_window_s"], "catch_aboard")):
            age = self.event_age(kind, ctx.now)
            if age is not None and age <= window:
                derived.add(flag)
        if ctx.is_night:
            derived.add("night")
        return replace(ctx, flags=frozenset(derived))

    # -- queries ------------------------------------------------------------
    def has_active(self) -> bool:
        return bool(self.active)

    def is_in_conversation(self, name: str) -> bool:
        return any(name in c.participants for c in self.active)

    def conversation_of(self, name: str) -> Optional[ActiveConversation]:
        return next((c for c in self.active if name in c.participants), None)

    # -- A1: tier selection ---------------------------------------------------
    def tier_weights(self, ctx: ConversationContext,
                     group: Sequence[Participant] = ()) -> dict[Tier, float]:
        """Context-modified tier weights (A1), un-normalised."""
        weights = {t: TIER_TABLE[t][2] for t in TIER_ORDER}
        close_idle = (len(group) >= 2 and all(p.idle for p in group)
                      and all(a.distance_to(b) <= BALANCE["conversation_radius_m"]
                              for i, a in enumerate(group) for b in group[i + 1:]))
        if close_idle:
            for t in (Tier.SHORT, Tier.MEDIUM, Tier.LONG, Tier.SETPIECE):
                weights[t] *= BALANCE["idle_close_bonus"]
        if ctx.is_night and ctx.task_load <= BALANCE["low_task_load"]:
            weights[Tier.LONG] *= BALANCE["night_long_bonus"]
        if self._setpiece_trigger(ctx):
            weights[Tier.SETPIECE] *= BALANCE["setpiece_trigger_bonus"]
        if len(group) >= 2 and ctx.familiarity is not None and ctx.grievance is not None:
            fam = max(ctx.familiarity(a.name, b.name) for i, a in enumerate(group) for b in group[i + 1:])
            gri = max(ctx.grievance(a.name, b.name) for i, a in enumerate(group) for b in group[i + 1:])
            for t in (Tier.MEDIUM, Tier.LONG, Tier.SETPIECE):
                if fam > 0.6:
                    weights[t] *= BALANCE["familiar_bonus"]
                if gri > 0.4:
                    weights[t] *= BALANCE["grievance_penalty"]
        if ctx.emergency:                                  # people don't chat mid-emergency
            for t in (Tier.MEDIUM, Tier.LONG, Tier.SETPIECE):
                weights[t] = 0.0
        if ctx.now < self.setpiece_ready_at:               # global setpiece cooldown
            weights[Tier.SETPIECE] = 0.0
        return weights

    def _setpiece_trigger(self, ctx: ConversationContext) -> bool:
        now = ctx.now
        age = self.event_age("flood_recovered", now)
        if age is not None and age <= BALANCE["flood_recovered_window_s"]:
            return True
        age = self.event_age("radio_assist", now)
        if age is not None and age <= BALANCE["radio_assist_window_s"]:
            return True
        age = self.event_age("catch", now)
        return age is not None and age <= BALANCE["catch_window_s"]

    def roll_tier(self, ctx: ConversationContext,
                  group: Sequence[Participant] = ()) -> Optional[Tier]:
        weights = self.tier_weights(ctx, group)
        total = sum(weights.values())
        if total <= 0.0:
            return None
        pick = self.rng.random() * total
        for t in TIER_ORDER:
            pick -= weights[t]
            if pick < 0.0 and weights[t] > 0.0:
                return t
        return next(t for t in reversed(TIER_ORDER) if weights[t] > 0.0)

    # -- A3: starting -----------------------------------------------------------
    def _eligible_pool(self, people: Sequence[Participant], now: float) -> list[Participant]:
        return [p for p in people
                if p.available and p.idle and not p.in_conversation
                and not self.is_in_conversation(p.name) and p.speaking_until <= now]

    def _colocated_groups(self, pool: list[Participant], size: int) -> list[list[Participant]]:
        """All subsets of ``size`` whose members are pairwise within the radius."""
        radius = BALANCE["conversation_radius_m"]
        groups: list[list[Participant]] = []

        def extend(chosen: list[Participant], start: int) -> None:
            if len(chosen) == size:
                groups.append(list(chosen))
                return
            for i in range(start, len(pool)):
                cand = pool[i]
                if (cand.level == chosen[0].level if chosen else True) and all(
                        cand.distance_to(c) <= radius for c in chosen):
                    chosen.append(cand)
                    extend(chosen, i + 1)
                    chosen.pop()

        extend([], 0)
        return groups

    def _script_ok(self, script: Script, ctx: ConversationContext) -> bool:
        if ctx.now < self.script_ready_at.get(script.id, -1e12):
            return False
        if script.tier is Tier.SETPIECE and ctx.now < self.setpiece_ready_at:
            return False
        return script.gate is None or bool(script.gate(ctx))

    def try_start(self, people: Sequence[Participant], ctx: ConversationContext
                  ) -> Optional[ActiveConversation]:
        """Weighted tier roll, then a script and a co-located group for it."""
        now = ctx.now
        ctx = self.with_event_flags(ctx)
        if ctx.critical:                                   # nobody strikes up a chat mid-emergency
            return None
        if now < self.next_start_at:                       # the watch is mostly quiet
            return None
        pool = self._eligible_pool(people, now)
        if len(pool) < 2:
            return None
        tier = self.roll_tier(ctx, pool)
        if tier is None:
            return None
        candidates = [s for s in self.scripts.values()
                      if s.tier is tier and self._script_ok(s, ctx)]
        self.rng.shuffle(candidates)                       # order-independent given the seed
        candidates.sort(key=lambda s: -s.priority)         # stable: priority first
        # Try scripts in descending priority, weighted within equal priority.
        while candidates:
            top = candidates[0].priority
            band = [s for s in candidates if s.priority == top]
            script = self._weighted(band, [s.weight for s in band])
            candidates = [s for s in candidates if s is not script]
            for size in range(script.participants[1], script.participants[0] - 1, -1):
                groups = self._colocated_groups(pool, size)
                if not groups:
                    continue
                group = self.rng.choice(groups)
                return self._begin(script, group, ctx)
        return None

    def _weighted(self, items: Sequence[Any], weights: Sequence[float]) -> Any:
        total = sum(max(0.0, w) for w in weights)
        if total <= 0.0:
            return self.rng.choice(list(items))
        pick = self.rng.random() * total
        for item, w in zip(items, weights):
            pick -= max(0.0, w)
            if pick < 0.0:
                return item
        return items[-1]

    def _affinity(self, a: Participant, group: Sequence[Participant],
                  ctx: ConversationContext) -> float:
        """A4: trust and task overlap decide who opens (higher = more likely)."""
        others = [b for b in group if b is not a]
        trust = 0.0
        if ctx.trust is not None and others:
            trust = sum(ctx.trust(a.name, b.name) for b in others) / len(others)
        overlap = sum(1.0 for b in others if b.task == a.task and a.task != "idle")
        return trust + 0.25 * overlap

    def _begin(self, script: Script, group: list[Participant],
               ctx: ConversationContext) -> ActiveConversation:
        scored = [(self._affinity(p, group, ctx), self.rng.random(), p) for p in group]
        scored.sort(key=lambda t: (-t[0], t[1]))           # affinity first; rng only breaks ties
        initiator = scored[0][2]
        order = [initiator] + [p for p in group if p is not initiator]
        conv = ActiveConversation(
            script=script, participants=[p.name for p in order],
            next_at=ctx.now + BALANCE["first_beat_delay_s"], started_at=ctx.now)
        self.active.append(conv)
        self.started_count += 1
        return conv

    # -- A2: resolving beats ------------------------------------------------------
    def _expand(self, conv: ActiveConversation, ctx: ConversationContext) -> list[Beat]:
        """Resolve the slot at ``beat_index`` into 0..n concrete beats (groups may pick >1)."""
        slot = conv.script.beats[conv.beat_index]
        if isinstance(slot, Beat):
            # cut_short beats are reserved for aborts; they never play in normal sequence.
            return [slot] if (slot.tag != TAG_CUT_SHORT and (slot.gate is None or slot.gate(ctx))) else []
        options = [b for b in slot.options
                   if b.tag != TAG_CUT_SHORT and (b.gate is None or b.gate(ctx))]
        chosen: list[Beat] = []
        for _ in range(min(slot.pick, len(options))):
            beat = self._weighted(options, [b.weight for b in options])
            options = [b for b in options if b is not beat]
            chosen.append(beat)
        return chosen

    # -- A4: speakers ---------------------------------------------------------------
    def _pick_speaker(self, conv: ActiveConversation, beat: Beat, now: float,
                      by_name: dict[str, Participant]) -> Optional[str]:
        names = conv.participants
        n = len(names)

        def eligible(name: str) -> bool:
            p = by_name.get(name)
            return p is not None and p.available and p.speaking_until <= now

        if beat.speaker is not None and 0 <= beat.speaker < n:
            return names[beat.speaker] if eligible(names[beat.speaker]) else None
        # Odd/even alternation: advance from the previous speaker, skipping the ineligible.
        start = 0 if conv.last_speaker is None else (names.index(conv.last_speaker) + 1) % n
        for k in range(n):
            cand = names[(start + k) % n]
            if cand == conv.last_speaker and n > 1:
                continue                                    # never the same speaker twice running
            if eligible(cand):
                return cand
        return None

    # -- A3: tick -----------------------------------------------------------------------
    def update(self, people: Sequence[Participant], ctx: ConversationContext
               ) -> list[ChatterEvent]:
        """Advance every conversation, then (if idle) try to start one."""
        now = ctx.now
        self.observe_flooding(ctx.flooding, now)
        ctx = self.with_event_flags(ctx)
        by_name = {p.name: p for p in people}
        events: list[ChatterEvent] = []
        for conv in list(self.active):
            events.extend(self._tick(conv, by_name, ctx))
        self.active = [c for c in self.active if not c.ended]
        # Participants flagged for callers that want to read the flag off the snapshot.
        for p in people:
            p.in_conversation = self.is_in_conversation(p.name)
        if not self.active:
            self.try_start(people, ctx)
            for p in people:
                p.in_conversation = self.is_in_conversation(p.name)
        return events

    def _lost_participant(self, conv: ActiveConversation, by_name: dict[str, Participant]) -> bool:
        present = [by_name.get(n) for n in conv.participants]
        if any(p is None or not p.available for p in present):
            return True
        far = BALANCE["abandon_radius_m"]
        return any(a.distance_to(b) > far for i, a in enumerate(present) for b in present[i + 1:])

    def _tick(self, conv: ActiveConversation, by_name: dict[str, Participant],
              ctx: ConversationContext) -> list[ChatterEvent]:
        now = ctx.now
        script = conv.script
        if self._lost_participant(conv, by_name):
            self._end(conv, "participant_left", now)
            return []

        # (4) interruption: only for interruptible scripts.
        if script.interruptible and ctx.critical:
            if not conv.paused:
                conv.paused, conv.paused_at = True, now
                return []
            if now - conv.paused_at > BALANCE["resume_window_s"]:
                return self._abort(conv, by_name, ctx)
            return []                                        # (1) paused: only the clock runs
        if conv.paused:                                      # critical cleared inside the window
            conv.next_at += now - conv.paused_at
            conv.paused = False

        if now < conv.next_at:
            return []

        # (2) deliver one beat per tick: queued group extras first, else the next live slot.
        beat: Optional[Beat] = conv.pending.pop(0) if conv.pending else None
        while beat is None and conv.beat_index < len(script.beats):
            beats = self._expand(conv, ctx)
            conv.beat_index += 1                              # slots whose gates all fail are skipped
            if beats:
                beat, conv.pending = beats[0], beats[1:]
        out: list[ChatterEvent] = []
        if beat is not None:
            event, ended = self._deliver(conv, beat, by_name, ctx, now)
            if event is not None:
                out.append(event)
            conv.next_at = now + self.rng.uniform(*beat.delay)
            if ended:
                conv.pending = []
                conv.beat_index = len(script.beats)
        # (3) end: ran off the end of the script, or the ends_on tag has been emitted.
        if not conv.pending and (conv.beat_index >= len(script.beats)
                                 or (script.ends_on and script.ends_on in conv.emitted_tags)):
            self._end(conv, "complete", now)
        return out

    def _deliver(self, conv: ActiveConversation, beat: Beat, by_name: dict[str, Participant],
                 ctx: ConversationContext, now: float) -> tuple[Optional[ChatterEvent], bool]:
        if beat.tag:
            conv.emitted_tags.add(beat.tag)
        ends = bool(conv.script.ends_on and beat.tag == conv.script.ends_on)
        if beat.is_silence:
            return None, ends
        speaker = self._pick_speaker(conv, beat, now, by_name)
        if speaker is None:                                  # nobody can speak: drop the beat
            return None, ends
        text = self.rng.choice(beat.lines)
        event = ChatterEvent(speaker=speaker, text=text, delay=0.0,
                             category=conv.script.category, tier="near",
                             payload={"script": conv.script.id, "tier": conv.script.tier.value,
                                      "beat": conv.beat_index - 1, "tag": beat.tag})
        conv.log.append(event)
        conv.last_speaker = speaker
        conv.turn_counter += 1
        return event, ends

    def _abort(self, conv: ActiveConversation, by_name: dict[str, Participant],
               ctx: ConversationContext) -> list[ChatterEvent]:
        """A3 (4): resume window expired -> exactly one cut_short beat, then end."""
        out: list[ChatterEvent] = []
        cuts = []
        for slot in conv.script.beats:
            for beat in (slot.options if isinstance(slot, BeatGroup) else (slot,)):
                if beat.tag == TAG_CUT_SHORT and beat.lines:
                    cuts.append(beat)
        if cuts:
            beat = self.rng.choice(cuts)
            speaker = conv.last_speaker or conv.participants[0]
            p = by_name.get(speaker)
            if p is not None and p.available:
                out.append(ChatterEvent(
                    speaker=speaker, text=self.rng.choice(beat.lines), category=conv.script.category,
                    payload={"script": conv.script.id, "tier": conv.script.tier.value,
                             "tag": TAG_CUT_SHORT}))
                conv.log.append(out[-1])
        self._end(conv, "aborted", ctx.now)
        return out

    def _end(self, conv: ActiveConversation, reason: str, now: float) -> None:
        conv.ended, conv.end_reason = True, reason
        self.next_start_at = now + self.rng.uniform(BALANCE["gap_min_s"], BALANCE["gap_max_s"])
        self.script_ready_at[conv.script.id] = now + conv.script.cooldown
        if conv.script.tier is Tier.SETPIECE:
            self.setpiece_ready_at = now + BALANCE["setpiece_cooldown_s"]
        self.end_reasons[reason] = self.end_reasons.get(reason, 0) + 1
        if reason == "complete":
            self.completed_count += 1
        else:
            self.aborted_count += 1

    # -- persistence (cooldowns only; an in-flight conversation is not saved) --------------
    def snapshot(self) -> dict:
        return {"schema": SCHEMA_VERSION, "script_ready_at": dict(self.script_ready_at),
                "setpiece_ready_at": self.setpiece_ready_at, "next_start_at": self.next_start_at,
                "event_times": dict(self.event_times),
                "rng_state": _rng_state_to_json(self.rng.getstate())}

    def restore(self, data: dict) -> None:
        if int(data.get("schema", 0)) != SCHEMA_VERSION:
            raise ValueError("unsupported conversation snapshot schema")
        self.script_ready_at = {str(k): float(v) for k, v in data.get("script_ready_at", {}).items()}
        self.setpiece_ready_at = float(data.get("setpiece_ready_at", -1e12))
        self.next_start_at = float(data.get("next_start_at", 0.0))
        self.event_times = {str(k): float(v) for k, v in data.get("event_times", {}).items()}
        if "rng_state" in data:
            self.rng.setstate(_rng_state_from_json(data["rng_state"]))
        self.active = []


def _rng_state_to_json(state: tuple) -> list:
    version, internal, gauss = state
    return [version, list(internal), gauss]


def _rng_state_from_json(data: Sequence) -> tuple:
    return (int(data[0]), tuple(int(x) for x in data[1]), data[2])
