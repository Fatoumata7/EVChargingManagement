"""
methods.py — Registry of the compared methods (ablation study).

A *method* is not a class: it is a set of flags applied to the single simulation
loop (`src/experiments/simulation.py`). Isolating those flags in a declarative
registry answers the question the BRAM-EV / Greedy comparison cannot settle:
**which part of the gain comes from what?**

Ablation ladder (each rung adds exactly one component)
-----------------------------------------------------
    nearest / greedy      single-station search, no reputation, no adaptation
    multistation          + multi-station search (request broadcast)
    multistation_rep      + behavioural reputation
    bramev                + cross-station adaptation (collective learning)

The gain attributable to a component is the difference between two consecutive
rungs, measured on the *same* world (same seed, same grid, same fleet, same
behaviour draws): see `src/pipeline/ablation.py`.

BRAM-EV variants (one internal mechanism replaced, everything else unchanged)
----------------------------------------------------------------------------
    bramev_nearest_offer  nearest offer selected instead of the multi-criteria
                          utility
    bramev_fixed_alpha    same alpha for every station (config.ALPHA_FIXED)
    bramev_global_rep     global reputation instead of a per-company reputation
    bramev_event_score    flat penalty per event instead of a penalty
                          proportional to the reserved duration

Reference baselines (pure choice policies)
------------------------------------------
    min_waiting           offer with the lowest waiting time
    load_aware            offer of the least loaded upcoming station
    random_feasible       offer drawn at random among the offers received

They share the protocol of `multistation` — broadcast to the stations within the
search radius, with no reputation and no adaptation — and differ from it only by
the offer selection rule. At identical information scope, a measured gap is
therefore attributable to the rule alone.

Compatibility
-------------
`greedy` remains the canonical name of the first rung: the runs, tables and
figures already produced stay readable. `nearest` is an accepted alias
everywhere a method is named.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

# Admissible values of the non-boolean flags.
OFFER_CHOICES = ('utility', 'nearest', 'waiting', 'load', 'random')
ALPHA_MODES = ('sampled', 'fixed')
REPUTATION_SCOPES = ('society', 'global')
SCORE_WEIGHTINGS = ('duration', 'event')


@dataclass(frozen=True)
class MethodSpec:
    """
    Full description of a method.

    The first three flags are the components of the ablation ladder; the next
    four replace an internal mechanism of BRAM-EV without removing anything from
    the protocol.
    """

    name: str
    label: str

    # ---- components of the ablation ladder
    broadcast: bool               # request broadcast to every eligible station
    use_reputation: bool          # stations score the behaviour of the vehicles
    collective_learning: bool     # companies propagate the alpha of their best station

    # ---- internal mechanisms (variants)
    offer_choice: str = 'utility'       # see OFFER_CHOICES
    alpha_mode: str = 'sampled'         # 'sampled' | 'fixed'
    reputation_scope: str = 'society'   # 'society' | 'global'
    score_weighting: str = 'duration'   # 'duration' | 'event'

    # ---- metadata
    family: str = 'ablation'            # 'ablation' | 'variant'
    note: str = ''

    def __post_init__(self):
        for field_name, allowed in (('offer_choice', OFFER_CHOICES),
                                    ('alpha_mode', ALPHA_MODES),
                                    ('reputation_scope', REPUTATION_SCOPES),
                                    ('score_weighting', SCORE_WEIGHTINGS)):
            value = getattr(self, field_name)
            if value not in allowed:
                raise ValueError(
                    f"{self.name}: {field_name}={value!r} invalid, "
                    f"expected one of {list(allowed)}"
                )
        if self.collective_learning and not self.broadcast:
            # Nothing forbids it technically, but the ablation ladder would lose
            # its meaning: a component is only added after the previous one.
            raise ValueError(
                f"{self.name}: collective_learning without broadcast breaks "
                "the order of the ablation ladder"
            )

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def flags(self) -> dict:
        """Columns added to `summary.csv`: the ablation plan, readable."""
        return {
            'method_label':     self.label,
            'method_family':    self.family,
            'broadcast':        self.broadcast,
            'reputation':       self.use_reputation,
            'adaptation':       self.collective_learning,
            'offer_choice':     self.offer_choice,
            'alpha_mode':       self.alpha_mode,
            'reputation_scope': self.reputation_scope,
            'score_weighting':  self.score_weighting,
        }

    def __str__(self) -> str:
        return self.name


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------

_SPECS: tuple[MethodSpec, ...] = (
    # ---- ablation ladder ---------------------------------------------
    MethodSpec(
        name='greedy', label='Nearest',
        broadcast=False, use_reputation=False, collective_learning=False,
        note="Baseline: the vehicle contacts only the nearest station.",
    ),
    MethodSpec(
        name='multistation', label='Multi-Station Only',
        broadcast=True, use_reputation=False, collective_learning=False,
        note="Request broadcast alone: measures the gain of putting the "
             "stations in competition, with no reputation at all.",
    ),
    MethodSpec(
        name='multistation_rep', label='Multi-Station + Reputation',
        broadcast=True, use_reputation=True, collective_learning=False,
        note="Adds the behavioural score to the station objective; alpha stays "
             "frozen at its initial value.",
    ),
    MethodSpec(
        name='bramev', label='BRAM-EV Full',
        broadcast=True, use_reputation=True, collective_learning=True,
        note="Complete method: broadcast + reputation + adaptation of alpha "
             "between the stations of one company.",
    ),

    # ---- reference baselines -----------------------------------------
    # They broadcast the request to the stations within the search radius `r_n`,
    # exactly like `multistation`, and differ from it *only* by the offer
    # selection rule. None of them uses reputation or adaptation: these are pure
    # choice policies. That identical scope is what makes the comparison
    # readable — a measured gap comes from the rule, not from an information
    # advantage.
    MethodSpec(
        name='min_waiting', label='Minimum Waiting Time',
        broadcast=True, use_reputation=False, collective_learning=False,
        offer_choice='waiting', family='baseline',
        note="The vehicle queries the stations within its search radius and "
             "keeps the offer with the lowest waiting time — the gap between "
             "the proposed slot and the targeted one.",
    ),
    MethodSpec(
        name='load_aware', label='Load-Aware',
        broadcast=True, use_reputation=False, collective_learning=False,
        offer_choice='load', family='baseline',
        note="The vehicle queries the stations within its search radius and "
             "keeps the offer of the station whose future occupancy rate is "
             "the lowest.",
    ),
    MethodSpec(
        name='random_feasible', label='Random Feasible',
        broadcast=True, use_reputation=False, collective_learning=False,
        offer_choice='random', family='baseline',
        note="The vehicle draws at random among the offers received, all "
             "feasible by construction. Reference floor: what the offer "
             "protocol yields with no choice policy at all.",
    ),

    # ---- BRAM-EV variants --------------------------------------------
    MethodSpec(
        name='bramev_nearest_offer', label='BRAM-EV / nearest offer',
        broadcast=True, use_reputation=True, collective_learning=True,
        offer_choice='nearest', family='variant',
        note="The vehicle keeps the nearest offer instead of maximising its "
             "multi-criteria utility (energy, distance, waiting).",
    ),
    MethodSpec(
        name='bramev_fixed_alpha', label='BRAM-EV / fixed alpha',
        broadcast=True, use_reputation=True, collective_learning=True,
        alpha_mode='fixed', family='variant',
        note="Every station shares config.ALPHA_FIXED. Collective learning "
             "stays enabled but becomes inert (all alphas are equal): the "
             "variant therefore isolates the contribution of the heterogeneity "
             "of the profit/risk trade-offs.",
    ),
    MethodSpec(
        name='bramev_global_rep', label='BRAM-EV / global reputation',
        broadcast=True, use_reputation=True, collective_learning=True,
        reputation_scope='global', family='variant',
        note="A single score shared by every company, instead of one score per "
             "company: reputation becomes a public good.",
    ),
    MethodSpec(
        name='bramev_event_score', label='BRAM-EV / event score',
        broadcast=True, use_reputation=True, collective_learning=True,
        score_weighting='event', family='variant',
        note="Flat penalty per event instead of a penalty proportional to the "
             "reserved duration: a 2 h no-show then costs as much as a 20 min "
             "one.",
    ),
)

METHODS: Mapping[str, MethodSpec] = {spec.name: spec for spec in _SPECS}
METHOD_NAMES: tuple[str, ...] = tuple(METHODS)

#: Alternative names accepted everywhere a method is named.
ALIASES: Mapping[str, str] = {
    'nearest':          'greedy',
    'ms':               'multistation',
    'multi_station':    'multistation',
    'ms_rep':           'multistation_rep',
    'multistation_reputation': 'multistation_rep',
    'bramev_full':      'bramev',
    'full':             'bramev',
}

#: Rungs of the ablation ladder, in the order the components are added.
LADDER: tuple[str, ...] = ('greedy', 'multistation', 'multistation_rep', 'bramev')

#: Label of the component added at each rung.
LADDER_STEPS: tuple[tuple[str, str, str], ...] = (
    ('greedy',           'multistation',     'Multi-station search'),
    ('multistation',     'multistation_rep', 'Reputation'),
    ('multistation_rep', 'bramev',           'Cross-station adaptation'),
)

#: BRAM-EV variants, compared against `bramev`.
VARIANTS: tuple[str, ...] = tuple(s.name for s in _SPECS if s.family == 'variant')

#: Reference baselines, compared against `bramev`. `greedy` is not one of them:
#: it is the first rung of the ablation ladder, and keeps that role there.
BASELINES: tuple[str, ...] = tuple(s.name for s in _SPECS if s.family == 'baseline')

#: Shortcuts usable everywhere a list of methods is expected.
METHOD_GROUPS: Mapping[str, tuple[str, ...]] = {
    'ablation':  LADDER,
    'variants':  VARIANTS,
    'baselines': BASELINES,
    #: Reference comparison: BRAM-EV against every baseline.
    'reference': ('bramev',) + BASELINES + ('greedy',),
    'baseline':  ('greedy', 'bramev'),
    'all':       METHOD_NAMES,
}

#: Everything a CLI or a YAML file may write in `methods`.
METHOD_TOKENS: tuple[str, ...] = (
    METHOD_NAMES + tuple(ALIASES) + tuple(METHOD_GROUPS)
)


# ----------------------------------------------------------------------
# Resolution
# ----------------------------------------------------------------------

def canonical(name: str) -> str:
    """Canonical name of a method (resolves aliases). Raises KeyError otherwise."""
    key = str(name).strip().lower()
    key = ALIASES.get(key, key)
    if key not in METHODS:
        raise KeyError(
            f"Unknown method: {name!r}. Expected one of {list(METHOD_NAMES)} "
            f"(aliases: {sorted(ALIASES)})"
        )
    return key


def resolve(name: str | MethodSpec) -> MethodSpec:
    """`MethodSpec` of a named method (aliases accepted)."""
    if isinstance(name, MethodSpec):
        return name
    return METHODS[canonical(name)]


def is_known(name: str) -> bool:
    try:
        canonical(name)
    except KeyError:
        return False
    return True


def expand(names: Iterable[str]) -> tuple[str, ...]:
    """
    Expand groups and aliases into canonical names, without duplicates and in order.

    An unknown token is **kept as is**: parameter validation is what reports it,
    with a situated message.
    """
    out: list[str] = []
    for token in names:
        key = str(token).strip().lower()
        expanded = METHOD_GROUPS.get(key, (key,))
        for item in expanded:
            name = canonical(item) if is_known(item) else item
            if name not in out:
                out.append(name)
    return tuple(out)


def label(name: str) -> str:
    """Readable label of a method; the raw name if it is unknown."""
    try:
        return resolve(name).label
    except KeyError:
        return str(name)


def describe_table() -> str:
    """Table of the ablation plan, as printed by `cli.py methods`."""
    header = (f"  {'method':<22}{'multi-station':>15}{'reputation':>12}"
              f"{'adaptation':>12}{'offer choice':>13}   {'label'}")
    lines = [header, '  ' + '-' * (len(header) - 2)]
    titles = {'ablation': 'ablation ladder', 'baseline': 'baselines',
              'variant': 'variants'}
    for family in ('ablation', 'baseline', 'variant'):
        group = [s for s in _SPECS if s.family == family]
        if not group:
            continue
        lines.append(f"  [{titles[family]}]")
        for spec in group:
            lines.append(
                f"  {spec.name:<22}"
                f"{'yes' if spec.broadcast else 'no':>15}"
                f"{'yes' if spec.use_reputation else 'no':>12}"
                f"{'yes' if spec.collective_learning else 'no':>12}"
                f"{spec.offer_choice:>13}"
                f"   {spec.label}"
            )
    return '\n'.join(lines)
