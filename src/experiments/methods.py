"""
methods.py — Registre des méthodes comparées (étude d'ablation).

Une *méthode* n'est pas une classe : c'est un jeu de drapeaux appliqué à la
boucle de simulation unique (`src/experiments/simulation.py`). Isoler ces
drapeaux dans un registre déclaratif permet de répondre à la question que la
comparaison BRAM-EV / Greedy ne peut pas trancher : **quelle part du gain vient
de quoi ?**

Échelle d'ablation (chaque barreau ajoute exactement un composant)
-----------------------------------------------------------------
    nearest / greedy      recherche mono-station, sans réputation, sans adaptation
    multistation          + recherche multi-stations (diffusion de la requête)
    multistation_rep      + réputation comportementale
    bramev                + adaptation entre stations (apprentissage collectif)

Le gain attribuable à un composant est la différence entre deux barreaux
consécutifs, mesurée sur le *même* monde (même graine, même grille, même
flotte, même tirage de comportements) : cf. `src/pipeline/ablation.py`.

Variantes de BRAM-EV (un mécanisme interne remplacé, le reste inchangé)
----------------------------------------------------------------------
    bramev_nearest_offer  sélection de l'offre la plus proche au lieu de
                          l'utilité multicritère
    bramev_fixed_alpha    même alpha pour toutes les stations (config.ALPHA_FIXED)
    bramev_global_rep     réputation globale au lieu d'une réputation par société
    bramev_event_score    pénalité par événement au lieu d'une pénalité
                          proportionnelle à la durée réservée

Baselines de référence (politiques de choix pures)
-------------------------------------------------
    min_waiting           offre dont l'attente est la plus faible
    load_aware            offre de la station la moins chargée à venir
    random_feasible       offre tirée au hasard parmi les offres reçues

Elles partagent le protocole de `multistation` — diffusion aux stations du
rayon de recherche, sans réputation ni adaptation — et n'en diffèrent que par
la règle de sélection de l'offre. À périmètre d'information identique, un écart
mesuré est donc imputable à la règle seule.

Compatibilité
-------------
`greedy` reste le nom canonique du premier barreau : les runs, tables et
figures déjà produits restent lisibles. `nearest` en est un alias accepté
partout où une méthode est nommée.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

# Valeurs admissibles des drapeaux non booléens.
OFFER_CHOICES = ('utility', 'nearest', 'waiting', 'load', 'random')
ALPHA_MODES = ('sampled', 'fixed')
REPUTATION_SCOPES = ('society', 'global')
SCORE_WEIGHTINGS = ('duration', 'event')


@dataclass(frozen=True)
class MethodSpec:
    """
    Description complète d'une méthode.

    Les trois premiers drapeaux sont les composants de l'échelle d'ablation ;
    les quatre suivants remplacent un mécanisme interne de BRAM-EV sans rien
    retirer au protocole.
    """

    name: str
    label: str

    # ---- composants de l'échelle d'ablation
    broadcast: bool               # requête diffusée à toutes les stations éligibles
    use_reputation: bool          # les stations notent le comportement des véhicules
    collective_learning: bool     # les sociétés propagent l'alpha de leur meilleure station

    # ---- mécanismes internes (variantes)
    offer_choice: str = 'utility'       # cf. OFFER_CHOICES
    alpha_mode: str = 'sampled'         # 'sampled' | 'fixed'
    reputation_scope: str = 'society'   # 'society' | 'global'
    score_weighting: str = 'duration'   # 'duration' | 'event'

    # ---- métadonnées
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
                    f"{self.name}: {field_name}={value!r} invalide, "
                    f"attendu parmi {list(allowed)}"
                )
        if self.collective_learning and not self.broadcast:
            # Rien ne l'interdit techniquement, mais l'échelle d'ablation
            # perdrait son sens : un composant ne s'ajoute qu'après le précédent.
            raise ValueError(
                f"{self.name}: collective_learning sans broadcast casse "
                "l'ordre de l'échelle d'ablation"
            )

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def flags(self) -> dict:
        """Colonnes ajoutées à `summary.csv` : le plan d'ablation lisible."""
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
# Registre
# ----------------------------------------------------------------------

