"""
test_ablation.py — Tests de l'étude d'ablation.

    python -m tests.test_ablation

Ce que ces tests protègent, dans l'ordre d'importance :

1. **Un composant à la fois.** Deux barreaux consécutifs de l'échelle ne
   diffèrent que par un drapeau. Si cette propriété casse, un écart mesuré
   n'est plus attribuable à un composant et toute l'étude devient fausse sans
   qu'aucun résultat n'ait l'air anormal.
2. **Les drapeaux atteignent les agents.** Un drapeau déclaré mais jamais lu
   produirait deux méthodes identiques — et une contribution nulle qu'on
   interpréterait comme « ce composant ne sert à rien ».
3. **La décomposition est fidèle.** Les écarts publiés doivent être ceux du
   `summary.csv`, avec la bonne direction (une baisse des no-shows est un
   gain, une baisse de la satisfaction n'en est pas un).
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
    """Un monde matérialisé, identique à celui que le runner fabrique."""
    config = params.build_config(scenario, nb_cars)
    shared = params.build_shared_config(nb_cars)
    grid = generate_grid_spec(shared, params.seed)
    fleet = generate_fleet_spec(shared, params.seed, nb_cars)
    spec = compose_world_spec(grid, fleet, config)
    return build_world(spec, config), config


# ----------------------------------------------------------------------
# Registre : la structure de l'échelle
# ----------------------------------------------------------------------

def test_ladder_changes_exactly_one_component_per_step():
    components = ('broadcast', 'use_reputation', 'collective_learning')
    for before, after, label in methods.LADDER_STEPS:
        a, b = methods.resolve(before), methods.resolve(after)
        changed = [c for c in components if getattr(a, c) != getattr(b, c)]
        assert len(changed) == 1, (
            f'{before} -> {after} change {changed}, or un barreau doit ajouter '
            f'exactement un composant ({label})')
        assert getattr(b, changed[0]) is True, 'un barreau ajoute, il ne retire pas'
        # Les mécanismes internes restent ceux de BRAM-EV tout au long.
        for field in ('offer_choice', 'alpha_mode', 'reputation_scope',
                      'score_weighting'):
            assert getattr(a, field) == getattr(b, field), (
                f'{field} varie entre {before} et {after} : le barreau '
                'mélangerait deux effets')


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
            f'{name} diffère de bramev sur {changed} : une variante ne doit '
            'neutraliser qu un seul mécanisme')
        assert name in ablation.VARIANT_MECHANISM, (
            f'{name} n a pas de libellé de mécanisme dans les tables')


def test_unknown_method_is_rejected_with_a_situated_message():
    try:
        methods.resolve('inexistante')
    except KeyError as exc:
        assert 'inexistante' in str(exc)
    else:
        raise AssertionError('une méthode inconnue doit lever KeyError')


# ----------------------------------------------------------------------
# Les drapeaux atteignent réellement les agents
# ----------------------------------------------------------------------

def test_flags_reach_stations():
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    alphas_before = [s.alpha for s in stations]

    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_global_rep')
    assert {s.score_index for s in stations} == {0}, \
        'réputation globale : toutes les stations doivent lire la même case'

    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_event_score')
    assert {s.score_weighting for s in stations} == {'event'}

    config.set_ALPHA_FIXED(0.42)
    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_fixed_alpha')
    assert {round(s.alpha, 6) for s in stations} == {0.42}
    assert all(s.alpha_save == [0.42] for s in stations), \
        'la trajectoire alpha doit refléter la valeur réellement utilisée'

    # Une méthode sans drapeau alpha ne touche pas aux alpha du monde.
    (cars, stations, societies), config = build_agents(params)
    Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode='bramev')
    assert [s.alpha for s in stations] == alphas_before


def test_score_weighting_changes_the_penalty():
    """
    Le score étant une moyenne bornée sur une fenêtre glissante, la durée agit
    *relativement* : elle décide du poids de chaque issue dans la moyenne, pas
    de l amplitude absolue du score.

    On compare donc une fenêtre hétérogène — une présence courte suivie d un
    no-show long. En pondération par la durée, le no-show domine ; en
    pondération forfaitaire, les deux issues comptent pareil.
    """
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    station = stations[0]
    car = cars[0]

    def window(mode):
        Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode=mode)
        car.reset_score()
        station.update_car_score(car, 'pres', 1)    # présence courte
        station.update_car_score(car, 'abs', 20)    # no-show long
        return float(car.score[station.score_index])

    proportional = window('bramev')
    per_event = window('bramev_event_score')

    assert proportional < per_event, (
        'pondérée par la durée, la fenêtre doit être dominée par le no-show '
        f'long : {proportional} vs {per_event} (forfaitaire)'
    )
    assert -1. <= proportional <= 1. and -1. <= per_event <= 1.

    # Sur une fenêtre homogène en durée, les deux pondérations coïncident :
    # c est la contrepartie du bornage, et elle doit être explicite.
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
        return          # grille trop petite pour distinguer les deux portées

    first, second = list(by_society.values())[:2]

    Simulation(cars, stations, societies, config.TOTAL_TIME, config, mode='bramev')
    car.reset_score()
    first.update_car_score(car, 'abs', 4)
    assert car.score[second.score_index] == 0., \
        'réputation par société : une société ne subit pas le score écrit par une autre'

    Simulation(cars, stations, societies, config.TOTAL_TIME, config,
               mode='bramev_global_rep')
    car.reset_score()
    first.update_car_score(car, 'abs', 4)
    assert car.score[second.score_index] < 0., \
        'réputation globale : le score écrit par une société est lu par les autres'


def test_offer_choice_nearest_ignores_utility():
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    car = cars[0]
    request = {'n': 'test', 't_n': 0, 'd_n': 6, 'loc': (0., 0.),
               'r_n': 5000., 'g_n': 12}

    def offer(station_id, distance, d_prop, t_arr):
        return Offer(station_id=station_id, charger_id=0, t_arr=t_arr,
                     t_dep=t_arr + d_prop, d_prop=d_prop, distance=distance)

    # La plus proche est aussi la moins bonne : durée partielle et attente.
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
        raise AssertionError('un critère inconnu doit être refusé')


# ----------------------------------------------------------------------
# Décomposition
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
    assert round(by_component['Recherche multi-stations']['delta'], 6) == 0.10
    assert round(by_component['Réputation']['delta'], 6) == 0.06
    assert round(by_component['Adaptation entre stations']['delta'], 6) == 0.06
    # Les contributions somment à l'écart total entre les deux extrémités.
    assert abs(sum(r['delta'] for r in detail) - (0.72 - 0.50)) < 1e-9
    assert all(r['improvement'] for r in detail)


def test_improvement_follows_the_metric_direction():
    rows = [_summary('greedy', rate_abs=0.30, exact_satisfaction=0.50),
            _summary('multistation', rate_abs=0.20, exact_satisfaction=0.40)]
    detail = {r['metric']: r for r in ablation.ladder_rows(rows)}
    assert detail['rate_abs']['delta'] < 0 and detail['rate_abs']['improvement'], \
        'moins de no-shows est un gain'
    assert not detail['exact_satisfaction']['improvement'], \
        'moins de satisfaction n est pas un gain'


def test_variant_rows_compare_to_the_full_method():
    rows = [_summary('bramev', exact_satisfaction=0.70),
            _summary('bramev_global_rep', exact_satisfaction=0.60)]
    detail = [r for r in ablation.variant_rows(rows)
              if r['metric'] == 'exact_satisfaction']
    assert len(detail) == 1
    row = detail[0]
    assert row['from_method'] == 'bramev' and row['to_method'] == 'bramev_global_rep'
    assert row['component'] == 'Réputation par société'
    assert not row['improvement'], \
        'neutraliser la réputation par société dégrade ici : le mécanisme sert'


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
        'un composant qui n aide que la moitié des mondes doit se voir'


def test_duplicate_methods_in_summary_are_rejected():
    rows = [_summary('greedy', exact_satisfaction=0.5),
            _summary('greedy', exact_satisfaction=0.6)]
    try:
        ablation.ladder_rows(rows)
    except ValueError as exc:
        assert 'doublons' in str(exc)
    else:
        raise AssertionError('un summary.csv dupliqué doit être refusé')


def test_incomparable_run_produces_no_table():
    rows = [_summary('bramev', exact_satisfaction=0.7)]
    assert ablation.detail_rows(rows) == []


# ----------------------------------------------------------------------
# Configurations livrées
# ----------------------------------------------------------------------

def test_shipped_configs_declare_their_methods():
    """
    Chaque preset de `experiments/` doit déclarer `methods` explicitement.

    `ExperimentParams.methods` a une valeur par défaut — l'échelle d'ablation.
    Un fichier qui omet la clé ne lève donc aucune erreur : il exécute
    silencieusement une *autre* campagne que celle que ses commentaires
    décrivent. C'est arrivé : `ablation_variants.yaml` privé de sa ligne
    `methods` a refait l'échelle pendant 21 h sous le label des variantes.
    """
    import yaml

    configs = sorted(Path('experiments').glob('*.yaml'))
    assert configs, 'aucune configuration livrée trouvée'

    for path in configs:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        assert 'methods' in data, (
            f"{path} ne déclare pas `methods` : la campagne retomberait sur "
            f"le défaut {list(methods.LADDER)} sans rien signaler")
        params = ExperimentParams.from_file(path)
        assert params.methods, f'{path} : liste de méthodes vide'


def test_variants_config_actually_runs_the_variants():
    """
    Le preset des variantes doit contenir la référence *et* les quatre
    variantes : sans `bramev`, aucun écart n'est calculable ; sans les
    variantes, il n'y a rien à comparer.
    """
    params = ExperimentParams.from_file('experiments/ablation_variants.yaml')
    assert set(params.methods) == {'bramev'} | set(methods.VARIANTS), (
        f'methods={list(params.methods)}')


def test_ablation_config_runs_the_ladder_and_the_baselines():
    """
    Le preset d ablation porte deux plans à la fois : l échelle complète — sans
    quoi aucune contribution de composant n est calculable — et les trois
    baselines, qui se comparent à `bramev`. Les deux se lisent sur le même
    monde, ce qui est tout l intérêt de les exécuter dans la même campagne.
    """
    params = ExperimentParams.from_file('experiments/ablation.yaml')
    manquants = set(methods.LADDER) - set(params.methods)
    assert not manquants, f'échelle incomplète, manque {sorted(manquants)}'
    manquants = set(methods.BASELINES) - set(params.methods)
    assert not manquants, f'baselines manquantes : {sorted(manquants)}'
    # L échelle garde son ordre : les barreaux se lisent dans l ordre d ajout.
    rang = {m: i for i, m in enumerate(params.methods)}
    assert [rang[m] for m in methods.LADDER] == sorted(rang[m] for m in methods.LADDER)


def test_reference_config_compares_bramev_to_every_baseline():
    """`full_grid.yaml` est la comparaison publiée : BRAM-EV face aux baselines."""
    params = ExperimentParams.from_file('experiments/full_grid.yaml')
    assert 'bramev' in params.methods, 'sans bramev, aucun écart calculable'
    manquants = set(methods.BASELINES) - set(params.methods)
    assert not manquants, f'baselines manquantes : {sorted(manquants)}'
    assert 'greedy' in params.methods, 'le plancher mono-station doit rester lisible'


# ----------------------------------------------------------------------
# Baselines de référence
# ----------------------------------------------------------------------

def test_baselines_are_pure_choice_policies():
    """
    Les trois baselines ne doivent différer de `multistation` que par la règle
    de sélection de l offre. Même diffusion, même rayon, ni réputation ni
    adaptation : à périmètre d information identique, un écart mesuré est
    imputable à la règle seule.
    """
    assert set(methods.BASELINES) == {'min_waiting', 'load_aware',
                                      'random_feasible'}
    reference = methods.resolve('multistation')
    partages = ('broadcast', 'use_reputation', 'collective_learning',
                'alpha_mode', 'reputation_scope', 'score_weighting')

    for name in methods.BASELINES:
        spec = methods.resolve(name)
        assert spec.family == 'baseline'
        derive = [f for f in partages if getattr(spec, f) != getattr(reference, f)]
        assert not derive, (
            f'{name} diffère de multistation sur {derive} : une baseline ne '
            'doit se distinguer que par sa règle de choix')
        assert spec.offer_choice != reference.offer_choice, (
            f'{name} : une baseline ne doit pas utiliser l utilité BRAM-EV')

    choix = {methods.resolve(n).offer_choice for n in methods.BASELINES}
    assert choix == {'waiting', 'load', 'random'}, (
        f'chaque baseline doit avoir sa propre règle, reçu {choix}')


def test_baselines_see_the_same_stations_as_multistation():
    """
    Le périmètre de diffusion doit être *identique* à celui de `multistation` :
    c est ce qui rend l écart imputable à la règle de choix et non à un
    avantage d information.
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

    assert contactees['multistation'], 'aucune requête émise : test non concluant'
    for name in methods.BASELINES:
        assert contactees[name] == contactees['multistation'], (
            f'{name} ne voit pas le même périmètre que multistation')

    # ... et ce périmètre reste borné par le rayon de recherche.
    assert max(n for _, n in contactees['multistation']) <= params.nb_stations
    assert min(n for _, n in contactees['multistation']) < params.nb_stations, (
        'le rayon devrait exclure au moins une station sur cette grille')


