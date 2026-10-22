# V9 — Random Incoming Broadcasts

- Added a dedicated ambient-broadcast timer to the `RadioSystem`.
- Added randomized coast-station, fishing-fleet, weather, harbour, market, gear-trouble, radio-check, and traffic messages.
- Incoming broadcast content responds to current fog, wind, storm, sea state, visibility, market index, and time of day.
- Broadcasts appear in the existing persistent radio bubble.
- Random broadcasts require an assigned operator physically manning the set. Unattended broadcasts are missed; no extra crew are dispatched to receive them.
- Outgoing F2/F3/F4 requests and replies take priority. Ambient traffic never starts tow logic or mutates navigation/station assignments.
- Added focused tests for timer behavior, staffed/unattended operation, priority handling, variety, weather context, and isolation from outgoing calls.
