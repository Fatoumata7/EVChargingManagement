"""
ablation.py — Décomposition des gains par composant.

La comparaison Nearest / BRAM-EV dit *qu'il y a* un écart ; elle ne dit pas
d'où il vient. Ce module répond à la question posée par l'étude d'ablation :
**quelle part du gain est imputable à quel composant ?**

Deux lectures, produites à partir du seul `summary.csv` :

Échelle d'ablation (`kind='ladder'`)
    Les quatre barreaux (`methods.LADDER`) n'ajoutent qu'un composant à la
    fois. Pour un même monde — même graine, même grille, même flotte, mêmes
    tirages de comportement — l'écart entre deux barreaux consécutifs *est* la
    contribution du composant ajouté, sans autre variable confondante.

Variantes de BRAM-EV (`kind='variant'`)
    Chaque variante remplace un mécanisme interne (sélection multicritère,
    hétérogénéité des alpha, portée de la réputation, pondération du score) et
    se compare à `bramev`. L'écart mesure ce que ce mécanisme apporte
    *à l'intérieur* de la méthode complète.

Le signe brut d'un écart ne suffit pas : une baisse du nombre de no-shows est
un progrès, une baisse du taux de satisfaction n'en est pas un. Chaque métrique
déclare donc sa direction (`GOAL_UP` / `GOAL_DOWN`), et `improvement` traduit
l'écart en jugement.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

import src.experiments.methods as methods

Row = Mapping[str, Any]
Rows = Sequence[Row]

GOAL_UP = 'up'      # plus c'est grand, mieux c'est
GOAL_DOWN = 'down'  # plus c'est petit, mieux c'est


@dataclass(frozen=True)
class Metric:
    """Une métrique suivie par l'ablation, avec sa direction et son unité."""

    column: str
    label: str
    goal: str
    unit: str = ''

    def improves(self, delta: float) -> bool:
        return delta > 0 if self.goal == GOAL_UP else delta < 0


#: Métriques décomposées par défaut : satisfaction des usagers, coût pour eux,
#: fiabilité des réservations, exploitation de l'infrastructure, coût de calcul.
METRICS: tuple[Metric, ...] = (
    Metric('exact_satisfaction',          'Satisfaction exacte',     GOAL_UP,   '%'),
    Metric('needs_satisfaction',          'Besoins satisfaits',      GOAL_UP,   '%'),
    Metric('confirm_rate',                'Taux de confirmation',    GOAL_UP,   '%'),
    Metric('mean_waiting_time_min',       'Attente moyenne',         GOAL_DOWN, 'min'),
    Metric('mean_travel_distance_km',     'Distance moyenne',        GOAL_DOWN, 'km'),
    Metric('rate_pres',                   'Taux de présentation',    GOAL_UP,   '%'),
    Metric('rate_abs',                    'Taux de no-show',         GOAL_DOWN, '%'),
    Metric('nb_no_show',                  'No-shows',                GOAL_DOWN, ''),
    Metric('nb_reservations',             'Réservations confirmées', GOAL_UP,   ''),
    Metric('mean_occupancy_rate',         "Taux d'occupation",       GOAL_UP,   '%'),
    Metric('mean_service_rate',           'Taux de service',         GOAL_UP,   '%'),
    Metric('slot_waste_rate',             'Slots réservés perdus',   GOAL_DOWN, '%'),
    Metric('nb_station_level_rejections', 'Demandes rejetées',       GOAL_DOWN, ''),
    Metric('total_ms_mean',               'Latence bout-en-bout',    GOAL_DOWN, 'ms'),
    Metric('wall_time_s',                 'Temps de calcul',         GOAL_DOWN, 's'),
)

METRICS_BY_COLUMN = {m.column: m for m in METRICS}

