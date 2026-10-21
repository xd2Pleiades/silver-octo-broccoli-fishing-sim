# Fishing Simulator v13.1.29 — Controls Reference

This is a Markdown document. **Open it in a text editor or Markdown viewer; do not run it with Python.** The same reference is available in-game from **F1 → CONTROLS**.

## Mouse and basic interface

| Input | Action |
|---|---|
| Left-click a visible sailor | Select that sailor. |
| Right-click a deck/room location | Order the selected sailor to move there. Right-clicking a person, hatch, roller, buoy, or other supported object may open its context menu instead. |
| Right-click open water from the main-deck view | Issue a quick steer-to order for the ship. This is not a guaranteed exact path. |
| Shift + right-drag from A to B over open water | Plot a quick ocean leg when daylight and visibility permit. The track is a desired course, not rails. |
| Mouse wheel in the world view | Zoom in or out. |
| Mouse wheel while a sheet/notebook is open | Scroll the current page or list. |
| `TAB` | Select the next available crew member. |

## Ship handling and navigation

| Key / input | Action |
|---|---|
| Arrow keys | Manual helm/engine telegraph, **only when the captain or relief helmsman is properly on watch at the helm**. Left/right steer; up increases ahead power; down reduces power and can request astern after slowing. |
| Hold `SPACE` | Stop the ship, cancel a destination, and apply the brake. It also serves the manual gaff/brake input while the fishing fight calls for it. |
| `A` or click **ANCHOR** beside the cash HUD | Drop/weigh anchor. Dropping cancels the current travel order and greatly reduces drift; weigh it before manoeuvring again. |
| `C` | Open/close the navigation chart. |
| Chart left-click in open water | Add a waypoint. Click an existing waypoint, then click its new position to move it. |
| `SHIFT` + chart left-click on a route leg | Insert a waypoint into that leg. |
| Chart right-click on a waypoint | Delete that waypoint. Right-click elsewhere closes the chart. |
| `ENTER` while the chart is open | Commit the staged route. |
| `ESC` while the chart is open | Clear/cancel the staged course. |
| `1` / `2` / `3` / `4` on the chart | Attempt landmark / sextant / RDF / sounder navigation fix, respectively. |
| `D` | Toggle automatic docking. |
| `N` | Set navigation to dead reckoning. |
| `T` | Cycle simulation speed through 1×, 3×, and 6×. |
| `,` / `.` | Reduce / increase the sea-state setting manually. This disables the automatically varying sea state. |
| `Q` / `E` | Climb up/down at a ladder; away from a ladder, peek between deck levels. |

**Navigation note:** A plotted line expresses the intended track. Rudder lag, momentum, engine reversal delay, current, wind, waves, and the helmsman's skill can make the ship deviate from it.

## Fishing and deck equipment

| Key | Action |
|---|---|
| `L` | Toggle automatic longline fishing. A manually plotted chart course can be cleared when auto-fishing takes priority. |
| `P` | Begin one manual longline set. |
| `J` | Request an immediate haul. |
| `M` | Operate/bypass the stern roller. If the line or buoy snags, send a deckhand aft to clear it. |
| `[` / `]` | Decrease / increase line slack by 0.05. |
| Hold `X` / `Z` during a fish fight | Tighten / ease the manual fishing brake. Avoid too much slack or tension. |
| `K` | Cycle the selected bait type. |
| `Y` | Toggle the safety harness for work near the rail. |
| `U` | Toggle the nearby hatch (the crew may need to physically reach it). |
| `F` | Start a seawater hose wash of the cutting table/deck. |
| `V` | Trim/rearrange ice in the hold. |

## Crew orders and safety

Select an onboard sailor first to assign a duty:

| Key | Duty / action |
|---|---|
| `1` | Longline setting |
| `2` | Hauling |
| `3` | Cleaning fish |
| `4` | Rest |
| `5` | Dressing fish |
| `6` | Engine watch |
| `7` | Helm watch |
| `0` | Clear the selected sailor's assigned duty |
| `H` | Begin a crew muster. |
| `R` | Order rescue for a crew member currently in the water. |
| `I` | Request a bearing-and-range report from the selected crew member. |
| `O` | Request a speed report from the selected crew member. |
| Click the same crew member again shortly after a report request | Request a second opinion when available. |

Crew cannot take the helm by pressing arrow keys alone; assign helm duty and make sure the helmsman reaches the helm station.

## Radio, port, and weather

| Key | Action |
|---|---|
| `F2` | Request a weather report by radio. |
| `F3` | Request a market/auction report by radio. |
| `F4` | Request a tow by radio. Repeated attempts may be necessary when signal clarity or range is poor. If fuel runs out offshore, the vessel automatically keeps transmitting until a tow answers. |
| `W` | Cycle the weather conditions. |
| `B` | Open settlement/auction when alongside at the quay. |
| Auction `1`–`4` | Sell the currently selected fish at the offered grade/price option. |
| Auction `K` | Keep the current fish. |
| Auction `A` | Accept the sale of all remaining fish. |

## Display, reports, and windows

| Key | Action |
|---|---|
| `F1` | Open the vessel information sheet. Use its tabs for **Ship & Catch**, **Telemetry**, **Crew**, and **Controls**. `TAB` or left/right switches tabs; up/down or the mouse wheel scrolls. `F1` or `ESC` closes the sheet. |
| `F5` | Show/hide the compact on-screen controls strip. |
| `F6` | Show/hide the fishing fight/tension meter. |
| `F7` | Switch the compact HUD between navigation and operations summaries. |
| `F8` | Show/hide the compact telemetry HUD. |
| `F9` | Open the Ship's Notebook. In the notebook, `1`–`5` selects a section, `TAB` advances sections, left/right (or comma/period) turns pages, `HOME` returns to the first page, and `F9`/`ESC` closes it. |
| `F10` | Toggle the debug longline profile/map. It is for debugging, not the normal HUD. |
| `F11` | Toggle fullscreen. |
| `ESC` | Close/cancel supported menus and route actions; its exact action depends on the active window. |

## Quick-start recommendation

1. Select the captain or a qualified relief sailor and assign **`7` — helm watch**. Right-click the wheelhouse/helm station if they need a movement order.
2. Press `C` to plan a route; add waypoints with left-click and press `ENTER` to commit it. Remember that the line is only the desired track.
3. Use `L` for automatic longline fishing, `P` for a manual set, and `J` to request a haul.
4. Keep an eye on fuel, bilge/flooding, crew fatigue, radio signal, and weather. Use `F4` for a tow request if needed. At zero fuel, automatic radio retries continue until an answer arrives; a successful tow moves the vessel gradually to the berth rather than teleporting it.
5. Use `A` or the **ANCHOR** button beside the cash HUD to stop unwanted drift. The anchor cancels the plotted/quick travel order; weigh anchor before sailing again.

*Controls are fixed in this release; there is no key-remapping menu.*
