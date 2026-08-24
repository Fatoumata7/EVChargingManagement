"""
test_shared_world.py — Vérifie que les scénarios tournent sur le même monde.

    python -m tests.test_shared_world

La comparabilité entre `optimistic`, `balance` et `pessimistic` repose sur une
propriété structurelle : la grille (sociétés, stations) et les flottes
(positions initiales, autonomies, préférences) sont tirées **avant** toute
simulation et réutilisées telles quelles ; seul `theta`, les probabilités de
comportement, dépend du scénario.

Cette propriété n'est pas visible à la lecture — elle se perd au premier
tirage égaré dans une fonction dépendant du scénario. Elle est donc vérifiée
ici, à trois niveaux : sur les specs, sur les agents matérialisés, et de bout
en bout sur une campagne réelle.

Aucune dépendance de test externe : uniquement des assertions et un compte-rendu.
"""

import sys
import tempfile
import traceback

import numpy as np

from src.experiments.config import SimulationConfig
from src.experiments.world import (BEHAVIOR_KEYS, FleetSpec, GridSpec,
                                   SpecMismatch, build_world,
                                   compose_world_spec, generate_fleet_spec,
                                   generate_grid_spec, theta_from_noise)
from src.pipeline import tables
from src.pipeline.params import CaseParams, ExperimentParams
from src.pipeline.runner import prepare_shared_world, run_grid
from src.pipeline.store import RunStore

SCENARIOS = ('optimistic', 'balance', 'pessimistic')
SEED = 4242

# Attributs d'un véhicule qui ne doivent PAS dépendre du scénario.
STATIC_CAR_KEYS = ('idx', 'loc', 'soc_init', 'autonomy', 'soc_threshold_m',
                   'pref', 'charging_power', 'behavior_noise')


def config_for(scenario: str | None = None, nb_cars: int = 12,
               nb_stations: int = 8, nb_societies: int = 3) -> SimulationConfig:
    config = SimulationConfig()
    config.set_VISUALIZE(False)
    config.set_seed(SEED)
    config.set_TOTAL_TIME(12 * 4)
    config.set_NB_CARS(nb_cars)
    config.set_NB_STATIONS(nb_stations)
    config.set_NB_SOCIETIES(nb_societies)
    if scenario is not None:
        config.set_scenario(scenario)
    return config


def tiny_params(**overrides) -> ExperimentParams:
    """Campagne minuscule : trois scénarios, deux flottes, deux méthodes."""
    base = dict(
        seed=SEED,
        scenarios=SCENARIOS,
        fleet_sizes=(6, 12),
        methods=('greedy', 'bramev'),
        total_time=12 * 3,
        nb_stations=6,
        nb_societies=2,
        keep_logs=False,
        figures=False,
        log_every=12,
    )
    base.update(overrides)
    return ExperimentParams(**base)


# ----------------------------------------------------------------------
# 1. La grille est unique
# ----------------------------------------------------------------------

def test_grid_is_identical_across_scenarios():
    grids = [generate_grid_spec(config_for(name), SEED).to_dict()
             for name in SCENARIOS]
    for name, grid in zip(SCENARIOS[1:], grids[1:]):
        assert grid == grids[0], f'la grille diffère pour {name}'


def test_grid_is_identical_across_fleet_sizes():
    reference = generate_grid_spec(config_for('balance', nb_cars=12), SEED)
    for nb_cars in (6, 12, 60):
        other = generate_grid_spec(config_for('balance', nb_cars=nb_cars), SEED)
        assert other.to_dict() == reference.to_dict(), \
            f'la grille dépend de la taille de flotte ({nb_cars})'


def test_grid_depends_on_the_seed():
    a = generate_grid_spec(config_for('balance'), SEED)
    b = generate_grid_spec(config_for('balance'), SEED + 1)
    assert a.stations != b.stations, 'deux graines donnent la même grille'


def test_grid_spec_roundtrips_and_rejects_a_foreign_config():
    grid = generate_grid_spec(config_for('balance'), SEED)
    with tempfile.TemporaryDirectory() as tmp:
        path = grid.save(f'{tmp}/grid.json')
        reloaded = GridSpec.load(path)
    assert reloaded.to_dict() == grid.to_dict()

    reloaded.check_matches(config_for('balance'))          # cohérent
    try:
        reloaded.check_matches(config_for('balance', nb_stations=99))
    except SpecMismatch as exc:
        assert 'NB_STATIONS' in str(exc)
    else:
        raise AssertionError('une grille incompatible doit être refusée')


# ----------------------------------------------------------------------
# 2. Les flottes sont uniques par taille, et emboîtées
# ----------------------------------------------------------------------

def test_fleet_is_identical_across_scenarios():
    fleets = [generate_fleet_spec(config_for(name), SEED, 12).to_dict()
              for name in SCENARIOS]
    for name, fleet in zip(SCENARIOS[1:], fleets[1:]):
        assert fleet == fleets[0], f'la flotte diffère pour {name}'