#: Mécanisme neutralisé par chaque variante, tel qu'affiché dans les tables.
VARIANT_MECHANISM: Mapping[str, str] = {
    'bramev_nearest_offer': 'Utilité multicritère',
    'bramev_fixed_alpha':   'Hétérogénéité des alpha',
    'bramev_global_rep':    'Réputation par société',
    'bramev_event_score':   'Score proportionnel à la durée',
}

#: Libellé de chaque baseline dans les tables, tel que publié.
BASELINE_LABEL: Mapping[str, str] = {
    name: methods.label(name) for name in methods.BASELINES
}

ROW_FIELDS: tuple[str, ...] = (
    'kind', 'scenario', 'nb_cars', 'metric', 'metric_label', 'goal', 'unit',
    'step', 'component', 'from_method', 'to_method',
    'value_from', 'value_to', 'delta', 'delta_pct', 'improvement',
)

MEAN_FIELDS: tuple[str, ...] = (
    'kind', 'metric', 'metric_label', 'goal', 'unit', 'step', 'component',
    'from_method', 'to_method', 'nb_worlds',
    'mean_value_from', 'mean_value_to', 'mean_delta', 'mean_delta_pct',
    'nb_improved', 'share_improved',
)


# ----------------------------------------------------------------------
# Sélection des lignes
# ----------------------------------------------------------------------

def _world_key(row: Row) -> tuple:
    """Identité du monde d'un cas : deux lignes de même clé sont comparables."""
    return (row.get('scenario'), row.get('nb_cars'), row.get('world_seed'))


def index_by_world(rows: Rows) -> dict[tuple, dict[str, Row]]:
    """
    `{monde: {méthode: ligne}}`.

    Une méthode dupliquée dans un même monde (relance partielle) est signalée
    plutôt que silencieusement écrasée : l'ablation deviendrait fausse sans
    qu'on puisse le voir.
    """
    index: dict[tuple, dict[str, Row]] = {}
    for row in rows:
        method = row.get('method')
        if method is None:
            continue
        bucket = index.setdefault(_world_key(row), {})
        if method in bucket:
            raise ValueError(
                f"Méthode {method!r} présente deux fois pour le monde "
                f"{_world_key(row)} : summary.csv contient des doublons."
            )
        bucket[method] = row
    return index


def _pairs(index: Mapping[tuple, Mapping[str, Row]],
           couples: Sequence[tuple[str, str, str]]):
    """Énumère (monde, composant, ligne_avant, ligne_après) pour les couples présents."""
    for world, by_method in sorted(index.items(), key=lambda kv: str(kv[0])):
        for src, dst, component in couples:
            if src in by_method and dst in by_method:
                yield world, component, by_method[src], by_method[dst]


# ----------------------------------------------------------------------
# Construction des tables
# ----------------------------------------------------------------------

def _delta_row(kind: str, world: tuple, component: str, step: int,
               before: Row, after: Row, metric: Metric) -> dict | None:
    value_from = before.get(metric.column)
    value_to = after.get(metric.column)
    if value_from is None or value_to is None:
        return None
    try:
        delta = float(value_to) - float(value_from)
    except (TypeError, ValueError):
        return None

    # Écart relatif : indéfini si la référence est nulle (et non « infini »).
    base = abs(float(value_from))
    delta_pct = round(100. * delta / base, 4) if base > 1e-12 else None

    scenario, nb_cars, _ = world
    return {
        'kind':         kind,
        'scenario':     scenario,
        'nb_cars':      nb_cars,
        'metric':       metric.column,
        'metric_label': metric.label,
        'goal':         metric.goal,
        'unit':         metric.unit,
        'step':         step,
        'component':    component,
        'from_method':  before.get('method'),
        'to_method':    after.get('method'),
        'value_from':   round(float(value_from), 6),
        'value_to':     round(float(value_to), 6),
        'delta':        round(delta, 6),
        'delta_pct':    delta_pct,
        'improvement':  metric.improves(delta),
    }


