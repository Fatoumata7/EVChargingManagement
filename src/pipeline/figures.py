"""
figures.py — Figures produites à partir des tables, jamais des objets de simulation.

Conséquence : `cli.py report --run-dir ...` régénère toutes les figures d'une
campagne sans relancer une seule simulation. Corriger un axe ou une couleur ne
coûte plus des heures de calcul.

Chaque fonction `fig_*` est une fonction pure (tables -> Figure) et renvoie
`None` si les données nécessaires sont absentes, afin qu'une campagne partielle
produise quand même les figures qu'elle peut.

Deux familles de tables alimentent ces figures :

* `summary.csv` — un résultat par cas, pour les figures de performance ;
* `grid_stations.csv`, `grid_societies.csv`, `fleet_<n>cars.csv` — la grille et
  les flottes partagées, écrites avant toute simulation. Les figures
  correspondantes (`fig_grid`, `fig_fleet`) documentent l'environnement commun
  à tous les scénarios : c'est la pièce justificative de leur comparabilité.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import matplotlib
matplotlib.use('Agg')          # aucun affichage : le pipeline est non interactif
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

import src.experiments.methods as methods
from src.pipeline import ablation

Row = Mapping[str, Any]
Rows = Sequence[Row]

# Couleurs par méthode, stables d'une figure à l'autre. Les quatre barreaux de
# l'échelle d'ablation vont du chaud (Nearest) au froid (BRAM-EV complet) ; les
# baselines de référence puis les variantes reprennent des teintes distinctes
# pour ne pas se confondre avec eux.
METHOD_COLORS = {
    'greedy':               '#d9822b',
    'multistation':         '#c9a227',
    'multistation_rep':     '#6a9a3a',
    'bramev':               '#3b7dd8',
    'min_waiting':          '#4a9c8c',
    'load_aware':           '#9c7b4a',
    'random_feasible':      '#8a8a8a',
    'bramev_nearest_offer': '#8e5bd0',
    'bramev_fixed_alpha':   '#12a5a5',
    'bramev_global_rep':    '#d1467f',
    'bramev_event_score':   '#7a6a5c',
}
METHOD_LABELS = {name: spec.label for name, spec in methods.METHODS.items()}
OUTCOME_COLORS = {
    'pres':  '#4c9a2a',
    'abs':   '#c0392b',
    'late':  '#e67e22',
    'early': '#f1c40f',
}
FIGSIZE = (11, 4.2)
DPI = 130


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _scenarios(rows: Rows) -> list[str]:
    order = ['optimistic', 'balance', 'pessimistic']
    present = {r['scenario'] for r in rows}
    return [s for s in order if s in present] + sorted(present - set(order))


def _methods(rows: Rows) -> list[str]:
    """Méthodes présentes, dans l'ordre du registre (échelle, baselines, variantes)."""
    order = list(methods.METHOD_NAMES)
    present = {r['method'] for r in rows}
    return [m for m in order if m in present] + sorted(present - set(order))


def _series(rows: Rows, scenario: str, method: str, column: str):
    """(x, y) triés par taille de flotte, points manquants exclus."""
    pairs = [(r['nb_cars'], r.get(column)) for r in rows
             if r['scenario'] == scenario and r['method'] == method
             and r.get(column) is not None]
    pairs.sort()
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _plot_lines(ax, rows: Rows, scenario: str, column: str, ylabel: str,
                title: str, percent: bool = False) -> bool:
    drawn = False
    for method in _methods(rows):
        x, y = _series(rows, scenario, method, column)
        if not x:
            continue
        if percent:
            y = [100 * v for v in y]
        ax.plot(x, y, marker='o', color=METHOD_COLORS.get(method),
                label=METHOD_LABELS.get(method, method))
        drawn = True
    ax.set_xlabel('Nombre de véhicules')
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight='bold', fontsize=10)
    ax.grid(alpha=0.3, linestyle=':')
    if drawn:
        ax.legend(fontsize=8)
    return drawn


def _tag(scenario: str) -> str:
    return scenario[:3].upper()


