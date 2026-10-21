"""Timed, attributed broadcast conversations for the 1962 fishing simulation.

The director is intentionally UI-agnostic.  The game decides when a channel is
ready and how a line is displayed; this module owns ordering, pacing, and priority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

PRIORITY_LOW = 1
PRIORITY_MEDIUM = 2
PRIORITY_HIGH = 3
PRIORITY_CRITICAL = 4

CHANNEL_RADIO = "radio"
CHANNEL_CREW = "crew"
CHANNEL_INTERCOM = "intercom"
CHANNEL_HARBOUR = "harbour"


@dataclass(frozen=True)
class BroadcastTurn:
    """One spoken line. ``delay`` is the wait before this line after its predecessor."""
    delay: float
    speaker: str
    text: str
    channel: str = CHANNEL_RADIO


@dataclass
class BroadcastConversation:
    turns: tuple[BroadcastTurn, ...]
    priority: int
    source: str = "broadcast"
    sequence: int = 0
    index: int = 0
    timer: float = 0.0

    @property
    def current_turn(self) -> Optional[BroadcastTurn]:
        if 0 <= self.index < len(self.turns):
            return self.turns[self.index]
        return None


class BroadcastDirector:
    """Single-conversation director with priority interruptions and FIFO ties."""

    def __init__(self):
        self.active: Optional[BroadcastConversation] = None
        self.pending: list[BroadcastConversation] = []
        self._sequence = 0
        self.interrupted_count = 0
        self.completed_count = 0
        self.emitted_count = 0

    @staticmethod
    def _normalise_turns(lines: Iterable, default_channel: str) -> tuple[BroadcastTurn, ...]:
        turns = []
        for item in lines:
            if isinstance(item, BroadcastTurn):
                turn = item
            else:
                values = tuple(item)
                if len(values) == 3:
                    delay, speaker, text = values
                    channel = default_channel
                elif len(values) == 4:
                    delay, speaker, text, channel = values
                else:
                    raise ValueError("broadcast turns require (delay, speaker, text[, channel])")
                turn = BroadcastTurn(max(0.0, float(delay)), str(speaker).strip(),
                                     str(text).strip(), str(channel or default_channel).lower())
            # Empty lines are not emitted. Silence is represented by the next turn's delay.
            if turn.speaker and turn.text:
                turns.append(BroadcastTurn(max(0.0, float(turn.delay)), turn.speaker,
                                           turn.text, turn.channel.lower()))
        if turns and turns[0].delay != 0:
            turns[0] = BroadcastTurn(0.0, turns[0].speaker, turns[0].text, turns[0].channel)
        return tuple(turns)

    def enqueue(self, lines: Iterable, priority: int = PRIORITY_LOW,
                channel: str = CHANNEL_RADIO, source: str = "broadcast") -> bool:
        """Queue a conversation. Return True if it interrupted the active conversation."""
        turns = self._normalise_turns(lines, channel)
        if not turns:
            return False
        self._sequence += 1
        conversation = BroadcastConversation(turns, int(priority), str(source),
                                             self._sequence, 0, turns[0].delay)
        interrupted = bool(self.active and conversation.priority > self.active.priority)
        if interrupted:
            self.active = None
            self.interrupted_count += 1
        self.pending.append(conversation)
        self.pending.sort(key=lambda item: (-item.priority, item.sequence))
        return interrupted

    def interrupt_below(self, priority: int) -> bool:
        """Discard the active lower-priority exchange; queued exchanges retain FIFO priority."""
        if self.active is not None and self.active.priority < int(priority):
            self.active = None
            self.interrupted_count += 1
            return True
        return False

    def discard_pending_below(self, priority: int) -> int:
        """Drop queued low-priority ambient traffic when the player requests a call."""
        priority = int(priority)
        old_len = len(self.pending)
        self.pending = [conversation for conversation in self.pending if conversation.priority >= priority]
        return old_len - len(self.pending)

    @property
    def active_priority(self) -> int:
        return self.active.priority if self.active is not None else 0

    def has_channel(self, channel: str, *, include_pending: bool = True) -> bool:
        channel = str(channel).lower()
        if self.active is not None and any(turn.channel == channel for turn in self.active.turns[self.active.index:]):
            return True
        if include_pending:
            return any(any(turn.channel == channel for turn in conv.turns) for conv in self.pending)
        return False

    def is_busy(self) -> bool:
        return self.active is not None or bool(self.pending)

    def update(self, dt: float, can_emit: Callable[[str, int], bool],
               emit: Callable[[BroadcastConversation, BroadcastTurn], None]) -> Optional[BroadcastTurn]:
        """Advance the active conversation and emit at most one ready line per call."""
        dt = max(0.0, float(dt))
        if self.active is None:
            if not self.pending:
                return None
            self.active = self.pending.pop(0)
        conversation = self.active
        conversation.timer = max(0.0, conversation.timer - dt)
        if conversation.timer > 0.0:
            return None
        turn = conversation.current_turn
        if turn is None:
            self.active = None
            self.completed_count += 1
            return None
        if not can_emit(turn.channel, conversation.priority):
            return None
        emit(conversation, turn)
        self.emitted_count += 1
        conversation.index += 1
        if conversation.index >= len(conversation.turns):
            self.active = None
            self.completed_count += 1
        else:
            conversation.timer = conversation.turns[conversation.index].delay
        return turn
