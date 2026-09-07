"""
test_ablation.py — Tests of the ablation study.

    python -m tests.test_ablation

What these tests protect, in order of importance:

1. **One component at a time.** Two consecutive rungs of the ladder differ by
   one flag only. If that property breaks, a measured gap is no longer
   attributable to a component and the whole study becomes wrong without any
   result looking abnormal.
2. **The flags actually reach the agents.** A flag declared but never read
   would produce two identical methods — and a zero contribution that would be
   read as "this component is good for nothing".
3. **The decomposition is faithful.** The published gaps must be those of
   `summary.csv`, with the right direction (a drop in no-shows is a gain, a
   drop in satisfaction is not).
"""

from __future__ import annotations

import io
import sys
import tempfile
import traceback
from pathlib import Path

import src.experiments.config as cfg_module
import src.experiments.methods as methods
from src.env.offer import Offer
from src.experiments.simulation import Simulation
from src.experiments.world import build_world, compose_world_spec, \
    generate_fleet_spec, generate_grid_spec
from src.pipeline import ablation
from src.pipeline.params import ExperimentParams
from src.pipeline.runner import run_grid
from src.pipeline.store import RunStore


def tiny_params(**overrides) -> ExperimentParams:
    base = dict(
        seed=13,
        scenarios=('pessimistic',),
        fleet_sizes=(12,),
        methods=('ablation',),
        total_time=48,
        nb_stations=6,
        nb_societies=2,
        log_every=10 ** 6,
        figures=False,
        save_latency=False,
    )
    base.update(overrides)
    return ExperimentParams(**base)


def build_agents(params: ExperimentParams, scenario='pessimistic', nb_cars=12):
    """A materialised world, identical to the one the runner builds."""
    config = params.build_config(scenario, nb_cars)
    shared = params.build_shared_config(nb_cars)
    grid = generate_grid_spec(shared, params.seed)
    fleet = generate_fleet_spec(shared, params.seed, nb_cars)
    spec = compose_world_spec(grid, fleet, config)
    return build_world(spec, config), config


# ----------------------------------------------------------------------
# Registry: the structure of the ladder
# ----------------------------------------------------------------------

def test_ladder_changes_exactly_one_component_per_step():
    components = ('broadcast', 'use_reputation', 'collective_learning')
    for before, after, label in methods.LADDER_STEPS:
        a, b = methods.resolve(before), methods.resolve(after)
        changed = [c for c in components if getattr(a, c) != getattr(b, c)]
        assert len(changed) == 1, (
            f'{before} -> {after} change {changed}, or un barreau doit ajouter '
            f'exactement un composant ({label})')
        assert getattr(b, changed[0]) is True, 'a rung adds, it does not remove'
        # The internal mechanisms stay those of BRAM-EV throughout.
        for field in ('offer_choice', 'alpha_mode', 'reputation_scope',
                      'score_weighting'):
            assert getattr(a, field) == getattr(b, field), (
                f'{field} varie entre {before} et {after} : le barreau '
                'would mix two effects')


def test_ladder_endpoints_are_the_historical_methods():
    assert methods.LADDER[0] == 'greedy'
    assert methods.LADDER[-1] == 'bramev'
    assert methods.canonical('nearest') == 'greedy'


def test_each_variant_differs_from_bramev_by_one_mechanism():
    full = methods.resolve('bramev')
    fields = ('broadcast', 'use_reputation', 'collective_learning',
              'offer_choice', 'alpha_mode', 'reputation_scope',
              'score_weighting')
    for name in methods.VARIANTS:
        spec = methods.resolve(name)
        changed = [f for f in fields if getattr(full, f) != getattr(spec, f)]
        assert changed == [f for f in fields if f in changed] and len(changed) == 1, (
            f'{name} differs from bramev on {changed}: a variant must '
            'must neutralise a single mechanism')
        assert name in ablation.VARIANT_MECHANISM, (
            f'{name} has no mechanism label in the tables')


def test_unknown_method_is_rejected_with_a_situated_message():
    try:
        methods.resolve('inexistante')
    except KeyError as exc:
        assert 'inexistante' in str(exc)
    else:
        raise AssertionError('an unknown method must raise KeyError')


