"""
world.py — Reproducible initial world, shared across methods *and* scenarios.

Problem solved
--------------
Each (scenario, fleet) pair used to draw its own world: station positions,
capacities, autonomies and preferences therefore differed between `optimistic`,
`balance` and `pessimistic`. A gap measured between two scenarios mixed the
effect of user behaviour with the effect of the world draw.

Three layers, drawn independently
---------------------------------
1. `GridSpec` — **the infrastructure**. Companies (position, point strategy) and
   stations (position, owning company, number of chargers, initial alpha).
   Drawn **only once per campaign**, from the seed alone: the grid is strictly
   identical for every scenario and every fleet size.

2. `FleetSpec` — **the fleet**. Static attributes of each vehicle (initial
   position, initial SoC, autonomy, charging threshold, preferences, power) and
   its normalised *behavioural noise*. Drawn once per fleet size, from the seed
   alone: the vehicles are identical from one scenario to the next. Since the
   streams are indexed by `idx` and not by call order (see `seeding.RngHub`),
   the fleets are **nested**: the first 50 vehicles of a fleet of 100 are
   exactly those of the fleet of 50, which makes the scalability curve an
   addition of vehicles to a given population rather than a complete
   resampling.

3. `WorldSpec` — **the composition** of the two for a given scenario. The only
   thing the scenario changes is `theta`, the behaviour probabilities of the
   vehicle, obtained by applying its fixed noise to `BASE_CANCEL_PROB`:

       theta_k ∝ max(0.1, base_k + base_k · noise_scale · u_k)

   with `u_k ∈ [-1, 1]` drawn once and for all in the `FleetSpec`. Two scenarios
   therefore see the same vehicle with the same "personality": what separates
   them is only the base probabilities.

What reproducibility guarantees — and what it does not
------------------------------------------------------
`build_world` draws no number: two calls on the same spec yield two identical
but disjoint worlds, which is what allows several methods to be evaluated on
exactly the same environment. The realised trajectories may nonetheless diverge
between methods or between scenarios, since a vehicle served here and not there
does not consume the same number of movement draws. What is guaranteed is that
the *source* of randomness is common — not that the histories are identical
after divergence.
"""

import json
import os
from dataclasses import dataclass, asdict, field

import numpy as np
from loguru import logger

import src.env.car as car_module
import src.env.station as st
import src.env.society as sct
import src.env.utils as utils
import src.experiments.config as cfg_module
from src.experiments.seeding import RngHub

SPEC_VERSION = 3

# Behaviour keys, in the order the noise is drawn: frozen, changing it would
# change the randomness of every fleet already produced.
BEHAVIOR_KEYS = ('pres', 'abs', 'early', 'late')


class SpecMismatch(ValueError):
    """A specification does not match the configuration provided."""


# ----------------------------------------------------------------------
# Common serialisation
# ----------------------------------------------------------------------

class _JsonSpec:
    """JSON save / reload, with a version check on loading."""

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: str):
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        if data.get('version') != SPEC_VERSION:
            raise ValueError(
                f"{cls.__name__} version {data.get('version')} incompatible "
                f"(expected {SPEC_VERSION}): {path}"
            )
        return cls(**data)


def _require(name: str, spec_value, config_value, mismatches: list) -> None:
    if spec_value != config_value:
        mismatches.append(f"{name}: spec={spec_value} config={config_value}")


def _raise_mismatches(what: str, mismatches: list) -> None:
    if mismatches:
        raise SpecMismatch(
            f"{what} incompatible with the configuration: " + " ; ".join(mismatches)
        )


# ----------------------------------------------------------------------
# 1. Infrastructure: the shared grid
# ----------------------------------------------------------------------

