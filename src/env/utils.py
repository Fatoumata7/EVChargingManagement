"""
utils.py — Shared helpers for the multi-agent model.
"""

from scipy.stats import truncnorm
import numpy as np
import math
import src.experiments.config as config


def nominal_arrival(t_n, lead, distance, config) -> int:
    """
    Nominal arrival slot of a demand: emission + planning horizon + travel time.

    Single source of truth. The formula used to be recomputed in four places
    (`Station.process_demands`, `Car.compute_utility`,
    `Car.update_schedule_requested`, `Simulation._handle_offers`) — with an
    `int()` on the station side and a `math.ceil()` everywhere else. On this
    grid the trip takes less than one slot, so the two views diverged
    systematically by one slot: the station offered `t_n` where the vehicle
    expected `t_n + 1`, and the measured waiting time was zero by construction.
    `ceil` is the retained rounding: a vehicle cannot have arrived before it has
    driven.

    `lead` (`request['l_n']`) is the driver's planning horizon: the number of
    slots between the emission of the request and the targeted slot. It is 0 for
    a "charge now" demand.
    """
    return math.ceil(t_n + lead + distance / config.CAR_SPEED)


def get_truncated_normal(mean, sd, low, high, rng=None):
    """
    Generate a value from a truncated normal distribution,
    value strictly between low and high.

    rng : np.random.Generator | None
        Dedicated stream (reproducibility). None -> global numpy generator.
    """
    a, b = (low - mean) / sd, (high - mean) / sd
    return truncnorm.rvs(a, b, loc=mean, scale=sd, random_state=rng)


def init_pos(config: config.SimulationConfig, precision=2, rng=None): # precision to milimeter (pos in meter)
    """
    Generate a 2D random position on the grid.

    rng : np.random.Generator | None
        Dedicated stream (reproducibility). None -> new unseeded generator.
    """
    if rng is None:
        rng = np.random.default_rng()
    loc = np.round(rng.uniform(0, config.C_GRID, size=2), precision)
    return loc


if __name__ == "__main__":
    print(get_truncated_normal(mean=0.25, sd=0.1, low=0.05, high=0.5))
