"""
simulation_greedy.py — Baseline gloutonne.

Version GREEDY :
- le véhicule contacte UNIQUEMENT la station la plus proche
- il accepte l'offre reçue (une seule offre, donc aucune comparaison utile)
- pas de score de réputation, pas d'apprentissage collectif entre stations

Implémentée comme une spécialisation de `Simulation` : le protocole (émission,
PLI, confirmation sécurisée, annulations, métriques) est strictement le même que
pour BRAM-EV, seules les trois différences de méthode sont activées. C'est ce
qui garantit qu'un correctif ne s'applique pas à une seule des deux branches.
"""

import src.experiments.config as cfg
from src.experiments.simulation import Simulation


class SimulationGreedy(Simulation):

    def __init__(self, cars, stations, societies, t_max,
                 config: cfg.SimulationConfig):
        super().__init__(cars=cars, stations=stations, societies=societies,
                         t_max=t_max, config=config, mode='greedy')
