"""Engine-room compatibility surface; diesel simulation lives in Game for now."""
from fishing_sim.core.game import Game

def engine_status(game):
    """Return the vessel's existing engine status string."""
    return game.engine_status()
