"""
runner.py — Exécution d'un cas et de la grille d'expériences.

Le runner ne connaît ni la ligne de commande, ni la disposition des fichiers
(déléguée à `RunStore`), ni la mise en forme des figures. Il orchestre :

    une fois par campagne            -> une grille unique (sociétés, stations)
    une fois par taille de flotte    -> une population de véhicules
        pour chaque scénario         -> composition : seul `theta` change
            pour chaque méthode      -> une simulation sur une copie du monde

C'est cette structure qui rend les comparaisons propres, à deux niveaux :

* **entre méthodes** — le monde est matérialisé autant de fois qu'il y a de
  méthodes, sans nouveau tirage (cf. `world.build_world`) ;
* **entre scénarios** — la grille et les positions initiales des véhicules sont
  tirées avant toute simulation et réutilisées telles quelles, si bien que
  l'écart mesuré entre `optimistic`, `balance` et `pessimistic` ne peut venir
  que des probabilités de comportement (cf. `world.compose_world_spec`).

La grille et les flottes sont persistées (JSON + CSV) dès leur tirage : elles
sont disponibles même si la campagne est interrompue au premier cas.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from loguru import logger

from src.experiments.simulation import Simulation
from src.experiments.world import (build_world, compose_world_spec,
                                   generate_fleet_spec, generate_grid_spec)
from src.pipeline import ablation, tables
from src.pipeline.params import CaseParams, ExperimentParams
from src.pipeline.store import RunStore


@dataclass
class CaseOutcome:
    """Ce qu'un cas produit, indépendamment de son stockage."""

    case: CaseParams
    result: dict
    summary: dict
    wall_time_s: float
    diagnostics: list[str]

    @property
    def invariant_ok(self) -> bool:
        return bool(self.result['invariant_ok'])


def run_case(case: CaseParams, params: ExperimentParams, spec,
             log_path=None) -> tuple[Simulation, CaseOutcome]:
    """
    Exécute un cas sur une matérialisation neuve du monde `spec`.

    Returns
    -------
    (simulation, outcome)
        La simulation est renvoyée pour permettre d'en extraire les tables
        détaillées ; l'appelant décide de ce qu'il persiste.
    """
    config = params.build_config(case.scenario, case.nb_cars)
    cars, stations, societies = build_world(spec, config)

    # Une seule classe pour toutes les méthodes : `mode` sélectionne le jeu de
    # drapeaux (cf. src/experiments/methods.py). Deux méthodes exécutent donc
    # strictement le même code sur le même monde, aux drapeaux près — condition
    # nécessaire pour attribuer un écart mesuré à un composant.
    simulation = Simulation(
        cars=cars, stations=stations, societies=societies,
        t_max=config.TOTAL_TIME, config=config, mode=case.method,
    )

    started = time.perf_counter()
    if log_path is not None:
        with open(log_path, 'w', encoding='utf-8') as handle:
            simulation.run(handle, print_metrics=False)
    else:
        # Le journal détaillé pèse plusieurs centaines de Mo sur la grille
        # complète et n'alimente aucune métrique : il est jeté par défaut.
        simulation.run(io.StringIO(), print_metrics=False)
    wall_time_s = time.perf_counter() - started

    result = simulation.results()
    result['world_seed'] = spec.seed
    result['grid_seed'] = spec.grid_seed
    result['world_file'] = f'{case.world_tag}.json'
    result['wall_time_s'] = round(wall_time_s, 3)

    outcome = CaseOutcome(
        case=case,
        result=result,
        summary=tables.summary_row(result),
        wall_time_s=wall_time_s,
        diagnostics=list(result['behaviors'].get('diagnostics', [])),
    )
    return simulation, outcome


def prepare_shared_world(params: ExperimentParams, store: RunStore):
    """
    Tire et persiste ce que tous les cas partagent : la grille et les flottes.

    Appelée une seule fois, avant toute simulation. La configuration utilisée
    ne fixe aucun scénario : ce qui est tiré ici ne peut donc pas en dépendre.

    Returns
    -------
    (grid, fleets)
        `grid` : `GridSpec` unique ; `fleets` : `{nb_cars: FleetSpec}`.
    """
    shared_config = params.build_shared_config()

    grid = generate_grid_spec(shared_config, params.seed)
    store.save_grid(grid)
    store.write_shared_table('grid_stations', tables.grid_station_table(grid))
    store.write_shared_table('grid_societies', tables.grid_society_table(grid))
    logger.info(
        f'Grille partagée : {grid.nb_stations} stations / {grid.nb_societies} '
        f'sociétés, {sum(s["nb_charg_spot"] for s in grid.stations)} bornes '
        f'-> {store.grid_path.name}'
    )

    fleets: dict[int, object] = {}
    for nb_cars in params.fleet_sizes:
        fleet = generate_fleet_spec(shared_config, params.seed, nb_cars)
        store.save_fleet(fleet)
        store.write_shared_table(f'fleet_{nb_cars}cars', tables.fleet_table(fleet))
        fleets[nb_cars] = fleet
    logger.info(f'Flottes partagées : {list(fleets)} véhicules '
                f'-> {store.fleets_dir.name}/')

    return grid, fleets


