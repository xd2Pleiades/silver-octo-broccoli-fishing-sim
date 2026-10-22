"""Hand-authored Part A conversation scripts (guide A2, A5, Appendix 4).

Scripts are written, not generated: beat groups give variety inside a script.
Lines suit a 1962 Japanese longliner crew and never name a specific sailor, so
any pair can deliver them.  ``after_flood`` and ``mayday_setpiece`` follow the
guide's A5 worked examples.
"""
from __future__ import annotations

from fishing_sim.systems.conversations import (
    Beat, BeatGroup, Script, Tier, silence,
    TAG_END, TAG_CUT_SHORT,
)


def _b(*lines, speaker=None, gate=None, weight=1.0, delay=(2.2, 3.6), tag=None) -> Beat:
    return Beat(lines=tuple(lines), speaker=speaker, gate=gate, weight=weight, delay=delay, tag=tag)


def _cut() -> Beat:
    """Reserved abort beat: spoken once, by the last speaker, if a CRITICAL event ends the script."""
    return _b("Hold that thought—", "Hang on, something's wrong—", "Later. Listen—",
              tag=TAG_CUT_SHORT)


def _g(*beats: Beat) -> BeatGroup:
    return BeatGroup(options=tuple(beats), pick=1)


def _calm(ctx) -> bool:
    return ctx.sea_state < 4 and ctx.flooding < 0.1


def _night(ctx) -> bool:
    return "night" in ctx.flags


def _rough(ctx) -> bool:
    return ctx.sea_state >= 4 or ctx.flooding >= 0.1


# --- micro (1 turn) -------------------------------------------------------------
MICRO = (
    Script("micro_weather_glance", "weather", Tier.MICRO, participants=(2, 2), cooldown=120.0,
           beats=(_b("Glass is steady, at least.", "Sky's clearing to the west.",
                     "Swell's lengthening. Good sign."),)),
    Script("micro_tea", "banter", Tier.MICRO, participants=(2, 2), cooldown=150.0, gate=_calm,
           beats=(_b("Tea's still hot if you want it.", "Somebody's been at the sugar again.",
                     "Wish the galley kept the stove lit longer."),)),
    Script("micro_work_ack", "work", Tier.MICRO, participants=(2, 2), cooldown=90.0,
           beats=(_b("Aye, I've got it.", "Leave it. I'll finish.", "Mind the line there."),)),
    Script("micro_cold", "banter", Tier.MICRO, participants=(2, 2), cooldown=150.0, gate=_rough,
           beats=(_b("Cold gets into the bones out here.", "Spray's coming over again.",
                     "Hold on to something, that one's coming."),)),
)

# --- short (2-3 turns) ------------------------------------------------------------
SHORT = (
    Script("short_fish_talk", "banter", Tier.SHORT, participants=(2, 2), cooldown=240.0, gate=_calm,
           beats=(_b("Think the yellowfin are still down deep?"),
                  _g(_b("Deeper than we're setting, I'd say."),
                      _b("Birds will tell us. Keep an eye out."),
                      _b("Ask the sea. It never answers straight.")),
                  _b("Hm. We'll see.", delay=(1.6, 2.4), tag=TAG_END))),
    Script("short_home", "banter", Tier.SHORT, participants=(2, 2), cooldown=300.0, gate=_calm,
           beats=(_b("Wonder what the harbour's like tonight."),
                  _b("Same as ever. Wet and loud."))),
    Script("short_tools", "work", Tier.SHORT, participants=(2, 2), cooldown=200.0,
           beats=(_b("Hand me that gaff, would you?"),
                  _b("Here. Careful, the handle's slick."),
                  _b("Thanks.", delay=(1.4, 2.0)))),
    Script("short_rough_check", "weather", Tier.SHORT, participants=(2, 2), cooldown=240.0, gate=_rough,
           beats=(_b("She's working hard in this."),
                  _b("She's seen worse. We have too.", tag=TAG_END))),
)

# --- medium (4-6 turns) ---------------------------------------------------------------
MEDIUM = (
    Script("medium_working_the_line", "work", Tier.MEDIUM, participants=(2, 2), cooldown=420.0, gate=_calm,
           beats=(_b("Snood's tangled again. Hold the line steady."),
                  _b("Steady. Go ahead."),
                  _g(_b("There. That one's been trouble all trip."),
                      _b("Salt gets in everything. Even the knots.")),
                  _b("Coil it clean this time, so we don't do this twice."),
                  _b("Aye. Clean as a new rope.", tag=TAG_END), _cut())),
    Script("medium_old_hand", "stories", Tier.MEDIUM, participants=(2, 2), cooldown=600.0, gate=_calm,
           beats=(_b("My father fished these waters before the war."),
                  _b("Did he say where the good ground was?"),
                  _g(_b("He said you don't ask. You watch the birds and you wait."),
                      _b("He said the sea keeps its own accounts.")),
                  _b("Sounds like every old fisherman I've known."),
                  _b("Probably the same man, then.", tag=TAG_END), _cut())),
    Script("medium_family", "personal", Tier.MEDIUM, participants=(2, 2), cooldown=720.0, gate=_calm,
           beats=(_b("Do you write home when we make port?"),
                  _g(_b("Every time. My wife keeps the letters in a tin."),
                      _b("Not enough. I mean to do better.")),
                  _b("The post is slow, but it's something."),
                  _b("It's what keeps a man steady, I think."),
                  _b("Aye.", delay=(1.5, 2.2), tag=TAG_END), _cut())),
    Script("medium_rough_work", "work", Tier.MEDIUM, participants=(2, 3), cooldown=480.0, gate=_rough,
           interruptible=True,
           beats=(_b("Lash that bucket down before it goes over."),
                  _b("Got it. Watch your feet on the wet."),
                  _g(_b("Deck's like glass."), _b("I can barely feel my hands.")),
                  _b("Two more minutes, then we take the rail in turns."),
                  _b("Aye.", tag=TAG_END), _cut())),
)