# ----------------------------------------------------------------------
# The flags do reach the agents
# ----------------------------------------------------------------------

def test_flags_reach_stations():
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    alphas_before = [s.alpha for s in stations]

    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_global_rep')
    assert {s.score_index for s in stations} == {0}, \
        'global reputation: every station must read the same slot'

    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_event_score')
    assert {s.score_weighting for s in stations} == {'event'}

    config.set_ALPHA_FIXED(0.42)
    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_fixed_alpha')
    assert {round(s.alpha, 6) for s in stations} == {0.42}
    assert all(s.alpha_save == [0.42] for s in stations), \
        'the alpha trajectory must reflect the value actually used'

    # A method with no alpha flag does not touch the alphas of the world.
    (cars, stations, societies), config = build_agents(params)
    Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode='bramev')
    assert [s.alpha for s in stations] == alphas_before


def test_score_weighting_changes_the_penalty():
    """
    Since the score is a bounded mean over a sliding window, the duration acts
    *relatively*: it decides the weight of each outcome in the mean, not the
    absolute amplitude of the score.

    So a heterogeneous window is compared — a short presence followed by a long
    no-show. Under duration weighting the no-show dominates; under flat
    weighting the two outcomes count the same.
    """
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    station = stations[0]
    car = cars[0]

    def window(mode):
        Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode=mode)
        car.reset_score()
        station.update_car_score(car, 'pres', 1)    # short presence
        station.update_car_score(car, 'abs', 20)    # no-show long
        return float(car.score[station.score_index])

    proportional = window('bramev')
    per_event = window('bramev_event_score')

    assert proportional < per_event, (
        'weighted by duration, the window must be dominated by the no-show '
        f'long : {proportional} vs {per_event} (forfaitaire)'
    )
    assert -1. <= proportional <= 1. and -1. <= per_event <= 1.

    # On a window homogeneous in duration, both weightings coincide:
    # that is the counterpart of the bounding, and it must be explicit.
    def homogeneous(mode):
        Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode=mode)
        car.reset_score()
        station.update_car_score(car, 'abs', 10)
        station.update_car_score(car, 'abs', 10)
        return float(car.score[station.score_index])

    assert abs(homogeneous('bramev') - homogeneous('bramev_event_score')) < 1e-12


def test_reputation_scope_separates_or_shares_the_score():
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    car = cars[0]
    by_society = {}
    for station in stations:
        by_society.setdefault(station.society_id, station)
    if len(by_society) < 2:
        return          # grid too small to distinguish the two scopes

    first, second = list(by_society.values())[:2]

    Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode='bramev')
    car.reset_score()
    first.update_car_score(car, 'abs', 4)
    assert car.score[second.score_index] == 0., \
        'per-company reputation: a company does not suffer the score written by another'

    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_global_rep')
    car.reset_score()
    first.update_car_score(car, 'abs', 4)
    assert car.score[second.score_index] < 0., \
        'global reputation: the score written by one company is read by the others'


def test_offer_choice_nearest_ignores_utility():
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    car = cars[0]
    request = {'n': 'test', 't_n': 0, 'd_n': 6, 'loc': (0., 0.),
               'r_n': 5000., 'g_n': 12}

    def offer(station_id, distance, d_prop, t_arr):
        return Offer(station_id=station_id, charger_id=0, t_arr=t_arr,
                     t_dep=t_arr + d_prop, d_prop=d_prop, distance=distance)

    # The nearest one is also the worst: partial duration and waiting.
    near_but_poor = offer(1, distance=100., d_prop=1, t_arr=10)
    far_but_good = offer(2, distance=4000., d_prop=6, t_arr=0)
    offers = [far_but_good, near_but_poor]

    best_utility, _ = car.rank_offers(offers, request, 100., 'utility')[0]
    best_nearest, _ = car.rank_offers(offers, request, 100., 'nearest')[0]
    assert best_utility is far_but_good
    assert best_nearest is near_but_poor

    try:
        car.rank_offers(offers, request, 100., 'inconnu')
    except ValueError:
        pass
    else:
        raise AssertionError('an unknown criterion must be refused')


