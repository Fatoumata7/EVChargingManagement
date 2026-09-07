"""
figures.py — Figures built from the tables, never from the simulation objects.

Consequence: `cli.py report --run-dir ...` regenerates every figure of a
campaign without re-running a single simulation. Fixing an axis or a color no
longer costs hours of computation.

Each `fig_*` function is a pure function (tables -> Figure) and returns `None`
when the data it needs is missing, so that a partial campaign still produces the
figures it can.

Two families of tables feed these figures:

* `summary.csv` — one result per case, for the performance figures;
* `grid_stations.csv`, `grid_societies.csv`, `fleet_<n>cars.csv` — the shared
  grid and fleets, written before any simulation. The corresponding figures
  (`fig_grid`, `fig_fleet`) document the environment common to every scenario:
  they are the supporting evidence of their comparability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import matplotlib
matplotlib.use('Agg')          # no display: the pipeline is non-interactive
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

import src.experiments.methods as methods
from src.pipeline import ablation

Row = Mapping[str, Any]
Rows = Sequence[Row]

# Colors per method, stable from one figure to the next. The four rungs of the
# ablation ladder go from warm (Nearest) to cold (full BRAM-EV); the reference
# baselines and then the variants use distinct hues so as not to be confused
# with them.
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
    """Methods present, in registry order (ladder, baselines, variants)."""
    order = list(methods.METHOD_NAMES)
    present = {r['method'] for r in rows}
    return [m for m in order if m in present] + sorted(present - set(order))


def _series(rows: Rows, scenario: str, method: str, column: str):
    """(x, y) sorted by fleet size, missing points excluded."""
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
    ax.set_xlabel('Number of vehicles')
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
# Per-scenario figures
# ----------------------------------------------------------------------

def fig_satisfaction(rows: Rows, scenario: str):
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'exact_satisfaction', 'Satisfaction (%)',
                     f'[{_tag(scenario)}] Exact satisfaction', percent=True)
    ok |= _plot_lines(axes[1], rows, scenario, 'needs_satisfaction', 'Satisfaction (%)',
                      f'[{_tag(scenario)}] Needs satisfaction', percent=True)
    for ax in axes:
        ax.set_ylim(0, 105)
        ax.axhline(100, color='black', linestyle='--', linewidth=0.8, alpha=0.4)
    return _finish(fig) if ok else None


def fig_travel_waiting(rows: Rows, scenario: str):
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'mean_travel_distance_km',
                     'Distance (km)', f'[{_tag(scenario)}] Mean distance driven')
    ok |= _plot_lines(axes[1], rows, scenario, 'mean_waiting_time_min',
                      'Waiting (min)', f'[{_tag(scenario)}] Mean waiting time at the station')
    return _finish(fig) if ok else None


def fig_latency(rows: Rows, scenario: str):
    """Decomposition of the latency: network response, selection, end to end."""
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    ok = _plot_lines(axes[0], rows, scenario, 'last_offer_ms_mean', 'ms',
                     f'[{_tag(scenario)}] Emission → last offer')
    ok |= _plot_lines(axes[1], rows, scenario, 'selection_ms_mean', 'ms',
                      f'[{_tag(scenario)}] Selection by the vehicle')
    ok |= _plot_lines(axes[2], rows, scenario, 'total_ms_mean', 'ms',
                      f'[{_tag(scenario)}] End to end (up to confirmation)')
    return _finish(fig) if ok else None


def fig_demand_funnel(rows: Rows, scenario: str):
    """Funnel: demands emitted, answered by an offer, confirmed."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'answer_rate',
                     "Share of the demands (%)",
                     f'[{_tag(scenario)}] Demands that received an offer',
                     percent=True)
    ok |= _plot_lines(axes[1], rows, scenario, 'mean_offers_per_demand',
                      "Offers / demand",
                      f'[{_tag(scenario)}] Offers received per demand')
    axes[0].set_ylim(0, 105)
    return _finish(fig) if ok else None


