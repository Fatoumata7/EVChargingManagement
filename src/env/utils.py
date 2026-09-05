"""
utils.py
"""

from scipy.stats import truncnorm
import numpy as np
import math
import src.experiments.config as config


def nominal_arrival(t_n, lead, distance, config) -> int:
    """
    Slot d'arrivée nominal d'une demande : émission + horizon de planification
    + temps de trajet.

    Point de vérité unique. La formule était auparavant recalculée dans quatre
    endroits (`Station.process_demands`, `Car.compute_utility`,
    `Car.update_schedule_requested`, `Simulation._handle_offers`) — avec un
    `int()` côté station et un `math.ceil()` ailleurs. Sur cette grille le
    trajet dure moins d'un slot, donc les deux vues divergeaient
    systématiquement d'un slot : la station proposait `t_n` là où le véhicule
    attendait `t_n + 1`, et l'attente mesurée était nulle par construction.
    `ceil` est retenu : un véhicule ne peut pas être arrivé avant d'avoir
    roulé.

    `lead` (`request['l_n']`) est l'horizon de planification du conducteur :
    le nombre de slots entre l'émission de la requête et le créneau souhaité.
    Il vaut 0 pour une demande « je charge maintenant ».
    """
    return math.ceil(t_n + lead + distance / config.CAR_SPEED)


def get_truncated_normal(mean, sd, low, high, rng=None):
    """
    Generate a value from a truncated normal distibutions,
    value strictly between low and high

    rng : np.random.Generator | None
        Flux dédié (reproductibilité). None -> générateur global numpy.
    """
    a, b = (low - mean) / sd, (high - mean) / sd
    return truncnorm.rvs(a, b, loc=mean, scale=sd, random_state=rng)


def init_pos(config: config.SimulationConfig, precision=2, rng=None): # precision to milimeter (pos in meter)
    """
    Generate a 2D random position on the grid

    rng : np.random.Generator | None
        Flux dédié (reproductibilité). None -> nouveau générateur non graine.
    """
    if rng is None:
        rng = np.random.default_rng()
    loc = np.round(rng.uniform(0, config.C_GRID, size=2), precision)
    return loc


if __name__ == "__main__":
    print(get_truncated_normal(mean=0.25, sd=0.1, low=0.05, high=0.5))