def ladder_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """Contribution de chaque composant, monde par monde et métrique par métrique."""
    index = index_by_world(rows)
    steps = {(src, dst): i + 1 for i, (src, dst, _) in enumerate(methods.LADDER_STEPS)}
    out: list[dict] = []
    for world, component, before, after in _pairs(index, methods.LADDER_STEPS):
        step = steps[(before['method'], after['method'])]
        for metric in metrics:
            row = _delta_row('ladder', world, component, step, before, after, metric)
            if row is not None:
                out.append(row)
    return out


def variant_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """
    Écart de chaque variante à `bramev`.

    Le sens de lecture est « BRAM-EV -> variante » : un `improvement` faux
    signifie que le mécanisme neutralisé par la variante était utile.
    """
    index = index_by_world(rows)
    couples = [('bramev', name, VARIANT_MECHANISM.get(name, name))
               for name in methods.VARIANTS]
    out: list[dict] = []
    for world, component, before, after in _pairs(index, couples):
        for metric in metrics:
            row = _delta_row('variant', world, component, 0, before, after, metric)
            if row is not None:
                out.append(row)
    return out


def baseline_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """
    Écart de `bramev` à chaque baseline de référence.

    Le sens de lecture est inverse de celui des variantes : « baseline ->
    BRAM-EV », de sorte qu'un `improvement` vrai signifie que BRAM-EV fait
    mieux que la baseline. C'est la question posée à une baseline, alors qu'une
    variante répond à « ce mécanisme sert-il à quelque chose ? ».
    """
    index = index_by_world(rows)
    couples = [(name, 'bramev', BASELINE_LABEL.get(name, name))
               for name in methods.BASELINES]
    out: list[dict] = []
    for world, component, before, after in _pairs(index, couples):
        for metric in metrics:
            row = _delta_row('baseline', world, component, 0, before, after, metric)
            if row is not None:
                out.append(row)
    return out


def detail_rows(rows: Rows, metrics: Sequence[Metric] = METRICS) -> list[dict]:
    """Table détaillée complète : échelle d'ablation, baselines, puis variantes."""
    return (ladder_rows(rows, metrics)
            + baseline_rows(rows, metrics)
            + variant_rows(rows, metrics))


def mean_rows(detail: Rows) -> list[dict]:
    """
    Moyenne des écarts sur tous les mondes, par (composant, métrique).

    C'est la table à citer dans le rapport : un composant qui n'améliore que
    la moitié des mondes (`share_improved` proche de 0.5) n'a pas de
    contribution robuste, même si son écart moyen est positif.
    """
    grouped: dict[tuple, list[Row]] = {}
    for row in detail:
        key = (row['kind'], row['step'], row['component'],
               row['from_method'], row['to_method'], row['metric'])
        grouped.setdefault(key, []).append(row)

    out: list[dict] = []
    for key, group in grouped.items():
        kind, step, component, from_method, to_method, metric = key
        pcts = [r['delta_pct'] for r in group if r['delta_pct'] is not None]
        nb_improved = sum(1 for r in group if r['improvement'])
        out.append({
            'kind':            kind,
            'metric':          metric,
            'metric_label':    group[0]['metric_label'],
            'goal':            group[0]['goal'],
            'unit':            group[0]['unit'],
            'step':            step,
            'component':       component,
            'from_method':     from_method,
            'to_method':       to_method,
            'nb_worlds':       len(group),
            'mean_value_from': round(mean(r['value_from'] for r in group), 6),
            'mean_value_to':   round(mean(r['value_to'] for r in group), 6),
            'mean_delta':      round(mean(r['delta'] for r in group), 6),
            'mean_delta_pct':  round(mean(pcts), 4) if pcts else None,
            'nb_improved':     nb_improved,
            'share_improved':  round(nb_improved / len(group), 4),
        })

    order = {m.column: i for i, m in enumerate(METRICS)}
    out.sort(key=lambda r: (r['kind'] != 'ladder', r['step'], r['component'],
                            order.get(r['metric'], 99)))
    return out


