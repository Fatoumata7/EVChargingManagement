"""
test_pipeline.py — Tests du pipeline (paramètres, stockage, exécution, figures).

    python -m tests.test_pipeline

Complète `tests/test_priority1.py`, qui couvre la correction du modèle. Ici on
vérifie l'orchestration : validation des paramètres, disposition et relecture
des artefacts, environnement partagé entre méthodes, régénération des figures
sans simulation, et interface en ligne de commande.
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

import src.experiments.methods as methods
from src.pipeline import figures, tables
from src.pipeline.cli import EXIT_ERROR, EXIT_OK, main as cli_main
from src.pipeline.params import CaseParams, ExperimentParams, ParamsError
from src.pipeline.runner import run_grid
from src.pipeline.store import RunStore


def tiny_params(**overrides) -> ExperimentParams:
    """Campagne minimale mais représentative : 2 flottes x 2 méthodes."""
    base = dict(
        seed=11,
        scenarios=('pessimistic',),
        fleet_sizes=(12, 18),
        methods=('greedy', 'bramev'),
        total_time=60,
        nb_stations=6,
        nb_societies=2,
        log_every=10 ** 6,
        figures=False,
    )
    base.update(overrides)
    return ExperimentParams(**base)


# ----------------------------------------------------------------------
# Paramètres
# ----------------------------------------------------------------------

def test_params_defaults_match_report_grid():
    params = ExperimentParams()
    # La grille par défaut est l'échelle d'ablation : 4 barreaux, dont les deux
    # méthodes historiques (`greedy` et `bramev`).
    assert params.methods == methods.LADDER
    assert params.nb_cases == 3 * 5 * 4
    assert params.total_time == 1440
    assert len(list(params.cases())) == params.nb_cases
    assert len(list(params.worlds())) == 3 * 5


def test_params_expand_method_groups_and_aliases():
    assert ExperimentParams(methods=('ablation',)).methods == methods.LADDER
    assert ExperimentParams(methods=('nearest',)).methods == ('greedy',)
    assert ExperimentParams(methods=('all',)).methods == methods.METHOD_NAMES
    # Un groupe et un nom déjà couvert par ce groupe ne produisent pas de doublon.
    assert ExperimentParams(methods=('ablation', 'greedy')).methods == methods.LADDER
    assert ExperimentParams(methods=('bramev', 'variants')).methods == \
        ('bramev',) + methods.VARIANTS


def test_params_reject_invalid_values():
    bad_cases = [
        {'scenarios': ['inconnu']},
        {'methods': ['random']},
        {'fleet_sizes': []},
        {'fleet_sizes': [50, 50]},
        {'total_time': 0},
        {'seed': -1},
        {'nb_societies': 99, 'nb_stations': 10},
        {'late_cancel_fraction': 1.5},
        {'nb_charg_spot_low': 8, 'nb_charg_spot_high': 4},
    ]
    for kwargs in bad_cases:
        try:
            ExperimentParams(**kwargs)
        except ParamsError:
            continue
        raise AssertionError(f"aurait dû être refusé : {kwargs}")


def test_params_reject_unknown_keys():
    try:
        ExperimentParams.from_mapping({'nb_voitures': 50})
    except ParamsError as exc:
        assert 'nb_voitures' in str(exc)
        return
    raise AssertionError("une clé inconnue doit être refusée")


def test_params_roundtrip_through_json_and_yaml():
    params = tiny_params(label='essai')
    with tempfile.TemporaryDirectory() as tmp:
        for suffix, dump in (('.json', json.dumps),
                             ('.yaml', _yaml_dump)):
            path = Path(tmp) / f'params{suffix}'
            path.write_text(dump(params.to_dict()), encoding='utf-8')
            reloaded = ExperimentParams.from_file(path)
            assert reloaded.to_dict() == params.to_dict(), suffix
            assert reloaded._source == str(path)


def _yaml_dump(data: dict) -> str:
    import yaml
    return yaml.safe_dump(data, allow_unicode=True)


def test_params_cli_overrides_win_over_config_file():
    params = tiny_params(seed=1, fleet_sizes=(10,))
    merged = params.merged_with({'seed': 99, 'fleet_sizes': None})
    assert merged.seed == 99
    assert merged.fleet_sizes == (10,), "None ne doit pas écraser le fichier"
    try:
        params.merged_with({'inconnu': 1})
    except ParamsError:
        return
    raise AssertionError("une surcharge inconnue doit être refusée")


def test_params_build_config_has_no_side_effect():
    params = tiny_params()
    a = params.build_config('pessimistic', 12)
    b = params.build_config('optimistic', 18)
    assert a.NB_CARS == 12 and b.NB_CARS == 18
    assert a.SCENARIO_NAME == 'pessimistic' and b.SCENARIO_NAME == 'optimistic'
    assert a.SEED == b.SEED == params.seed
    assert a.VISUALIZE is False, "le pipeline doit rester non interactif"


def test_params_shared_config_ignores_the_scenario():
    """
    La config des tirages partagés ne doit pas être scénarisée : c'est ce qui
    rend la grille et les flottes structurellement identiques d'un scénario à
    l'autre (cf. `tests/test_shared_world.py` pour l'invariance obtenue).
    """
    params = tiny_params()
    shared = params.build_shared_config()
    assert shared.SCENARIO_NAME == 'custom'
    assert shared.NB_CARS == params.max_fleet_size
    assert shared.NB_STATIONS == params.nb_stations

    # ...alors que la config d'un cas l'est, elle.
    case_config = params.build_config('pessimistic', params.fleet_sizes[0])
    assert case_config.SCENARIO_NAME == 'pessimistic'
    assert case_config.BASE_CANCEL_PROB != shared.BASE_CANCEL_PROB


# ----------------------------------------------------------------------
# Stockage
# ----------------------------------------------------------------------

def test_store_layout_and_roundtrip():
    params = tiny_params()
    with tempfile.TemporaryDirectory() as tmp:
        store = RunStore.create(tiny_params(output_root=tmp))
        assert store.params_path.is_file() and store.manifest_path.is_file()
        for directory in (store.fleets_dir, store.worlds_dir,
                          store.results_dir, store.tables_dir,
                          store.figures_dir, store.logs_dir):
            assert directory.is_dir()

        reloaded = store.read_params()
        assert reloaded.seed == params.seed
        assert reloaded.fleet_sizes == params.fleet_sizes

        case = CaseParams('pessimistic', 12, 'bramev')
        store.save_result(case, {'mode': 'bramev', 'value': 1})
        assert store.has_result(case)
        assert store.load_result(case)['value'] == 1

        store.write_table(case, 'demo', [{'a': 1, 'b': 'x'}])
        assert store.table_path(case, 'demo').is_file()
        assert store.write_table(case, 'vide', []) is None

        assert RunStore.list_runs(tmp) == [store.root]
        assert RunStore.latest(tmp).root == store.root


def test_store_summary_roundtrip_preserves_types():
    with tempfile.TemporaryDirectory() as tmp:
        store = RunStore.create(tiny_params(output_root=tmp))
        rows = [{'scenario': 'pessimistic', 'nb_cars': 12, 'method': 'bramev',
                 'exact_satisfaction': 0.5, 'invariant_ok': True,
                 'mean_lead_slots': None}]
        store.write_summary(rows, ('scenario', 'nb_cars', 'method',
                                   'exact_satisfaction', 'invariant_ok',
                                   'mean_lead_slots'))
        back = store.read_summary()[0]
        assert back['nb_cars'] == 12 and isinstance(back['nb_cars'], int)
        assert back['exact_satisfaction'] == 0.5
        assert back['invariant_ok'] is True
        assert back['mean_lead_slots'] is None


def test_store_open_rejects_non_run_directory():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            RunStore.open(tmp)
        except FileNotFoundError:
            return
    raise AssertionError("un dossier sans params.json doit être refusé")


# ----------------------------------------------------------------------
# Exécution
# ----------------------------------------------------------------------

def test_run_grid_produces_all_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        summary = store.read_summary()
        assert len(summary) == params.nb_cases
        assert set(summary[0]) == set(tables.SUMMARY_FIELDS)

        for case in params.cases():
            assert store.has_result(case), case.tag
            for table in ('stations', 'behaviors', 'latency'):
                assert store.table_path(case, table).is_file(), f'{case.tag}/{table}'

        for scenario, nb_cars in params.worlds():
            assert store.world_path(scenario, nb_cars).is_file()

        # L'environnement partagé, persisté avant toute simulation.
        assert store.grid_path.is_file()
        assert store.shared_table_path('grid_stations').is_file()
        assert store.shared_table_path('grid_societies').is_file()
        for nb_cars in params.fleet_sizes:
            assert store.fleet_path(nb_cars).is_file()
            assert store.shared_table_path(f'fleet_{nb_cars}cars').is_file()

        manifest = store.read_manifest()
        assert manifest['nb_cases_done'] == params.nb_cases
        assert manifest['finished_utc'] and manifest['total_wall_time_s'] >= 0
        assert all(c['invariant_ok'] for c in manifest['cases'])
        assert all(row['invariant_ok'] for row in summary)


def test_run_grid_compares_methods_on_the_same_world():
    """Le cœur de l'équité : un monde par (scénario, flotte), pas par méthode."""
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        for scenario, nb_cars in params.worlds():
            per_method = {}
            for method in params.methods:
                result = store.load_result(CaseParams(scenario, nb_cars, method))
                per_method[method] = result
            world_seeds = {r['world_seed'] for r in per_method.values()}
            assert len(world_seeds) == 1, f'{scenario}/{nb_cars}: {world_seeds}'

            # mêmes stations, mêmes capacités : seul le comportement diffère
            capacities = {
                method: [s['nb_charg_spot'] for s in sorted(
                    result['stations'], key=lambda s: s['station_id'])]
                for method, result in per_method.items()
            }
            assert len(set(map(tuple, capacities.values()))) == 1
            alphas = {
                method: [s['alpha'] for s in sorted(
                    result['stations'], key=lambda s: s['station_id'])]
                for method, result in per_method.items()
            }
            # Greedy n'apprend pas : ses alphas restent ceux du monde initial,
            # qui sont donc un sous-ensemble de ceux vus par BRAM-EV au départ.
            assert len(alphas['greedy']) == len(alphas['bramev'])