# ----------------------------------------------------------------------
# Decomposition
# ----------------------------------------------------------------------

def _summary(method: str, **values) -> dict:
    row = {'scenario': 'pessimistic', 'nb_cars': 10, 'world_seed': 1,
           'method': method}
    row.update(values)
    return row


def test_ladder_rows_measure_consecutive_steps_only():
    rows = [_summary(m, exact_satisfaction=v) for m, v in
            (('greedy', 0.50), ('multistation', 0.60),
             ('multistation_rep', 0.66), ('bramev', 0.72))]
    detail = [r for r in ablation.ladder_rows(rows)
              if r['metric'] == 'exact_satisfaction']
    assert len(detail) == 3
    by_component = {r['component']: r for r in detail}
    assert round(by_component['Multi-station search']['delta'], 6) == 0.10
    assert round(by_component['Reputation']['delta'], 6) == 0.06
    assert round(by_component['Cross-station adaptation']['delta'], 6) == 0.06
    # The contributions sum to the total gap between the two endpoints.
    assert abs(sum(r['delta'] for r in detail) - (0.72 - 0.50)) < 1e-9
    assert all(r['improvement'] for r in detail)


def test_improvement_follows_the_metric_direction():
    rows = [_summary('greedy', rate_abs=0.30, exact_satisfaction=0.50),
            _summary('multistation', rate_abs=0.20, exact_satisfaction=0.40)]
    detail = {r['metric']: r for r in ablation.ladder_rows(rows)}
    assert detail['rate_abs']['delta'] < 0 and detail['rate_abs']['improvement'], \
        'fewer no-shows is a gain'
    assert not detail['exact_satisfaction']['improvement'], \
        'less satisfaction is not a gain'


def test_variant_rows_compare_to_the_full_method():
    rows = [_summary('bramev', exact_satisfaction=0.70),
            _summary('bramev_global_rep', exact_satisfaction=0.60)]
    detail = [r for r in ablation.variant_rows(rows)
              if r['metric'] == 'exact_satisfaction']
    assert len(detail) == 1
    row = detail[0]
    assert row['from_method'] == 'bramev' and row['to_method'] == 'bramev_global_rep'
    assert row['component'] == 'Per-company reputation'
    assert not row['improvement'], \
        'neutralising the per-company reputation degrades here: the mechanism is useful'


def test_mean_rows_report_robustness_not_only_the_average():
    rows = []
    for world, (before, after) in enumerate([(0.50, 0.60), (0.50, 0.45)]):
        rows.append(_summary('greedy', exact_satisfaction=before) | {'nb_cars': world})
        rows.append(_summary('multistation', exact_satisfaction=after) | {'nb_cars': world})
    means = [r for r in ablation.mean_rows(ablation.ladder_rows(rows))
             if r['metric'] == 'exact_satisfaction']
    assert len(means) == 1
    assert means[0]['nb_worlds'] == 2
    assert means[0]['share_improved'] == 0.5, \
        'a component that only helps half of the worlds must show'


def test_duplicate_methods_in_summary_are_rejected():
    rows = [_summary('greedy', exact_satisfaction=0.5),
            _summary('greedy', exact_satisfaction=0.6)]
    try:
        ablation.ladder_rows(rows)
    except ValueError as exc:
        assert 'duplicates' in str(exc)
    else:
        raise AssertionError('a duplicated summary.csv must be refused')


def test_incomparable_run_produces_no_table():
    rows = [_summary('bramev', exact_satisfaction=0.7)]
    assert ablation.detail_rows(rows) == []


# ----------------------------------------------------------------------
# Shipped configurations
# ----------------------------------------------------------------------

def test_shipped_configs_declare_their_methods():
    """
    Every preset of `experiments/` must declare `methods` explicitly.

    `ExperimentParams.methods` has a default value — the ablation ladder. A
    file that omits the key therefore raises no error: it silently runs a
    *different* campaign from the one its comments describe. It happened:
    `ablation_variants.yaml` deprived of its `methods` line redid the ladder for
    21 h under the label of the variants.
    """
    import yaml

    configs = sorted(Path('experiments').glob('*.yaml'))
    assert configs, 'no shipped configuration found'

    for path in configs:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        assert 'methods' in data, (
            f"{path} does not declare `methods`: the campaign would fall back on "
            f"the default {list(methods.LADDER)} without reporting anything")
        params = ExperimentParams.from_file(path)
        assert params.methods, f'{path}: empty method list'


