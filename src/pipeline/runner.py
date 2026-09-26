"""
runner.py — Execution of one case and of the experiment grid.

The runner knows neither the command line, nor the file layout (delegated to
`RunStore`), nor the styling of the figures. It orchestrates:

    once per seed                 -> a grid (companies, stations)
    once per fleet size           -> a vehicle population
        for each scenario         -> composition: only `theta` changes
            for each method       -> a simulation on a copy of the world

That structure is what makes the comparisons clean, at three levels:

* **between methods** — the world is materialised as many times as there are
  methods, with no new draw (see `world.build_world`);
* **between scenarios** — the grid and the initial vehicle positions are drawn
  before any simulation and reused as is, so that the gap measured between
  `optimistic`, `balance` and `pessimistic` can only come from the behaviour
  probabilities (see `world.compose_world_spec`);
* **between seeds** — nothing is shared. Each seed redraws the grid, the fleets
  and every behaviour, so a seed is a **replicate on another world**, not a
  re-run of the same one. That is what a decomposition aggregated over seeds
  measures, and what `share_improved` counts in `src/pipeline/ablation.py`.

There is deliberately no way to hold the grid fixed while varying only the
behaviour draws: a single root seed feeds both. A gap that survives several
seeds survives a change of world too, which is the stronger claim.

The grid and the fleets are persisted (JSON + CSV) as soon as they are drawn:
they are available even if the campaign is interrupted at the first case.
"""

from __future__ import annotations

import io
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterable

from loguru import logger

from src.experiments.simulation import Simulation
from src.experiments.world import (build_world, compose_world_spec,
                                   generate_fleet_spec, generate_grid_spec)
from src.pipeline import ablation, aggregate, tables
from src.pipeline.params import CaseParams, ExperimentParams
from src.pipeline.store import RunStore, _utc_stamp, git_commit, git_is_dirty


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
    config = params.build_config(case.scenario, case.nb_cars, case.seed)
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


def prepare_shared_world(params: ExperimentParams, store: RunStore,
                         seed: int | None = None, reuse: bool = False):
    """
    Draw and persist what every case of one replicate shares: grid and fleets.

    Called once per seed, before any simulation of that replicate. The
    configuration used sets no scenario: what is drawn here therefore cannot
    depend on one.

    `reuse=True` (resuming a run) reads back the grid and the fleets already
    persisted instead of drawing them again: the cases still to run then see
    exactly the environment of the cases already done.

    Returns
    -------
    (grid, fleets)
        `grid`: the `GridSpec` of the replicate; `fleets`: `{nb_cars: FleetSpec}`.
    """
    seed = params.seed if seed is None else int(seed)
    if reuse and store.grid_path(seed).is_file() and all(
            store.fleet_path(n, seed).is_file() for n in params.fleet_sizes):
        grid = store.load_grid(seed)
        fleets = {n: store.load_fleet(n, seed) for n in params.fleet_sizes}
        logger.info(f'[seed {seed}] grid and fleets reloaded from {store.root.name}')
        return grid, fleets

    shared_config = params.build_shared_config(seed=seed)

    grid = generate_grid_spec(shared_config, seed)
    store.save_grid(grid, seed)
    store.write_shared_table('grid_stations', tables.grid_station_table(grid), seed)
    store.write_shared_table('grid_societies', tables.grid_society_table(grid), seed)
    logger.info(
        f'[seed {seed}] grid: {grid.nb_stations} stations / {grid.nb_societies} '
        f'companies, {sum(s["nb_charg_spot"] for s in grid.stations)} chargers '
        f'-> {store.grid_path(seed).name}'
    )

    fleets: dict[int, object] = {}
    for nb_cars in params.fleet_sizes:
        fleet = generate_fleet_spec(shared_config, seed, nb_cars)
        store.save_fleet(fleet, seed)
        store.write_shared_table(f'fleet_{nb_cars}cars', tables.fleet_table(fleet), seed)
        fleets[nb_cars] = fleet
    logger.info(f'[seed {seed}] fleets: {list(fleets)} vehicles '
                f'-> {store.fleets_dir.name}/')

    return grid, fleets