def test_run_grid_is_reproducible():
    with tempfile.TemporaryDirectory() as tmp:
        first = run_grid(tiny_params(output_root=str(Path(tmp) / 'a')))
        second = run_grid(tiny_params(output_root=str(Path(tmp) / 'b')))

        def comparable(rows):
            drop = {'wall_time_s', 'total_ms_mean', 'total_ms_p95',
                    'last_offer_ms_mean', 'last_offer_ms_p95',
                    'first_offer_ms_mean', 'selection_ms_mean',
                    'confirmation_ms_mean', 'mean_processing_ms'}
            return [{k: v for k, v in row.items() if k not in drop} for row in rows]

        assert comparable(first.read_summary()) == comparable(second.read_summary())


def test_run_grid_writes_summary_incrementally():
    """Une campagne interrompue doit laisser un summary.csv déjà valide."""
    seen = []
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp, fleet_sizes=(12,))
        store = RunStore.create(params)

        def after_case(outcome):
            rows = store.read_summary()
            seen.append(len(rows))
            assert set(rows[0]) == set(tables.SUMMARY_FIELDS)

        run_grid(params, store=store, on_case=after_case)
    assert seen == [1, 2], seen


# ----------------------------------------------------------------------
# Tables & figures
# ----------------------------------------------------------------------