def test_fleet_carries_no_scenario_dependent_field():
    """`theta` ne doit pas être figé dans la flotte : il dépend du scénario."""
    fleet = generate_fleet_spec(config_for('balance'), SEED, 12)
    for car in fleet.cars:
        assert 'theta' not in car
        assert set(car['behavior_noise']) == set(BEHAVIOR_KEYS)
        assert all(-1. <= v <= 1. for v in car['behavior_noise'].values())
        assert set(car) == set(STATIC_CAR_KEYS)


def test_fleets_are_nested():
    """Une flotte de 12 commence exactement par les 6 véhicules d'une flotte de 6."""
    small = generate_fleet_spec(config_for('balance', nb_cars=6), SEED, 6)
    large = generate_fleet_spec(config_for('balance', nb_cars=12), SEED, 12)
    assert large.cars[:6] == small.cars, 'flottes non emboîtées'
    assert large.nb_cars == 12 and small.nb_cars == 6


def test_fleet_spec_roundtrips_and_rejects_a_foreign_config():
    fleet = generate_fleet_spec(config_for('balance'), SEED, 12)
    with tempfile.TemporaryDirectory() as tmp:
        path = fleet.save(f'{tmp}/fleet.json')
        reloaded = FleetSpec.load(path)
    assert reloaded.to_dict() == fleet.to_dict()

    reloaded.check_matches(config_for('balance', nb_cars=12))
    try:
        reloaded.check_matches(config_for('balance', nb_cars=13))
    except SpecMismatch as exc:
        assert 'NB_CARS' in str(exc)
    else:
        raise AssertionError('une flotte incompatible doit être refusée')


# ----------------------------------------------------------------------
# 3. Seul theta change d'un scénario à l'autre
# ----------------------------------------------------------------------

def test_only_theta_varies_between_scenarios():
    grid = generate_grid_spec(config_for('balance'), SEED)
    fleet = generate_fleet_spec(config_for('balance'), SEED, 12)
    worlds = {name: compose_world_spec(grid, fleet, config_for(name))
              for name in SCENARIOS}

    reference = worlds['balance']
    for name, world in worlds.items():
        assert world.stations == reference.stations, f'stations : {name}'
        assert world.societies == reference.societies, f'sociétés : {name}'
        for car, ref in zip(world.cars, reference.cars):
            for key in STATIC_CAR_KEYS:
                assert car[key] == ref[key], f'{name} : {key} du véhicule {car["idx"]}'

    # ...et theta, lui, change bien.
    thetas = {name: [c['theta'] for c in w.cars] for name, w in worlds.items()}
    assert thetas['optimistic'] != thetas['pessimistic']


def test_theta_is_a_pure_function_of_noise_and_base_probabilities():
    """Le scénario n'agit que par `BASE_CANCEL_PROB` : rien n'est retiré au hasard."""
    grid = generate_grid_spec(config_for('balance'), SEED)
    fleet = generate_fleet_spec(config_for('balance'), SEED, 12)

    for name in SCENARIOS:
        config = config_for(name)
        world = compose_world_spec(grid, fleet, config)
        for car, source in zip(world.cars, fleet.cars):
            expected = theta_from_noise(source['behavior_noise'],
                                        config.BASE_CANCEL_PROB)
            assert car['theta'] == expected
            assert abs(sum(car['theta'].values()) - 1.) < 1e-12
            assert all(v > 0 for v in car['theta'].values())


def test_pessimistic_shifts_behaviour_in_the_expected_direction():
    """
    Contrôle de bon sens : à véhicules identiques, le scénario pessimiste doit
    réduire la probabilité moyenne de présence.
    """
    grid = generate_grid_spec(config_for('balance'), SEED)
    fleet = generate_fleet_spec(config_for('balance'), SEED, 60)
    means = {}
    for name in SCENARIOS:
        world = compose_world_spec(grid, fleet, config_for(name, nb_cars=60))
        means[name] = float(np.mean([c['theta']['pres'] for c in world.cars]))
    assert means['optimistic'] > means['balance'] > means['pessimistic']


# ----------------------------------------------------------------------
# 4. Les agents matérialisés héritent bien du partage
# ----------------------------------------------------------------------

def test_materialized_agents_share_grid_and_positions():
    grid = generate_grid_spec(config_for('balance'), SEED)
    fleet = generate_fleet_spec(config_for('balance'), SEED, 12)

    built = {}
    for name in SCENARIOS:
        config = config_for(name)
        built[name] = build_world(compose_world_spec(grid, fleet, config), config)

    ref_cars, ref_stations, ref_societies = built['balance']
    for name, (cars, stations, societies) in built.items():
        for station, ref in zip(stations, ref_stations):
            assert np.allclose(station.loc, ref.loc), f'{name} : position station'
            assert station.nb_charg_spot == ref.nb_charg_spot
            assert station.alpha == ref.alpha
            assert station.society_id == ref.society_id
        for society, ref in zip(societies, ref_societies):
            assert society.strategy == ref.strategy, f'{name} : stratégie société'
        for car, ref in zip(cars, ref_cars):
            assert np.allclose(car.loc, ref.loc), f'{name} : position véhicule'
            assert car.autonomy == ref.autonomy
            assert car.pref == ref.pref
            assert car.charging_power == ref.charging_power