def test_variants_config_actually_runs_the_variants():
    """
    The variants preset must contain the reference *and* the four variants:
    without `bramev` no gap is computable; without the variants there is
    nothing to compare.
    """
    params = ExperimentParams.from_file('experiments/ablation_variants.yaml')
    assert set(params.methods) == {'bramev'} | set(methods.VARIANTS), (
        f'methods={list(params.methods)}')


def test_ablation_config_runs_the_ladder_and_the_baselines():
    """
    The ablation preset carries two plans at once: the complete ladder —
    without which no component contribution is computable — and the three
    baselines, which compare against `bramev`. Both are read on the same world,
    which is the whole point of running them in the same campaign.
    """
    params = ExperimentParams.from_file('experiments/ablation.yaml')
    missing = set(methods.LADDER) - set(params.methods)
    assert not missing, f'incomplete ladder, missing {sorted(missing)}'
    missing = set(methods.BASELINES) - set(params.methods)
    assert not missing, f'baselines manquantes : {sorted(missing)}'
    # The ladder keeps its order: the rungs read in the order components are added.
    rang = {m: i for i, m in enumerate(params.methods)}
    assert [rang[m] for m in methods.LADDER] == sorted(rang[m] for m in methods.LADDER)


def test_reference_config_compares_bramev_to_every_baseline():
    """`full_grid.yaml` is the published comparison: BRAM-EV against the baselines."""
    params = ExperimentParams.from_file('experiments/full_grid.yaml')
    assert 'bramev' in params.methods, 'without bramev, no computable gap'
    missing = set(methods.BASELINES) - set(params.methods)
    assert not missing, f'baselines manquantes : {sorted(missing)}'
    assert 'greedy' in params.methods, 'the single-station floor must stay readable'


# ----------------------------------------------------------------------
# Reference baselines
# ----------------------------------------------------------------------

def test_baselines_are_pure_choice_policies():
    """
    The three baselines must differ from `multistation` only by the offer
    selection rule. Same broadcast, same radius, no reputation and no
    adaptation: at identical information scope, a measured gap is attributable
    to the rule alone.
    """
    assert set(methods.BASELINES) == {'min_waiting', 'load_aware',
                                      'random_feasible'}
    reference = methods.resolve('multistation')
    partages = ('broadcast', 'use_reputation', 'collective_learning',
                'alpha_mode', 'reputation_scope', 'score_weighting')

    for name in methods.BASELINES:
        spec = methods.resolve(name)
        assert spec.family == 'baseline'
        drift = [f for f in partages if getattr(spec, f) != getattr(reference, f)]
        assert not drift, (
            f'{name} differs from multistation on {drift}: a baseline must '
            'must differ only by its choice rule')
        assert spec.offer_choice != reference.offer_choice, (
            f'{name}: a baseline must not use the BRAM-EV utility')

    choices = {methods.resolve(n).offer_choice for n in methods.BASELINES}
    assert choices == {'waiting', 'load', 'random'}, (
        f'each baseline must have its own rule, got {choices}')


def test_baselines_see_the_same_stations_as_multistation():
    """
    The broadcast scope must be *identical* to that of `multistation`: that is
    what makes the gap attributable to the choice rule and not to an
    information advantage.
    """
    params = tiny_params()
    contactees = {}
    for name in ('multistation', 'min_waiting', 'load_aware', 'random_feasible'):
        (cars, stations, societies), config = build_agents(params)
        sim = Simulation(cars, stations, societies, config.TOTAL_TIME, config,
                         mode=name)
        vues = []
        original = Simulation._get_eligible_stations

        def espion(self, x, y, r_n, _v=vues, _o=original):
            eligible, min_d, min_s = _o(self, x, y, r_n)
            _v.append((round(float(r_n), 6), len(eligible)))
            return eligible, min_d, min_s

        Simulation._get_eligible_stations = espion
        try:
            sim.run(io.StringIO(), print_metrics=False)
        finally:
            Simulation._get_eligible_stations = original
        contactees[name] = vues

    assert contactees['multistation'], 'no request emitted: inconclusive test'
    for name in methods.BASELINES:
        assert contactees[name] == contactees['multistation'], (
            f'{name} does not see the same scope as multistation')

    # ... and that scope stays bounded by the search radius.
    assert max(n for _, n in contactees['multistation']) <= params.nb_stations
    assert min(n for _, n in contactees['multistation']) < params.nb_stations, (
        'the radius should exclude at least one station on this grid')