def test_tables_carry_case_identity():
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp, fleet_sizes=(12,), methods=('bramev',))
        store = run_grid(params)
        case = CaseParams('pessimistic', 12, 'bramev')
        result = store.load_result(case)

        for builder in (tables.station_table, tables.behavior_table):
            rows = builder(result)
            assert rows
            for row in rows:
                assert row['scenario'] == 'pessimistic'
                assert row['nb_cars'] == 12
                assert row['method'] == 'bramev'
                assert row['world_seed'] == result['world_seed']

        summary = tables.summary_row(result)
        stations = tables.station_table(result)
        assert summary['nb_reservations'] == sum(s['nb_reservations'] for s in stations)
        assert summary['nb_offer_issued'] == sum(s['nb_offer_issued'] for s in stations)


def test_figures_are_rebuilt_from_summary_only():
    """`report` doit fonctionner sans les objets de simulation."""
    with tempfile.TemporaryDirectory() as tmp:
        store = run_grid(tiny_params(output_root=tmp))
        summary = store.read_summary()

        grid_rows = store.read_shared_table('grid_stations')
        society_rows = store.read_shared_table('grid_societies')
        fleet_rows = {n: store.read_shared_table(f'fleet_{n}cars')
                      for n in store.read_params().fleet_sizes}

        written = figures.render_all(summary, store.figures_dir,
                                     grid_rows=grid_rows,
                                     society_rows=society_rows,
                                     fleet_rows=fleet_rows)
        assert written, 'aucune figure produite'
        assert all(path.is_file() and path.stat().st_size > 0 for path in written)
        names = {path.name for path in written}
        assert 'satisfaction_pessimistic.png' in names
        assert 'intent_vs_observed.png' in names
        assert 'grid.png' in names, "la grille partagée doit être tracée"
        assert all(f'fleet_{n}cars.png' in names for n in fleet_rows)

        # idempotent : régénérer écrit le même ensemble de fichiers
        again = figures.render_all(summary, store.figures_dir,
                                   grid_rows=grid_rows,
                                   society_rows=society_rows,
                                   fleet_rows=fleet_rows)
        assert {p.name for p in again} == names

        # Sans les tables partagées, le rendu doit rester possible.
        summary_only = figures.render_all(summary, store.figures_dir)
        assert summary_only and 'grid.png' not in {p.name for p in summary_only}


