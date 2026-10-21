"""Run with: python -m fishing_sim"""
from fishing_sim.diagnostics import install_diagnostics

install_diagnostics()

from fishing_sim.core.game import Game  # noqa: E402


if __name__ == "__main__":
    Game().run()
