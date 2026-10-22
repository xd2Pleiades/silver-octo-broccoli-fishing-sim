# Fishing Simulator 12v14 — Sea Rescue & Catch Quality

## Man-overboard recovery

- A witnessed man-overboard event triggers an explicit ALL STOP response: destination/docking are cancelled, propulsion is commanded to zero, and the ship decelerates before rescue operations continue.
- Casualties inside 190 units of the hull are handled by the existing davit-lifeline system.
- At sea state 0.75 or higher, the crew do not launch a boat for distant casualties; after stopping, the ship turns back and approaches at dead slow until a lifeline can reach.
- In lower seas, two available crew pathfind to the davit, wait for the ship to stop, lower the rescue boat, paddle toward the swimmer, pick them up, and return to the ship.
- A squall during assembly/launch cancels launch. If the sea becomes too rough after the boat has departed, an empty boat returns and the ship-turn/lifeline strategy takes over.
- The casualty enters a distinct rescue-boat state while aboard the launch; crew return to the deck only when the launch returns. Drowning and cancelled-rescue paths clean up their task state. The vessel does not automatically resume its previous course after a rescue.

## Catch quality and cold hold report

- The hold display now shows average catch quality, average grade, hold temperature, and whether fish are cold/chilling/warming.
- Dock settlement emits a compact trip report before selling the catch, including per-fish handling state, quality/grade, core temperature, and deck exposure (up to four individual fish plus a count/grade summary for the remainder).
- The existing catch-quality decay, ice consumption, storage-temperature model, and settlement economy remain in use.

## Preserved systems

- Preserves 12v11 deck/fishing/engine/headcount work, 12v12 shore-leave/hiring, 12v13 fishing UI, SPACE controls, bucket line and engine-room flooding, plus the 12v13.1 slipping-overboard crash fix.
- Preserves `run_fishing_sim.py` and `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`.

## Verification and known limitations

- Automated regression suite: 59 tests passed.
- Python compilation passed.
- Graphical Pygame playtesting was not possible in the build environment. The sea-rescue visual path, navigation to davit, storm threshold behavior, and actual in-game feel still require manual playtesting.
- Auction UI remains deferred to 12v15.
