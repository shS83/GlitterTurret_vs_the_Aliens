"""
Launcher script to run the glittery turret shooter.

This file intentionally delegates to aliens.py to avoid the legacy
pinball code that previously lived here and caused syntax/runtime errors.
"""

from aliens import main as run_aliens

if __name_ _ == "__main__":
    run_aliens()