# ----------------------------------------------------------------------
# Persistance
# ----------------------------------------------------------------------

def write_tables(store, rows: Rows | None = None,
                 metrics: Sequence[Metric] = METRICS) -> list:
    """
    Écrit `ablation.csv` et `ablation_mean.csv` à la racine du run.

    Sans couple comparable (une seule méthode dans la campagne), rien n'est
    écrit et la liste renvoyée est vide : une campagne mono-méthode reste
    valide, elle n'a simplement rien à décomposer.
    """
    rows = list(rows if rows is not None else store.read_summary())
    detail = detail_rows(rows, metrics)
    if not detail:
        return []
    written = [
        store.write_root_table('ablation', detail, ROW_FIELDS),
        store.write_root_table('ablation_mean', mean_rows(detail), MEAN_FIELDS),
    ]
    return [path for path in written if path is not None]


# ----------------------------------------------------------------------
# Restitution texte
# ----------------------------------------------------------------------

DEFAULT_REPORT_METRICS: tuple[str, ...] = (
    'exact_satisfaction', 'rate_abs', 'mean_service_rate',
    'slot_waste_rate', 'nb_reservations',
)


def render_mean_table(means: Rows,
                      metric_columns: Sequence[str] = DEFAULT_REPORT_METRICS) -> str:
    """
    Tableau lisible : une ligne par composant, une colonne par métrique.

    Chaque cellule porte l'écart moyen et, entre parenthèses, la part des
    mondes où le composant améliore la métrique — la contribution moyenne et
    sa robustesse se lisent d'un coup.

    L'écart est relatif quand la référence est non nulle. Elle ne l'est pas
    toujours (une attente moyenne nulle, par exemple) : la cellule bascule
    alors sur l'écart absolu, préfixé `Δ`, plutôt que d'afficher un tiret qui
    ferait passer une mesure faite pour une mesure manquante.
    """
    selected = [c for c in metric_columns if c in METRICS_BY_COLUMN]
    by_component: dict[tuple, dict[str, Row]] = {}
    for row in means:
        if row['metric'] not in selected:
            continue
        key = (row['kind'], row['step'], row['component'])
        by_component.setdefault(key, {})[row['metric']] = row
    if not by_component:
        return '(aucune contribution calculable)'

    headers = [METRICS_BY_COLUMN[c].label for c in selected]
    name_width = max(len('Composant'),
                     *(len(k[2]) for k in by_component))
    widths = [max(len(h), 16) for h in headers]

    def line(cells: Sequence[str], first: str) -> str:
        parts = [first.ljust(name_width)]
        parts += [c.rjust(w) for c, w in zip(cells, widths)]
        return '  '.join(parts)

    out = [line(headers, 'Composant'),
           line(['-' * w for w in widths], '-' * name_width)]

    for kind in ('ladder', 'baseline', 'variant'):
        keys = sorted(k for k in by_component if k[0] == kind)
        if not keys:
            continue
        title = {
            'ladder':   "Échelle d'ablation (contribution du composant ajouté)",
            'baseline': "Baselines de référence (écart de la baseline à BRAM-EV)",
            'variant':  "Variantes de BRAM-EV (effet du mécanisme neutralisé)",
        }[kind]
        out.append('')
        out.append(title)
        for key in keys:
            cells = []
            for column in selected:
                row = by_component[key].get(column)
                if row is None:
                    cells.append('-')
                    continue
                if row['mean_delta_pct'] is not None:
                    value = f"{row['mean_delta_pct']:+.1f}%"
                else:
                    value = f"Δ{row['mean_delta']:+.3g}"
                cells.append(f"{value} ({row['share_improved']:.0%})")
            out.append(line(cells, key[2]))
    out.append('')
    out.append("Lecture : écart relatif moyen sur tous les mondes du run "
               "(part des mondes où le composant améliore la métrique).")
    return '\n'.join(out)
