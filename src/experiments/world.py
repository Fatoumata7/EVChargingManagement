"""
world.py — Monde initial reproductible, partagé entre méthodes *et* scénarios.

Problème résolu
---------------
Chaque couple (scénario, flotte) tirait auparavant son propre monde : positions
de stations, capacités, autonomies et préférences différaient donc entre
`optimistic`, `balance` et `pessimistic`. Un écart mesuré entre deux scénarios
mélangeait l'effet du comportement des usagers et celui du tirage du monde.

Trois couches, tirées indépendamment
------------------------------------
1. `GridSpec` — **l'infrastructure**. Sociétés (position, stratégie de points) et
   stations (position, société propriétaire, nombre de bornes, alpha initial).
   Tirée **une seule fois par campagne**, à partir de la graine seule : la
   grille est rigoureusement identique pour tous les scénarios et toutes les
   tailles de flotte.

2. `FleetSpec` — **la flotte**. Attributs statiques de chaque véhicule (position
   initiale, SoC initial, autonomie, seuil de recharge, préférences, puissance)
   et son *bruit comportemental* normalisé. Tirée une seule fois par taille de
   flotte, à partir de la graine seule : les véhicules sont identiques d'un
   scénario à l'autre. Les flux étant indexés par `idx` et non par ordre
   d'appel (cf. `seeding.RngHub`), les flottes sont **emboîtées** : les 50
   premiers véhicules d'une flotte de 100 sont exactement ceux de la flotte
   de 50, ce qui fait de la courbe de passage à l'échelle un ajout de véhicules
   à une population donnée, et non un ré-échantillonnage complet.

3. `WorldSpec` — **la composition** des deux pour un scénario donné. La seule
   chose que le scénario change est `theta`, les probabilités de comportement
   du véhicule, obtenues en appliquant son bruit fixe à `BASE_CANCEL_PROB` :

       theta_k ∝ max(0.1, base_k + base_k · noise_scale · u_k)

   avec `u_k ∈ [-1, 1]` tiré une fois pour toutes dans la `FleetSpec`. Deux
   scénarios voient donc le même véhicule avec la même « personnalité » : ce
   qui les sépare, ce sont uniquement les probabilités de base.

Ce que la reproductibilité garantit — et ce qu'elle ne garantit pas
------------------------------------------------------------------
`build_world` ne tire aucun nombre : deux appels sur la même spec rendent deux
mondes identiques mais disjoints, ce qui permet d'évaluer plusieurs méthodes sur
exactement le même environnement. Les trajectoires réalisées peuvent malgré tout
diverger entre méthodes ou entre scénarios, puisqu'un véhicule servi ici et non
servi là ne consomme pas le même nombre de tirages de déplacement. Ce qui est
garanti, c'est que la *source* d'aléa est commune — pas que les histoires soient
identiques après divergence.
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

# Clés de comportement, dans l'ordre de tirage du bruit : figé, le modifier
# changerait l'aléa de toutes les flottes déjà produites.
BEHAVIOR_KEYS = ('pres', 'abs', 'early', 'late')


class SpecMismatch(ValueError):
    """Une spécification ne correspond pas à la configuration fournie."""


# ----------------------------------------------------------------------
# Sérialisation commune
# ----------------------------------------------------------------------

class _JsonSpec:
    """Sauvegarde / relecture JSON, avec contrôle de version au chargement."""

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
                f"(attendu {SPEC_VERSION}) : {path}"
            )
        return cls(**data)


def _require(name: str, spec_value, config_value, mismatches: list) -> None:
    if spec_value != config_value:
        mismatches.append(f"{name}: spec={spec_value} config={config_value}")


def _raise_mismatches(what: str, mismatches: list) -> None:
    if mismatches:
        raise SpecMismatch(
            f"{what} incompatible avec la configuration : " + " ; ".join(mismatches)
        )


# ----------------------------------------------------------------------
# 1. Infrastructure : la grille partagée
# ----------------------------------------------------------------------

@dataclass
class GridSpec(_JsonSpec):
    """
    Infrastructure de recharge : sociétés et stations.

    Indépendante du scénario et de la taille de flotte — c'est précisément ce
    qui rend les scénarios comparables. Les champs autres que `societies` et
    `stations` décrivent la configuration sous laquelle la grille a été tirée,
    de sorte qu'une relecture sous une configuration incompatible échoue au lieu
    de produire des résultats silencieusement faux.
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
    Tire l'infrastructure : une grille unique pour toute la campagne.

    Aucun champ de `config` dépendant du scénario n'est lu ici. C'est ce qui
    permet d'appeler la fonction avec une configuration de référence et
    d'obtenir la même grille quel que soit le scénario simulé ensuite ;
    `tests/test_shared_world.py` le vérifie.
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

    # L'affectation des stations est indépendante d'une station à l'autre : rien
    # n'interdit qu'une société reste sans station. Le cas est légitime mais la
    # société ne participe alors pas à l'apprentissage collectif — autant le dire.
    empty = [s['f_id'] for s in societies if not spec.stations_of(s['f_id'])]
    if empty:
        logger.warning(
            f"Grille (seed={spec.seed}) : sociétés sans station {empty} — "
            "elles ne participeront pas à l'apprentissage collectif."
        )
    return spec