@dataclass
class GridSpec(_JsonSpec):
    """
    Charging infrastructure: companies and stations.

    Independent from the scenario and from the fleet size — which is precisely
    what makes the scenarios comparable. The fields other than `societies` and
    `stations` describe the configuration under which the grid was drawn, so
    that reloading it under an incompatible configuration fails instead of
    producing silently wrong results.
    """

    seed: int
    nb_societies: int
    nb_stations: int
    grid_m: float
    nb_charg_spot: dict = field(default_factory=dict)
    base_points_strategy: dict = field(default_factory=dict)
    strategy_noise: float = 0.0
    societies: list = field(default_factory=list)
    stations: list = field(default_factory=list)
    version: int = SPEC_VERSION

    def stations_of(self, society_id: int) -> list:
        return [s for s in self.stations if s['society_id'] == society_id]

    def check_matches(self, config: cfg_module.SimulationConfig) -> None:
        mismatches: list = []
        _require('NB_SOCIETIES', self.nb_societies, config.NB_SOCIETIES, mismatches)
        _require('NB_STATIONS', self.nb_stations, config.NB_STATIONS, mismatches)
        _require('C_GRID', self.grid_m, config.C_GRID, mismatches)
        _require('NB_CHARG_SPOT', self.nb_charg_spot,
                 dict(config.NB_CHARG_SPOT), mismatches)
        _raise_mismatches('GridSpec', mismatches)


def generate_grid_spec(config: cfg_module.SimulationConfig,
                       seed: int | None = None) -> GridSpec:
    """
    Draw the infrastructure: a single grid for the whole campaign.

    No scenario-dependent field of `config` is read here. That is what allows
    calling the function with a reference configuration and obtaining the same
    grid whatever the scenario simulated afterwards;
    `tests/test_shared_world.py` verifies it.
    """
    if seed is None:
        seed = config.SEED
    hub = RngHub(seed)

    societies = []
    for f_id in range(config.NB_SOCIETIES):
        rng = hub.stream('society_init', f_id)
        strategy = {}
        for key, value in config.BASE_POINTS_STRATEGY.items():
            noise = rng.uniform(-config.STRATEGY_NOISE * value,
                                config.STRATEGY_NOISE * value)
            strategy[key] = float(max(0.1, value + noise))
        societies.append({
            'f_id':     f_id,
            'loc':      _pos(config, rng),
            'strategy': strategy,
        })

    stations = []
    for m in range(config.NB_STATIONS):
        rng = hub.stream('station_init', m)
        stations.append({
            'm':             m,
            'society_id':    int(rng.integers(0, config.NB_SOCIETIES)),
            'loc':           _pos(config, rng),
            'nb_charg_spot': int(rng.integers(config.NB_CHARG_SPOT['low'],
                                              config.NB_CHARG_SPOT['high'] + 1)),
            'alpha':         float(rng.uniform(0.1, 0.9)),
        })

    spec = GridSpec(
        seed=hub.seed,
        nb_societies=config.NB_SOCIETIES,
        nb_stations=config.NB_STATIONS,
        grid_m=config.C_GRID,
        nb_charg_spot=dict(config.NB_CHARG_SPOT),
        base_points_strategy=dict(config.BASE_POINTS_STRATEGY),
        strategy_noise=config.STRATEGY_NOISE,
        societies=societies,
        stations=stations,
    )

    # Station assignment is independent from one station to the next: nothing
    # forbids a company from ending up with no station. The case is legitimate,
    # but that company then takes no part in collective learning — worth saying.
    empty = [s['f_id'] for s in societies if not spec.stations_of(s['f_id'])]
    if empty:
        logger.warning(
            f"Grid (seed={spec.seed}): companies with no station {empty} — "
            "they will not take part in collective learning."
        )
    return spec


# ----------------------------------------------------------------------
# 2. Fleet: vehicles independent from the scenario
# ----------------------------------------------------------------------

