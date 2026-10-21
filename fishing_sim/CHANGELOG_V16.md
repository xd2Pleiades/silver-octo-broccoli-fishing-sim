# 12v16 — Compact Telemetry and Ship & Catch Tabs

## Changes
- Combined the previous separate telemetry and ship/catch cards into one compact, edge-aligned tabbed panel.
- Added TELEMETRY and SHIP & CATCH tabs with click-to-select and F7 keyboard switching.
- Added F8 hide/restore; the collapsed tag remains small and keyboard controls continue to work.
- Capped panel width at 252 px, used a 14 px monospace font, clipped rows to the card, truncated long text, and bounded the displayed rows to keep the layout predictable.
- Retained the key at-a-glance telemetry and moved hold quality/value, ice/temperature, deck wetness, engine-room bilge, fuel, gaffs, bait, engine condition and line slack into SHIP & CATCH.
- Kept muster and man-overboard state visible in the Telemetry tab. HUD clicks are consumed by the UI so they cannot accidentally issue world actions behind it.
- Preserved the 12v15 auction, mandatory muster, swimmer visibility, 12v14 rescue/catch quality, 12v13.1 bucket line, launcher, and preservation marker.

## Verification
- 68 automated tests passed.
- Python syntax compilation passed.
- Graphical playtest not performed in the build environment; check readability and overlap at both small and large window sizes.