def prepare_worlds(params: ExperimentParams, store: RunStore,
                   reuse: bool = False) -> None:
    """
    Persist every world of the campaign before any simulation.

    A case then only needs the run directory and its own identity to run: it
    reads its world back from `worlds/`, which is what lets it run in another
    process. On a resume (`reuse=True`) a world already on disk is kept as is.
    """
    for seed in params.seeds:
        grid, fleets = prepare_shared_world(params, store, seed, reuse=reuse)
        for scenario in params.scenarios:
            for nb_cars in params.fleet_sizes:
                if reuse and store.world_path(scenario, nb_cars, seed).is_file():
                    continue
                config_ref = params.build_config(scenario, nb_cars, seed)
                spec = compose_world_spec(grid, fleets[nb_cars], config_ref)
                store.save_world(spec, scenario, nb_cars, seed)


def execute_case(root: str, case: CaseParams) -> tuple[dict, dict]:
    """
    Run one case from its persisted world; return `(result, tables)`.

    Self-contained on purpose — it takes a path and a case, reads everything
    else from disk and writes nothing but its optional log — so that it runs
    unchanged in a worker process. Persisting the outcome is the parent's job:
    a single writer means no two processes ever write the same file.
    """
    store = RunStore.open(root)
    params = store.read_params()
    spec = store.load_world(case.scenario, case.nb_cars, case.seed)
    log_path = store.log_path(case) if params.keep_logs else None
    simulation, outcome = run_case(case, params, spec, log_path)
    case_tables = (tables.case_tables(simulation, outcome.result,
                                      with_latency=params.save_latency)
                   if params.save_tables else {})
    return outcome.result, case_tables


def _quiet_worker() -> None:
    """Worker initialiser: keep warnings, drop the per-slot progress log."""
    import sys
    logger.remove()
    logger.add(sys.stderr, level='WARNING',
               format='{time:HH:mm:ss} | {level: <7} | [worker] {message}')


