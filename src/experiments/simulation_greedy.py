"""
simulation_greedy.py — Baseline « Nearest » (recherche mono-station).

Version NEAREST (nom historique : `greedy`) :
- le véhicule contacte UNIQUEMENT la station la plus proche
- il accepte l'offre reçue (une seule offre, donc aucune comparaison utile)
- pas de score de réputation, pas d'apprentissage collectif entre stations

C'est le premier barreau de l'échelle d'ablation
(`src/experiments/methods.py`) : chaque barreau suivant lui ajoute exactement
un composant.

Cette classe n'est plus qu'un raccourci de confort : le pipeline instancie
directement `Simulation(mode=...)` pour toutes les méthodes, y compris
celle-ci. La conserver garde le code d'appel historique valide.
"""

import src.experiments.config as cfg
from src.experiments.simulation import Simulation


class SimulationGreedy(Simulation):

    def __init__(self, cars, stations, societies, t_max,
                 config: cfg.SimulationConfig):
        super().__init__(cars=cars, stations=stations, societies=societies,
                         t_max=t_max, config=config, mode='greedy')