def test_each_baseline_applies_its_own_rule():
    """Each rule must rank the offers according to its own criterion."""
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    car = cars[0]
    request = {'n': 'test', 't_n': 0, 'd_n': 6, 'loc': (0., 0.),
               'r_n': 5000., 'g_n': 12, 'l_n': 0}

    # Three offers where waiting, load and distance order differently.
    offers = [
        Offer(station_id=1, charger_id=0, t_arr=9, t_dep=15, d_prop=6,
              distance=100., station_load=0.9),
        Offer(station_id=2, charger_id=0, t_arr=1, t_dep=7, d_prop=6,
              distance=4000., station_load=0.5),
        Offer(station_id=3, charger_id=0, t_arr=5, t_dep=11, d_prop=6,
              distance=2000., station_load=0.1),
    ]

    par_attente = car.rank_offers(offers, request, 100., criterion='waiting')
    assert par_attente[0][0].station_id == 2, 'min_waiting: lowest waiting time'

    par_charge = car.rank_offers(offers, request, 100., criterion='load')
    assert par_charge[0][0].station_id == 3, 'load_aware: least loaded station'

    par_distance = car.rank_offers(offers, request, 100., criterion='nearest')
    assert par_distance[0][0].station_id == 1

    # The three rules must indeed designate different winners here.
    assert len({par_attente[0][0].station_id, par_charge[0][0].station_id,
                par_distance[0][0].station_id}) == 3

    # Every offer received stays ranked, none is discarded.
    for classement in (par_attente, par_charge, par_distance):
        assert len(classement) == len(offers)


def test_random_feasible_is_random_but_reproducible():
    """
    The draw must vary from one request to the next, be identical at equal
    seed, and not depend on the arrival order of the offers — which follows the
    station order and means nothing to the vehicle.
    """
    params = tiny_params()
    request = {'n': 'test', 't_n': 0, 'd_n': 6, 'loc': (0., 0.),
               'r_n': 5000., 'g_n': 12, 'l_n': 0}

    def offers():
        return [Offer(station_id=i, charger_id=0, t_arr=2, t_dep=8, d_prop=6,
                      distance=100. * (i + 1), station_load=0.1 * i)
                for i in range(6)]

    def tirages(car, n=15, ordre=None):
        out = []
        for _ in range(n):
            lot = offers()
            if ordre is not None:
                lot = [lot[i] for i in ordre]
            out.append(car.rank_offers(lot, request, 100.,
                                       criterion='random')[0][0].station_id)
        return out

    (cars_a, *_), config = build_agents(params)
    (cars_b, *_), _ = build_agents(params)

    a = tirages(cars_a[0])
    assert len(set(a)) > 1, 'the draw must vary from one request to the next'

    b = tirages(cars_b[0])
    assert a == b, 'at equal seed, the draw must be reproducible'

    # Arrival order reversed: the result must not change.
    (cars_c, *_), _ = build_agents(params)
    c = tirages(cars_c[0], ordre=list(reversed(range(6))))
    assert a == c, "the draw must not depend on the arrival order of the offers"