def run_grid(params: ExperimentParams, store: RunStore | None = None,
             on_case: Callable[[CaseOutcome], None] | None = None,
             workers: int | None = None, resume: bool = False) -> RunStore:
    """
    Run the whole grid defined by `params` and persist the artifacts.

    Saving as it goes
    -----------------
    Every case is persisted **as soon as it finishes**, by the parent process
    only: its tables first, then its result JSON — written atomically, it is the
    marker of a finished case — then `summary.csv`, the ablation tables and the
    manifest, all rebuilt from the results on disk. A crash, a `Ctrl-C` or a
    machine going to sleep therefore loses at most the cases still running;
    `resume=True` (`run --resume <run dir>`) runs only the cases with no result.

    Parallelism
    -----------
    `workers > 1` spreads the cases over that many processes. A case depends on
    nothing but its world, read from `worlds/`, so the results are the same as
    in a sequential run (only the wall-clock columns differ: they measure a
    machine shared by `workers` simulations). The largest fleets are submitted
    first, which shortens the tail of the campaign.
    """
    workers = params.workers if workers is None else int(workers)
    store = store or RunStore.create(params)
    logger.info(f'Run: {store.root}')
    logger.info(params.describe())
    if resume:
        _check_resume(store)

    started = time.perf_counter()
    prepare_worlds(params, store, reuse=resume)

    cases = list(params.cases())
    order = {case.tag: i for i, case in enumerate(cases)}
    rows: dict[str, dict] = {}
    for case in cases:
        if store.has_result(case):
            rows[case.tag] = tables.summary_row(store.load_result(case))
    pending = [case for case in cases if case.tag not in rows]
    if rows:
        logger.info(f'{len(rows)}/{len(cases)} cases already done, '
                    f'{len(pending)} to run')

    seen_diagnostics: set[str] = set()
    failures: dict[str, str] = {}

    def persist(case: CaseParams, result: dict, case_tables: dict) -> None:
        # Tables before the result: the result file marks a finished case,
        # so a case interrupted between the two is simply run again.
        for name, table_rows in case_tables.items():
            store.write_table(case, name, table_rows)
        store.save_result(case, result)

        summary = tables.summary_row(result)
        rows[case.tag] = summary
        ordered = [rows[tag] for tag in sorted(rows, key=order.__getitem__)]
        store.write_summary(ordered, tables.SUMMARY_FIELDS)
        # Rewritten at every case, like summary.csv: a long campaign can be
        # analysed while it runs, and an interrupted one stays usable.
        ablation.write_tables(store, ordered)
        store.record_case({
            'tag': case.tag,
            'seed': case.seed,
            'scenario': case.scenario,
            'nb_cars': case.nb_cars,
            'method': case.method,
            'world_seed': result.get('world_seed'),
            'wall_time_s': result['wall_time_s'],
            'invariant_ok': bool(result['invariant_ok']),
            'nb_diagnostics': len(result['behaviors'].get('diagnostics', [])),
        })

        outcome = CaseOutcome(
            case=case, result=result, summary=summary,
            wall_time_s=float(result['wall_time_s']),
            diagnostics=list(result['behaviors'].get('diagnostics', [])))
        logger.info(f'[{len(rows)}/{len(cases)}] {case.tag}')
        _log_outcome(outcome, seen_diagnostics)
        if on_case is not None:
            on_case(outcome)

    root = str(store.root)
    if workers <= 1:
        for case in pending:
            logger.info(f'[{len(rows) + 1}/{len(cases)}] running {case.tag}')
            try:
                result, case_tables = execute_case(root, case)
            except Exception as exc:     # keep the other cases going
                failures[case.tag] = repr(exc)
                logger.exception(f'{case.tag} failed')
                continue
            persist(case, result, case_tables)
    elif pending:
        # Largest fleets first: the longest cases start early, so the last
        # minutes of the campaign are not spent waiting on a single one.
        queue = sorted(pending, key=lambda c: (-c.nb_cars, order[c.tag]))
        logger.info(f'{len(queue)} cases on {workers} worker processes')
        pool = ProcessPoolExecutor(max_workers=workers, initializer=_quiet_worker)
        try:
            futures = {pool.submit(execute_case, root, case): case for case in queue}
            for future in as_completed(futures):
                case = futures[future]
                try:
                    result, case_tables = future.result()
                except Exception as exc:
                    failures[case.tag] = repr(exc)
                    logger.error(f'{case.tag} failed: {exc!r}')
                    continue
                persist(case, result, case_tables)
        except BaseException:
            # Ctrl-C or a failure of the parent: the finished cases are on disk.
            pool.shutdown(wait=False, cancel_futures=True)
            logger.warning(f'Interrupted: {len(rows)}/{len(cases)} cases saved. '
                           f'Continue with: run --resume {store.root}')
            raise
        pool.shutdown()

    ordered = [rows[tag] for tag in sorted(rows, key=order.__getitem__)]
    for path in ablation.write_tables(store, ordered):
        logger.info(f'Ablation → {path}')

    if failures:
        manifest = store.read_manifest()
        manifest['failed_cases'] = failures
        store.write_manifest(manifest)
        logger.error(f'{len(failures)} case(s) failed: {sorted(failures)}. '
                     f'Fix the cause, then: run --resume {store.root}')
    elif len(rows) == len(cases):
        # Statistics over the replicates — written once, at the end, unlike the
        # ablation tables. A mid-campaign aggregate would be computed on the
        # seeds finished so far and would publish a confidence interval over a
        # sample that is still growing: a number that looks like a result and
        # is not one.
        for path in aggregate.write_tables(store, ordered):
            logger.info(f'Replicates → {path}')
        if params.nb_seeds == 1:
            logger.info('Single seed: the interval columns stay empty. Run with '
                        '--seeds to obtain a spread.')

    store.close_manifest(time.perf_counter() - started)
    logger.info(f'{len(rows)}/{len(cases)} cases finished → {store.root}')
    return store


def _check_resume(store: RunStore) -> None:
    """Warn when the code changed since the run started: results would mix."""
    manifest = store.read_manifest()
    before, now = manifest.get('git_commit'), git_commit()
    if before and now and before != now:
        logger.warning(f'Resuming a run started at commit {before[:7]} with '
                       f'commit {now[:7]}: the cases already done and the ones '
                       'still to run may not share the same code')
    if git_is_dirty():
        logger.warning('Uncommitted changes: the resumed cases may not run the '
                       'code of the cases already done')
    manifest.setdefault('resumed_utc', []).append(_utc_stamp())
    manifest.pop('failed_cases', None)
    store.write_manifest(manifest)


def _log_outcome(outcome: CaseOutcome,
                 seen_diagnostics: set[str] | None = None) -> None:
    row = outcome.summary
    logger.info(
        '    served={served} | no-show={abs} early={early} late={late} | '
        'offers {issued}→{confirmed} | e2e {e2e} ms | {wall}s'.format(
            served=row['satisfied_rate'],
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