def test_each_baseline_applies_its_own_rule():
    """Chaque règle doit classer les offres selon son propre critère."""
    params = tiny_params()
    (cars, stations, societies), config = build_agents(params)
    car = cars[0]
    request = {'n': 'test', 't_n': 0, 'd_n': 6, 'loc': (0., 0.),
               'r_n': 5000., 'g_n': 12, 'l_n': 0}

    # Trois offres où attente, charge et distance ordonnent différemment.
    offres = [
        Offer(station_id=1, charger_id=0, t_arr=9, t_dep=15, d_prop=6,
              distance=100., station_load=0.9),
        Offer(station_id=2, charger_id=0, t_arr=1, t_dep=7, d_prop=6,
              distance=4000., station_load=0.5),
        Offer(station_id=3, charger_id=0, t_arr=5, t_dep=11, d_prop=6,
              distance=2000., station_load=0.1),
    ]

    par_attente = car.rank_offers(offres, request, 100., criterion='waiting')
    assert par_attente[0][0].station_id == 2, 'min_waiting : attente la plus faible'

    par_charge = car.rank_offers(offres, request, 100., criterion='load')
    assert par_charge[0][0].station_id == 3, 'load_aware : station la moins chargée'

    par_distance = car.rank_offers(offres, request, 100., criterion='nearest')
    assert par_distance[0][0].station_id == 1

    # Les trois règles doivent bien désigner des gagnants différents ici.
    assert len({par_attente[0][0].station_id, par_charge[0][0].station_id,
                par_distance[0][0].station_id}) == 3

    # Toutes les offres reçues restent classées, aucune n est écartée.
    for classement in (par_attente, par_charge, par_distance):
        assert len(classement) == len(offres)