def test_baseline_rows_compare_bramev_to_each_baseline():
    """
    The table must read "baseline -> BRAM-EV": a true `improvement` means that
    BRAM-EV does better, which is the question asked of a baseline.
    """
    world = {'scenario': 'balance', 'nb_cars': 50, 'seed': 1,
             'world_seed': 1, 'grid_seed': 1}
    rows = [dict(world, method='bramev', exact_satisfaction=0.90),
            dict(world, method='min_waiting', exact_satisfaction=0.70),
            dict(world, method='load_aware', exact_satisfaction=0.95),
            dict(world, method='random_feasible', exact_satisfaction=0.60)]

    metric = ablation.METRICS_BY_COLUMN['exact_satisfaction']
    produites = ablation.baseline_rows(rows, [metric])
    par_methode = {r['from_method']: r for r in produites}

    assert set(par_methode) == set(methods.BASELINES)
    for r in produites:
        assert r['kind'] == 'baseline'
        assert r['to_method'] == 'bramev'

    assert par_methode['min_waiting']['improvement'] is True
    assert par_methode['load_aware']['improvement'] is False, (
        'a baseline that beats BRAM-EV must appear as such')
    assert abs(par_methode['random_feasible']['delta'] - 0.30) < 1e-9

    # The baselines join the complete detailed table.
    kinds = {r['kind'] for r in ablation.detail_rows(rows, [metric])}
    assert 'baseline' in kinds


# ----------------------------------------------------------------------
# Bout en bout
# ----------------------------------------------------------------------

def test_run_grid_writes_the_ablation_tables():
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = run_grid(params)

        detail = store.read_root_table('ablation')
        means = store.read_root_table('ablation_mean')
        assert detail and means

        components = {r['component'] for r in detail}
        assert components == {label for _, _, label in methods.LADDER_STEPS}

        summary = store.read_summary()
        assert {r['method'] for r in summary} == set(methods.LADDER)
        # The flags travel all the way to summary.csv: the table reads on its own.
        by_method = {r['method']: r for r in summary}
        assert by_method['greedy']['broadcast'] is False
        assert by_method['multistation']['broadcast'] is True
        assert by_method['multistation']['reputation'] is False
        assert by_method['multistation_rep']['reputation'] is True
        assert by_method['multistation_rep']['adaptation'] is False
        assert by_method['bramev']['adaptation'] is True


def test_ablation_tables_are_written_incrementally():
    """
    A complete campaign takes hours. The decomposition tables must therefore
    exist *during* the campaign, like `summary.csv`: otherwise a run still going
    — or interrupted — has nothing to analyse, although every case needed is
    already computed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = RunStore.create(params)
        seen = []

        def apres_chaque_cas(outcome):
            seen.append(outcome.case.method)
            # As soon as two consecutive rungs are done, the table exists.
            if len(seen) >= 2:
                assert store.read_root_table('ablation'), (
                    f'ablation.csv missing after {len(seen)} cases ({seen})')

        run_grid(params, store=store, on_case=apres_chaque_cas)
        assert len(seen) == params.nb_cases


def test_broadcast_actually_contacts_more_stations():
    """
    The first rung must show in the metrics, not only in the flags: without
    that, a zero contribution would be uninterpretable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp, methods=('greedy', 'multistation'),
                             nb_stations=8, fleet_sizes=(16,), total_time=60)
        store = run_grid(params)
        by_method = {r['method']: r for r in store.read_summary()}
        assert (by_method['multistation']['mean_offers_per_demand'] >
                by_method['greedy']['mean_offers_per_demand']), (
            'broadcasting must produce strictly more offers per demand')


def test_occupancy_survives_the_release_of_the_calendar():
    """
    `schedule` is reset to -1 at every session end: an occupancy rate read
    there at the end of the run was 0 for every method. The cumulative counters,
    on the other hand, must reflect the actual activity.
    """
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp, methods=('bramev',),
                             fleet_sizes=(16,), total_time=60)
        store = run_grid(params)
        row = store.read_summary()[0]
        assert row['nb_reservations'] > 0
        assert row['nb_slots_reserved'] > 0
        assert 0. < row['mean_occupancy_rate'] <= 1.
        assert 0. <= row['mean_service_rate'] <= row['mean_occupancy_rate']
        assert row['nb_slots_served'] <= row['nb_slots_reserved']


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

    print(f'\n{len(tests) - len(failures)}/{len(tests)} tests passed')
    for name, tb in failures:
        print(f'\n===== {name} =====\n{tb}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
