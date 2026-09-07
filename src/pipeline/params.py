"""
params.py — Experiment parameters.

The whole configuration of a campaign is carried by a single validated
dataclass, built indifferently from the command line or from a YAML/JSON file.
It is serialised with the results (`params.json`), which makes a run replayable
without having to recover the original command.
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

#: Available methods, in registry order (ablation ladder then BRAM-EV
#: variants) — see `src/experiments/methods.py`.
METHODS = methods_module.METHOD_NAMES

#: What a YAML file or the CLI may write in `methods`: a name, an alias
#: (`nearest`), or a group (`ablation`, `variants`, `baseline`, `all`).
METHOD_TOKENS = methods_module.METHOD_TOKENS

SLOTS_PER_HOUR = cfg_module.SimulationConfig.NB_SLOTS_IN_ONE_HOUR
SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR


class ParamsError(ValueError):
    """Invalid experiment parameters."""


@dataclass(frozen=True)
class CaseParams:
    """One elementary case of the grid: a scenario, a fleet, a method."""

    scenario: str
    nb_cars: int
    method: str

    @property
    def world_tag(self) -> str:
        """Identifier of the initial world, shared by every method."""
        return f"{self.scenario}_{self.nb_cars}cars"

    @property
    def tag(self) -> str:
        return f"{self.world_tag}_{self.method}"

    def __str__(self) -> str:
        return self.tag


@dataclass
class ExperimentParams:
    """
    Parameters of a campaign of experiments.

    The default values reproduce the grid of the report: 3 scenarios x 5 fleet
    sizes x the 4 rungs of the ablation ladder, over 5 simulated days. That
    ladder contains the two historical methods (`greedy` and `bramev`): the
    original comparison stays readable, and the two intermediate rungs say where
    the gap comes from.
    """

    # ---- experiment plan
    seed: int = DEFAULT_SEED
    scenarios: tuple[str, ...] = SCENARIOS
    fleet_sizes: tuple[int, ...] = (50, 100, 150, 200, 250)
    methods: tuple[str, ...] = methods_module.LADDER

    # ---- simulated environment
    total_time: int = 5 * SLOTS_PER_DAY
    nb_stations: int = 40
    nb_societies: int = 4
    nb_charg_spot_low: int = 4
    nb_charg_spot_high: int = 6
    strategy_noise: float = 0.5

    # ---- protocol
    offer_ttl_slots: int = 1
    late_cancel_fraction: float = 0.5
    #: Planning horizon (slots) between the emission of a request and the
    #: targeted slot, drawn uniformly in [low, high]. (0, 0) disables
    #: anticipation — reservation for the immediate slot, hence a zero delay and
    #: cancellations all qualified as "late": that is the control arm of the
    #: ablation, not a neutral setting.
    reservation_lead_low: int = 0
    reservation_lead_high: int = 12
    society_update_interval: int | None = None
    #: Common alpha imposed on the fixed-alpha methods (`bramev_fixed_alpha`).
    #: No effect on the others: their alpha comes from the shared world.
    alpha_fixed: float = 0.5

    # ---- outputs
    output_root: str = 'results_grid'
    label: str | None = None
    keep_logs: bool = False
    save_latency: bool = True
    save_tables: bool = True
    figures: bool = True
    log_every: int = 12 * SLOTS_PER_HOUR

    # ---- internal fields (not expected in a config file)
    _source: str | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __post_init__(self):
        # Normalise the sequences into tuples: a configuration dataclass must
        # not expose a shared mutable container.
        object.__setattr__(self, 'scenarios', tuple(self.scenarios))
        object.__setattr__(self, 'fleet_sizes', tuple(int(n) for n in self.fleet_sizes))
        # Groups (`ablation`, `variants`, `all`) and aliases (`nearest`) are
        # expanded into canonical names here: the rest of the pipeline — case
        # tags, file names, the `method` column of summary.csv — only ever sees
        # a canonical name. An unknown token is kept as is so that `validate()`
        # reports it with a situated message.
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
                f"Unknown keys in the parameters: {unknown}. "
                f"Expected one of {sorted(known)}"
            )
        return cls(**dict(data), _source=source)

    @classmethod
    def from_file(cls, path: str | os.PathLike) -> "ExperimentParams":
        """
        Load parameters from a YAML or JSON file.

        The format is deduced from the extension; a `.yaml` file without PyYAML
        installed raises an explicit error rather than failing silently.
        """
        path = Path(path)
        if not path.is_file():
            raise ParamsError(f"Parameter file not found: {path}")
        text = path.read_text(encoding='utf-8')

        if path.suffix.lower() in ('.yaml', '.yml'):
            try:
                import yaml
            except ImportError as exc:      # pragma: no cover
                raise ParamsError(
                    "PyYAML is required to read a .yaml file "
                    "(`uv sync` installs it)."
                ) from exc
            data = yaml.safe_load(text) or {}
        elif path.suffix.lower() == '.json':
            data = json.loads(text)
        else:
            raise ParamsError(
                f"Unsupported extension: {path.suffix!r}. Expected .yaml, .yml or .json"
            )

        if not isinstance(data, Mapping):
            raise ParamsError(f"{path} must contain a dictionary of parameters")
        return cls.from_mapping(data, source=str(path))

    def merged_with(self, overrides: Mapping[str, Any]) -> "ExperimentParams":
        """Apply overrides (typically the CLI options)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        unknown = sorted(set(clean) - set(self.field_names()))
        if unknown:
            raise ParamsError(f"Unknown overrides: {unknown}")
        return replace(self, **clean)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        errors: list[str] = []

        if not isinstance(self.seed, int) or self.seed < 0:
            errors.append(f"seed must be an integer >= 0, got {self.seed!r}")

        if not self.scenarios:
            errors.append("scenarios cannot be empty")
        for name in self.scenarios:
            if name not in SCENARIOS:
                errors.append(f"unknown scenario: {name!r} (expected {list(SCENARIOS)})")

        if not self.methods:
            errors.append("methods cannot be empty")
        for name in self.methods:
            if not methods_module.is_known(name):
                errors.append(
                    f"unknown method: {name!r} (expected {list(METHODS)}, "
                    f"aliases {sorted(methods_module.ALIASES)}, "
                    f"groups {sorted(methods_module.METHOD_GROUPS)})"
                )

        if not self.fleet_sizes:
            errors.append("fleet_sizes cannot be empty")
        for n in self.fleet_sizes:
            if n <= 0:
                errors.append(f"invalid fleet size: {n}")
        if len(set(self.fleet_sizes)) != len(self.fleet_sizes):
            errors.append(f"duplicated fleet sizes: {self.fleet_sizes}")

        for name, value in (('total_time', self.total_time),
                            ('nb_stations', self.nb_stations),
                            ('nb_societies', self.nb_societies),
                            ('offer_ttl_slots', self.offer_ttl_slots),
                            ('log_every', self.log_every)):
            if not isinstance(value, int) or value <= 0:
                errors.append(f"{name} must be an integer > 0, got {value!r}")

        if self.nb_charg_spot_low <= 0 or self.nb_charg_spot_high <= 0:
            errors.append("nb_charg_spot_low/high must be > 0")
        elif self.nb_charg_spot_low > self.nb_charg_spot_high:
            errors.append("nb_charg_spot_low must be <= nb_charg_spot_high")

        if self.nb_societies > self.nb_stations:
            errors.append(
                f"nb_societies ({self.nb_societies}) cannot exceed "
                f"nb_stations ({self.nb_stations}): a company with no station "
                "takes no part in collective learning"
            )

        if self.strategy_noise < 0:
            errors.append("strategy_noise must be >= 0")
        if not 0 < self.late_cancel_fraction <= 1:
            errors.append("late_cancel_fraction must be in ]0, 1]")

        for name, value in (('reservation_lead_low', self.reservation_lead_low),
                            ('reservation_lead_high', self.reservation_lead_high)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{name} must be an integer >= 0, got {value!r}")
        if (isinstance(self.reservation_lead_low, int)
                and isinstance(self.reservation_lead_high, int)
                and self.reservation_lead_low > self.reservation_lead_high):
            errors.append(
                f"reservation_lead_low ({self.reservation_lead_low}) must be "
                f"<= reservation_lead_high ({self.reservation_lead_high})"
            )
        # Structural warning, not an error: too short a horizon is legitimate
        # but leaves the `early` branch unreachable. The effective delay is
        # `l_n + ceil(travel)`, i.e. at least `l_n + 1`, to be compared with the
        # minimum derived from the threshold (see `min_lead_for_early_cancel`).
        probe = cfg_module.SimulationConfig()
        probe.LATE_CANCEL_FRACTION = self.late_cancel_fraction
        min_lead = probe.min_lead_for_early_cancel()
        if 0 < self.reservation_lead_high and self.reservation_lead_high + 1 < min_lead:
            warnings.warn(
                f"reservation_lead_high={self.reservation_lead_high}: no drawn "
                f"horizon will allow an early cancellation "
                f"(minimal delay {min_lead} slots for "
                f"late_cancel_fraction={self.late_cancel_fraction}). "
                "Every cancellation will be qualified as late.",
                stacklevel=2,
            )

        if self.society_update_interval is not None and self.society_update_interval <= 0:
            errors.append("society_update_interval must be > 0 or None (default)")

        if not 0. <= float(self.alpha_fixed) <= 1.:
            errors.append(
                f"alpha_fixed must be in [0, 1], got {self.alpha_fixed!r}")

        if errors:
            raise ParamsError("Invalid parameters:\n  - " + "\n  - ".join(errors))

    # ------------------------------------------------------------------
    # Experiment plan
    # ------------------------------------------------------------------

    def cases(self) -> Iterator[CaseParams]:
        """Enumerate the cases in execution order (worlds grouped)."""
        for scenario in self.scenarios:
            for nb_cars in self.fleet_sizes:
                for method in self.methods:
                    yield CaseParams(scenario=scenario, nb_cars=nb_cars, method=method)

    def worlds(self) -> Iterator[tuple[str, int]]:
        """
        Enumerate the (scenario, fleet) pairs.

        Each pair gives a world, but all those worlds share the same grid and,
        at equal fleet size, the same vehicle population: only the behaviour
        probabilities change from one scenario to the next (see
        `src/experiments/world.py`).
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
    # Translation into a simulation configuration
    # ------------------------------------------------------------------

    def build_config(self, scenario: str, nb_cars: int) -> cfg_module.SimulationConfig:
        """Build the `SimulationConfig` of a case. No side effect."""
        config = self._build_common_config(nb_cars)
        config.set_scenario(scenario)
        return config

    def build_shared_config(self, nb_cars: int | None = None) -> cfg_module.SimulationConfig:
        """
        Configuration of the shared draws: the grid and the fleets.

        The scenario is **deliberately not set** here. A shared draw reading
        `BASE_CANCEL_PROB` would produce the default values rather than those of
        a scenario: the omission is the guard, and `tests/test_shared_world.py`
        verifies the resulting invariance.
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
            f"seed={self.seed} | scenarios={list(self.scenarios)} | "
            f"fleets={list(self.fleet_sizes)} | methods={list(self.methods)} | "
            f"{self.total_time} slots ({self.total_time / SLOTS_PER_DAY:.1f} d) | "
            f"{self.nb_stations} stations / {self.nb_societies} companies | "
            f"reservation horizon [{self.reservation_lead_low}, "
            f"{self.reservation_lead_high}] slots | "
            f"{self.nb_cases} runs"
        )
