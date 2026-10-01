"""
bimodal.py — Analysis of the bimodal pilot (`balance_bimodal`).

Two questions:

1. What does reputation add in a strongly heterogeneous population? Each
   component is compared within the seed (the replicate): Multi-station + Rep.
   against Multi-station (reputation), BRAM-EV against Multi-station + Rep.
   (adaptation), and BRAM-EV against Load-aware (descriptive). The per-seed
   differences are kept; their mean and 95 % Student interval are reported.
   For the two component contrasts, two-sided paired t-tests on the three
   service endpoints of the paper (S_del, S_full, E_tot) are Holm-adjusted
   within each contrast: two separate families of three tests.
2. Do the scores separate the two profiles? Within each operator, the scores
   of H and L vehicles are compared day by day, separating empty and non-empty
   histories. A score gap is signed historical evidence, not a calibrated
   attendance probability.

Every indicator uses the definitions of the re-analysis (`reanalysis.py`), i.e.
of the paper. CSV files are written at full precision; rounding happens in
`README.md` only. The pilot is exploratory (5 seeds).

Usage:
    python -m src.pipeline.bimodal <run dir>
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.pipeline import aggregate, reanalysis
from src.pipeline.holm import holm_adjust
from src.pipeline.store import _write_csv

METHODS = ('multistation', 'multistation_rep', 'bramev', 'load_aware')
LABELS = {'multistation': 'Multi-station', 'multistation_rep': 'Multi-station + Rep.',
          'bramev': 'BRAM-EV', 'load_aware': 'Load-aware'}
REPUTATION = ('multistation_rep', 'bramev')
PROFILES = ('H', 'L')

#: (name, from, to, Holm family?) — the difference is `to - from`.
CONTRASTS = (
    ('reputation', 'multistation', 'multistation_rep', True),
    ('adaptation', 'multistation_rep', 'bramev', True),
    ('bramev_vs_load_aware', 'load_aware', 'bramev', False),
)
ENDPOINTS = ('S_del', 'S_full', 'E_tot')
ALPHA = 0.05

#: Indicators of the method table: (column, label, display factor, format).
INDICATORS = (
    ('S_del',           'S_del (%)',                     100., '.2f'),
    ('S_full',          'S_full (%)',                    100., '.2f'),
    ('E_tot',           'E_tot (MWh)',                   1e-3, '.2f'),
    ('I_held',          'I_held — unused held capacity (%)', 100., '.2f'),
    ('U',               'U — utilization (%)',           100., '.2f'),
    ('O_mean',          'Mean O_m (%)',                  100., '.2f'),
    ('O_max',           'Max O_m (%)',                   100., '.2f'),
    ('sched_delay_min', 'Scheduled delay (min)',         1.,   '.2f'),
    ('n_requests',      'Requests',                      1.,   '.1f'),
    ('withdrawals',     'Withdrawals',                   1.,   '.1f'),
)
SOLVER = ('nb_ilp_not_optimal', 'nb_ilp_feasible_time_limit', 'nb_ilp_failed')

#: Profile colours: categorical slots 1 and 2 of the reference palette.
COLORS = {'H': '#2a78d6', 'L': '#eb6834'}
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#d9d8d2'


def _tag(row: Mapping) -> str:
    return (f"seed{row['seed']}_{row['scenario']}_{row['nb_cars']}cars_"
            f"{row['method']}")


def _table(run: Path, row: Mapping, name: str) -> list[dict]:
    return reanalysis._read_csv(run / 'tables' / f'{_tag(row)}_{name}.csv')


def _ci(values: Sequence[float]) -> dict:
    est = aggregate.estimate(values)
    return {'n': est.n, 'mean': est.mean, 'sd': est.sd,
            'ci95_low': est.ci_low, 'ci95_high': est.ci_high,
            'ci95_halfwidth': est.halfwidth}


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------

def method_rows(rows: Sequence[Mapping]) -> list[dict]:
    out = []
    for method in METHODS:
        sub = [r for r in rows if r['method'] == method]
        for column, *_ in INDICATORS:
            out.append({'method': method, 'metric': column,
                        **_ci([float(r[column]) for r in sub])})
        for column in SOLVER:
            out.append({'method': method, 'metric': column, 'n': len(sub),
                        'sum': sum(int(r[column]) for r in sub)})
    return out


def profile_case_rows(run: Path, rows: Sequence[Mapping]) -> list[dict]:
    """Service per profile in each case, with its number of requests."""
    out = []
    for row in rows:
        profile = {r['car_id']: r['profile'] for r in _table(run, row, 'profiles')}
        demands = _table(run, row, 'latency')
        scores = _table(run, row, 'scores')
        last_day = max(r['day'] for r in scores)
        withdrawn = {r['car_id'] for r in scores
                     if r['day'] == last_day and r['withdrawn'] is True}
        for name in PROFILES:
            sub = [d for d in demands if profile[d['car_id']] == name]
            service = reanalysis.demand_service(sub)
            out.append({
                'method': row['method'], 'seed': row['world_seed'], 'profile': name,
                'nb_vehicles': sum(p == name for p in profile.values()),
                'n_requests': len(sub),
                'S_del': service['service_ratio_mean'],
                'S_full': service['fully_satisfied_rate'],
                'E_tot': service['E_tot'],
                'served_rate': (sum(d['outcome'] == 'satisfied' for d in sub) / len(sub)
                                if sub else None),
                'withdrawals': sum(profile[c] == name for c in withdrawn),
            })
    return out


def profile_rows(case_rows: Sequence[Mapping]) -> list[dict]:
    out = []
    for method in METHODS:
        for name in PROFILES:
            sub = [r for r in case_rows if r['method'] == method and r['profile'] == name]
            for column in ('n_requests', 'S_del', 'S_full', 'E_tot', 'withdrawals'):
                out.append({'method': method, 'profile': name, 'metric': column,
                            **_ci([float(r[column]) for r in sub])})
    return out


def paired_rows(rows: Sequence[Mapping], case_profiles: Sequence[Mapping]
                ) -> tuple[list[dict], list[dict]]:
    """
    `(paired, per_seed)`: the paired statistics of every contrast, and the
    per-seed differences behind them. Profile-level contrasts are descriptive.
    """
    by = {(r['method'], r['world_seed']): r for r in rows}
    prof = {(r['method'], r['seed'], r['profile']): r for r in case_profiles}
    seeds = sorted({r['world_seed'] for r in rows})
    columns = ENDPOINTS + tuple(c for c, *_ in INDICATORS if c not in ENDPOINTS)

    paired, per_seed = [], []
    for name, src, dst, family in CONTRASTS:
        groups = [('all', column, lambda m, s, c: float(by[(m, s)][c]))
                  for column in columns]
        groups += [(p, column, lambda m, s, c, p=p: float(prof[(m, s, p)][c]))
                   for p in PROFILES for column in ('S_del', 'S_full', 'E_tot', 'n_requests')]
        family_rows = []
        for population, column, get in groups:
            deltas = []
            for seed in seeds:
                a, b = get(src, seed, column), get(dst, seed, column)
                deltas.append(b - a)
                per_seed.append({'contrast': name, 'population': population,
                                 'metric': column, 'seed': seed,
                                 'value_from': a, 'value_to': b, 'delta': b - a})
            est, t_stat, p_value = aggregate.paired_test(deltas)
            entry = {'contrast': name, 'from_method': src, 'to_method': dst,
                     'population': population, 'metric': column,
                     'nb_pairs': est.n, 'mean_delta': est.mean, 'sd_delta': est.sd,
                     'ci95_low': est.ci_low, 'ci95_high': est.ci_high,
                     't_stat': t_stat, 'p_value': p_value,
                     'nb_positive': sum(d > 0 for d in deltas),
                     'holm_family': name if (family and population == 'all'
                                             and column in ENDPOINTS) else '',
                     'p_holm': None, 'reject_holm_05': None}
            paired.append(entry)
            if entry['holm_family']:
                family_rows.append(entry)
        if family_rows:
            adjusted = holm_adjust([r['p_value'] for r in family_rows])
            for entry, p in zip(family_rows, adjusted):
                entry['p_holm'] = p
                entry['reject_holm_05'] = p <= ALPHA
    return paired, per_seed


def score_rows(run: Path, rows: Sequence[Mapping]) -> tuple[list[dict], list[dict]]:
    """
    `(levels, separation)`. Levels: mean score per (method, seed, day,
    operator, profile, history). Separation: per (method, seed, day, operator),
    among non-empty histories, the H - L mean gap and the probability that a
    random H score exceeds a random L score (ties count one half).
    """
    levels, separation = [], []
    for row in rows:
        if row['method'] not in REPUTATION:
            continue
        profile = {r['car_id']: r['profile'] for r in _table(run, row, 'profiles')}
        cells = defaultdict(list)
        for r in _table(run, row, 'scores'):
            history = 'non_empty' if r['history_length'] > 0 else 'empty'
            cells[(r['day'], r['operator'], profile[r['car_id']], history)].append(r['score'])
        for (day, op, name, history), values in sorted(cells.items()):
            levels.append({'method': row['method'], 'seed': row['world_seed'],
                           'day': day, 'operator': op, 'profile': name,
                           'history': history, 'n': len(values),
                           'mean_score': mean(values)})
        for day, op in sorted({(d, o) for d, o, _, _ in cells}):
            h = cells.get((day, op, 'H', 'non_empty'), [])
            l = cells.get((day, op, 'L', 'non_empty'), [])
            if not h or not l:
                continue
            wins = sum((x > y) + 0.5 * (x == y) for x in h for y in l)
            separation.append({'method': row['method'], 'seed': row['world_seed'],
                               'day': day, 'operator': op,
                               'n_H': len(h), 'n_L': len(l),
                               'mean_H': mean(h), 'mean_L': mean(l),
                               'gap_H_minus_L': mean(h) - mean(l),
                               'p_H_above_L': wins / (len(h) * len(l))})
    return levels, separation


def decision_rows(run: Path, rows: Sequence[Mapping]) -> list[dict]:
    """What the stations did with each profile: offer rate, score read, duration."""
    out = []
    for row in rows:
        profile = {r['car_id']: r['profile'] for r in _table(run, row, 'profiles')}
        decisions = [d for d in _table(run, row, 'decisions') if d['station_id'] is not None]
        for name in PROFILES:
            sub = [d for d in decisions if profile[d['car_id']] == name]
            known = [d for d in sub if d['history_length'] > 0]
            out.append({
                'method': row['method'], 'seed': row['world_seed'], 'profile': name,
                'nb_decisions': len(sub),
                'offer_rate': mean(d['outcome'] == 'offer' for d in sub),
                'share_known_history': len(known) / len(sub),
                'mean_score_before': mean(d['score_before'] for d in sub),
                'mean_score_before_known': (mean(d['score_before'] for d in known)
                                            if known else None),
                'offer_rate_known': (mean(d['outcome'] == 'offer' for d in known)
                                     if known else None),
                'offered_over_requested': mean(d['duration_offered'] / d['duration_requested']
                                               for d in sub),
            })
    return out


# ----------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------

def _style(ax) -> None:
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis='y', color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def fig_reputation_effects(per_seed: Sequence[Mapping], paired: Sequence[Mapping],
                           path: Path) -> None:
    """The five per-seed reputation effects on S_del, their mean and 95 % CI."""
    pts = sorted((r['seed'], 100 * r['delta']) for r in per_seed
                 if r['contrast'] == 'reputation' and r['population'] == 'all'
                 and r['metric'] == 'S_del')
    stat = next(r for r in paired if r['contrast'] == 'reputation'
                and r['population'] == 'all' and r['metric'] == 'S_del')
    fig, ax = plt.subplots(figsize=(4.2, 3.0), dpi=200)
    _style(ax)
    xs = list(range(len(pts)))
    ax.axhline(0, color=MUTED, linewidth=0.8)
    lo, hi, m = 100 * stat['ci95_low'], 100 * stat['ci95_high'], 100 * stat['mean_delta']
    ax.axhspan(lo, hi, color=COLORS['H'], alpha=0.12, linewidth=0)
    ax.axhline(m, color=COLORS['H'], linewidth=1.5)
    ax.scatter(xs, [d for _, d in pts], s=36, color=COLORS['H'], zorder=3,
               edgecolors='white', linewidths=1.5)
    for x, (_, d) in zip(xs, pts):
        ax.annotate(f'{d:+.2f}', (x, d), textcoords='offset points', xytext=(7, -3),
                    fontsize=7, color=MUTED)
    ax.annotate(f'mean {m:+.2f} pp\n95% CI [{lo:+.2f}, {hi:+.2f}]',
                (len(pts) - 0.6, m), textcoords='offset points', xytext=(0, 6),
                fontsize=7, color=INK, ha='right')
    ax.set_xticks(xs, [f'seed {s}' for s, _ in pts])
    ax.set_xlim(-0.5, len(pts) - 0.3)
    ax.set_ylabel('Δ S_del (percentage points)', fontsize=8, color=INK)
    ax.set_title('Reputation effect on S_del\n(Multi-station + Rep. − Multi-station)',
                 fontsize=9, color=INK, loc='left')
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_scores(levels: Sequence[Mapping], path: Path) -> None:
    """Daily mean score of H and L (non-empty histories), per operator and method."""
    operators = sorted({r['operator'] for r in levels})
    days = sorted({r['day'] for r in levels})
    fig, axes = plt.subplots(len(REPUTATION), len(operators),
                             figsize=(2.3 * len(operators), 2.4 * len(REPUTATION)),
                             dpi=200, sharex=True, sharey=True, squeeze=False)
    for i, method in enumerate(REPUTATION):
        for j, op in enumerate(operators):
            ax = axes[i][j]
            _style(ax)
            ax.axhline(0, color=MUTED, linewidth=0.6)
            for name in PROFILES:
                means, lows, highs, xs = [], [], [], []
                for day in days:
                    vals = [r['mean_score'] for r in levels
                            if r['method'] == method and r['operator'] == op
                            and r['profile'] == name and r['day'] == day
                            and r['history'] == 'non_empty']
                    if len(vals) < 2:
                        continue
                    c = _ci(vals)
                    xs.append(day); means.append(c['mean'])
                    lows.append(c['ci95_low']); highs.append(c['ci95_high'])
                ax.fill_between(xs, lows, highs, color=COLORS[name], alpha=0.15, linewidth=0)
                ax.plot(xs, means, color=COLORS[name], linewidth=2, marker='o',
                        markersize=4, label=f'{name} profile')
            if i == 0:
                ax.set_title(f'Operator {op}', fontsize=8, color=INK)
            if j == 0:
                ax.set_ylabel(f'{LABELS[method]}\nmean score', fontsize=8, color=INK)
            if i == len(REPUTATION) - 1:
                ax.set_xlabel('day', fontsize=8, color=INK)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper right', fontsize=8, frameon=False, ncol=2)
    fig.suptitle('Reputation scores by profile — vehicles with a non-empty history\n'
                 '(mean over 5 seeds, band: 95% CI across seeds)',
                 fontsize=9, color=INK, x=0.01, ha='left')
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path)
    plt.close(fig)


# ----------------------------------------------------------------------
# Display (rounded)
# ----------------------------------------------------------------------

def _fmt(value, factor=1., spec='.2f', sign=False) -> str:
    if value is None:
        return '—'
    return format(value * factor, ('+' if sign else '') + spec)


def readme(rows, methods_tbl, profiles_tbl, paired, per_seed, separation,
           decisions, run: Path) -> str:
    idx = {(r['method'], r['metric']): r for r in methods_tbl}
    out = [f'# Bimodal pilot — {run.name}', '',
           'Regime `balance_bimodal`: 125 H vehicles (presence .90, absence .05, '
           'early .03, late .02) and 125 L vehicles (.30, .35, .21, .14); mean '
           '= balanced regime, no per-vehicle noise. 250 vehicles, 40 stations '
           'with 2 chargers, 4 operators, 1440 slots, seeds 1–5. Exploratory: '
           '5 seeds, Student multiplier 2.776. CSVs are at full precision; '
           'tables below are rounded.', '',
           '## Methods (mean ± 95% CI half-width over the 5 seeds)', '',
           '| Indicator | ' + ' | '.join(LABELS[m] for m in METHODS) + ' |',
           '|---|' + '---:|' * len(METHODS)]
    for column, label, factor, spec in INDICATORS:
        cells = [f"{_fmt(idx[(m, column)]['mean'], factor, spec)} ± "
                 f"{_fmt(idx[(m, column)]['ci95_halfwidth'], factor, spec)}"
                 for m in METHODS]
        out.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    for column, label in zip(SOLVER, ('MILP not proven optimal (sum)',
                                      '  of which feasible at time limit',
                                      '  of which failed')):
        out.append(f'| {label} | ' + ' | '.join(str(idx[(m, column)]['sum'])
                                                for m in METHODS) + ' |')

    pidx = {(r['method'], r['profile'], r['metric']): r for r in profiles_tbl}
    out += ['', '## Service by profile (mean ± 95% CI half-width)', '',
            '| Method | Profile | Requests | S_del (%) | S_full (%) | E_tot (MWh) | Withdrawals |',
            '|---|---|---:|---:|---:|---:|---:|']
    for m in METHODS:
        for p in PROFILES:
            g = lambda c, f, s: (f"{_fmt(pidx[(m, p, c)]['mean'], f, s)} ± "
                                 f"{_fmt(pidx[(m, p, c)]['ci95_halfwidth'], f, s)}")
            out.append(f'| {LABELS[m]} | {p} | {g("n_requests", 1, ".1f")} | '
                       f'{g("S_del", 100, ".2f")} | {g("S_full", 100, ".2f")} | '
                       f'{g("E_tot", 1e-3, ".2f")} | {g("withdrawals", 1, ".1f")} |')

    unit = {'S_del': (100, 'pp'), 'S_full': (100, 'pp'), 'E_tot': (1e-3, 'MWh'),
            'n_requests': (1, '')}
    seeds = sorted({r['seed'] for r in per_seed})
    out += ['', '## Paired contrasts (difference = to − from, per seed; mean, 95% CI)', '',
            'Holm: within each component contrast, over S_del, S_full and E_tot '
            '(two families of three tests). BRAM-EV − Load-aware and profile '
            'rows are descriptive.', '',
            '| Contrast | Population | Endpoint | ' +
            ' | '.join(f'seed {s}' for s in seeds) +
            ' | Mean [95% CI] | p | p Holm |',
            '|---|---|---|' + '---:|' * len(seeds) + '---|---:|---:|']
    for r in paired:
        if r['metric'] not in unit:
            continue
        f, u = unit[r['metric']]
        spec = '.1f' if r['metric'] == 'n_requests' else '.2f'
        deltas = [x['delta'] for x in per_seed if x['contrast'] == r['contrast']
                  and x['population'] == r['population'] and x['metric'] == r['metric']]
        out.append(
            f"| {r['contrast']} | {r['population']} | {r['metric']} {('(' + u + ')') if u else ''} | "
            + ' | '.join(_fmt(d, f, spec, True) for d in deltas)
            + f" | {_fmt(r['mean_delta'], f, spec, True)} [{_fmt(r['ci95_low'], f, spec, True)}, "
              f"{_fmt(r['ci95_high'], f, spec, True)}] | "
              f"{'—' if r['p_value'] is None else format(r['p_value'], '.3g')} | "
              f"{'—' if r['p_holm'] is None else format(r['p_holm'], '.3g')} |")

    out += ['', '## Score separation (non-empty histories, mean over seeds)', '',
            'P(H > L): probability that a random H score exceeds a random L score '
            'within the same operator (0.5 = no separation). Not a calibrated '
            'attendance probability.', '',
            '| Method | Day | Operator | n H | n L | mean H | mean L | gap H − L [95% CI] | P(H > L) |',
            '|---|---:|---:|---:|---:|---:|---:|---|---:|']
    keys = sorted({(r['method'], r['day'], r['operator']) for r in separation},
                  key=lambda k: (REPUTATION.index(k[0]), k[1], k[2]))
    for m, d, o in keys:
        sub = [r for r in separation if (r['method'], r['day'], r['operator']) == (m, d, o)]
        gap = _ci([r['gap_H_minus_L'] for r in sub])
        out.append(f"| {LABELS[m]} | {d} | {o} | {mean(r['n_H'] for r in sub):.1f} | "
                   f"{mean(r['n_L'] for r in sub):.1f} | {mean(r['mean_H'] for r in sub):+.3f} | "
                   f"{mean(r['mean_L'] for r in sub):+.3f} | {_fmt(gap['mean'], 1, '.3f', True)} "
                   f"[{_fmt(gap['ci95_low'], 1, '.3f', True)}, {_fmt(gap['ci95_high'], 1, '.3f', True)}] | "
                   f"{mean(r['p_H_above_L'] for r in sub):.3f} |")

    out += ['', '## Station decisions by profile (mean over seeds)', '',
            '| Method | Profile | Decisions | Offer rate | Known history | '
            'Score read | Score read (known) | Offer rate (known) | Offered / requested |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for m in METHODS:
        for p in PROFILES:
            sub = [r for r in decisions if r['method'] == m and r['profile'] == p]
            avg = lambda c: mean(r[c] for r in sub if r[c] is not None) \
                if any(r[c] is not None for r in sub) else None
            out.append(f"| {LABELS[m]} | {p} | {avg('nb_decisions'):.0f} | "
                       f"{_fmt(avg('offer_rate'), 100, '.1f')}% | "
                       f"{_fmt(avg('share_known_history'), 100, '.1f')}% | "
                       f"{_fmt(avg('mean_score_before'), 1, '.3f', True)} | "
                       f"{_fmt(avg('mean_score_before_known'), 1, '.3f', True)} | "
                       f"{_fmt(avg('offer_rate_known'), 100, '.1f')}% | "
                       f"{_fmt(avg('offered_over_requested'), 100, '.1f')}% |")
    out += ['', 'Figures: `figures/reputation_effects_S_del.png`, '
            '`figures/scores_by_profile.png`.']
    return '\n'.join(out) + '\n'


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def report(run: Path, out: Path | None = None) -> Path:
    run = Path(run)
    out = Path(out) if out is not None else run / 'bimodal'
    rows, fields, solver, _ = reanalysis.recompute_run(run)
    case_profiles = profile_case_rows(run, rows)
    methods_tbl = method_rows(rows)
    profiles_tbl = profile_rows(case_profiles)
    paired, per_seed = paired_rows(rows, case_profiles)
    levels, separation = score_rows(run, rows)
    decisions = decision_rows(run, rows)

    (out / 'figures').mkdir(parents=True, exist_ok=True)
    _write_csv(out / 'summary.csv', rows, fields)
    _write_csv(out / 'methods.csv', methods_tbl,
               ['method', 'metric', 'n', 'mean', 'sd', 'ci95_low', 'ci95_high',
                'ci95_halfwidth', 'sum'])
    _write_csv(out / 'profiles_per_case.csv', case_profiles)
    _write_csv(out / 'profiles.csv', profiles_tbl)
    _write_csv(out / 'paired.csv', paired)
    _write_csv(out / 'paired_per_seed.csv', per_seed)
    _write_csv(out / 'score_levels.csv', levels)
    _write_csv(out / 'score_separation.csv', separation)
    _write_csv(out / 'decisions_by_profile.csv', decisions)
    _write_csv(out / 'solver_status.csv', solver, list(solver[0]) if solver else ['scenario'])
    fig_reputation_effects(per_seed, paired, out / 'figures' / 'reputation_effects_S_del.png')
    fig_scores(levels, out / 'figures' / 'scores_by_profile.png')
    (out / 'README.md').write_text(
        readme(rows, methods_tbl, profiles_tbl, paired, per_seed, separation,
               decisions, run), encoding='utf-8')
    return out


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__.split('Usage:')[1])
    print(report(*map(Path, sys.argv[1:])))