# ----------------------------------------------------------------------
# 2. Flotte : véhicules indépendants du scénario
# ----------------------------------------------------------------------

@dataclass
class FleetSpec(_JsonSpec):
    """
    Population de véhicules : tout ce qui ne dépend pas du scénario.

    `theta` en est délibérément absent : les probabilités de comportement sont
    la seule chose que le scénario fait varier, elles sont donc calculées à la
    composition (`compose_world_spec`) à partir de `behavior_noise`.
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
    """Paramètres des lois de tirage des véhicules (pour contrôle de cohérence)."""
    return {
        'autonomy_km':   dict(config.CAR_AUTONOMY_PARAMS_KM),
        'init_soc':      dict(config.CAR_INIT_SOC),
        'soc_threshold': dict(config.CAR_SOC_THRESHOLD_PARAMS),
    }


def generate_fleet_spec(config: cfg_module.SimulationConfig,
                        seed: int | None = None,
                        nb_cars: int | None = None) -> FleetSpec:
    """
    Tire une flotte : positions initiales et attributs statiques figés.

    Chaque véhicule est tiré dans son propre flux `('car_init', idx)`, si bien
    que le véhicule `idx` ne dépend ni du nombre de véhicules de la flotte ni de
    l'ordre de génération : les flottes de tailles croissantes sont emboîtées.
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
            # Bruit comportemental normalisé : mis à l'échelle par le scénario.
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
    Probabilités de comportement d'un véhicule dans un scénario donné.

    Le bruit `u_k ∈ [-1, 1]` est propre au véhicule et fixe ; l'amplitude
    (`base_cancel_prob['noise']`) et les probabilités de base viennent du
    scénario. Le même véhicule garde donc son écart relatif à la moyenne d'un
    scénario à l'autre.
    """
    scale = base_cancel_prob['noise']
    weights = {}
    for key in BEHAVIOR_KEYS:
        base = base_cancel_prob[key]
        weights[key] = max(0.1, base + base * scale * float(behavior_noise[key]))
    total = sum(weights.values())
    return {k: float(v / total) for k, v in weights.items()}


# ----------------------------------------------------------------------
# 3. Composition : le monde d'un cas
# ----------------------------------------------------------------------

@dataclass
class WorldSpec(_JsonSpec):
    """
    Monde initial d'un cas : grille partagée + flotte partagée + scénario.

    Entièrement dérivé de `GridSpec`, `FleetSpec` et `BASE_CANCEL_PROB` : il est
    persisté pour la traçabilité, mais reste recomposable à l'identique.
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
    Assemble un monde pour le scénario porté par `config`.

    Seul `theta` dépend du scénario ; tout le reste est recopié tel quel depuis
    la grille et la flotte.
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
    Raccourci : grille + flotte + scénario en un appel, pour une simulation isolée.

    Le pipeline n'utilise pas cette fonction : il tire la grille et les flottes
    une fois pour toute la campagne, puis compose (cf. `src/pipeline/runner.py`).
    """
    if seed is None:
        seed = config.SEED
    grid = generate_grid_spec(config, seed)
    fleet = generate_fleet_spec(config, seed, config.NB_CARS)
    return compose_world_spec(grid, fleet, config)


# ----------------------------------------------------------------------
# Tirages élémentaires
# ----------------------------------------------------------------------

def _pos(config, rng):
    return [float(v) for v in np.round(rng.uniform(0, config.C_GRID, size=2), 2)]


def _autonomy(config, rng):
    """Autonomie en mètres, multiple de 5 km (identique à Car.define_autonomy)."""
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
# Matérialisation
# ----------------------------------------------------------------------

def build_world(spec: WorldSpec, config: cfg_module.SimulationConfig):
    """
    Construit (cars, stations, societies) à partir d'une spécification.

    Déterministe : aucun tirage aléatoire. Deux appels sur la même spec donnent
    deux mondes identiques et indépendants — c'est ce qui permet d'évaluer
    plusieurs méthodes sur exactement le même environnement.
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
    Raccourci : génère une spec et en matérialise `nb_copies` mondes identiques.

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

    # --- La grille ne dépend ni du scénario ni de la flotte
    grids = [generate_grid_spec(_config(name, n), SEED).to_dict()
             for name, n in (('optimistic', 10), ('balance', 10),
                             ('pessimistic', 30))]
    assert all(g == grids[0] for g in grids), "grille dépendante du scénario"

    # --- La flotte ne dépend pas du scénario, et les flottes sont emboîtées
    fleet_a = generate_fleet_spec(_config('optimistic', 10), SEED, 10)
    fleet_b = generate_fleet_spec(_config('pessimistic', 10), SEED, 10)
    assert fleet_a.to_dict() == fleet_b.to_dict(), "flotte dépendante du scénario"
    fleet_big = generate_fleet_spec(_config('balance', 30), SEED, 30)
    assert fleet_big.cars[:10] == fleet_a.cars, "flottes non emboîtées"

    # --- Seul theta change d'un scénario à l'autre
    grid = generate_grid_spec(_config('balance', 10), SEED)
    worlds = {name: compose_world_spec(grid, fleet_a, _config(name, 10))
              for name in ('optimistic', 'balance', 'pessimistic')}
    for name, spec in worlds.items():
        for car, ref in zip(spec.cars, worlds['balance'].cars):
            assert car['loc'] == ref['loc'] and car['autonomy'] == ref['autonomy']
            assert abs(sum(car['theta'].values()) - 1.) < 1e-12
    assert worlds['optimistic'].cars[0]['theta'] != worlds['pessimistic'].cars[0]['theta']

    # --- build_world reste déterministe et rend des graphes disjoints
    config = _config('balance', 10)
    spec, (world_a, world_b) = make_worlds(config, seed=SEED)
    cars_a, stations_a, _ = world_a
    cars_b, stations_b, _ = world_b
    for ca, cb in zip(cars_a, cars_b):
        assert ca is not cb
        assert np.allclose(ca.loc, cb.loc) and ca.theta == cb.theta
        # Common random numbers : mêmes tirages de comportement
        assert [ca.draw_behavior() for _ in range(20)] == \
               [cb.draw_behavior() for _ in range(20)]
    for sa, sb in zip(stations_a, stations_b):
        assert np.allclose(sa.loc, sb.loc)
        assert sa.nb_charg_spot == sb.nb_charg_spot and sa.alpha == sb.alpha

    # --- Deux graines différentes -> mondes différents
    assert generate_grid_spec(config, SEED + 1).stations[0]['loc'] != \
        grid.stations[0]['loc']

    print(f"world.py OK — grille partagée ({grid.nb_stations} stations, "
          f"{grid.nb_societies} sociétés), flottes emboîtées, "
          f"scénarios ne différant que par theta")
