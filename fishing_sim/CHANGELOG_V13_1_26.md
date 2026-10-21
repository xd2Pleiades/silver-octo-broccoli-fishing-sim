# Fishing Simulator v13.1.26

## HUD and navigation
- Removed the longline minimap from normal gameplay; an optional developer-only longline overview is available with **F10**.
- Added a compact heading compass and wind-direction pennant to the HUD. The depth profile remains a separate water-column panel.

## Crew health
- Sailors can slowly recover while resting in the below-deck crew cabin, capped at 60% health during a fishing trip. Harbour recovery remains necessary for full treatment.

## Distress radio and foundering
- Tow calls now factor in estimated radio clarity, range, and weather interference. Failed calls schedule another transmission rather than ending the request after one static-filled attempt.
- Severe, sustained flooding can trigger an abandon-ship emergency. The ship stops and the crew enter the existing swimmer/recovery system instead of the whole crew being teleported to harbour.

## Notes
- This is a code-verified patch; graphical playtesting was unavailable because Pygame is not installed in the build environment.
