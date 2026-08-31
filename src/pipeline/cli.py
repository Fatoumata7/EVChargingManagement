"""
cli.py — Interface en ligne de commande du pipeline BRAM-EV.

    python -m src.pipeline.cli run --scenarios pessimistic --cars 50 100 --seed 42
    python -m src.pipeline.cli run --methods ablation      # les 4 configurations
    python -m src.pipeline.cli run --methods all           # + variantes de BRAM-EV
    python -m src.pipeline.cli ablation --latest
    python -m src.pipeline.cli report --run-dir results_grid/<run>
    python -m src.pipeline.cli show --latest
    python -m src.pipeline.cli runs
    python -m src.pipeline.cli scenarios
    python -m src.pipeline.cli methods

Les sous-commandes séparent volontairement le calcul (`run`) de la restitution
(`report`, `show`) : les figures se régénèrent à partir des tables persistées,
sans relancer les simulations.

Codes de retour : 
    0 succès
    1 erreur de paramètres ou d'entrée/sortie
    2 usage (argparse)
    3 au moins un invariant de réservation violé.
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
# Journalisation
# ----------------------------------------------------------------------

def configure_logging(verbosity: int) -> None:
    """-q -> avertissements seulement ; défaut -> info ; -v -> debug."""
    level = {(-1): 'WARNING', 0: 'INFO'}.get(verbosity, 'DEBUG')
    logger.remove()
    logger.add(sys.stderr, level=level,
               format='<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}')


# ----------------------------------------------------------------------
# Analyseur d'arguments
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='python -m src.pipeline.cli',
        description="Pipeline d'expériences BRAM-EV (simulation, restitution).",
    )
    parser.add_argument('-q', '--quiet', dest='verbosity', action='store_const',
                        const=-1, default=0, help='Limite la sortie aux avertissements.')
    parser.add_argument('-v', '--verbose', dest='verbosity', action='store_const',
                        const=1, help='Sortie de débogage.')

    subparsers = parser.add_subparsers(dest='command', required=True,
                                       metavar='<commande>')
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
        'run', help="Lance une campagne d'expériences.",
        description="Lance une campagne. Tous les paramètres sont surchargeables "
                    "depuis la ligne de commande ou fournis par --config.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.set_defaults(func=cmd_run)

    p.add_argument('--config', type=Path, default=None,
                   help='Fichier YAML/JSON de paramètres. Les options ci-dessous '
                        'le surchargent.')

    plan = p.add_argument_group("plan d'expérience")
    plan.add_argument('--seed', type=int, default=None,
                      help=f'Graine racine (défaut : {DEFAULT_SEED}).')
    plan.add_argument('--scenarios', nargs='+', choices=SCENARIOS, default=None,
                      metavar='NOM', help=f'Scénarios à exécuter {list(SCENARIOS)}.')
    plan.add_argument('--cars', dest='fleet_sizes', nargs='+', type=int, default=None,
                      metavar='N', help='Tailles de flotte à tester.')
    # Pas de `choices` ici : la valeur peut être un nom, un alias (`nearest`) ou
    # un groupe (`ablation`, `variants`, `all`). La validation — et son message
    # d'erreur — appartient à `ExperimentParams`, seule à connaître le registre.
    plan.add_argument('--methods', nargs='+', default=None, metavar='NOM',
                      help="Méthodes à comparer : noms, alias, ou groupes "
                           "(ablation, variants, baseline, all). "
                           "`cli.py methods` affiche la table complète.")

    env = p.add_argument_group('environnement simulé')
    env.add_argument('--total-time', type=int, default=None,
                     help='Durée en slots de 5 min (1440 = 5 jours).')
    env.add_argument('--nb-stations', type=int, default=None)
    env.add_argument('--nb-societies', type=int, default=None)
    env.add_argument('--charg-spot-low', dest='nb_charg_spot_low', type=int, default=None,
                     help='Nombre minimal de bornes par station.')
    env.add_argument('--charg-spot-high', dest='nb_charg_spot_high', type=int, default=None,
                     help='Nombre maximal de bornes par station.')
    env.add_argument('--strategy-noise', type=float, default=None)

    proto = p.add_argument_group("protocole")
    proto.add_argument('--offer-ttl-slots', type=int, default=None,
                       help="Durée de validité d'une offre, en slots.")
    proto.add_argument('--late-cancel-fraction', type=float, default=None,
                       help='Fraction du délai requête→arrivée séparant '
                            'annulation anticipée et tardive.')
    proto.add_argument('--society-update-interval', type=int, default=None,
                       help="Période d'apprentissage collectif, en slots.")
    proto.add_argument('--alpha-fixed', type=float, default=None,
                       help="Alpha commun imposé aux méthodes à alpha fixe "
                            "(bramev_fixed_alpha). Sans effet sur les autres.")

    out = p.add_argument_group('sorties')
    out.add_argument('--output-root', default=None,
                     help=f'Racine des runs (défaut : {DEFAULT_OUTPUT_ROOT}).')
    out.add_argument('--label', default=None,
                     help='Suffixe lisible ajouté au nom du run.')
    out.add_argument('--keep-logs', action=argparse.BooleanOptionalAction, default=None,
                     help='Conserve le journal texte détaillé (volumineux).')
    out.add_argument('--save-latency', action=argparse.BooleanOptionalAction, default=None,
                     help='Table de latence, une ligne par demande.')
    out.add_argument('--save-tables', action=argparse.BooleanOptionalAction, default=None,
                     help='Tables tidy (stations, comportements, alpha…).')
    out.add_argument('--figures', action=argparse.BooleanOptionalAction, default=None,
                     help='Génère les figures à la fin de la campagne.')
    out.add_argument('--log-every', type=int, default=None,
                     help='Fréquence des lignes de progression, en slots.')

    p.add_argument('--dry-run', action='store_true',
                   help='Valide et affiche le plan sans rien exécuter.')


def _add_report(subparsers) -> None:
    p = subparsers.add_parser(
        'report', help='Régénère les figures d\'un run existant.',
        description="Reconstruit toutes les figures depuis summary.csv, "
                    "sans relancer de simulation.")
    p.set_defaults(func=cmd_report)
    _add_run_selector(p)


def _add_show(subparsers) -> None:
    p = subparsers.add_parser(
        'show', help='Affiche le tableau de synthèse d\'un run.')
    p.set_defaults(func=cmd_show)
    _add_run_selector(p)
    p.add_argument('--columns', nargs='+', default=None, metavar='COL',
                   help='Colonnes à afficher (défaut : sélection lisible).')


def _add_runs(subparsers) -> None:
    p = subparsers.add_parser('runs', help='Liste les runs disponibles.')
    p.set_defaults(func=cmd_runs)
    p.add_argument('--output-root', default=DEFAULT_OUTPUT_ROOT)


def _add_scenarios(subparsers) -> None:
    p = subparsers.add_parser(
        'scenarios', help='Affiche la table des scénarios.',
        description="Probabilités de comportement, source unique de vérité "
                    "(src/experiments/config.py).")
    p.set_defaults(func=cmd_scenarios)


def _add_methods(subparsers) -> None:
    p = subparsers.add_parser(
        'methods', help="Affiche le plan d'ablation (méthodes disponibles).",
        description="Composants activés par chaque méthode. Source unique de "
                    "vérité : src/experiments/methods.py.")
    p.set_defaults(func=cmd_methods)
    p.add_argument('--detail', action='store_true',
                   help='Ajoute la note explicative de chaque méthode.')


def _add_ablation(subparsers) -> None:
    p = subparsers.add_parser(
        'ablation', help="Décompose les gains par composant.",
        description="Recalcule ablation.csv / ablation_mean.csv depuis "
                    "summary.csv et affiche la contribution de chaque "
                    "composant. Ne relance aucune simulation.")
    p.set_defaults(func=cmd_ablation)
    _add_run_selector(p)
    p.add_argument('--metrics', nargs='+', default=None, metavar='COL',
                   help='Métriques affichées (défaut : sélection lisible). '
                        'Toutes restent écrites dans ablation.csv.')
    p.add_argument('--no-write', action='store_true',
                   help="Affiche sans réécrire les tables du run.")


def _add_run_selector(p: argparse.ArgumentParser) -> None:
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-dir', type=Path, help='Dossier du run.')
    group.add_argument('--latest', action='store_true',
                       help='Utilise le run le plus récent.')
    p.add_argument('--output-root', default=DEFAULT_OUTPUT_ROOT,
                   help='Racine où chercher avec --latest.')


# ----------------------------------------------------------------------
# Commandes
# ----------------------------------------------------------------------

PARAM_OPTIONS = ('seed', 'scenarios', 'fleet_sizes', 'methods',
                 'total_time', 'nb_stations', 'nb_societies', 'nb_charg_spot_low',
                 'nb_charg_spot_high', 'strategy_noise', 'offer_ttl_slots',
                 'late_cancel_fraction', 'society_update_interval', 'alpha_fixed',
                 'output_root', 'label', 'keep_logs', 'save_latency',
                 'save_tables', 'figures', 'log_every')


def params_from_args(args: argparse.Namespace) -> ExperimentParams:
    """Fichier de configuration éventuel, surchargé par les options fournies."""
    base = (ExperimentParams.from_file(args.config) if args.config
            else ExperimentParams())
    overrides = {name: getattr(args, name, None) for name in PARAM_OPTIONS}
    return base.merged_with(overrides)


def cmd_run(args: argparse.Namespace) -> int:
    params = params_from_args(args)

    if args.dry_run:
        print(params.describe())
        nb_scenarios = len(params.scenarios)
        shared_with = ('commune aux ' + ', '.join(params.scenarios)
                       if nb_scenarios > 1 else f'scénario {params.scenarios[0]}')
        print(f'\nEnvironnement partagé (seed={params.seed}) :')
        print(f'  grille unique : {params.nb_stations} stations / '
              f'{params.nb_societies} sociétés — {shared_with}')
        print(f'  {len(params.fleet_sizes)} flotte(s) : '
              f'{list(params.fleet_sizes)} véhicules — positions initiales '
              f'fixées avant toute simulation, communes aux scénarios')
        print('\nCas planifiés :')
        for case in params.cases():
            print(f'  {case.tag}')
        return EXIT_OK

    store = run_grid(params)

    if params.figures:
        written = figures.render_all(store.read_summary(), store.figures_dir,
                                     **_shared_tables(store))
        logger.info(f'{len(written)} figures écrites dans {store.figures_dir}')

    means = ablation.mean_rows(ablation.detail_rows(store.read_summary()))
    if means:
        print()
        print(ablation.render_mean_table(means))
        print()

    manifest = store.read_manifest()
    failed = [c['tag'] for c in manifest['cases'] if not c['invariant_ok']]
    if failed:
        logger.error(f"Invariant de réservation violé pour : {failed}")
        return EXIT_INVARIANT

    print(store.root)
    return EXIT_OK


def _shared_tables(store: RunStore) -> dict:
    """
    Tables décrivant l'environnement partagé, telles que `figures.render_all`
    les attend. Absentes (run antérieur à la grille partagée), les figures
    correspondantes sont simplement omises.
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
        logger.error(f'{store.summary_path} est vide ou absent')
        return EXIT_ERROR
    written = figures.render_all(summary, store.figures_dir,
                                 **_shared_tables(store))
    logger.info(f'{len(written)} figures écrites dans {store.figures_dir}')
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
        logger.error(f'{store.summary_path} est vide ou absent')
        return EXIT_ERROR

    params = store.read_params()
    manifest = store.read_manifest()
    print(f'Run       : {store.root}')
    print(f'Graine    : {params.seed}   (commit {manifest.get("git_commit")})')
    print(f'Plan      : {params.describe()}')
    print(f'Cas       : {manifest["nb_cases_done"]}/{manifest["nb_cases_planned"]}')
    print()

    columns = list(args.columns) if args.columns else list(SHOW_COLUMNS)
    unknown = [c for c in columns if c not in rows[0]]
    if unknown:
        logger.error(f'Colonnes inconnues : {unknown}')
        return EXIT_ERROR
    print(_render_table(rows, columns))

    diagnostics = _collect_diagnostics(store)
    if diagnostics:
        print('\nDiagnostics :')
        for warning, tags in diagnostics:
            scope = 'tous les cas' if len(tags) == len(rows) else ', '.join(tags)
            print(f'  ({scope})\n    {warning}')
    return EXIT_OK