def test_random_feasible_is_random_but_reproducible():
    """
    Le tirage doit varier d une requête à l autre, être identique à graine
    égale, et ne pas dépendre de l ordre d arrivée des offres — qui suit
    l ordre des stations et n a aucun sens pour le véhicule.
    """
    params = tiny_params()
    request = {'n': 'test', 't_n': 0, 'd_n': 6, 'loc': (0., 0.),
               'r_n': 5000., 'g_n': 12, 'l_n': 0}

    def offres():
        return [Offer(station_id=i, charger_id=0, t_arr=2, t_dep=8, d_prop=6,
                      distance=100. * (i + 1), station_load=0.1 * i)
                for i in range(6)]

    def tirages(car, n=15, ordre=None):
        out = []
        for _ in range(n):
            lot = offres()
            if ordre is not None:
                lot = [lot[i] for i in ordre]
            out.append(car.rank_offers(lot, request, 100.,
                                       criterion='random')[0][0].station_id)
        return out

    (cars_a, *_), config = build_agents(params)
    (cars_b, *_), _ = build_agents(params)

    a = tirages(cars_a[0])
    assert len(set(a)) > 1, 'le tirage doit varier d une requête à l autre'

    b = tirages(cars_b[0])
    assert a == b, 'à graine égale, le tirage doit être reproductible'

    # Ordre d arrivée inversé : le résultat ne doit pas changer.
    (cars_c, *_), _ = build_agents(params)
    c = tirages(cars_c[0], ordre=list(reversed(range(6))))
    assert a == c, "le tirage ne doit pas dépendre de l ordre d arrivée des offres"