_SPECS: tuple[MethodSpec, ...] = (
    # ---- échelle d'ablation ------------------------------------------
    MethodSpec(
        name='greedy', label='Nearest',
        broadcast=False, use_reputation=False, collective_learning=False,
        note="Baseline : le véhicule ne contacte que la station la plus proche.",
    ),
    MethodSpec(
        name='multistation', label='Multi-Station Only',
        broadcast=True, use_reputation=False, collective_learning=False,
        note="Diffusion de la requête seule : mesure le gain de la mise en "
             "concurrence des stations, sans aucune réputation.",
    ),
    MethodSpec(
        name='multistation_rep', label='Multi-Station + Reputation',
        broadcast=True, use_reputation=True, collective_learning=False,
        note="Ajoute le score comportemental à l'objectif des stations ; "
             "alpha reste figé à sa valeur initiale.",
    ),
    MethodSpec(
        name='bramev', label='BRAM-EV Full',
        broadcast=True, use_reputation=True, collective_learning=True,
        note="Méthode complète : diffusion + réputation + adaptation de alpha "
             "entre stations d'une même société.",
    ),

    # ---- baselines de référence --------------------------------------
    # Elles diffusent la requête aux stations du rayon de recherche `r_n`,
    # exactement comme `multistation`, et ne diffèrent de lui *que* par la règle
    # de sélection de l'offre. Aucune n'utilise la réputation ni l'adaptation :
    # ce sont des politiques de choix pures. Ce périmètre identique est ce qui
    # rend la comparaison lisible — un écart mesuré vient de la règle, pas d'un
    # avantage d'information.
    MethodSpec(
        name='min_waiting', label='Minimum Waiting Time',
        broadcast=True, use_reputation=False, collective_learning=False,
        offer_choice='waiting', family='baseline',
        note="Le véhicule interroge les stations de son rayon de recherche et "
             "retient l'offre dont l'attente est la plus faible — écart entre "
             "le créneau proposé et le créneau visé.",
    ),
    MethodSpec(
        name='load_aware', label='Load-Aware',
        broadcast=True, use_reputation=False, collective_learning=False,
        offer_choice='load', family='baseline',
        note="Le véhicule interroge les stations de son rayon de recherche et "
             "retient l'offre de la station dont le taux d'occupation futur "
             "est le plus faible.",
    ),
    MethodSpec(
        name='random_feasible', label='Random Feasible',
        broadcast=True, use_reputation=False, collective_learning=False,
        offer_choice='random', family='baseline',
        note="Le véhicule tire au hasard parmi les offres reçues, toutes "
             "faisables par construction. Plancher de référence : ce que "
             "rapporte le protocole d'offre sans aucune politique de choix.",
    ),

    # ---- variantes de BRAM-EV ----------------------------------------
    MethodSpec(
        name='bramev_nearest_offer', label='BRAM-EV / offre la plus proche',
        broadcast=True, use_reputation=True, collective_learning=True,
        offer_choice='nearest', family='variant',
        note="Le véhicule retient l'offre la plus proche au lieu de maximiser "
             "son utilité multicritère (énergie, distance, attente).",
    ),
    MethodSpec(
        name='bramev_fixed_alpha', label='BRAM-EV / alpha fixe',
        broadcast=True, use_reputation=True, collective_learning=True,
        alpha_mode='fixed', family='variant',
        note="Toutes les stations partagent config.ALPHA_FIXED. L'apprentissage "
             "collectif reste actif mais devient inerte (tous les alpha sont "
             "égaux) : la variante isole donc l'apport de l'hétérogénéité "
             "des arbitrages profit/risque.",
    ),
    MethodSpec(
        name='bramev_global_rep', label='BRAM-EV / réputation globale',
        broadcast=True, use_reputation=True, collective_learning=True,
        reputation_scope='global', family='variant',
        note="Un score unique partagé par toutes les sociétés, au lieu d'un "
             "score par société : la réputation devient un bien public.",
    ),
    MethodSpec(
        name='bramev_event_score', label='BRAM-EV / score par événement',
        broadcast=True, use_reputation=True, collective_learning=True,
        score_weighting='event', family='variant',
        note="Pénalité forfaitaire par événement au lieu d'une pénalité "
             "proportionnelle à la durée réservée : un no-show de 2 h coûte "
             "alors autant qu'un no-show de 20 min.",
    ),
)