@dataclass
class FleetSpec(_JsonSpec):
    """
    Vehicle population: everything that does not depend on the scenario.

    `theta` is deliberately absent from it: the behaviour probabilities are the
    only thing the scenario varies, so they are computed at composition time
    (`compose_world_spec`) from `behavior_noise`.
    """

    seed: int
    nb_cars: int
    grid_m: float
    car_params: dict = field(default_factory=dict)
    cars: list = field(default_factory=list)
    version: int = SPEC_VERSION

    def check_matches(self, config: cfg_module.SimulationConfig) -> None:
        mismatches: list = []
        _require('NB_CARS', self.nb_cars, config.NB_CARS, mismatches)
        _require('C_GRID', self.grid_m, config.C_GRID, mismatches)
        _require('car_params', self.car_params, _car_params(config), mismatches)
        _raise_mismatches('FleetSpec', mismatches)


def _car_params(config: cfg_module.SimulationConfig) -> dict:
    """Parameters of the vehicle draw laws (for a consistency check)."""
    return {
        'autonomy_km':   dict(config.CAR_AUTONOMY_PARAMS_KM),
        'init_soc':      dict(config.CAR_INIT_SOC),
        'soc_threshold': dict(config.CAR_SOC_THRESHOLD_PARAMS),
    }


def generate_fleet_spec(config: cfg_module.SimulationConfig,
                        seed: int | None = None,
                        nb_cars: int | None = None) -> FleetSpec:
    """
    Draw a fleet: initial positions and frozen static attributes.

    Each vehicle is drawn in its own `('car_init', idx)` stream, so vehicle
    `idx` depends neither on the number of vehicles in the fleet nor on the
    generation order: fleets of increasing sizes are nested.
    """
    if seed is None:
        seed = config.SEED
    if nb_cars is None:
        nb_cars = config.NB_CARS
    hub = RngHub(seed)

    cars = []
    for idx in range(int(nb_cars)):
        rng = hub.stream('car_init', idx)
        autonomy = _autonomy(config, rng)
        threshold = float(utils.get_truncated_normal(
            mean=config.CAR_SOC_THRESHOLD_PARAMS['mean'],
            sd=config.CAR_SOC_THRESHOLD_PARAMS['sd'],
            low=config.CAR_SOC_THRESHOLD_PARAMS['low'],
            high=config.CAR_SOC_THRESHOLD_PARAMS['high'],
            rng=rng) * autonomy)
        cars.append({
            'idx':             idx,
            'loc':             _pos(config, rng),
            'soc_init':        float(rng.uniform(config.CAR_INIT_SOC['low'],
                                                 config.CAR_INIT_SOC['high'])),
            'autonomy':        autonomy,
            'soc_threshold_m': threshold,
            'pref':            _pref(rng),
            'charging_power':  int(rng.integers(4, 9)),
            # Normalised behavioural noise: scaled by the scenario.
            'behavior_noise':  {k: float(rng.uniform(-1., 1.))
                                for k in BEHAVIOR_KEYS},
        })

    return FleetSpec(
        seed=hub.seed,
        nb_cars=int(nb_cars),
        grid_m=config.C_GRID,
        car_params=_car_params(config),
        cars=cars,
    )


def theta_from_noise(behavior_noise: dict, base_cancel_prob: dict) -> dict:
    """
    Behaviour probabilities of a vehicle in a given scenario.

    The noise `u_k ∈ [-1, 1]` belongs to the vehicle and is fixed; the amplitude
    (`base_cancel_prob['noise']`) and the base probabilities come from the
    scenario. The same vehicle therefore keeps its relative deviation from the
    average from one scenario to the next.
    """
    scale = base_cancel_prob['noise']
    weights = {}
    for key in BEHAVIOR_KEYS:
        base = base_cancel_prob[key]
        weights[key] = max(0.1, base + base * scale * float(behavior_noise[key]))
    total = sum(weights.values())
    return {k: float(v / total) for k, v in weights.items()}


# ----------------------------------------------------------------------
# 3. Composition: the world of one case
# ----------------------------------------------------------------------

