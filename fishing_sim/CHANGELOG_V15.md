# Fishing Simulator 12v15

## Added
- Modal per-fish direct-offer auction (Model A) with Sashimi Chef, Canner, Wholesaler lots, Harbour Trader floor offers, and occasional Collector offers.
- Auction controls: `1`–`4` sell to an offer, `K`/`Esc` keep a fish, `A` accept best offers for all remaining fish, arrows browse the catch.
- Auction pauses simulation and preserves the existing settlement path for fuel, ice, bait, gaffs, and wages. Kept fish remain in the hold and continue to be subject to quality decay.
- Muster temporarily suppresses automatic station reassignment so the captain and all post keepers physically leave their posts to report on deck.
- `R` issues a rescue order for the nearest swimmer even if nobody has visually spotted them yet.
- Swimmers no longer know the ship's location automatically: they scan with a forward view cone based on visibility, then swim toward the ship once they sight it.

## Verification
- Regression suite and Python syntax compilation run during packaging.
- A graphical playtest is still required to verify the auction modal and swimmer sighting behavior in the actual Pygame loop.
