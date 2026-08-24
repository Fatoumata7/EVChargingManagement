"""
utils.py
"""

from scipy.stats import truncnorm
import numpy as np
import src.experiments.config as config


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