@dataclass
class WorldSpec(_JsonSpec):
    """
    Initial world of a case: shared grid + shared fleet + scenario.

    Entirely derived from `GridSpec`, `FleetSpec` and `BASE_CANCEL_PROB`: it is
    persisted for traceability, but stays identically recomposable.
    """

    seed: int
    scenario: str
    nb_cars: int
    nb_societies: int
    nb_stations: int
    grid_seed: int = 0
    fleet_seed: int = 0
    base_cancel_prob: dict = field(default_factory=dict)
    societies: list = field(default_factory=list)
    stations: list = field(default_factory=list)
    cars: list = field(default_factory=list)
    config_summary: dict = field(default_factory=dict)
    version: int = SPEC_VERSION


def compose_world_spec(grid: GridSpec, fleet: FleetSpec,
                       config: cfg_module.SimulationConfig) -> WorldSpec:
    """
    Assemble a world for the scenario carried by `config`.

    Only `theta` depends on the scenario; everything else is copied as is from
    the grid and the fleet.
    """
    grid.check_matches(config)
    fleet.check_matches(config)

    cars = [
        dict(car, theta=theta_from_noise(car['behavior_noise'],
                                         config.BASE_CANCEL_PROB))
        for car in fleet.cars
    ]

    return WorldSpec(
        seed=fleet.seed,
        scenario=config.SCENARIO_NAME,
        nb_cars=fleet.nb_cars,
        nb_societies=grid.nb_societies,
        nb_stations=grid.nb_stations,
        grid_seed=grid.seed,
        fleet_seed=fleet.seed,
        base_cancel_prob=dict(config.BASE_CANCEL_PROB),
        societies=[dict(s) for s in grid.societies],
        stations=[dict(s) for s in grid.stations],
        cars=cars,
        config_summary=config.summary(),
    )


def generate_world_spec(config: cfg_module.SimulationConfig,
                        seed: int | None = None) -> WorldSpec:
    """
    Shortcut: grid + fleet + scenario in one call, for an isolated simulation.

    The pipeline does not use this function: it draws the grid and the fleets
    once for the whole campaign, then composes (see `src/pipeline/runner.py`).
    """
    if seed is None:
        seed = config.SEED
    grid = generate_grid_spec(config, seed)
    fleet = generate_fleet_spec(config, seed, config.NB_CARS)
    return compose_world_spec(grid, fleet, config)


# ----------------------------------------------------------------------
# Elementary draws
# ----------------------------------------------------------------------

def _pos(config, rng):
    return [float(v) for v in np.round(rng.uniform(0, config.C_GRID, size=2), 2)]


def _autonomy(config, rng):
    """Autonomy in meters, multiple of 5 km (identical to Car.define_autonomy)."""
    scale = 5
    value = utils.get_truncated_normal(
        mean=config.CAR_AUTONOMY_PARAMS_KM['mean'] / scale,
        sd=config.CAR_AUTONOMY_PARAMS_KM['sd'] / scale,
        low=config.CAR_AUTONOMY_PARAMS_KM['low'] / scale,
        high=config.CAR_AUTONOMY_PARAMS_KM['high'] / scale,
        rng=rng)
    return float(int(value) * scale * 1e3)


def _pref(rng):
    prefs = {k: rng.uniform(0., 1.) for k in ('energy', 'dist', 'wait')}
    total = sum(prefs.values())
    return {k: float(v / total) for k, v in prefs.items()}


# ----------------------------------------------------------------------
# Materialisation
# ----------------------------------------------------------------------

def build_world(spec: WorldSpec, config: cfg_module.SimulationConfig):
    """
    Build (cars, stations, societies) from a specification.

    Deterministic: no random draw. Two calls on the same spec give two identical
    and independent worlds — that is what allows several methods to be evaluated
    on exactly the same environment.
    """
    _check_spec_matches_config(spec, config)

    hub = RngHub(spec.seed)

    societies = [sct.Society(f_id=s['f_id'], config=config, spec=s)
                 for s in spec.societies]

    stations = []
    for s in spec.stations:
        station = st.Station(m=s['m'], society_id=s['society_id'],
                             config=config, spec=s)
        societies[s['society_id']].add_station(station)
        stations.append(station)

    cars = [car_module.Car(idx=c['idx'], nb_society=config.NB_SOCIETIES,
                           config=config, spec=c, rng_hub=hub)
            for c in spec.cars]

    return cars, stations, societies