def _finish(fig) -> Any:
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------
# Figures par scénario
# ----------------------------------------------------------------------

def fig_satisfaction(rows: Rows, scenario: str):
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'exact_satisfaction', 'Satisfaction (%)',
                     f'[{_tag(scenario)}] Satisfaction exacte', percent=True)
    ok |= _plot_lines(axes[1], rows, scenario, 'needs_satisfaction', 'Satisfaction (%)',
                      f'[{_tag(scenario)}] Satisfaction des besoins', percent=True)
    for ax in axes:
        ax.set_ylim(0, 105)
        ax.axhline(100, color='black', linestyle='--', linewidth=0.8, alpha=0.4)
    return _finish(fig) if ok else None


def fig_travel_waiting(rows: Rows, scenario: str):
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'mean_travel_distance_km',
                     'Distance (km)', f'[{_tag(scenario)}] Distance moyenne parcourue')
    ok |= _plot_lines(axes[1], rows, scenario, 'mean_waiting_time_min',
                      'Attente (min)', f'[{_tag(scenario)}] Attente moyenne en station')
    return _finish(fig) if ok else None


def fig_latency(rows: Rows, scenario: str):
    """Décomposition de la latence : réponse réseau, sélection, bout en bout."""
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    ok = _plot_lines(axes[0], rows, scenario, 'last_offer_ms_mean', 'ms',
                     f'[{_tag(scenario)}] Émission → dernière offre')
    ok |= _plot_lines(axes[1], rows, scenario, 'selection_ms_mean', 'ms',
                      f'[{_tag(scenario)}] Sélection par le véhicule')
    ok |= _plot_lines(axes[2], rows, scenario, 'total_ms_mean', 'ms',
                      f'[{_tag(scenario)}] Bout en bout (jusqu\'à confirmation)')
    return _finish(fig) if ok else None


def fig_demand_funnel(rows: Rows, scenario: str):
    """Entonnoir : demandes émises, ayant reçu une offre, confirmées."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'answer_rate',
                     "Part des demandes (%)",
                     f'[{_tag(scenario)}] Demandes ayant reçu une offre',
                     percent=True)
    ok |= _plot_lines(axes[1], rows, scenario, 'mean_offers_per_demand',
                      "Offres / demande",
                      f'[{_tag(scenario)}] Offres reçues par demande')
    axes[0].set_ylim(0, 105)
    return _finish(fig) if ok else None


def fig_outcomes(rows: Rows, scenario: str):
    """
    Issues des réservations, en part du total, méthode par méthode.

    Les quatre issues comportementales sont empilées ; `breakdown` et
    `unresolved` sont exclues car elles ne relèvent pas du comportement de
    l'usager (panne, fin d'horizon).
    """
    methods = _methods(rows)
    fleets = sorted({r['nb_cars'] for r in rows if r['scenario'] == scenario})
    if not fleets:
        return None

    fig, axes = plt.subplots(1, len(methods), figsize=(5.5 * len(methods), 4.2),
                             squeeze=False)
    bar_width = 0.6 if len(fleets) > 2 else 0.4
    outcomes = ('pres', 'late', 'early', 'abs')
    keys = {'pres': 'nb_pres', 'late': 'nb_late_canc',
            'early': 'nb_early_canc', 'abs': 'nb_no_show'}

    for ax, method in zip(axes[0], methods):
        bottom = np.zeros(len(fleets))
        for outcome in outcomes:
            values = []
            for nb_cars in fleets:
                row = next((r for r in rows if r['scenario'] == scenario
                            and r['method'] == method and r['nb_cars'] == nb_cars), None)
                total = (row or {}).get('nb_reservations') or 0
                count = (row or {}).get(keys[outcome]) or 0
                values.append(100 * count / total if total else 0.)
            ax.bar([str(n) for n in fleets], values, bottom=bottom,
                   width=bar_width, color=OUTCOME_COLORS[outcome],
                   label=outcome, alpha=0.9)
            bottom += np.asarray(values)
        ax.set_title(f'[{_tag(scenario)}] Issues — {METHOD_LABELS.get(method, method)}',
                     fontweight='bold', fontsize=10)
        ax.set_xlabel('Nombre de véhicules')
        ax.set_ylabel('Part des réservations (%)')
        ax.set_ylim(0, 105)
        ax.legend(fontsize=8, ncol=2)
        ax.grid(alpha=0.3, linestyle=':', axis='y')
    return _finish(fig)


def fig_offer_protocol(rows: Rows, scenario: str):
    """Santé du protocole d'offre : émises, confirmées, expirées, refusées."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'nb_offer_issued', "Offres",
                     f'[{_tag(scenario)}] Offres émises')
    ok |= _plot_lines(axes[0], rows, scenario, 'nb_reservations', "Offres",
                      f'[{_tag(scenario)}] Offres émises vs confirmées')
    ok |= _plot_lines(axes[1], rows, scenario, 'nb_confirm_refused',
                      "Confirmations refusées",
                      f'[{_tag(scenario)}] Confirmations refusées par la station')
    return _finish(fig) if ok else None


