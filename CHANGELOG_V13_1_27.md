# Fishing Simulator v13.1.27

## Crash fix
- Fixed cabin recovery crashing because `crew_quarters` is a coordinate tuple, not a `pygame.Rect`. The cabin check now uses the tuple's bounds.

## Movement and hauling
- Stalled sailors now retry pathfinding without dynamic crew blockers, helping them escape crowded passages while still respecting the ship's static walkable map.
- During hauling, the ship now navigates toward the position that aligns the hauler station with the moving line head, instead of steering its centre directly onto the underwater hook and remaining offset.

## HUD
- Removed the top-right line/depth profile from normal gameplay. It is now shown only with the F10 debug line-map view.
- Kept depth as a simple HUD readout beneath the ship telemetry.

## Verification
- Python syntax compilation and targeted regression tests passed.
- Full graphical playtesting was not available in this environment because Pygame is not installed.
