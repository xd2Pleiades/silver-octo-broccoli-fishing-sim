# Chapter A — Conversations (Sailor Systems Design Guide v3.2, Part A)

## Delivered

- `fishing_sim/systems/conversations.py` — Pygame-free engine: length tiers (A1), script/beat/beat-group data model (A2), runtime state machine with pause / resume window / abort-with-one-cut-short (A3), affinity-first speaker then alternation, silence beats and overlap guard (A4), seeded RNG and JSON snapshot of cooldowns (guide §0.3).
- `fishing_sim/systems/conversation_scripts.py` — 17 hand-written scripts across all five tiers, including the guide's `after_flood` and `mayday_setpiece` worked examples.
- `Game` integration (A6): `_update_crew_conversations()` runs each frame from `_queue_ambient_crew_conversation()`. While a conversation is active the ambient deck-chatter exchange is skipped; otherwise ambient chatter is the fallback. Lines are delivered through `crew.say("Name: text")`.
- World events feed the setpiece weights: `catch` (`Crew.add_catch`), `radio_assist` (player rescue completion), `flood_recovered` (detected from flooding falling below 0.2 after a spike).
- `Sailor.conversation_hold`: idle participants stand still instead of wandering off (needed so scripts finish; see Boundaries).
- Tests: `fishing_sim/tests/test_chapter_a_conversations.py` — all nine A7 assertions plus cooldown, gating, pacing, determinism, frame-rate independence, persistence, script-data validity, and eight Game-level integration tests (skipped without Pygame).

## Boundaries (not part of Chapter A, or deliberately deferred)

- **Participants who are not already within 3 m never start a conversation.** The B8 *gather* behaviour that walks two idle sailors together does not exist yet.
- **Facing the speaker (B5)** and the full motion layer are Part B. `conversation_hold` is only a stand-still flag on the existing idle task.
- **Hearing-based interruption (D8.2)** does not exist yet. CRITICAL is a single flag: flooding >= 0.5, man overboard, or a critical broadcast.
- **Relationship matrix (D7)** does not exist. `ConversationContext` accepts optional trust / familiarity / grievance callables; the game passes none, so affinity falls back to task overlap and a seeded tie-break.
- **Persistence:** `snapshot()` / `restore()` exist and are tested but are not yet wired into the career save. After a load, cooldowns start fresh and an in-flight conversation is not resumed.
- **Balance profile:** the repo has no profile loader. Tunables live in the `BALANCE` dict at the top of `conversations.py`.
- **Ambient suppression is crew-wide**, not per participant: while any conversation runs, the ambient deck-chatter exchange is skipped for everyone.
- Conversation lines are written to the dated career log via `crew.say`, like other crew speech.
- Sea state: `World.sea_state` (0..1) is mapped to a 0..9 scale for the A1 "sea state 5" threshold.
- Deck scale: 75 px per metre (`Game.DECK_PX_PER_METRE`), inferred from the 12 x 2.2 px body radius against the guide's 0.35 m personal space. Worth confirming.
