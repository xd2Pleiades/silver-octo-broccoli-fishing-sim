# Fishing Simulator V8 — Changelog

## Focus: exclusive station ownership and proper handover

- The captain is the default, sole helm owner. Deckhands do not auto-promote to the helm when the captain leaves it.
- When the captain takes a rest duty or reaches the fatigue threshold, the named veteran is assigned as relief helmsman. The captain rests on the main deck. When the captain is fit again, helm control returns to him.
- Fixed a handover leak where a veteran who had been relieved could remain idle in the wheelhouse and crowd the captain on return. Any relieved non-radio helmsman in the wheelhouse is ordered back to the main deck.
- Right-clicking the radio station assigns one deckhand as a persistent wireless operator. Other crew cannot take his station through routine AI; reassign or explicitly release the radio watch to change ownership.
- F2 weather, F3 market, and F4 tow requests use the assigned radio operator, dispatch a suitable deckhand if necessary, and wait for him to reach the set.
- Radio traffic appears in a persistent screen-space bubble instead of depending on which sailor/deck is currently visible.
- Retained the V7 ladder transition and bounded docking-retry fixes.

## Validation

- 11 source-contract tests pass.
- Python compilation passes for all packaged `.py` files.
- Pygame is not installed in the build environment; real graphical gameplay and voyage-level integration still require local testing.