def cmd_runs(args: argparse.Namespace) -> int:
    runs = RunStore.list_runs(args.output_root)
    if not runs:
        print(f'Aucun run dans {args.output_root}')
        return EXIT_OK
    for path in runs:
        store = RunStore(path)
        try:
            manifest = store.read_manifest()
            done = f"{manifest['nb_cases_done']}/{manifest['nb_cases_planned']}"
            state = 'terminé' if manifest.get('finished_utc') else 'interrompu'
            print(f"{path}  seed={manifest['seed']}  cas={done}  {state}")
        except (OSError, KeyError, ValueError):
            print(f'{path}  (manifeste illisible)')
    return EXIT_OK


def cmd_methods(args: argparse.Namespace) -> int:
    print(methods_module.describe_table())
    if getattr(args, 'detail', False):
        print()
        for name in methods_module.METHOD_NAMES:
            spec = methods_module.resolve(name)
            print(f"  {name} — {spec.label}")
            print(f"      {spec.note}")
    print(f"\nGroupes : {', '.join(sorted(methods_module.METHOD_GROUPS))}")
    print(f"Alias   : {', '.join(sorted(methods_module.ALIASES))}")
    print("\nUtiliser avec : --methods ablation | --methods all | --methods "
          "greedy bramev")
    return EXIT_OK