# --- long (7-12 turns) ------------------------------------------------------------------
AFTER_FLOOD = Script(
    "after_flood", "after_flood", Tier.LONG, participants=(2, 2), cooldown=600.0,
    gate=lambda c: "flood_recovered" in c.flags and c.flooding < 0.2, priority=10,
    beats=(
        _b("That was closer than I like.", tag="open"),
        _g(_b("Close enough to taste it."),
           _b("She came back. Boats do, sometimes."),
           _b("I've seen worse. Once.")),
        _b("You had the pump going before I even got my boots on."),
        _g(_b("Instinct. Nothing clever about it."),
           _b("Somebody had to.")),
        silence(2.5, 3.5),
        _b("Water's still in the fish room sole."),
        _b("We'll pump it dry before we shoot gear. Or we won't."),
        _g(_b("We will."), _b("Not tonight we won't.")),
        _b("Get some sleep. I'll take the next watch.", tag="close"),
        _cut(),
    ),
)

LONG = (
    AFTER_FLOOD,
    Script("long_night_watch", "night_watch", Tier.LONG, participants=(2, 2), cooldown=900.0,
           gate=lambda c: "night" in c.flags and c.sea_state < 4, priority=5,
           beats=(_b("Quiet tonight. Almost too quiet.", tag="open"),
                  _b("I like it. Gives a man time to think."),
                  _b("About what?"),
                  _g(_b("Home, mostly. The kids will have grown by the time we dock."),
                     _b("Nothing worth saying. That's the point of the night watch.")),
                  silence(2.8, 3.8),
                  _b("The stars are sharp out here."),
                  _b("My grandfather steered by them. No compass, no radio."),
                  _b("I'd like to see him try it in this fog bank we had on Tuesday."),
                  _b("He'd have just kept going and hoped. They all did."),
                  _b("Get some tea in you. It's a long way till morning.", tag="close"), _cut())),
    Script("long_post_haul", "post_haul", Tier.LONG, participants=(2, 3), cooldown=900.0,
           gate=lambda c: "catch_aboard" in c.flags and c.sea_state < 5,
           beats=(_b("That's a fair haul for one set.", tag="open"),
                  _g(_b("Better than the last three put together."),
                     _b("Better than I feared, anyway.")),
                  _b("The ice will have to stretch."),
                  _b("It'll stretch. It always does, until it doesn't."),
                  silence(2.2, 3.0),
                  _g(_b("The buyers will fight over the big ones."),
                     _b("If the price holds, the whole crew eats well this month.")),
                  _b("Don't say it aloud. You'll jinx the market."),
                  _b("Fair. Not a word more.", tag="close"), _cut())),
)

# --- setpiece (13+ turns) --------------------------------------------------------------------
MAYDAY_SETPIECE = Script(
    "mayday_setpiece", "mayday_setpiece", Tier.SETPIECE, participants=(2, 3), cooldown=1200.0,
    gate=lambda c: "radio_assist" in c.flags and c.sea_state < 4 and c.flooding < 0.1,
    interruptible=False, priority=20,
    beats=(
        _b("They're safe. All of them.", tag="open", delay=(2.8, 3.6)),
        _b("Every hand accounted for. I counted twice."),
        silence(3.0, 4.0),
        _b("I didn't think we'd reach them in time."),
        _g(_b("Neither did I. I just kept the throttle open."),
           _b("The sea gave us that one.")),
        _b("Did you see the boat? Half under at the stern."),
        _b("I saw it. I'll see it for a long time."),
        silence(3.0, 4.0),
        _b("They'll talk about this one in the harbour."),
        _g(_b("Let them. I'd rather they talked than wept."),
           _b("They'll get it wrong. They always do.")),
        _b("What would you have done, if we'd been too late?"),
        _b("Turned back for home and said nothing for a week."),
        _b("You'd have blamed yourself anyway."),
        silence(2.5, 3.5),
        _b("Well, we weren't too late."),
        _b("No. We weren't.", tag="close"),
    ),
)

SETPIECE = (MAYDAY_SETPIECE,
            Script("big_catch_setpiece", "setpiece", Tier.SETPIECE, participants=(2, 3), cooldown=1200.0,
                   gate=lambda c: "catch_aboard" in c.flags and c.sea_state < 4 and c.flooding < 0.1,
                   interruptible=True, priority=5,
                   beats=(_b("Did you see the size of that one?", tag="open"),
                          _b("I did. My arms still ache."),
                          _b("Forty kilos if it's an ounce."),
                          _b("Fifty. Tell the buyers fifty."),
                          silence(2.0, 3.0),
                          _b("The captain's smiling. That doesn't happen often."),
                          _b("It happens when the hold's heavy."),
                          _b("My father never landed a fish like that."),
                          _b("Your father fished from a rowboat."),
                          _b("A rowboat with a lot of nerve."),
                          _b("Mark the position. The captain will want it."),
                          _g(_b("Remember this one. We won't see many."),
                             _b("We'll tell it better than it happened.")),
                          _b("Of course we will."),
                          _b("Come on. Let's get it stowed before it spoils.", tag="close"), _cut())),)

ALL_SCRIPTS = MICRO + SHORT + MEDIUM + LONG + SETPIECE
