# Fishing Simulator 13.1.21 — Full-Length Lower Deck Refit

This release revises the below-deck layout so the lower deck uses almost the entire hull: aft stores, ice hold, engine room, and a forward crew cabin are connected by one continuous centre passage. Six sailor-sized berths sit in the forward cabin. A sleeping sailor is drawn lying on the mattress and is exempt from bed and crew collision response until woken by a task.

It also fixes a navigation failure mode where a failed A* query caused a sailor to steer directly at the destination through blocking geometry. Unreachable routes now stop/retry instead of pinning crew against the engine casing or bunks.

Read `../CHANGELOG_V13_1_21.md`, `../docs/V13_1_21_LOWER_DECK.md`, and `../Roadmap_V2.md`. Run `python -m compileall -q fishing_sim run_fishing_sim.py` and `python -m unittest discover -s fishing_sim/tests` from the project directory.

The code and headless tests can be verified in this environment, but a graphical Pygame playtest is still required to judge actual bunks/corridor scale and watch crew travel between every station.