def run_grid(params: ExperimentParams, store: RunStore | None = None,
             on_case: Callable[[CaseOutcome], None] | None = None) -> RunStore:
    """
    Exécute toute la grille définie par `params` et persiste les artefacts.

    Les résultats sont écrits au fur et à mesure (résultat, tables, summary.csv,
    manifeste) : une campagne interrompue reste exploitable et le `summary.csv`
    partiel est déjà valide.
    """
    store = store or RunStore.create(params)
    logger.info(f'Run : {store.root}')
    logger.info(params.describe())

    grid, fleets = prepare_shared_world(params, store)

    summary_rows: list[dict] = []
    # Les diagnostics sont structurels : les répéter à chaque cas noie la sortie.
    seen_diagnostics: set[str] = set()
    started = time.perf_counter()
    case_no = 0

    for scenario, nb_cars in params.worlds():
        # Composition : grille et flotte partagées, `theta` du scénario.
        config_ref = params.build_config(scenario, nb_cars)
        spec = compose_world_spec(grid, fleets[nb_cars], config_ref)
        world_seed = spec.seed
        store.save_world(spec, scenario, nb_cars)

        for method in params.methods:
            case = CaseParams(scenario=scenario, nb_cars=nb_cars, method=method)
            case_no += 1
            logger.info(f'[{case_no}/{params.nb_cases}] {case.tag} '
                        f'(seed={params.seed}, world_seed={world_seed})')

            log_path = store.log_path(case) if params.keep_logs else None
            simulation, outcome = run_case(case, params, spec, log_path)

            store.save_result(case, outcome.result)
            if params.save_tables:
                for name, rows in tables.case_tables(
                        simulation, outcome.result,
                        with_latency=params.save_latency).items():
                    store.write_table(case, name, rows)

            summary_rows.append(outcome.summary)
            store.write_summary(summary_rows, tables.SUMMARY_FIELDS)
            store.record_case({
                'tag': case.tag,
                'scenario': scenario,
                'nb_cars': nb_cars,
                'method': method,
                'world_seed': world_seed,
                'wall_time_s': outcome.result['wall_time_s'],
                'invariant_ok': outcome.invariant_ok,
                'nb_diagnostics': len(outcome.diagnostics),
            })

            _log_outcome(outcome, seen_diagnostics)
            if on_case is not None:
                on_case(outcome)

            # Libère explicitement le monde de ce cas avant le suivant.
            del simulation

    # Décomposition des contributions : écrite dès que la campagne contient au
    # moins deux méthodes comparables sur un même monde.
    written = ablation.write_tables(store, summary_rows)
    for path in written:
        logger.info(f'Ablation → {path}')

    store.close_manifest(time.perf_counter() - started)
    logger.info(f'{len(summary_rows)} cas terminés → {store.root}')
    return store


def _log_outcome(outcome: CaseOutcome,
                 seen_diagnostics: set[str] | None = None) -> None:
    row = outcome.summary
    logger.info(
        '    satisf={exact} | no-show={abs} early={early} late={late} | '
        'offres {issued}→{confirmed} | e2e {e2e} ms | {wall}s'.format(
            exact=row['exact_satisfaction'],
            abs=row['nb_no_show'], early=row['nb_early_canc'],
            late=row['nb_late_canc'],
            issued=row['nb_offer_issued'], confirmed=row['nb_reservations'],
            e2e=row['total_ms_mean'], wall=round(outcome.wall_time_s, 1),
        )
    )
    if not outcome.invariant_ok:
        logger.error(f'    invariant de réservation violé : '
                     f'{outcome.result["invariant_errors"][:2]}')
    for warning in outcome.diagnostics:
        if seen_diagnostics is not None:
            if warning in seen_diagnostics:
                continue
            seen_diagnostics.add(warning)
        logger.warning(f'    {warning}')