def fig_stations(rows: Rows, scenario: str):
    """Charge côté opérateur : occupation des bornes et énergie délivrée."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'mean_occupancy_rate',
                     "Occupation (%)",
                     f'[{_tag(scenario)}] Taux d\'occupation moyen des bornes',
                     percent=True)
    ok |= _plot_lines(axes[1], rows, scenario, 'total_station_demand_kwh',
                      "Énergie (kWh)",
                      f'[{_tag(scenario)}] Énergie délivrée (toutes stations)')
    return _finish(fig) if ok else None


# ----------------------------------------------------------------------
# Figures transverses
# ----------------------------------------------------------------------

def fig_scenarios_overview(rows: Rows):
    """Satisfaction exacte, un panneau par scénario : vue d'ensemble."""
    scenarios = _scenarios(rows)
    if not scenarios:
        return None
    fig, axes = plt.subplots(1, len(scenarios), figsize=(4.6 * len(scenarios), 4.2),
                             squeeze=False, sharey=True)
    for ax, scenario in zip(axes[0], scenarios):
        _plot_lines(ax, rows, scenario, 'exact_satisfaction', 'Satisfaction (%)',
                    f'[{_tag(scenario)}] Satisfaction exacte', percent=True)
        ax.set_ylim(0, 105)
    return _finish(fig)


