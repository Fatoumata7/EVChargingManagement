"""
params.py — Paramètres d'expérience.

Toute la configuration d'une campagne est portée par une seule dataclasse
validée, construite indifféremment depuis la ligne de commande ou depuis un
fichier YAML/JSON. Elle est sérialisée avec les résultats (`params.json`), ce qui
rend un run rejouable sans avoir à retrouver la commande d'origine.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, asdict, field, fields, replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import src.experiments.config as cfg_module
import src.experiments.methods as methods_module
from src.experiments.seeding import DEFAULT_SEED

SCENARIOS = tuple(cfg_module.SimulationConfig.SCENARIOS)

#: Méthodes disponibles, dans l'ordre du registre (échelle d'ablation puis
#: variantes de BRAM-EV) — cf. `src/experiments/methods.py`.
METHODS = methods_module.METHOD_NAMES

#: Ce qu'un fichier YAML ou la CLI peut écrire dans `methods` : un nom, un alias
#: (`nearest`), ou un groupe (`ablation`, `variants`, `baseline`, `all`).
METHOD_TOKENS = methods_module.METHOD_TOKENS

SLOTS_PER_HOUR = cfg_module.SimulationConfig.NB_SLOTS_IN_ONE_HOUR
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR


class ParamsError(ValueError):
    """Paramètres d'expérience invalides."""


@dataclass(frozen=True)
class CaseParams:
    """Un cas élémentaire de la grille : un scénario, une flotte, une méthode."""

    scenario: str
    nb_cars: int
    method: str

    @property
    def world_tag(self) -> str:
        """Identifiant du monde initial, partagé par toutes les méthodes."""
        return f"{self.scenario}_{self.nb_cars}cars"

    @property
    def tag(self) -> str:
        return f"{self.world_tag}_{self.method}"

    def __str__(self) -> str:
        return self.tag


