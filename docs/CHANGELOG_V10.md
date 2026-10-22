# V10 changelog

## Dock and shore management
- Settled docking now sends crew ashore for abstracted town leave and recovery. Health, fatigue, and morale recover faster while ashore.
- Added an F1 full-window Crew & Shore Sheet with Aboard, Shore, and Hire tabs, mouse action buttons, and scroll support.
- Deckhands can be kept ashore or brought back aboard. Captain and veteran are auto-recalled when the vessel leaves the quay, preventing the ship from being stranded without its command pair.
- Added a randomized hiring board; new sailors can be hired directly aboard or hired but retained ashore. Recruitment fees are checked against ship cash.
- Shore leave is represented in headcount and does not accrue onboard wages while the sailor is ashore.

## Wheelhouse exit recovery
- A station owner's exit request first hands over helm duty or releases radio duty.
- Wheelhouse exits retry the ladder route if movement is stalled; after a second blockage the sailor is moved only to the wheelhouse's own ladder landing and starts the ladder animation, never teleported to the engine room.
- Removed fallback promotion of arbitrary deckhands to relief helmsman; only the designated veteran can relieve the captain.

## Packaging
- Added root-level `run_fishing_sim.py` launcher.
- Added `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md` with the requested exact reminder.
- Updated run instructions for the extracted ZIP layout.
