"""
runner.py — Execution of one case and of the experiment grid.

The runner knows neither the command line, nor the file layout (delegated to
`RunStore`), nor the styling of the figures. It orchestrates:

    once per campaign             -> a single grid (companies, stations)
    once per fleet size           -> a vehicle population
        for each scenario         -> composition: only `theta` changes
            for each method       -> a simulation on a copy of the world

That structure is what makes the comparisons clean, at two levels:

* **between methods** — the world is materialised as many times as there are
  methods, with no new draw (see `world.build_world`);
* **between scenarios** — the grid and the initial vehicle positions are drawn
  before any simulation and reused as is, so that the gap measured between
  `optimistic`, `balance` and `pessimistic` can only come from the behaviour
  probabilities (see `world.compose_world_spec`).

The grid and the fleets are persisted (JSON + CSV) as soon as they are drawn:
they are available even if the campaign is interrupted at the first case.
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
    """What a case produces, independently of how it is stored."""

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
    Run one case on a fresh materialisation of the world `spec`.

    Returns
    -------
    (simulation, outcome)
        The simulation is returned so that the detailed tables can be extracted
        from it; the caller decides what to persist.
    """
    config = params.build_config(case.scenario, case.nb_cars)
    cars, stations, societies = build_world(spec, config)

    # A single class for every method: `mode` selects the flag set (see
    # src/experiments/methods.py). Two methods therefore run strictly the same
    # code on the same world, up to the flags — the condition required to
    # attribute a measured gap to a component.
    simulation = Simulation(
        cars=cars, stations=stations, societies=societies,
        t_max=config.TOTAL_TIME, config=config, mode=case.method,
    )

    started = time.perf_counter()
    if log_path is not None:
        with open(log_path, 'w', encoding='utf-8') as handle:
            simulation.run(handle, print_metrics=False)
    else:
        # The detailed log weighs several hundred MB on the full grid and
        # feeds no metric: it is discarded by default.
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
    Draw and persist what every case shares: the grid and the fleets.

    Called only once, before any simulation. The configuration used sets no
    scenario: what is drawn here therefore cannot depend on one.

    Returns
    -------
    (grid, fleets)
        `grid`: the single `GridSpec`; `fleets`: `{nb_cars: FleetSpec}`.
    """
    shared_config = params.build_shared_config()

    grid = generate_grid_spec(shared_config, params.seed)
    store.save_grid(grid)
    store.write_shared_table('grid_stations', tables.grid_station_table(grid))
    store.write_shared_table('grid_societies', tables.grid_society_table(grid))
    logger.info(
        f'Shared grid: {grid.nb_stations} stations / {grid.nb_societies} '
        f'companies, {sum(s["nb_charg_spot"] for s in grid.stations)} chargers '
        f'-> {store.grid_path.name}'
    )

    fleets: dict[int, object] = {}
    for nb_cars in params.fleet_sizes:
        fleet = generate_fleet_spec(shared_config, params.seed, nb_cars)
        store.save_fleet(fleet)
        store.write_shared_table(f'fleet_{nb_cars}cars', tables.fleet_table(fleet))
        fleets[nb_cars] = fleet
    logger.info(f'Shared fleets: {list(fleets)} vehicles '
                f'-> {store.fleets_dir.name}/')

    return grid, fleets


def run_grid(params: ExperimentParams, store: RunStore | None = None,
             on_case: Callable[[CaseOutcome], None] | None = None) -> RunStore:
    """
    Run the whole grid defined by `params` and persist the artifacts.

    Results are written as they come (result, tables, summary.csv, manifest): an
    interrupted campaign stays usable and the partial `summary.csv` is already
    valid.
    """
    store = store or RunStore.create(params)
    logger.info(f'Run: {store.root}')
    logger.info(params.describe())

    grid, fleets = prepare_shared_world(params, store)

    summary_rows: list[dict] = []
    # Diagnostics are structural: repeating them at every case drowns the output.
    seen_diagnostics: set[str] = set()
    started = time.perf_counter()
    case_no = 0

    for scenario, nb_cars in params.worlds():
        # Composition: shared grid and fleet, `theta` of the scenario.
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
            # The decomposition is rewritten at every case, like summary.csv:
            # a long campaign can be analysed while it runs, and an interrupted
            # campaign stays usable. The computation is a mere re-read of the
            # rows already in memory.
            ablation.write_tables(store, summary_rows)
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

            # Explicitly release the world of this case before the next one.
            del simulation

    for path in ablation.write_tables(store, summary_rows):
        logger.info(f'Ablation → {path}')

    store.close_manifest(time.perf_counter() - started)
    logger.info(f'{len(summary_rows)} cases finished → {store.root}')
    return store


def _log_outcome(outcome: CaseOutcome,
                 seen_diagnostics: set[str] | None = None) -> None:
    row = outcome.summary
    logger.info(
        '    satisf={exact} | no-show={abs} early={early} late={late} | '
        'offers {issued}→{confirmed} | e2e {e2e} ms | {wall}s'.format(
            exact=row['exact_satisfaction'],
            abs=row['nb_no_show'], early=row['nb_early_canc'],
            late=row['nb_late_canc'],
            issued=row['nb_offer_issued'], confirmed=row['nb_reservations'],
            e2e=row['total_ms_mean'], wall=round(outcome.wall_time_s, 1),
        )
    )
    if not outcome.invariant_ok:
        logger.error(f'    reservation invariant violated: '
                     f'{outcome.result["invariant_errors"][:2]}')
    for warning in outcome.diagnostics:
        if seen_diagnostics is not None:
            if warning in seen_diagnostics:
                continue
            seen_diagnostics.add(warning)
        logger.warning(f'    {warning}')