def test_figures_tolerate_partial_campaign():
    """Une campagne à une seule méthode ne doit pas faire échouer le rendu."""
    rows = [{'scenario': 'balance', 'nb_cars': 50, 'method': 'greedy',
             'exact_satisfaction': 0.9, 'needs_satisfaction': 0.92,
             'mean_travel_distance_km': 0.5, 'mean_waiting_time_min': 0.,
             'nb_reservations': 10, 'nb_pres': 8, 'nb_no_show': 1,
             'nb_early_canc': 0, 'nb_late_canc': 1,
             'answer_rate': 0.8, 'mean_offers_per_demand': 1.0,
             'last_offer_ms_mean': 10., 'selection_ms_mean': 1.,
             'total_ms_mean': 12., 'nb_offer_issued': 10,
             'nb_confirm_refused': 0, 'mean_occupancy_rate': 0.3,
             'total_station_demand_kwh': 100., 'mean_processing_ms': 5.,
             'wall_time_s': 1., 'intent_pres': 0.6, 'intent_abs': 0.2,
             'intent_early': 0.12, 'intent_late': 0.08,
             'rate_pres': 0.8, 'rate_abs': 0.1, 'rate_early': None,
             'rate_late': 0.1}]
    with tempfile.TemporaryDirectory() as tmp:
        written = figures.render_all(rows, tmp)
        assert written
    assert figures.render_all([], tmp) == []


# ----------------------------------------------------------------------
# Interface en ligne de commande
# ----------------------------------------------------------------------

def test_cli_dry_run_does_not_write():
    with tempfile.TemporaryDirectory() as tmp:
        code = cli_main(['-q', 'run', '--dry-run', '--output-root', tmp,
                         '--scenarios', 'balance', '--cars', '10',
                         '--total-time', '24'])
        assert code == EXIT_OK
        assert RunStore.list_runs(tmp) == []


def test_cli_run_report_show_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        code = cli_main(['-q', 'run', '--output-root', tmp, '--seed', '5',
                         '--scenarios', 'balance', '--cars', '12',
                         '--methods', 'greedy', 'bramev',
                         '--total-time', '48', '--nb-stations', '6',
                         '--nb-societies', '2', '--log-every', '1000',
                         '--no-save-latency', '--label', 'test cli'])
        assert code == EXIT_OK

        runs = RunStore.list_runs(tmp)
        assert len(runs) == 1
        assert runs[0].name.endswith('_test-cli'), runs[0].name

        store = RunStore.open(runs[0])
        case = CaseParams('balance', 12, 'greedy')
        assert not store.table_path(case, 'latency').is_file(), \
            '--no-save-latency doit désactiver la table de latence'
        assert store.table_path(case, 'stations').is_file()

        assert cli_main(['-q', 'report', '--run-dir', str(runs[0])]) == EXIT_OK
        assert list(store.figures_dir.glob('*.png'))
        assert cli_main(['-q', 'show', '--latest', '--output-root', tmp]) == EXIT_OK
        assert cli_main(['-q', 'runs', '--output-root', tmp]) == EXIT_OK
        assert cli_main(['-q', 'scenarios']) == EXIT_OK


def test_cli_reports_errors_without_traceback():
    with tempfile.TemporaryDirectory() as tmp:
        assert cli_main(['-q', 'show', '--run-dir', tmp]) == EXIT_ERROR
        assert cli_main(['-q', 'run', '--config', str(Path(tmp) / 'absent.yaml')]) \
            == EXIT_ERROR
        assert cli_main(['-q', 'show', '--latest', '--output-root', tmp]) == EXIT_ERROR


def test_cli_config_file_is_overridden_by_options():
    import yaml
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / 'campagne.yaml'
        config_path.write_text(yaml.safe_dump({
            'seed': 3, 'scenarios': ['balance'], 'fleet_sizes': [10],
            'methods': ['greedy'], 'total_time': 24, 'nb_stations': 5,
            'nb_societies': 2, 'output_root': tmp, 'figures': False,
        }), encoding='utf-8')

        assert cli_main(['-q', 'run', '--dry-run', '--config', str(config_path)]) == EXIT_OK
        assert cli_main(['-q', 'run', '--config', str(config_path),
                         '--seed', '4', '--log-every', '1000']) == EXIT_OK

        store = RunStore.latest(tmp)
        params = store.read_params()
        assert params.seed == 4, 'la CLI doit primer sur le fichier'
        assert params.fleet_sizes == (10,), 'le reste doit venir du fichier'


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