@dataclass
class ExperimentParams:
    """
    Paramètres d'une campagne d'expériences.

    Les valeurs par défaut reproduisent la grille du rapport :
    3 scénarios x 5 tailles de flotte x les 4 barreaux de l'échelle d'ablation,
    sur 5 jours simulés. Cette échelle contient les deux méthodes historiques
    (`greedy` et `bramev`) : la comparaison d'origine reste lisible, et les deux
    barreaux intermédiaires disent d'où vient l'écart.
    """

    # ---- plan d'expérience
    seed: int = DEFAULT_SEED
    scenarios: tuple[str, ...] = SCENARIOS
    fleet_sizes: tuple[int, ...] = (50, 100, 150, 200, 250)
    methods: tuple[str, ...] = methods_module.LADDER

    # ---- environnement simulé
    total_time: int = 5 * SLOTS_PER_DAY
    nb_stations: int = 40
    nb_societies: int = 4
    nb_charg_spot_low: int = 4
    nb_charg_spot_high: int = 6
    strategy_noise: float = 0.5

    # ---- protocole
    offer_ttl_slots: int = 1
    late_cancel_fraction: float = 0.5
    #: Horizon de planification (slots) entre l'émission d'une requête et le
    #: créneau souhaité, tiré uniformément dans [low, high]. (0, 0) désactive
    #: l'anticipation — réservation pour le créneau immédiat, d'où un délai nul
    #: et des annulations toutes qualifiées « tardives » : c'est le bras de
    #: contrôle de l'ablation, pas un réglage neutre.
    reservation_lead_low: int = 0
    reservation_lead_high: int = 12
    society_update_interval: int | None = None
    #: Alpha commun imposé aux méthodes à alpha fixe (`bramev_fixed_alpha`).
    #: Sans effet sur les autres : leur alpha vient du monde partagé.
    alpha_fixed: float = 0.5

    # ---- sorties
    output_root: str = 'results_grid'
    label: str | None = None
    keep_logs: bool = False
    save_latency: bool = True
    save_tables: bool = True
    figures: bool = True
    log_every: int = 12 * SLOTS_PER_HOUR

    # ---- champs internes (non attendus dans un fichier de config)
    _source: str | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __post_init__(self):
        # Normalise les séquences en tuples : une dataclasse de configuration
        # ne doit pas exposer de conteneur mutable partagé.
        object.__setattr__(self, 'scenarios', tuple(self.scenarios))
        object.__setattr__(self, 'fleet_sizes', tuple(int(n) for n in self.fleet_sizes))
        # Groupes (`ablation`, `variants`, `all`) et alias (`nearest`) sont
        # développés en noms canoniques ici : le reste du pipeline — tags de
        # cas, noms de fichiers, colonne `method` de summary.csv — ne voit
        # jamais qu'un nom canonique. Un jeton inconnu est conservé tel quel
        # pour que `validate()` le signale avec un message situé.
        object.__setattr__(self, 'methods', methods_module.expand(self.methods))
        self.validate()

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls) if not f.name.startswith('_'))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], source: str | None = None) -> "ExperimentParams":
        known = set(cls.field_names())
        unknown = sorted(set(data) - known)
        if unknown:
            raise ParamsError(
                f"Clés inconnues dans les paramètres : {unknown}. "
                f"Attendu parmi {sorted(known)}"
            )
        return cls(**dict(data), _source=source)

    @classmethod
    def from_file(cls, path: str | os.PathLike) -> "ExperimentParams":
        """
        Charge des paramètres depuis un fichier YAML ou JSON.

        Le format est déduit de l'extension ; un fichier `.yaml` sans PyYAML
        installé lève une erreur explicite plutôt qu'un échec silencieux.
        """
        path = Path(path)
        if not path.is_file():
            raise ParamsError(f"Fichier de paramètres introuvable : {path}")
        text = path.read_text(encoding='utf-8')

        if path.suffix.lower() in ('.yaml', '.yml'):
            try:
                import yaml
            except ImportError as exc:      # pragma: no cover
                raise ParamsError(
                    "PyYAML est requis pour lire un fichier .yaml "
                    "(`uv sync` l'installe)."
                ) from exc
            data = yaml.safe_load(text) or {}
        elif path.suffix.lower() == '.json':
            data = json.loads(text)
        else:
            raise ParamsError(
                f"Extension non gérée : {path.suffix!r}. Attendu .yaml, .yml ou .json"
            )

        if not isinstance(data, Mapping):
            raise ParamsError(f"{path} doit contenir un dictionnaire de paramètres")
        return cls.from_mapping(data, source=str(path))

    def merged_with(self, overrides: Mapping[str, Any]) -> "ExperimentParams":
        """Applique des surcharges (typiquement les options de la CLI)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        unknown = sorted(set(clean) - set(self.field_names()))
        if unknown:
            raise ParamsError(f"Surcharges inconnues : {unknown}")
        return replace(self, **clean)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        errors: list[str] = []

        if not isinstance(self.seed, int) or self.seed < 0:
            errors.append(f"seed doit être un entier >= 0, reçu {self.seed!r}")

        if not self.scenarios:
            errors.append("scenarios ne peut pas être vide")
        for name in self.scenarios:
            if name not in SCENARIOS:
                errors.append(f"scénario inconnu : {name!r} (attendu {list(SCENARIOS)})")

        if not self.methods:
            errors.append("methods ne peut pas être vide")
        for name in self.methods:
            if not methods_module.is_known(name):
                errors.append(
                    f"méthode inconnue : {name!r} (attendu {list(METHODS)}, "
                    f"alias {sorted(methods_module.ALIASES)}, "
                    f"groupes {sorted(methods_module.METHOD_GROUPS)})"
                )

        if not self.fleet_sizes:
            errors.append("fleet_sizes ne peut pas être vide")
        for n in self.fleet_sizes:
            if n <= 0:
                errors.append(f"taille de flotte invalide : {n}")
        if len(set(self.fleet_sizes)) != len(self.fleet_sizes):
            errors.append(f"tailles de flotte dupliquées : {self.fleet_sizes}")

        for name, value in (('total_time', self.total_time),
                            ('nb_stations', self.nb_stations),
                            ('nb_societies', self.nb_societies),
                            ('offer_ttl_slots', self.offer_ttl_slots),
                            ('log_every', self.log_every)):
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{name} doit être un entier > 0, reçu {value!r}")

        if self.nb_charg_spot_low <= 0 or self.nb_charg_spot_high <= 0:
            errors.append("nb_charg_spot_low/high doivent être > 0")
        elif self.nb_charg_spot_low > self.nb_charg_spot_high:
            errors.append("nb_charg_spot_low doit être <= nb_charg_spot_high")

        if self.nb_societies > self.nb_stations:
            errors.append(
                f"nb_societies ({self.nb_societies}) ne peut pas dépasser "
                f"nb_stations ({self.nb_stations}) : une société sans station "
                "ne participe pas à l'apprentissage collectif"
            )

        if self.strategy_noise < 0:
            errors.append("strategy_noise doit être >= 0")
        if not 0 < self.late_cancel_fraction <= 1:
            errors.append("late_cancel_fraction doit être dans ]0, 1]")

        for name, value in (('reservation_lead_low', self.reservation_lead_low),
                            ('reservation_lead_high', self.reservation_lead_high)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{name} doit être un entier >= 0, reçu {value!r}")
        if (isinstance(self.reservation_lead_low, int)
                and isinstance(self.reservation_lead_high, int)
                and self.reservation_lead_low > self.reservation_lead_high):
            errors.append(
                f"reservation_lead_low ({self.reservation_lead_low}) doit être "
                f"<= reservation_lead_high ({self.reservation_lead_high})"
            )
        # Avertissement structurel, pas une erreur : un horizon trop court est
        # licite mais laisse la branche `early` inatteignable. Le délai effectif
        # vaut `l_n + ceil(trajet)`, soit au moins `l_n + 1`, à comparer au
        # minimum déduit du seuil (cf. `min_lead_for_early_cancel`).
        probe = cfg_module.SimulationConfig()
        probe.LATE_CANCEL_FRACTION = self.late_cancel_fraction
        min_lead = probe.min_lead_for_early_cancel()
        if 0 < self.reservation_lead_high and self.reservation_lead_high + 1 < min_lead:
            warnings.warn(
                f"reservation_lead_high={self.reservation_lead_high} : aucun "
                f"horizon tiré ne permettra une annulation anticipée "
                f"(délai minimal {min_lead} slots pour "
                f"late_cancel_fraction={self.late_cancel_fraction}). "
                "Toutes les annulations seront qualifiées « tardives ».",
                stacklevel=2,
            )

        if self.society_update_interval is not None and self.society_update_interval <= 0:
            errors.append("society_update_interval doit être > 0 ou nul (défaut)")

        if not 0. <= float(self.alpha_fixed) <= 1.:
            errors.append(
                f"alpha_fixed doit être dans [0, 1], reçu {self.alpha_fixed!r}")

        if errors:
            raise ParamsError("Paramètres invalides :\n  - " + "\n  - ".join(errors))

    # ------------------------------------------------------------------
    # Plan d'expérience
    # ------------------------------------------------------------------

    def cases(self) -> Iterator[CaseParams]:
        """Énumère les cas dans l'ordre d'exécution (mondes regroupés)."""
        for scenario in self.scenarios:
            for nb_cars in self.fleet_sizes:
                for method in self.methods:
                    yield CaseParams(scenario=scenario, nb_cars=nb_cars, method=method)

    def worlds(self) -> Iterator[tuple[str, int]]:
        """
        Énumère les couples (scénario, flotte).

        Chaque couple donne un monde, mais tous ces mondes partagent la même
        grille et, à taille de flotte égale, la même population de véhicules :
        seules les probabilités de comportement changent d'un scénario à
        l'autre (cf. `src/experiments/world.py`).
        """
        for scenario in self.scenarios:
            for nb_cars in self.fleet_sizes:
                yield scenario, nb_cars

    @property
    def nb_cases(self) -> int:
        return len(self.scenarios) * len(self.fleet_sizes) * len(self.methods)

    @property
    def max_fleet_size(self) -> int:
        return max(self.fleet_sizes)

    # ------------------------------------------------------------------
    # Traduction en configuration de simulation
    # ------------------------------------------------------------------

    def build_config(self, scenario: str, nb_cars: int) -> cfg_module.SimulationConfig:
        """Construit la `SimulationConfig` d'un cas. Sans effet de bord."""
        config = self._build_common_config(nb_cars)
        config.set_scenario(scenario)
        return config

    def build_shared_config(self, nb_cars: int | None = None) -> cfg_module.SimulationConfig:
        """
        Configuration des tirages partagés : la grille et les flottes.

        Le scénario n'y est **délibérément pas fixé**. Un tirage partagé qui
        lirait `BASE_CANCEL_PROB` produirait ici les valeurs par défaut plutôt
        que celles d'un scénario : l'omission est le garde-fou, et
        `tests/test_shared_world.py` vérifie l'invariance obtenue.
        """
        return self._build_common_config(nb_cars or self.max_fleet_size)

    def _build_common_config(self, nb_cars: int) -> cfg_module.SimulationConfig:
        config = cfg_module.SimulationConfig()
        config.set_VISUALIZE(False)
        config.set_seed(self.seed)
        config.set_TOTAL_TIME(self.total_time)
        config.set_NB_CARS(nb_cars)
        config.set_NB_STATIONS(self.nb_stations)
        config.set_NB_SOCIETIES(self.nb_societies)
        config.set_NB_CHARG_SPOT({'low': self.nb_charg_spot_low,
                                  'high': self.nb_charg_spot_high})
        config.set_STRATEGY_NOISE(self.strategy_noise)
        config.set_OFFER_TTL_SLOTS(self.offer_ttl_slots)
        config.LATE_CANCEL_FRACTION = self.late_cancel_fraction
        config.set_RESERVATION_LEAD_PARAMS({'low': self.reservation_lead_low,
                                            'high': self.reservation_lead_high})
        config.set_ALPHA_FIXED(self.alpha_fixed)
        if self.society_update_interval is not None:
            config.SOCIETY_UPDATE_INTERVAL = self.society_update_interval
        config.set_log_iter(self.log_every)
        return config

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if not k.startswith('_')}
        data['scenarios'] = list(self.scenarios)
        data['fleet_sizes'] = list(self.fleet_sizes)
        data['methods'] = list(self.methods)
        return data

    def describe(self) -> str:
        return (
            f"seed={self.seed} | scénarios={list(self.scenarios)} | "
            f"flottes={list(self.fleet_sizes)} | méthodes={list(self.methods)} | "
            f"{self.total_time} slots ({self.total_time / SLOTS_PER_DAY:.1f} j) | "
            f"{self.nb_stations} stations / {self.nb_societies} sociétés | "
            f"horizon de réservation [{self.reservation_lead_low}, "
            f"{self.reservation_lead_high}] slots | "
            f"{self.nb_cases} runs"
        )