METHODS: Mapping[str, MethodSpec] = {spec.name: spec for spec in _SPECS}
METHOD_NAMES: tuple[str, ...] = tuple(METHODS)

#: Noms alternatifs acceptés partout où une méthode est nommée.
ALIASES: Mapping[str, str] = {
    'nearest':          'greedy',
    'ms':               'multistation',
    'multi_station':    'multistation',
    'ms_rep':           'multistation_rep',
    'multistation_reputation': 'multistation_rep',
    'bramev_full':      'bramev',
    'full':             'bramev',
}

#: Barreaux de l'échelle d'ablation, dans l'ordre d'ajout des composants.
LADDER: tuple[str, ...] = ('greedy', 'multistation', 'multistation_rep', 'bramev')

#: Libellé du composant ajouté à chaque barreau.
LADDER_STEPS: tuple[tuple[str, str, str], ...] = (
    ('greedy',           'multistation',     'Recherche multi-stations'),
    ('multistation',     'multistation_rep', 'Réputation'),
    ('multistation_rep', 'bramev',           'Adaptation entre stations'),
)

#: Variantes de BRAM-EV, comparées à `bramev`.
VARIANTS: tuple[str, ...] = tuple(s.name for s in _SPECS if s.family == 'variant')

#: Baselines de référence, comparées à `bramev`. `greedy` n'en fait pas partie :
#: c'est le premier barreau de l'échelle d'ablation, et il y garde son rôle.
BASELINES: tuple[str, ...] = tuple(s.name for s in _SPECS if s.family == 'baseline')

#: Raccourcis utilisables partout où une liste de méthodes est attendue.
METHOD_GROUPS: Mapping[str, tuple[str, ...]] = {
    'ablation':  LADDER,
    'variants':  VARIANTS,
    'baselines': BASELINES,
    #: Comparaison de référence : BRAM-EV face à toutes les baselines.
    'reference': ('bramev',) + BASELINES + ('greedy',),
    'baseline':  ('greedy', 'bramev'),
    'all':       METHOD_NAMES,
}

#: Tout ce qu'une CLI ou un fichier YAML peut écrire dans `methods`.
METHOD_TOKENS: tuple[str, ...] = (
    METHOD_NAMES + tuple(ALIASES) + tuple(METHOD_GROUPS)
)


# ----------------------------------------------------------------------
# Résolution
# ----------------------------------------------------------------------

def canonical(name: str) -> str:
    """Nom canonique d'une méthode (résout les alias). Lève KeyError sinon."""
    key = str(name).strip().lower()
    key = ALIASES.get(key, key)
    if key not in METHODS:
        raise KeyError(
            f"Méthode inconnue : {name!r}. Attendu parmi {list(METHOD_NAMES)} "
            f"(alias : {sorted(ALIASES)})"
        )
    return key


def resolve(name: str | MethodSpec) -> MethodSpec:
    """`MethodSpec` d'une méthode nommée (alias acceptés)."""
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
    Développe groupes et alias en noms canoniques, sans doublon et dans l'ordre.

    Un jeton inconnu est **conservé tel quel** : c'est la validation des
    paramètres qui le signalera, avec un message situé.
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
    """Libellé lisible d'une méthode ; le nom brut si elle est inconnue."""
    try:
        return resolve(name).label
    except KeyError:
        return str(name)


def describe_table() -> str:
    """Table du plan d'ablation, telle qu'affichée par `cli.py methods`."""
    header = (f"  {'méthode':<22}{'multi-stations':>15}{'réputation':>12}"
              f"{'adaptation':>12}{'choix offre':>13}   {'libellé'}")
    lines = [header, '  ' + '-' * (len(header) - 2)]
    titres = {'ablation': 'échelle d ablation', 'baseline': 'baselines',
              'variant': 'variantes'}
    for family in ('ablation', 'baseline', 'variant'):
        group = [s for s in _SPECS if s.family == family]
        if not group:
            continue
        lines.append(f"  [{titres[family]}]")
        for spec in group:
            lines.append(
                f"  {spec.name:<22}"
                f"{'oui' if spec.broadcast else 'non':>15}"
                f"{'oui' if spec.use_reputation else 'non':>12}"
                f"{'oui' if spec.collective_learning else 'non':>12}"
                f"{spec.offer_choice:>13}"
                f"   {spec.label}"
            )
    return '\n'.join(lines)