def cmd_ablation(args: argparse.Namespace) -> int:
    store = _resolve_store(args)
    rows = store.read_summary()
    if not rows:
        logger.error(f'{store.summary_path} est vide ou absent')
        return EXIT_ERROR

    try:
        detail = ablation.detail_rows(rows)
    except ValueError as exc:          # doublons dans summary.csv
        logger.error(str(exc))
        return EXIT_ERROR

    if not detail:
        present = sorted({r['method'] for r in rows})
        logger.error(
            "Aucun couple comparable dans ce run : méthodes présentes "
            f"{present}. Relancer avec --methods ablation pour obtenir "
            "les quatre configurations."
        )
        return EXIT_ERROR

    if not args.no_write:
        for path in ablation.write_tables(store, rows):
            logger.info(f'écrit : {path}')

    metrics = args.metrics or ablation.DEFAULT_REPORT_METRICS
    unknown = [m for m in metrics if m not in ablation.METRICS_BY_COLUMN]
    if unknown:
        logger.error(f'Métriques inconnues : {unknown} '
                     f'(attendu {list(ablation.METRICS_BY_COLUMN)})')
        return EXIT_ERROR

    means = ablation.mean_rows(detail)
    nb_worlds = len({(r['scenario'], r['nb_cars']) for r in rows})
    print(f'Run    : {store.root}')
    print(f'Mondes : {nb_worlds}   méthodes : '
          f'{", ".join(sorted({r["method"] for r in rows}))}')
    print()
    print(ablation.render_mean_table(means, metrics))
    return EXIT_OK


def cmd_scenarios(args: argparse.Namespace) -> int:
    table = cfg_module.SimulationConfig.SCENARIOS
    print(f"  {'scénario':<14}{'pres':>6}{'abs':>6}{'early':>7}{'late':>6}{'noise':>7}")
    for name in SCENARIOS:
        p = table[name]
        print(f"  {name:<14}{p['pres']:>6}{p['abs']:>6}{p['early']:>7}"
              f"{p['late']:>6}{p['noise']:>7}")
    print("\nAppliquer avec : config.set_scenario(nom) ou --scenarios")
    return EXIT_OK


# ----------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------

def _resolve_store(args: argparse.Namespace) -> RunStore:
    if getattr(args, 'latest', False):
        return RunStore.latest(args.output_root)
    return RunStore.open(args.run_dir)


def _collect_diagnostics(store: RunStore) -> list[tuple[str, list[str]]]:
    """Diagnostics groupés par message, avec la liste des cas concernés."""
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
        logger.warning('Interrompu par l\'utilisateur.')
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