def fig_scalability(rows: Rows):
    """Coût de calcul : temps de résolution PLI et latence bout en bout."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    drawn = False
    for scenario in _scenarios(rows):
        for method in _methods(rows):
            x, y = _series(rows, scenario, method, 'mean_processing_ms')
            if x:
                axes[0].plot(x, y, marker='o',
                             label=f'{_tag(scenario)} / {METHOD_LABELS.get(method, method)}')
                drawn = True
            x, y = _series(rows, scenario, method, 'wall_time_s')
            if x:
                axes[1].plot(x, y, marker='o',
                             label=f'{_tag(scenario)} / {METHOD_LABELS.get(method, method)}')
    for ax, ylabel, title in ((axes[0], 'ms', 'Temps de résolution PLI par station'),
                              (axes[1], 's', 'Temps de calcul total du run')):
        ax.set_xlabel('Nombre de véhicules')
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontweight='bold', fontsize=10)
        ax.grid(alpha=0.3, linestyle=':')
        ax.legend(fontsize=7)
    return _finish(fig) if drawn else None


def fig_intent_vs_observed(rows: Rows):
    """
    Probabilité du scénario, intention tirée et issue observée.

    Rend visible l'écart structurel : une intention d'annulation anticipée peut
    ne pas être réalisable si la réservation n'est pas prise à l'avance.
    """
    scenarios = _scenarios(rows)
    if not scenarios:
        return None
    outcomes = ('pres', 'abs', 'early', 'late')
    fig, axes = plt.subplots(1, len(scenarios), figsize=(4.6 * len(scenarios), 4.2),
                             squeeze=False, sharey=True)
    width = 0.38
    positions = np.arange(len(outcomes))

    for ax, scenario in zip(axes[0], scenarios):
        subset = [r for r in rows if r['scenario'] == scenario]
        if not subset:
            continue
        intents = [_mean_of(subset, f'intent_{o}') for o in outcomes]
        observed = [_mean_of(subset, f'rate_{o}') for o in outcomes]
        ax.bar(positions - width / 2, [100 * v for v in intents], width,
               label='intention tirée', color='#8e9aaf')
        ax.bar(positions + width / 2, [100 * v for v in observed], width,
               label='issue observée', color='#3b7dd8')
        ax.set_xticks(positions)
        ax.set_xticklabels(outcomes)
        ax.set_ylabel('Part des réservations (%)')
        ax.set_title(f'[{_tag(scenario)}] Intention vs issue', fontweight='bold',
                     fontsize=10)
        ax.grid(alpha=0.3, linestyle=':', axis='y')
        ax.legend(fontsize=8)
    return _finish(fig)


def _society_colors(rows: Rows) -> dict:
    """Une couleur stable par société, partagée par toutes les figures de grille."""
    ids = sorted({int(r['society_id']) for r in rows})
    cmap = plt.get_cmap('tab10')
    return {sid: cmap(i % 10) for i, sid in enumerate(ids)}


def _grid_extent(rows: Rows) -> float:
    """Côté de la zone simulée, en mètres, lu dans la table elle-même."""
    values = [r.get('grid_m') for r in rows if r.get('grid_m')]
    return float(values[0]) if values else 0.


def _draw_grid_map(ax, station_rows: Rows, colors: dict,
                   annotate: bool = True) -> None:
    """Carte des stations : couleur = société, aire du marqueur ∝ nb de bornes."""
    side = _grid_extent(station_rows)
    for row in station_rows:
        sid = int(row['society_id'])
        ax.scatter(row['x_m'] / 1e3, row['y_m'] / 1e3,
                   s=28 * float(row['nb_charg_spot']),
                   color=colors[sid], edgecolor='black', linewidth=0.6,
                   zorder=3)
        if annotate:
            ax.annotate(str(int(row['station_id'])),
                        (row['x_m'] / 1e3, row['y_m'] / 1e3),
                        fontsize=6, ha='center', va='center',
                        color='white', zorder=4)
    if side:
        ax.set_xlim(-0.05 * side / 1e3, 1.05 * side / 1e3)
        ax.set_ylim(-0.05 * side / 1e3, 1.05 * side / 1e3)
    ax.set_aspect('equal')
    ax.set_xlabel('x (km)')
    ax.set_ylabel('y (km)')
    ax.grid(alpha=0.3, linestyle=':')


def fig_grid(station_rows: Rows, society_rows: Rows | None = None):
    """
    L'infrastructure partagée : où sont les stations, à qui, avec quel alpha.

    Cette figure ne dépend d'aucun scénario — c'est précisément son intérêt :
    elle atteste que `optimistic`, `balance` et `pessimistic` ont bien tourné
    sur la même grille.
    """
    if not station_rows:
        return None

    colors = _society_colors(station_rows)
    societies = sorted(society_rows or [], key=lambda r: int(r['society_id']))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.9),
                             gridspec_kw={'width_ratios': [1, 1.25, 1]})

    # --- 1. Où sont les stations, et à qui
    _draw_grid_map(axes[0], station_rows, colors)
    for row in societies:
        axes[0].scatter(row['x_m'] / 1e3, row['y_m'] / 1e3,
                        marker='*', s=260,
                        color=colors[int(row['society_id'])],
                        edgecolor='black', linewidth=0.8, zorder=5)
    total_spots = sum(int(r['nb_charg_spot']) for r in station_rows)
    axes[0].set_title(f'{len(station_rows)} stations, {len(colors)} sociétés, '
                      f'{total_spots} bornes',
                      fontweight='bold', fontsize=10)

    handles = [plt.Line2D([], [], marker='o', linestyle='', color=color,
                          markeredgecolor='black', markersize=8,
                          label=f'Société {sid}')
               for sid, color in colors.items()]
    if societies:
        handles.append(plt.Line2D([], [], marker='*', linestyle='', color='grey',
                                  markeredgecolor='black', markersize=12,
                                  label='Siège'))
    # `best` : matplotlib place la légende là où elle masque le moins de
    # stations. Hors des axes, `tight_layout` la rognerait.
    axes[0].legend(handles=handles, fontsize=7, loc='best', framealpha=0.85)

    # --- 2. Alpha initial, station par station, regroupées par société
    ordered = sorted(station_rows,
                     key=lambda r: (int(r['society_id']), int(r['station_id'])))
    axes[1].bar(range(len(ordered)),
                [float(r['alpha_init']) for r in ordered],
                color=[colors[int(r['society_id'])] for r in ordered],
                edgecolor='black', linewidth=0.4)
    axes[1].set_xticks(range(len(ordered)))
    axes[1].set_xticklabels([int(r['station_id']) for r in ordered],
                            fontsize=6, rotation=90 if len(ordered) > 25 else 0)
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel('Station (regroupées par société)')
    axes[1].set_ylabel(r'$\alpha$ initial')
    axes[1].set_title(r'Stratégie initiale des stations ($\alpha$)',
                      fontweight='bold', fontsize=10)
    axes[1].grid(alpha=0.3, linestyle=':', axis='y')

    # --- 3. Points de stratégie, portés par la société
    keys = sorted({k for row in societies for k in row if k.startswith('strategy_')})
    if keys:
        width = 0.8 / len(societies)
        offsets = np.arange(len(keys))
        for i, row in enumerate(societies):
            sid = int(row['society_id'])
            axes[2].bar(offsets + i * width, [float(row[k]) for k in keys],
                        width=width, color=colors[sid], edgecolor='black',
                        linewidth=0.4,
                        label=f"S{sid} ({int(row['nb_stations'])} st.)")
        axes[2].set_xticks(offsets + 0.4 - width / 2)
        axes[2].set_xticklabels([k.split('_', 1)[1] for k in keys], fontsize=8)
        axes[2].legend(fontsize=7, frameon=False)
    axes[2].set_xlabel('Issue de la réservation')
    axes[2].set_ylabel('Points')
    axes[2].set_title('Stratégie de points des sociétés',
                      fontweight='bold', fontsize=10)
    axes[2].grid(alpha=0.3, linestyle=':', axis='y')

    fig.suptitle('Grille partagée par tous les scénarios et toutes les flottes',
                 fontweight='bold', fontsize=11)
    return _finish(fig)


def fig_fleet(station_rows: Rows, car_rows: Rows, nb_cars: int):
    """
    Une flotte : positions initiales des véhicules sur la grille, et dispersion
    de leurs caractéristiques.

    Comme la grille, cette flotte est commune aux trois scénarios.
    """
    if not car_rows:
        return None

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4),
                             gridspec_kw={'width_ratios': [1.25, 1, 1]})

    if station_rows:
        _draw_grid_map(axes[0], station_rows, _society_colors(station_rows),
                       annotate=False)
    axes[0].scatter([r['x_m'] / 1e3 for r in car_rows],
                    [r['y_m'] / 1e3 for r in car_rows],
                    s=9, color='#3b7dd8', alpha=0.65, zorder=2,
                    label='Position initiale')
    axes[0].set_aspect('equal')
    axes[0].set_xlabel('x (km)')
    axes[0].set_ylabel('y (km)')
    axes[0].grid(alpha=0.3, linestyle=':')
    axes[0].set_title(f'Flotte partagée — {nb_cars} véhicules',
                      fontweight='bold', fontsize=10)
    axes[0].legend(fontsize=7, loc='upper right', framealpha=0.9)

    for ax, column, title, unit in (
        (axes[1], 'autonomy_km', 'Autonomie', 'km'),
        (axes[2], 'soc_init', 'SoC initial', 'fraction de la batterie'),
    ):
        values = [float(r[column]) for r in car_rows if r.get(column) is not None]
        ax.hist(values, bins=min(20, max(5, len(set(values)))),
                color='#3b7dd8', edgecolor='black', linewidth=0.4)
        ax.set_xlabel(unit)
        ax.set_ylabel('Véhicules')
        # Un effectif est entier : des graduations à 3.5 véhicules n'ont pas de sens.
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_title(title, fontweight='bold', fontsize=10)
        ax.grid(alpha=0.3, linestyle=':', axis='y')

    return _finish(fig)


def _mean_of(rows: Rows, column: str) -> float:
    values = [r[column] for r in rows if r.get(column) is not None]
    return float(np.mean(values)) if values else 0.


# ----------------------------------------------------------------------
# Étude d'ablation
# ----------------------------------------------------------------------

#: Métriques tracées par les figures d'ablation, dans l'ordre des panneaux.
ABLATION_METRICS: tuple[str, ...] = (
    'exact_satisfaction', 'rate_abs', 'mean_service_rate', 'slot_waste_rate',
)


def _ablation_bars(means: Rows, kind: str, title: str):
    """
    Un panneau par métrique, une barre par composant.

    La barre porte l'écart relatif moyen ; sa couleur dit si le composant
    améliore ou dégrade la métrique (la direction dépend de la métrique : un
    taux de no-show qui baisse est un gain). L'étiquette au-dessus donne la
    part des mondes où le composant améliore effectivement la métrique — un
    gain moyen porté par un seul monde se repère ainsi immédiatement.
    """
    selected = [c for c in ABLATION_METRICS
                if any(r['metric'] == c and r['kind'] == kind for r in means)]
    if not selected:
        return None

    components: list[str] = []
    for row in means:
        if row['kind'] == kind and row['component'] not in components:
            components.append(row['component'])
    if not components:
        return None

    fig, axes = plt.subplots(1, len(selected),
                             figsize=(3.4 * len(selected) + 1.5, 4.4),
                             squeeze=False)
    x = np.arange(len(components))

    for ax, column in zip(axes[0], selected):
        by_component = {r['component']: r for r in means
                        if r['kind'] == kind and r['metric'] == column}
        values, colors, shares = [], [], []
        for component in components:
            row = by_component.get(component)
            value = None if row is None else row['mean_delta_pct']
            values.append(0. if value is None else value)
            improves = bool(row and row['mean_delta'] and
                            ablation.METRICS_BY_COLUMN[column].improves(row['mean_delta']))
            colors.append('#3b7dd8' if improves else '#c0392b')
            shares.append(None if row is None else row['share_improved'])

        ax.bar(x, values, color=colors, width=0.6)
        ax.axhline(0, color='#333', linewidth=0.8)
        span = max(abs(v) for v in values) or 1.
        for xi, value, share in zip(x, values, shares):
            if share is None:
                continue
            offset = 0.06 * span * (1 if value >= 0 else -1)
            ax.text(xi, value + offset, f'{share:.0%}', ha='center',
                    va='bottom' if value >= 0 else 'top', fontsize=8,
                    color='#444')
        ax.set_xticks(x)
        ax.set_xticklabels([_wrap(c) for c in components], fontsize=8)
        ax.set_ylabel('écart relatif moyen (%)')
        ax.set_title(ablation.METRICS_BY_COLUMN[column].label,
                     fontweight='bold', fontsize=10)
        ax.grid(alpha=0.3, linestyle=':', axis='y')
        ax.margins(y=0.25)

    fig.suptitle(title, fontweight='bold', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def _wrap(text: str, width: int = 14) -> str:
    """Coupe une étiquette d'axe sur deux lignes plutôt que de la tronquer."""
    words, lines, current = text.split(), [], ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return '\n'.join(lines)


