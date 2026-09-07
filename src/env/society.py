"""
society.py — Charging company agent.
"""

import copy
import numpy as np
import random
import src.env.station as station
import src.env.utils as utils
import src.experiments.config as config


class Society:

    def __init__(self, f_id: int, config: config.SimulationConfig,
                 spec: dict | None = None, rng=None):
        """
        Parameters
        ----------
        spec : dict | None
            Explicit parameters (loc, strategy) coming from a `WorldSpec`.
            When provided, no random draw happens here.
        """
        self.f_id = f_id
        self.config = config
        self.stations = []

        if spec is not None:
            self.loc = np.asarray(spec['loc'], dtype=float)
            self.strategy = dict(spec['strategy'])
        else:
            self.loc = utils.init_pos(config, rng=rng)
            self.strategy = copy.deepcopy(config.BASE_POINTS_STRATEGY)
            for k in self.strategy:
                v = self.strategy[k]
                self.strategy[k] = max(
                    0.1,
                    v + np.random.uniform(-config.STRATEGY_NOISE * v,
                                          config.STRATEGY_NOISE * v)
                )

    def add_station(self, s: station.Station):
        self.stations.append(s)
        s.strategy = self.strategy   # injected by reference

    def update_strategy(self, file):
        """
        FIX: the *strategy* of the best station is copied, not the station object.
        Collective learning: the best station dictates the common strategy.
        """
        if not self.stations:
            return

        print('### UPDATE STRATEGY ###', file=file)
        perf = [s.total_nb_allocated_slot() for s in self.stations]
        print(f'---> PERF (total_nb_allocated_slot): {perf}', file=file)
        best_idx = int(np.argmax(perf))
        print(f'best_station perf: {perf[best_idx]} allocated_slots', file=file)

        # Propagation to every station
        best_alpha = self.stations[best_idx].alpha
        for idx, s in enumerate(self.stations):
            if idx != best_idx:
                prev_alpha = s.alpha
                new_alpha = prev_alpha + self.config.GAMMA * (best_alpha - prev_alpha)
                s.alpha = new_alpha
                s.alpha_save.append(new_alpha)
            else:
                s.alpha_save.append(best_alpha)

    def display_parameters(self, file):
        print('--- AGENT SOCIETY', file=file)
        print(f'  f_id          : {self.f_id}', file=file)
        print(f'  nb stations   : {len(self.stations)}', file=file)
        print(f'  strategy      : {self.strategy}', file=file)