def test_baseline_rows_compare_bramev_to_each_baseline():
    """
    La table doit lire « baseline -> BRAM-EV » : un `improvement` vrai signifie
    que BRAM-EV fait mieux, ce qui est la question posée à une baseline.
    """
    monde = {'scenario': 'balance', 'nb_cars': 50, 'seed': 1,
             'world_seed': 1, 'grid_seed': 1}
    rows = [dict(monde, method='bramev', exact_satisfaction=0.90),
            dict(monde, method='min_waiting', exact_satisfaction=0.70),
            dict(monde, method='load_aware', exact_satisfaction=0.95),
            dict(monde, method='random_feasible', exact_satisfaction=0.60)]

    metric = ablation.METRICS_BY_COLUMN['exact_satisfaction']
    produites = ablation.baseline_rows(rows, [metric])
    par_methode = {r['from_method']: r for r in produites}

    assert set(par_methode) == set(methods.BASELINES)
    for r in produites:
        assert r['kind'] == 'baseline'
        assert r['to_method'] == 'bramev'

    assert par_methode['min_waiting']['improvement'] is True
    assert par_methode['load_aware']['improvement'] is False, (
        'une baseline qui bat BRAM-EV doit apparaître comme telle')
    assert abs(par_methode['random_feasible']['delta'] - 0.30) < 1e-9

    # Les baselines rejoignent la table détaillée complète.
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
        # Les drapeaux voyagent jusqu'à summary.csv : la table se lit seule.
        by_method = {r['method']: r for r in summary}
        assert by_method['greedy']['broadcast'] is False
        assert by_method['multistation']['broadcast'] is True
        assert by_method['multistation']['reputation'] is False
        assert by_method['multistation_rep']['reputation'] is True
        assert by_method['multistation_rep']['adaptation'] is False
        assert by_method['bramev']['adaptation'] is True