def fig_outcomes(rows: Rows, scenario: str):
    """
    Reservation outcomes, as a share of the total, method by method.

    The four behavioural outcomes are stacked; `breakdown` and `unresolved` are
    excluded because they do not stem from user behaviour (breakdown, end of
    horizon).
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
        ax.set_title(f'[{_tag(scenario)}] Outcomes — {METHOD_LABELS.get(method, method)}',
                     fontweight='bold', fontsize=10)
        ax.set_xlabel('Number of vehicles')
        ax.set_ylabel('Share of the reservations (%)')
        ax.set_ylim(0, 105)
        ax.legend(fontsize=8, ncol=2)
        ax.grid(alpha=0.3, linestyle=':', axis='y')
    return _finish(fig)


def fig_offer_protocol(rows: Rows, scenario: str):
    """Health of the offer protocol: issued, confirmed, expired, refused."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'nb_offer_issued', "Offers",
                     f'[{_tag(scenario)}] Offers issued')
    ok |= _plot_lines(axes[0], rows, scenario, 'nb_reservations', "Offers",
                      f'[{_tag(scenario)}] Offers issued vs confirmed')
    ok |= _plot_lines(axes[1], rows, scenario, 'nb_confirm_refused',
                      "Confirmations refused",
                      f'[{_tag(scenario)}] Confirmations refused by the station')
    return _finish(fig) if ok else None


def fig_stations(rows: Rows, scenario: str):
    """Operator-side load: charger occupancy and energy delivered."""
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], rows, scenario, 'mean_occupancy_rate',
                     "Occupancy (%)",
                     f'[{_tag(scenario)}] Mean charger occupancy rate',
                     percent=True)
    ok |= _plot_lines(axes[1], rows, scenario, 'total_station_demand_kwh',
                      "Energy (kWh)",
                      f'[{_tag(scenario)}] Energy delivered (all stations)')
    return _finish(fig) if ok else None


# ----------------------------------------------------------------------
# Cross-cutting figures
# ----------------------------------------------------------------------

def fig_scenarios_overview(rows: Rows):
    """Exact satisfaction, one panel per scenario: the overview."""
    scenarios = _scenarios(rows)
    if not scenarios:
        return None
    fig, axes = plt.subplots(1, len(scenarios), figsize=(4.6 * len(scenarios), 4.2),
                             squeeze=False, sharey=True)
    for ax, scenario in zip(axes[0], scenarios):
        _plot_lines(ax, rows, scenario, 'exact_satisfaction', 'Satisfaction (%)',
                    f'[{_tag(scenario)}] Exact satisfaction', percent=True)
        ax.set_ylim(0, 105)
    return _finish(fig)


def fig_scalability(rows: Rows):
    """Compute cost: ILP solving time and end-to-end latency."""
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
    for ax, ylabel, title in ((axes[0], 'ms', 'ILP solving time per station'),
                              (axes[1], 's', 'Total wall time of the run')):
        ax.set_xlabel('Number of vehicles')
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontweight='bold', fontsize=10)
        ax.grid(alpha=0.3, linestyle=':')
        ax.legend(fontsize=7)
    return _finish(fig) if drawn else None