def fig_ablation_components(rows: Rows):
    """Contribution de chaque composant ajouté le long de l'échelle d'ablation."""
    means = ablation.mean_rows(ablation.ladder_rows(rows))
    if not means:
        return None
    return _ablation_bars(
        means, 'ladder',
        "Contribution de chaque composant (écart au barreau précédent)")


def fig_ablation_variants(rows: Rows):
    """Effet du remplacement d'un mécanisme interne de BRAM-EV."""
    means = ablation.mean_rows(ablation.variant_rows(rows))
    if not means:
        return None
    return _ablation_bars(
        means, 'variant',
        "Variantes de BRAM-EV (écart à la méthode complète)")


def fig_ablation_ladder(rows: Rows, scenario: str):
    """Satisfaction et no-shows barreau par barreau, en fonction de la flotte."""
    ladder = [r for r in rows if r['method'] in methods.LADDER
              and r['scenario'] == scenario]
    if not ladder:
        return None
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], ladder, scenario, 'exact_satisfaction',
                     'Satisfaction (%)',
                     f'[{_tag(scenario)}] Satisfaction — échelle d\'ablation',
                     percent=True)
    ok |= _plot_lines(axes[1], ladder, scenario, 'rate_abs', 'No-show (%)',
                      f'[{_tag(scenario)}] Taux de no-show — échelle d\'ablation',
                      percent=True)
    return _finish(fig) if ok else None


