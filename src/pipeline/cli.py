"""
cli.py — Command line interface of the BRAM-EV pipeline.

    python -m src.pipeline.cli run --scenarios pessimistic --cars 50 100 --seed 42
    python -m src.pipeline.cli run --methods ablation      # the 4 configurations
    python -m src.pipeline.cli run --methods all           # + BRAM-EV variants
    python -m src.pipeline.cli ablation --latest
    python -m src.pipeline.cli report --run-dir results_grid/<run>
    python -m src.pipeline.cli show --latest
    python -m src.pipeline.cli runs
    python -m src.pipeline.cli scenarios
    python -m src.pipeline.cli methods

The sub-commands deliberately separate computing (`run`) from reporting
(`report`, `show`): the figures are regenerated from the persisted tables,
without re-running the simulations.

Exit codes: 
    0 success
    1 parameter or input/output error
    2 usage (argparse)
    3 at least one reservation invariant violated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from loguru import logger

import src.experiments.config as cfg_module
import src.experiments.methods as methods_module
from src.experiments.seeding import DEFAULT_SEED
from src.pipeline import ablation, figures
from src.pipeline.params import (METHODS, SCENARIOS, ExperimentParams,
                                 ParamsError)
from src.pipeline.runner import run_grid
from src.pipeline.store import RunStore

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVARIANT = 3

DEFAULT_OUTPUT_ROOT = 'results_grid'


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

def configure_logging(verbosity: int) -> None:
    """-q -> warnings only; default -> info; -v -> debug."""
    level = {(-1): 'WARNING', 0: 'INFO'}.get(verbosity, 'DEBUG')
    logger.remove()
    logger.add(sys.stderr, level=level,
               format='<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}')


# ----------------------------------------------------------------------
# Argument parser
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='python -m src.pipeline.cli',
        description="BRAM-EV experiment pipeline (simulation, reporting).",
    )
    parser.add_argument('-q', '--quiet', dest='verbosity', action='store_const',
                        const=-1, default=0, help='Limit the output to warnings.')
    parser.add_argument('-v', '--verbose', dest='verbosity', action='store_const',
                        const=1, help='Debug output.')

    subparsers = parser.add_subparsers(dest='command', required=True,
                                       metavar='<command>')
    _add_run(subparsers)
    _add_report(subparsers)
    _add_show(subparsers)
    _add_runs(subparsers)
    _add_scenarios(subparsers)
    _add_methods(subparsers)
    _add_ablation(subparsers)
    return parser


def _add_run(subparsers) -> None:
    p = subparsers.add_parser(
        'run', help="Run a campaign of experiments.",
        description="Run a campaign. Every parameter can be overridden from the "
                    "command line or supplied through --config.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.set_defaults(func=cmd_run)

    p.add_argument('--config', type=Path, default=None,
                   help='YAML/JSON parameter file. The options below override '
                        'it.')

    plan = p.add_argument_group("experiment plan")
    plan.add_argument('--seed', type=int, default=None,
                      help=f'Root seed (default: {DEFAULT_SEED}).')
    plan.add_argument('--scenarios', nargs='+', choices=SCENARIOS, default=None,
                      metavar='NAME', help=f'Scenarios to run {list(SCENARIOS)}.')
    plan.add_argument('--cars', dest='fleet_sizes', nargs='+', type=int, default=None,
                      metavar='N', help='Fleet sizes to test.')
    # No `choices` here: the value may be a name, an alias (`nearest`) or a
    # group (`ablation`, `variants`, `all`). Validation — and its error message
    # — belongs to `ExperimentParams`, the only place that knows the registry.
    plan.add_argument('--methods', nargs='+', default=None, metavar='NAME',
                      help="Methods to compare: names, aliases, or groups "
                           "(ablation, variants, baseline, all). "
                           "`cli.py methods` prints the complete table.")

    env = p.add_argument_group('simulated environment')
    env.add_argument('--total-time', type=int, default=None,
                     help='Duration in 5 min slots (1440 = 5 days).')
    env.add_argument('--nb-stations', type=int, default=None)
    env.add_argument('--nb-societies', type=int, default=None)
    env.add_argument('--charg-spot-low', dest='nb_charg_spot_low', type=int, default=None,
                     help='Minimal number of chargers per station.')
    env.add_argument('--charg-spot-high', dest='nb_charg_spot_high', type=int, default=None,
                     help='Maximal number of chargers per station.')
    env.add_argument('--strategy-noise', type=float, default=None)

    proto = p.add_argument_group("protocol")
    proto.add_argument('--offer-ttl-slots', type=int, default=None,
                       help="Validity of an offer, in slots.")
    proto.add_argument('--late-cancel-fraction', type=float, default=None,
                       help='Fraction of the request→arrival delay separating '
                            'an early from a late cancellation.')
    proto.add_argument('--reservation-lead-low', type=int, default=None,
                       help="Lower bound of the planning horizon, in slots "
                            '(delay between the request and the targeted '
                            'slot).')
    proto.add_argument('--reservation-lead-high', type=int, default=None,
                       help="Upper bound of the planning horizon. 0 "
                            '(default) = immediate reservation, historical '
                            "behaviour; >= 3 for an early cancellation to be "
                            'reachable.')
    proto.add_argument('--society-update-interval', type=int, default=None,
                       help="Period of the collective learning, in slots.")
    proto.add_argument('--alpha-fixed', type=float, default=None,
                       help="Common alpha imposed on the fixed-alpha methods "
                            "(bramev_fixed_alpha). No effect on the others.")

    out = p.add_argument_group('outputs')
    out.add_argument('--output-root', default=None,
                     help=f'Root directory of the runs (default: {DEFAULT_OUTPUT_ROOT}).')
    out.add_argument('--label', default=None,
                     help='Readable suffix appended to the run name.')
    out.add_argument('--keep-logs', action=argparse.BooleanOptionalAction, default=None,
                     help='Keep the detailed text log (bulky).')
    out.add_argument('--save-latency', action=argparse.BooleanOptionalAction, default=None,
                     help='Latency table, one row per demand.')
    out.add_argument('--save-tables', action=argparse.BooleanOptionalAction, default=None,
                     help='Tidy tables (stations, behaviours, alpha…).')
    out.add_argument('--figures', action=argparse.BooleanOptionalAction, default=None,
                     help='Generate the figures at the end of the campaign.')
    out.add_argument('--log-every', type=int, default=None,
                     help='Frequency of the progress lines, in slots.')

    p.add_argument('--dry-run', action='store_true',
                   help='Validate and print the plan without running anything.')


def _add_report(subparsers) -> None:
    p = subparsers.add_parser(
        'report', help='Regenerate the figures of an existing run.',
        description="Rebuild every figure from summary.csv, without re-running "
                    "any simulation.")
    p.set_defaults(func=cmd_report)
    _add_run_selector(p)


def _add_show(subparsers) -> None:
    p = subparsers.add_parser(
        'show', help='Print the summary table of a run.')
    p.set_defaults(func=cmd_show)
    _add_run_selector(p)
    p.add_argument('--columns', nargs='+', default=None, metavar='COL',
                   help='Columns to print (default: a readable selection).')


def _add_runs(subparsers) -> None:
    p = subparsers.add_parser('runs', help='List the available runs.')
    p.set_defaults(func=cmd_runs)
    p.add_argument('--output-root', default=DEFAULT_OUTPUT_ROOT)


def _add_scenarios(subparsers) -> None:
    p = subparsers.add_parser(
        'scenarios', help='Print the scenario table.',
        description="Behaviour probabilities, single source of truth "
                    "(src/experiments/config.py).")
    p.set_defaults(func=cmd_scenarios)


def _add_methods(subparsers) -> None:
    p = subparsers.add_parser(
        'methods', help="Print the ablation plan (available methods).",
        description="Components enabled by each method. Single source of "
                    "truth: src/experiments/methods.py.")
    p.set_defaults(func=cmd_methods)
    p.add_argument('--detail', action='store_true',
                   help='Add the explanatory note of each method.')


def _add_ablation(subparsers) -> None:
    p = subparsers.add_parser(
        'ablation', help="Decompose the gains per component.",
        description="Recompute ablation.csv / ablation_mean.csv from "
                    "summary.csv and print the contribution of each component. "
                    "Re-runs no simulation.")
    p.set_defaults(func=cmd_ablation)
    _add_run_selector(p)
    p.add_argument('--metrics', nargs='+', default=None, metavar='COL',
                   help='Metrics printed (default: a readable selection). '
                        'All of them stay written in ablation.csv.')
    p.add_argument('--no-write', action='store_true',
                   help="Print without rewriting the tables of the run.")


def _add_run_selector(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-dir', type=Path, help='Directory of the run.')
    group.add_argument('--latest', action='store_true',
                       help='Use the most recent run.')
    p.add_argument('--output-root', default=DEFAULT_OUTPUT_ROOT,
                   help='Root directory to search with --latest.')


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------

PARAM_OPTIONS = ('seed', 'scenarios', 'fleet_sizes', 'methods',
                 'total_time', 'nb_stations', 'nb_societies', 'nb_charg_spot_low',
                 'nb_charg_spot_high', 'strategy_noise', 'offer_ttl_slots',
                 'late_cancel_fraction', 'reservation_lead_low',
                 'reservation_lead_high', 'society_update_interval', 'alpha_fixed',
                 'output_root', 'label', 'keep_logs', 'save_latency',
                 'save_tables', 'figures', 'log_every')


def params_from_args(args: argparse.Namespace) -> ExperimentParams:
    """Optional configuration file, overridden by the options supplied."""
    base = (ExperimentParams.from_file(args.config) if args.config
            else ExperimentParams())
    overrides = {name: getattr(args, name, None) for name in PARAM_OPTIONS}
    return base.merged_with(overrides)


def cmd_run(args: argparse.Namespace) -> int:
    params = params_from_args(args)

    if args.dry_run:
        print(params.describe())
        nb_scenarios = len(params.scenarios)
        shared_with = ('common to ' + ', '.join(params.scenarios)
                       if nb_scenarios > 1 else f'scenario {params.scenarios[0]}')
        print(f'\nShared environment (seed={params.seed}):')
        print(f'  single grid: {params.nb_stations} stations / '
              f'{params.nb_societies} companies — {shared_with}')
        print(f'  {len(params.fleet_sizes)} fleet(s): '
              f'{list(params.fleet_sizes)} vehicles — initial positions fixed '
              f'before any simulation, common to the scenarios')
        print('\nPlanned cases:')
        for case in params.cases():
            print(f'  {case.tag}')
        return EXIT_OK

    store = run_grid(params)

    if params.figures:
        written = figures.render_all(store.read_summary(), store.figures_dir,
                                     **_shared_tables(store))
        logger.info(f'{len(written)} figures written in {store.figures_dir}')

    means = ablation.mean_rows(ablation.detail_rows(store.read_summary()))
    if means:
        print()
        print(ablation.render_mean_table(means))
        print()

    manifest = store.read_manifest()
    failed = [c['tag'] for c in manifest['cases'] if not c['invariant_ok']]
    if failed:
        logger.error(f"Reservation invariant violated for: {failed}")
        return EXIT_INVARIANT

    print(store.root)
    return EXIT_OK


def _shared_tables(store: RunStore) -> dict:
    """
    Tables describing the shared environment, as `figures.render_all` expects
    them. When absent (run predating the shared grid), the corresponding
    figures are simply omitted.
    """
    params = store.read_params()
    fleet_rows = {n: store.read_shared_table(f'fleet_{n}cars')
                  for n in params.fleet_sizes}
    return {
        'grid_rows':    store.read_shared_table('grid_stations'),
        'society_rows': store.read_shared_table('grid_societies'),
        'fleet_rows':   {n: rows for n, rows in fleet_rows.items() if rows},
    }


def cmd_report(args: argparse.Namespace) -> int:
    store = _resolve_store(args)
    summary = store.read_summary()
    if not summary:
        logger.error(f'{store.summary_path} is empty or missing')
        return EXIT_ERROR
    written = figures.render_all(summary, store.figures_dir,
                                 **_shared_tables(store))
    logger.info(f'{len(written)} figures written in {store.figures_dir}')
    for path in written:
        print(path)
    return EXIT_OK


SHOW_COLUMNS = ('scenario', 'nb_cars', 'method', 'exact_satisfaction',
                'needs_satisfaction', 'mean_travel_distance_km',
                'mean_waiting_time_min', 'total_ms_mean', 'nb_reservations',
                'nb_pres', 'nb_no_show', 'nb_early_canc', 'nb_late_canc',
                'invariant_ok')


def cmd_show(args: argparse.Namespace) -> int:
    store = _resolve_store(args)
    rows = store.read_summary()
    if not rows:
        logger.error(f'{store.summary_path} is empty or missing')
        return EXIT_ERROR

    params = store.read_params()
    manifest = store.read_manifest()
    print(f'Run    : {store.root}')
    print(f'Seed   : {params.seed}   (commit {manifest.get("git_commit")})')
    print(f'Plan   : {params.describe()}')
    print(f'Cases  : {manifest["nb_cases_done"]}/{manifest["nb_cases_planned"]}')
    print()

    columns = list(args.columns) if args.columns else list(SHOW_COLUMNS)
    unknown = [c for c in columns if c not in rows[0]]
    if unknown:
        logger.error(f'Unknown columns: {unknown}')
        return EXIT_ERROR
    print(_render_table(rows, columns))

    diagnostics = _collect_diagnostics(store)
    if diagnostics:
        print('\nDiagnostics:')
        for warning, tags in diagnostics:
            scope = 'every case' if len(tags) == len(rows) else ', '.join(tags)
            print(f'  ({scope})\n    {warning}')
    return EXIT_OK


def cmd_runs(args: argparse.Namespace) -> int:
    runs = RunStore.list_runs(args.output_root)
    if not runs:
        print(f'No run in {args.output_root}')
        return EXIT_OK
    for path in runs:
        store = RunStore(path)
        try:
            manifest = store.read_manifest()
            done = f"{manifest['nb_cases_done']}/{manifest['nb_cases_planned']}"
            state = 'finished' if manifest.get('finished_utc') else 'interrupted'
            print(f"{path}  seed={manifest['seed']}  cases={done}  {state}")
        except (OSError, KeyError, ValueError):
            print(f'{path}  (unreadable manifest)')
    return EXIT_OK


def cmd_methods(args: argparse.Namespace) -> int:
    print(methods_module.describe_table())
    if getattr(args, 'detail', False):
        print()
        for name in methods_module.METHOD_NAMES:
            spec = methods_module.resolve(name)
            print(f"  {name} — {spec.label}")
            print(f"      {spec.note}")
    print(f"\nGroups : {', '.join(sorted(methods_module.METHOD_GROUPS))}")
    print(f"Aliases: {', '.join(sorted(methods_module.ALIASES))}")
    print("\nUse with: --methods ablation | --methods all | --methods "
          "greedy bramev")
    return EXIT_OK


def cmd_ablation(args: argparse.Namespace) -> int:
    store = _resolve_store(args)
    rows = store.read_summary()
    if not rows:
        logger.error(f'{store.summary_path} is empty or missing')
        return EXIT_ERROR

    try:
        detail = ablation.detail_rows(rows)
    except ValueError as exc:          # duplicates in summary.csv
        logger.error(str(exc))
        return EXIT_ERROR

    if not detail:
        present = sorted({r['method'] for r in rows})
        logger.error(
            "No comparable pair in this run: methods present "
            f"{present}. Re-run with --methods ablation to obtain the four "
            "configurations."
        )
        return EXIT_ERROR

    if not args.no_write:
        for path in ablation.write_tables(store, rows):
            logger.info(f'written: {path}')

    metrics = args.metrics or ablation.DEFAULT_REPORT_METRICS
    unknown = [m for m in metrics if m not in ablation.METRICS_BY_COLUMN]
    if unknown:
        logger.error(f'Unknown metrics: {unknown} '
                     f'(expected {list(ablation.METRICS_BY_COLUMN)})')
        return EXIT_ERROR

    means = ablation.mean_rows(detail)
    nb_worlds = len({(r['scenario'], r['nb_cars']) for r in rows})
    print(f'Run    : {store.root}')
    print(f'Worlds : {nb_worlds}   methods: '
          f'{", ".join(sorted({r["method"] for r in rows}))}')
    print()
    print(ablation.render_mean_table(means, metrics))
    return EXIT_OK


def cmd_scenarios(args: argparse.Namespace) -> int:
    table = cfg_module.SimulationConfig.SCENARIOS
    print(f"  {'scenario':<14}{'pres':>6}{'abs':>6}{'early':>7}{'late':>6}{'noise':>7}")
    for name in SCENARIOS:
        p = table[name]
        print(f"  {name:<14}{p['pres']:>6}{p['abs']:>6}{p['early']:>7}"
              f"{p['late']:>6}{p['noise']:>7}")
    print("\nApply with: config.set_scenario(name) or --scenarios")
    return EXIT_OK


# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------

def _resolve_store(args: argparse.Namespace) -> RunStore:
    if getattr(args, 'latest', False):
        return RunStore.latest(args.output_root)
    return RunStore.open(args.run_dir)


def _collect_diagnostics(store: RunStore) -> list[tuple[str, list[str]]]:
    """Diagnostics grouped by message, with the list of the cases concerned."""
    grouped: dict[str, list[str]] = {}
    for result in store.iter_results():
        tag = f"{result['scenario']}/{result['config']['nb_cars']}/{result['mode']}"
        for warning in result['behaviors'].get('diagnostics', []):
            grouped.setdefault(warning, []).append(tag)
    return sorted(grouped.items(), key=lambda kv: -len(kv[1]))


def _render_table(rows: Sequence[dict], columns: Sequence[str]) -> str:
    def cell(value) -> str:
        if value is None:
            return '-'
        if isinstance(value, float):
            return f'{value:.4g}'
        return str(value)

    widths = {c: max(len(c), *(len(cell(r.get(c))) for r in rows)) for c in columns}
    lines = ['  '.join(c.rjust(widths[c]) for c in columns),
             '  '.join('-' * widths[c] for c in columns)]
    for row in rows:
        lines.append('  '.join(cell(row.get(c)).rjust(widths[c]) for c in columns))
    return '\n'.join(lines)


# ----------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbosity)
    try:
        return args.func(args)
    except (ParamsError, FileNotFoundError, OSError) as exc:
        logger.error(str(exc))
        return EXIT_ERROR
    except KeyboardInterrupt:                       # pragma: no cover
        logger.warning('Interrupted by the user.')
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