def fig_intent_vs_observed(rows: Rows):
    """
    Scenario probability, drawn intent and observed outcome.

    Makes the structural gap visible: an early-cancellation intent may not be
    realisable if the reservation is not taken in advance.
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
               label='drawn intent', color='#8e9aaf')
        ax.bar(positions + width / 2, [100 * v for v in observed], width,
               label='observed outcome', color='#3b7dd8')
        ax.set_xticks(positions)
        ax.set_xticklabels(outcomes)
        ax.set_ylabel('Share of the reservations (%)')
        ax.set_title(f'[{_tag(scenario)}] Intent vs outcome', fontweight='bold',
                     fontsize=10)
        ax.grid(alpha=0.3, linestyle=':', axis='y')
        ax.legend(fontsize=8)
    return _finish(fig)


def _society_colors(rows: Rows) -> dict:
    """One stable color per company, shared by every grid figure."""
    ids = sorted({int(r['society_id']) for r in rows})
    cmap = plt.get_cmap('tab10')
    return {sid: cmap(i % 10) for i, sid in enumerate(ids)}


def _grid_extent(rows: Rows) -> float:
    """Side of the simulated area, in meters, read from the table itself."""
    values = [r.get('grid_m') for r in rows if r.get('grid_m')]
    return float(values[0]) if values else 0.


def _draw_grid_map(ax, station_rows: Rows, colors: dict,
                   annotate: bool = True) -> None:
    """Station map: color = company, marker area ∝ number of chargers."""
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
    The shared infrastructure: where the stations are, whose they are, with
    which alpha.

    This figure depends on no scenario — which is exactly its point: it attests
    that `optimistic`, `balance` and `pessimistic` did run on the same grid.
    """
    if not station_rows:
        return None

    colors = _society_colors(station_rows)
    societies = sorted(society_rows or [], key=lambda r: int(r['society_id']))
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.9),
                             gridspec_kw={'width_ratios': [1, 1.25, 1]})

    # --- 1. Where the stations are, and whose they are
    _draw_grid_map(axes[0], station_rows, colors)
    for row in societies:
        axes[0].scatter(row['x_m'] / 1e3, row['y_m'] / 1e3,
                        marker='*', s=260,
                        color=colors[int(row['society_id'])],
                        edgecolor='black', linewidth=0.8, zorder=5)
    total_spots = sum(int(r['nb_charg_spot']) for r in station_rows)
    axes[0].set_title(f'{len(station_rows)} stations, {len(colors)} companies, '
                      f'{total_spots} chargers',
                      fontweight='bold', fontsize=10)

    handles = [plt.Line2D([], [], marker='o', linestyle='', color=color,
                          markeredgecolor='black', markersize=8,
                          label=f'Company {sid}')
               for sid, color in colors.items()]
    if societies:
        handles.append(plt.Line2D([], [], marker='*', linestyle='', color='grey',
                                  markeredgecolor='black', markersize=12,
                                  label='Head office'))
    # `best`: matplotlib places the legend where it hides the fewest stations.
    # Outside the axes, `tight_layout` would clip it.
    axes[0].legend(handles=handles, fontsize=7, loc='best', framealpha=0.85)

    # --- 2. Initial alpha, station by station, grouped by company
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
    axes[1].set_xlabel('Station (grouped by company)')
    axes[1].set_ylabel(r'initial $\alpha$')
    axes[1].set_title(r'Initial station strategy ($\alpha$)',
                      fontweight='bold', fontsize=10)
    axes[1].grid(alpha=0.3, linestyle=':', axis='y')

    # --- 3. Strategy points, carried by the company
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
    axes[2].set_xlabel('Reservation outcome')
    axes[2].set_ylabel('Points')
    axes[2].set_title('Point strategy of the companies',
                      fontweight='bold', fontsize=10)
    axes[2].grid(alpha=0.3, linestyle=':', axis='y')

    fig.suptitle('Grid shared by every scenario and every fleet',
                 fontweight='bold', fontsize=11)
    return _finish(fig)


