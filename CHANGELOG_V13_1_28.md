# Fishing Simulator v13.1.28

## Controls reference

- Added a dedicated **CONTROLS** tab to the F1 vessel information sheet.
- Documented keyboard shortcuts, mouse gestures, chart editing, navigation, crew duties, fishing equipment, radio, HUD, and modal-window controls.
- Controls descriptions wrap in the tab and can be scrolled, including on narrower windows.
- Added `CONTROLS.md` at the project root and inside the `fishing_sim` package.
- Updated the runtime diagnostic version label to v13.1.28.

## Previous v13.1.27 fixes retained

- Fixed the cabin recovery crash where `crew_quarters` was treated as a rectangle despite being stored as a coordinate tuple.
- Retained the hauling alignment and sailor path retry improvements.
- Retained the F10-only longline debug profile and normal depth HUD.