# ----------------------------------------------------------------------
# Rendu complet
# ----------------------------------------------------------------------

PER_SCENARIO: tuple[tuple[str, Callable], ...] = (
    ('satisfaction',   fig_satisfaction),
    ('ablation_ladder', fig_ablation_ladder),
    ('travel_waiting', fig_travel_waiting),
    ('latency',        fig_latency),
    ('demand_funnel',  fig_demand_funnel),
    ('outcomes',       fig_outcomes),
    ('offer_protocol', fig_offer_protocol),
    ('stations',       fig_stations),
)

GLOBAL: tuple[tuple[str, Callable], ...] = (
    ('overview_satisfaction', fig_scenarios_overview),
    ('scalability',           fig_scalability),
    ('intent_vs_observed',    fig_intent_vs_observed),
    ('ablation_components',   fig_ablation_components),
    ('ablation_variants',     fig_ablation_variants),
)


def _save(fig, path: Path, written: list[Path]) -> None:
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    written.append(path)


def render_all(summary_rows: Rows, figures_dir: str | Path,
               grid_rows: Rows | None = None,
               society_rows: Rows | None = None,
               fleet_rows: Mapping[int, Rows] | None = None) -> list[Path]:
    """
    Produit toutes les figures exploitables à partir des tables persistées.

    Parameters
    ----------
    summary_rows : Rows
        `summary.csv` — figures de performance.
    grid_rows, society_rows : Rows | None
        `grid_stations.csv` / `grid_societies.csv` — figure de la grille
        partagée. Absents (par exemple pour un run antérieur au partage de
        grille), la figure est simplement omise.
    fleet_rows : Mapping[int, Rows] | None
        `{nb_cars: fleet_<n>cars.csv}` — une figure de flotte par taille.

    Returns
    -------
    list[Path]
        Fichiers PNG écrits.
    """
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # L'environnement partagé se trace même sans résultat : il est disponible
    # dès la préparation du run, avant la première simulation.
    if grid_rows:
        fig = fig_grid(grid_rows, society_rows)
        if fig is not None:
            _save(fig, figures_dir / 'grid.png', written)

    for nb_cars, rows in sorted((fleet_rows or {}).items()):
        fig = fig_fleet(grid_rows or [], rows, nb_cars)
        if fig is not None:
            _save(fig, figures_dir / f'fleet_{nb_cars}cars.png', written)

    if not summary_rows:
        return written

    for scenario in _scenarios(summary_rows):
        for name, builder in PER_SCENARIO:
            fig = builder(summary_rows, scenario)
            if fig is None:
                continue
            _save(fig, figures_dir / f'{name}_{scenario}.png', written)

    for name, builder in GLOBAL:
        fig = builder(summary_rows)
        if fig is None:
            continue
        _save(fig, figures_dir / f'{name}.png', written)

    return written