def _check_spec_matches_config(spec: WorldSpec, config):
    mismatches: list = []
    _require('NB_CARS', spec.nb_cars, config.NB_CARS, mismatches)
    _require('NB_STATIONS', spec.nb_stations, config.NB_STATIONS, mismatches)
    _require('NB_SOCIETIES', spec.nb_societies, config.NB_SOCIETIES, mismatches)
    _raise_mismatches('WorldSpec', mismatches)


def make_worlds(config: cfg_module.SimulationConfig, seed: int | None = None,
                nb_copies: int = 2):
    """
    Shortcut: generate a spec and materialise `nb_copies` identical worlds from it.

    Returns
    -------
    (spec, [ (cars, stations, societies), ... ])
    """
    spec = generate_world_spec(config, seed)
    return spec, [build_world(spec, config) for _ in range(nb_copies)]


if __name__ == "__main__":
    def _config(scenario, nb_cars):
        config = cfg_module.SimulationConfig()
        config.set_VISUALIZE(False)
        config.set_scenario(scenario)
        config.set_NB_CARS(nb_cars)
        config.set_NB_STATIONS(6)
        config.set_NB_SOCIETIES(2)
        return config

    SEED = 42

    # --- The grid depends neither on the scenario nor on the fleet
    grids = [generate_grid_spec(_config(name, n), SEED).to_dict()
             for name, n in (('optimistic', 10), ('balance', 10),
                             ('pessimistic', 30))]
    assert all(g == grids[0] for g in grids), "grid depends on the scenario"

    # --- The fleet does not depend on the scenario, and fleets are nested
    fleet_a = generate_fleet_spec(_config('optimistic', 10), SEED, 10)
    fleet_b = generate_fleet_spec(_config('pessimistic', 10), SEED, 10)
    assert fleet_a.to_dict() == fleet_b.to_dict(), "fleet depends on the scenario"
    fleet_big = generate_fleet_spec(_config('balance', 30), SEED, 30)
    assert fleet_big.cars[:10] == fleet_a.cars, "fleets are not nested"

    # --- Only theta changes from one scenario to the next
    grid = generate_grid_spec(_config('balance', 10), SEED)
    worlds = {name: compose_world_spec(grid, fleet_a, _config(name, 10))
              for name in ('optimistic', 'balance', 'pessimistic')}
    for name, spec in worlds.items():
        for car, ref in zip(spec.cars, worlds['balance'].cars):
            assert car['loc'] == ref['loc'] and car['autonomy'] == ref['autonomy']
            assert abs(sum(car['theta'].values()) - 1.) < 1e-12
    assert worlds['optimistic'].cars[0]['theta'] != worlds['pessimistic'].cars[0]['theta']

    # --- build_world stays deterministic and returns disjoint object graphs
    config = _config('balance', 10)
    spec, (world_a, world_b) = make_worlds(config, seed=SEED)
    cars_a, stations_a, _ = world_a
    cars_b, stations_b, _ = world_b
    for ca, cb in zip(cars_a, cars_b):
        assert ca is not cb
        assert np.allclose(ca.loc, cb.loc) and ca.theta == cb.theta
        # Common random numbers: same behaviour draws
        assert [ca.draw_behavior() for _ in range(20)] == \
               [cb.draw_behavior() for _ in range(20)]
    for sa, sb in zip(stations_a, stations_b):
        assert np.allclose(sa.loc, sb.loc)
        assert sa.nb_charg_spot == sb.nb_charg_spot and sa.alpha == sb.alpha

    # --- Two different seeds -> different worlds
    assert generate_grid_spec(config, SEED + 1).stations[0]['loc'] != \
        grid.stations[0]['loc']

    print(f"world.py OK — shared grid ({grid.nb_stations} stations, "
          f"{grid.nb_societies} companies), nested fleets, "
          f"scenarios differing only by theta")
