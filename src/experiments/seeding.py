"""
seeding.py — Centralised management of randomness.

Goal: strict reproducibility of the experiments and *common random numbers*
(CRN) across the methods being compared.

Principle
---------
A single seed drives the whole experiment. It is split into independent streams
through `numpy.random.SeedSequence`, one stream per (kind, index):

    hub = RngHub(seed=42)
    rng = hub.stream('car_move', car_idx)

Two executions with the same seed produce:
  * the same initial world (positions, capacities, preferences, behaviours);
  * the same draws for a given vehicle, in the order of its own stream.

Streams are separated by usage (movement / behaviour / request) so that the
divergence of a method on one usage does not shift the draws of the others:
that is what makes it possible to compare BRAM-EV and Greedy on the *same*
randomness.

Indexed by key, never by order
------------------------------
A stream is determined by `(kind, idx)`, not by the rank of the call. That is
what lets `world.py` draw station `m` or vehicle `idx` without the number of
entities already drawn influencing the result: at equal seed, a fleet of 100
vehicles starts with exactly the 50 vehicles of a fleet of 50.
"""

import random
import numpy as np


# Stream codes — FROZEN. Never reorder them nor reuse a code: that would change
# the randomness of every experiment already published.
STREAM_CODES = {
    'world':        1,   # monolithic world generation (legacy, see world.py)
    'car_move':     2,   # free movement of the vehicle
    'car_behavior': 3,   # behaviour draw (pres/abs/early/late), speed
    'car_request':  4,   # request parameters (duration, radius, patience)
    'station':      5,   # reserved (the ILP optimisation is deterministic)
    'society_init': 6,   # draw of a company of the shared grid
    'station_init': 7,   # draw of a station of the shared grid
    'car_init':     8,   # draw of the static attributes of a vehicle
    'car_lead':     9,   # planning horizon of a request (l_n)
    'car_choice':  10,   # random tie-break between offers (random baseline)
}

DEFAULT_SEED = 20260101

_UINT32 = 2 ** 32


def seed_everything(seed: int) -> int:
    """
    Seed the global `random` and `numpy.random` generators.

    Needed for the few calls that do not go through a dedicated stream
    (including `scipy.stats` without `random_state`) and for the iteration order
    of randomised containers. The `RngHub` streams remain the preferred source.
    """
    seed = int(seed)
    random.seed(seed)
    np.random.seed(seed % _UINT32)
    return seed


class RngHub:
    """
    Factory of reproducible, mutually independent generators.

    Parameters
    ----------
    seed : int | None
        Root seed. `None` → `DEFAULT_SEED` (still reproducible).
    """

    def __init__(self, seed: int | None = DEFAULT_SEED):
        if seed is None:
            seed = DEFAULT_SEED
        if not isinstance(seed, (int, np.integer)):
            raise TypeError(
                f"seed must be an integer, got: {type(seed).__name__}"
            )
        self.seed = int(seed)
        seed_everything(self.seed)

    def stream(self, kind: str, idx: int = 0) -> np.random.Generator:
        """
        Return the generator of the (`kind`, `idx`) stream.

        Two identical calls return two distinct generators producing the same
        sequence: a stream is determined by its key, not by the order of the
        calls.
        """
        if kind not in STREAM_CODES:
            raise KeyError(
                f"Unknown stream: {kind!r}. Expected one of {sorted(STREAM_CODES)}"
            )
        seq = np.random.SeedSequence(
            entropy=self.seed,
            spawn_key=(STREAM_CODES[kind], int(idx))
        )
        return np.random.default_rng(seq)

    def __repr__(self):
        return f"RngHub(seed={self.seed})"


if __name__ == "__main__":
    hub_a = RngHub(42)
    hub_b = RngHub(42)
    # Same key -> same sequence, whatever the order of the calls
    assert hub_a.stream('car_move', 7).random() == hub_b.stream('car_move', 7).random()
    # Different keys -> uncorrelated sequences
    assert hub_a.stream('car_move', 7).random() != hub_a.stream('car_move', 8).random()
    print("seeding.py OK")