def fig_fleet(station_rows: Rows, car_rows: Rows, nb_cars: int):
    """
    One fleet: initial vehicle positions on the grid, and dispersion of their
    characteristics.

    Like the grid, this fleet is common to the three scenarios.
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
                    label='Initial position')
    axes[0].set_aspect('equal')
    axes[0].set_xlabel('x (km)')
    axes[0].set_ylabel('y (km)')
    axes[0].grid(alpha=0.3, linestyle=':')
    axes[0].set_title(f'Shared fleet — {nb_cars} vehicles',
                      fontweight='bold', fontsize=10)
    axes[0].legend(fontsize=7, loc='upper right', framealpha=0.9)

    for ax, column, title, unit in (
        (axes[1], 'autonomy_km', 'Autonomy', 'km'),
        (axes[2], 'soc_init', 'Initial SoC', 'fraction of the battery'),
    ):
        values = [float(r[column]) for r in car_rows if r.get(column) is not None]
        ax.hist(values, bins=min(20, max(5, len(set(values)))),
                color='#3b7dd8', edgecolor='black', linewidth=0.4)
        ax.set_xlabel(unit)
        ax.set_ylabel('Vehicles')
        # A count is an integer: ticks at 3.5 vehicles make no sense.
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_title(title, fontweight='bold', fontsize=10)
        ax.grid(alpha=0.3, linestyle=':', axis='y')

    return _finish(fig)


def _mean_of(rows: Rows, column: str) -> float:
    values = [r[column] for r in rows if r.get(column) is not None]
    return float(np.mean(values)) if values else 0.


# ----------------------------------------------------------------------
# Ablation study
# ----------------------------------------------------------------------

#: Metrics plotted by the ablation figures, in panel order.
ABLATION_METRICS: tuple[str, ...] = (
    'exact_satisfaction', 'rate_abs', 'mean_service_rate', 'slot_waste_rate',
)


def _ablation_bars(means: Rows, kind: str, title: str):
    """
    One panel per metric, one bar per component.

    The bar carries the mean relative gap; its color says whether the component
    improves or degrades the metric (the direction depends on the metric: a
    falling no-show rate is a gain). The label above gives the share of the
    worlds where the component actually improves the metric — a mean gain
    carried by a single world is thus spotted immediately.
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
        ax.set_ylabel('mean relative gap (%)')
        ax.set_title(ablation.METRICS_BY_COLUMN[column].label,
                     fontweight='bold', fontsize=10)
        ax.grid(alpha=0.3, linestyle=':', axis='y')
        ax.margins(y=0.25)

    fig.suptitle(title, fontweight='bold', fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def _wrap(text: str, width: int = 14) -> str:
    """Wrap an axis label over two lines rather than truncating it."""
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
    """Contribution of each component added along the ablation ladder."""
    means = ablation.mean_rows(ablation.ladder_rows(rows))
    if not means:
        return None
    return _ablation_bars(
        means, 'ladder',
        "Contribution of each component (gap to the previous rung)")


def fig_ablation_variants(rows: Rows):
    """Effect of replacing an internal mechanism of BRAM-EV."""
    means = ablation.mean_rows(ablation.variant_rows(rows))
    if not means:
        return None
    return _ablation_bars(
        means, 'variant',
        "BRAM-EV variants (gap to the complete method)")


def fig_ablation_ladder(rows: Rows, scenario: str):
    """Satisfaction and no-shows rung by rung, against fleet size."""
    ladder = [r for r in rows if r['method'] in methods.LADDER
              and r['scenario'] == scenario]
    if not ladder:
        return None
    fig, axes = plt.subplots(1, 2, figsize=FIGSIZE)
    ok = _plot_lines(axes[0], ladder, scenario, 'exact_satisfaction',
                     'Satisfaction (%)',
                     f'[{_tag(scenario)}] Satisfaction — ablation ladder',
                     percent=True)
    ok |= _plot_lines(axes[1], ladder, scenario, 'rate_abs', 'No-show (%)',
                      f'[{_tag(scenario)}] No-show rate — ablation ladder',
                      percent=True)
    return _finish(fig) if ok else None


# ----------------------------------------------------------------------
# Complete rendering
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
    Produce every usable figure from the persisted tables.

    Parameters
    ----------
    summary_rows : Rows
        `summary.csv` — performance figures.
    grid_rows, society_rows : Rows | None
        `grid_stations.csv` / `grid_societies.csv` — figure of the shared grid.
        When absent (for instance for a run predating the shared grid), the
        figure is simply omitted.
    fleet_rows : Mapping[int, Rows] | None
        `{nb_cars: fleet_<n>cars.csv}` — one fleet figure per size.

    Returns
    -------
    list[Path]
        PNG files written.
    """
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # The shared environment is plotted even with no result: it is available
    # as soon as the run is prepared, before the first simulation.
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
