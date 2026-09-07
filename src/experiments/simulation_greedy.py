"""
simulation_greedy.py — "Nearest" baseline (single-station search).

NEAREST version (historical name: `greedy`):
- the vehicle contacts ONLY the nearest station
- it accepts the offer received (a single offer, so no useful comparison)
- no reputation score, no collective learning between stations

This is the first rung of the ablation ladder
(`src/experiments/methods.py`): every later rung adds exactly one component to
it.

This class is now only a convenience shortcut: the pipeline instantiates
`Simulation(mode=...)` directly for every method, this one included. Keeping it
leaves the historical calling code valid.
"""

import src.experiments.config as cfg
from src.experiments.simulation import Simulation


class SimulationGreedy(Simulation):

    def __init__(self, cars, stations, societies, t_max,
                 config: cfg.SimulationConfig):
        super().__init__(cars=cars, stations=stations, societies=societies,
                         t_max=t_max, config=config, mode='greedy')