def test_ablation_tables_are_written_incrementally():
    """
    Une campagne complète met des heures. Les tables de décomposition doivent
    donc exister *pendant* la campagne, comme `summary.csv` : autrement un run
    encore en cours — ou interrompu — n'a rien à analyser, alors que tous les
    cas nécessaires sont déjà calculés.
    """
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp)
        store = RunStore.create(params)
        vus = []

        def apres_chaque_cas(outcome):
            vus.append(outcome.case.method)
            # Dès que deux barreaux consécutifs sont faits, la table existe.
            if len(vus) >= 2:
                assert store.read_root_table('ablation'), (
                    f'ablation.csv absent après {len(vus)} cas ({vus})')

        run_grid(params, store=store, on_case=apres_chaque_cas)
        assert len(vus) == params.nb_cases


def test_broadcast_actually_contacts_more_stations():
    """
    Le premier barreau doit se voir dans les métriques, pas seulement dans les
    drapeaux : sans cela, une contribution nulle serait ininterprétable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        params = tiny_params(output_root=tmp, methods=('greedy', 'multistation'),
                             nb_stations=8, fleet_sizes=(16,), total_time=60)
        store = run_grid(params)
        by_method = {r['method']: r for r in store.read_summary()}
        assert (by_method['multistation']['mean_offers_per_demand'] >
                by_method['greedy']['mean_offers_per_demand']), (
            'la diffusion doit produire strictement plus d offres par demande')


def test_occupancy_survives_the_release_of_the_calendar():
    """
    `schedule` est remis à -1 à chaque fin de session : un taux d'occupation
    lu à la fin du run y valait 0 pour toutes les méthodes. Les compteurs
    cumulés doivent, eux, refléter l'activité réelle.
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

    print(f'\n{len(tests) - len(failures)}/{len(tests)} tests réussis')
    for name, tb in failures:
        print(f'\n===== {name} =====\n{tb}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