# ----------------------------------------------------------------------
# 5. De bout en bout : une campagne réelle
# ----------------------------------------------------------------------

def test_run_grid_shares_one_grid_across_every_case():
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        grid = store.load_grid()
        expected = [(s['m'], s['loc'], s['nb_charg_spot'], s['society_id'])
                    for s in grid.stations]

        for scenario, nb_cars in params.worlds():
            world = store.load_world(scenario, nb_cars)
            assert world.grid_seed == grid.seed
            got = [(s['m'], s['loc'], s['nb_charg_spot'], s['society_id'])
                   for s in world.stations]
            assert got == expected, f'grille différente pour {scenario}/{nb_cars}'

        # Toutes les lignes du résumé pointent la même grille et la même graine.
        summary = store.read_summary()
        assert len({row['grid_seed'] for row in summary}) == 1
        assert len({row['world_seed'] for row in summary}) == 1


def test_run_grid_shares_car_positions_across_scenarios():
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        for nb_cars in params.fleet_sizes:
            fleet = store.load_fleet(nb_cars)
            expected = [c['loc'] for c in fleet.cars]
            thetas = {}
            for scenario in params.scenarios:
                world = store.load_world(scenario, nb_cars)
                assert [c['loc'] for c in world.cars] == expected, \
                    f'positions initiales différentes pour {scenario}/{nb_cars}'
                thetas[scenario] = [c['theta'] for c in world.cars]
            assert thetas['optimistic'] != thetas['pessimistic'], \
                'les scénarios doivent malgré tout différer par theta'


def test_prepare_shared_world_persists_before_any_simulation():
    """La grille doit être exploitable même si la campagne échoue au premier cas."""
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = RunStore.create(params)
        grid, fleets = prepare_shared_world(params, store)

        assert store.grid_path.is_file()
        assert store.load_grid().to_dict() == grid.to_dict()
        assert set(fleets) == set(params.fleet_sizes)
        for nb_cars, fleet in fleets.items():
            assert store.load_fleet(nb_cars).to_dict() == fleet.to_dict()

        stations = store.read_shared_table('grid_stations')
        assert len(stations) == params.nb_stations
        assert {row['station_id'] for row in stations} == set(range(params.nb_stations))
        assert all(row['grid_seed'] == grid.seed for row in stations)
        assert any(key.startswith('strategy_') for key in stations[0])

        societies = store.read_shared_table('grid_societies')
        assert len(societies) == params.nb_societies
        assert sum(row['nb_stations'] for row in societies) == params.nb_stations

        for nb_cars in params.fleet_sizes:
            cars = store.read_shared_table(f'fleet_{nb_cars}cars')
            assert len(cars) == nb_cars
            assert all(row['nb_cars'] == nb_cars for row in cars)


def test_shared_tables_match_the_specs():
    grid = generate_grid_spec(config_for('balance'), SEED)
    fleet = generate_fleet_spec(config_for('balance'), SEED, 12)

    station_rows = tables.grid_station_table(grid)
    assert len(station_rows) == grid.nb_stations
    for row, station in zip(station_rows, grid.stations):
        assert row['station_id'] == station['m']
        assert (row['x_m'], row['y_m']) == tuple(station['loc'])
        assert row['alpha_init'] == station['alpha']
        strategy = next(s['strategy'] for s in grid.societies
                        if s['f_id'] == station['society_id'])
        assert row['strategy_pres'] == strategy['pres']

    car_rows = tables.fleet_table(fleet)
    assert len(car_rows) == fleet.nb_cars
    for row, car in zip(car_rows, fleet.cars):
        assert row['car_id'] == car['idx']
        assert (row['x_m'], row['y_m']) == tuple(car['loc'])
        assert row['autonomy_km'] == car['autonomy'] / 1e3
        assert row['noise_pres'] == car['behavior_noise']['pres']
    # `theta` dépend du scénario : il n'a rien à faire dans une table de flotte.
    assert not any(key.startswith('theta') for key in car_rows[0])


def test_methods_still_share_the_world_within_a_scenario():
    """Le partage entre scénarios ne doit pas casser celui entre méthodes."""
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        for scenario, nb_cars in params.worlds():
            per_method = {
                method: store.load_result(CaseParams(scenario, nb_cars, method))
                for method in params.methods
            }
            capacities = {
                method: tuple(s['nb_charg_spot'] for s in sorted(
                    result['stations'], key=lambda s: s['station_id']))
                for method, result in per_method.items()
            }
            assert len(set(capacities.values())) == 1, f'{scenario}/{nb_cars}'


# ----------------------------------------------------------------------

def main() -> int:
    tests = [(name, obj) for name, obj in sorted(globals().items())
             if name.startswith('test_') and callable(obj)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f'  ok    {name}')
        except Exception as exc:
            failures.append((name, traceback.format_exc()))
            print(f'  FAIL  {name}: {exc}')

    print(f'\n{len(tests) - len(failures)}/{len(tests)} tests réussis')
    for name, tb in failures:
        print(f'\n===== {name} =====\n{tb}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
