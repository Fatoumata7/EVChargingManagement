"""
store.py — Layout and persistence of the artifacts of a run.

A run is a self-contained directory: the parameters, the initial worlds, the
results, the tables and the figures live together in it, so that a run can be
archived, shared or re-analysed without depending on the command that created
it.

    <output_root>/<timestamp>_seed<seed>[_<label>]/
        params.json                      parameters of the campaign
        manifest.json                    environment, progress, timings
        summary.csv                      one row per case (pivot table)
        grid.json                        infrastructure shared by ALL the cases
        fleets/fleet_<n>cars.json        vehicle population, per fleet
        worlds/<scenario>_<n>cars.json   composed world (grid + fleet + scenario)
        results/<tag>.json               complete metrics of one case
        tables/grid_stations.csv         the grid, flat: positions, companies, alpha
        tables/grid_societies.csv        companies: position and point strategy
        tables/fleet_<n>cars.csv         the fleet, flat: initial positions…
        tables/<tag>_<table>.csv         tidy tables of a case (latency, stations…)
        logs/<tag>.txt                   detailed log (--keep-logs option)
        figures/*.png                    figures regenerable without re-simulating

`grid.json` and `fleets/` are the *primitives*: the worlds in `worlds/` are
entirely derived from them (see `src/experiments/world.compose_world_spec`) and
are persisted for traceability only.

`RunStore` is the only place that knows this layout: no other module builds a
path by hand.
"""

from __future__ import annotations

import csv
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from src.pipeline.params import ExperimentParams, CaseParams

MANIFEST = 'manifest.json'
PARAMS = 'params.json'
SUMMARY = 'summary.csv'
GRID = 'grid.json'


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def git_commit() -> str | None:
    """Current commit, to trace the code that produced the results."""
    try:
        out = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                      stderr=subprocess.DEVNULL, timeout=5)
        return out.decode().strip()
    except Exception:
        return None


def git_is_dirty() -> bool | None:
    try:
        out = subprocess.check_output(['git', 'status', '--porcelain'],
                                      stderr=subprocess.DEVNULL, timeout=5)
        return bool(out.decode().strip())
    except Exception:
        return None


class RunStore:
    """Read/write access to the artifacts of a run."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ------------------------------------------------------------------
    # Creation / opening
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, params: ExperimentParams) -> "RunStore":
        """Create the run directory and write the parameters and manifest in it."""
        name = f"{_utc_stamp()}_seed{params.seed}"
        if params.label:
            name = f"{name}_{_slug(params.label)}"
        store = cls(Path(params.output_root) / name)
        store._mkdirs()
        store.write_params(params)
        store.write_manifest({
            'run': store.root.name,
            'started_utc': _utc_stamp(),
            'finished_utc': None,
            'seed': params.seed,
            'nb_cases_planned': params.nb_cases,
            'nb_cases_done': 0,
            'params_source': params._source,
            'git_commit': git_commit(),
            'git_dirty': git_is_dirty(),
            'python': sys.version.split()[0],
            'platform': platform.platform(),
            'cases': [],
        })
        return store

    @classmethod
    def open(cls, root: str | Path) -> "RunStore":
        store = cls(root)
        if not store.params_path.is_file():
            raise FileNotFoundError(
                f"{store.root} n'est pas un dossier de run "
                f"({PARAMS} introuvable)"
            )
        return store

    @classmethod
    def latest(cls, output_root: str | Path = 'results_grid') -> "RunStore":
        runs = cls.list_runs(output_root)
        if not runs:
            raise FileNotFoundError(f"No run found in {output_root}")
        return cls.open(runs[-1])

    @classmethod
    def latest_with_methods(cls, methods: Sequence[str],
                            output_root: str | Path = 'results_grid') -> "RunStore":
        """
        Most recent run whose `summary.csv` contains all of these methods.

        A campaign does not necessarily carry every method of the registry:
        `latest()` may therefore designate a run where the requested comparison
        is impossible. This selector avoids analysing a run that is silent on
        the question asked — and, on failure, says which methods each run
        contains rather than leaving an empty table to explain itself.

        Parameters
        ----------
        methods : Sequence[str]
            Canonical names required (see `src/experiments/methods.py`).

        Raises
        ------
        FileNotFoundError
            No run contains all of them.
        """
        required = set(methods)
        inventory: list[tuple[Path, set[str]]] = []
        for path in reversed(cls.list_runs(output_root)):
            store = cls(path)
            present = {row['method'] for row in store.read_summary()
                       if row.get('method')}
            if required <= present:
                return cls.open(path)
            inventory.append((path, present))

        detail = '\n'.join(
            f"  {path.name} : {', '.join(sorted(present)) or 'no case'}"
            for path, present in inventory) or '  (no run)'
        raise FileNotFoundError(
            f"No run in {output_root} contains all the methods "
            f"{sorted(required)}.\nAvailable runs:\n{detail}"
        )

    @staticmethod
    def list_runs(output_root: str | Path = 'results_grid') -> list[Path]:
        root = Path(output_root)
        if not root.is_dir():
            return []
        return sorted(p for p in root.iterdir()
                      if (p / PARAMS).is_file())

    def _mkdirs(self) -> None:
        for path in (self.root, self.fleets_dir, self.worlds_dir,
                     self.results_dir, self.tables_dir, self.figures_dir,
                     self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Chemins
    # ------------------------------------------------------------------

    @property
    def params_path(self) -> Path:
        return self.root / PARAMS

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST

    @property
    def summary_path(self) -> Path:
        return self.root / SUMMARY

    @property
    def grid_path(self) -> Path:
        return self.root / GRID

    @property
    def fleets_dir(self) -> Path:
        return self.root / 'fleets'

    @property
    def worlds_dir(self) -> Path:
        return self.root / 'worlds'

    @property
    def results_dir(self) -> Path:
        return self.root / 'results'

    @property
    def tables_dir(self) -> Path:
        return self.root / 'tables'

    @property
    def figures_dir(self) -> Path:
        return self.root / 'figures'

    @property
    def logs_dir(self) -> Path:
        return self.root / 'logs'

    def fleet_path(self, nb_cars: int) -> Path:
        return self.fleets_dir / f'fleet_{nb_cars}cars.json'

    def world_path(self, scenario: str, nb_cars: int) -> Path:
        return self.worlds_dir / f'{scenario}_{nb_cars}cars.json'

    def shared_table_path(self, name: str) -> Path:
        """Campaign table (grid, fleet), as opposed to the table of a case."""
        return self.tables_dir / f'{name}.csv'

    def result_path(self, case: CaseParams) -> Path:
        return self.results_dir / f'{case.tag}.json'

    def table_path(self, case: CaseParams, table: str) -> Path:
        return self.tables_dir / f'{case.tag}_{table}.csv'

    def log_path(self, case: CaseParams) -> Path:
        return self.logs_dir / f'{case.tag}.txt'

    def figure_path(self, name: str) -> Path:
        return self.figures_dir / f'{name}.png'

    # ------------------------------------------------------------------
    # Parameters & manifest
    # ------------------------------------------------------------------

    def write_params(self, params: ExperimentParams) -> None:
        _write_json(self.params_path, params.to_dict())

    def read_params(self) -> ExperimentParams:
        return ExperimentParams.from_mapping(
            _read_json(self.params_path), source=str(self.params_path))

    def write_manifest(self, manifest: Mapping[str, Any]) -> None:
        _write_json(self.manifest_path, dict(manifest))

    def read_manifest(self) -> dict:
        return _read_json(self.manifest_path)

    def record_case(self, entry: Mapping[str, Any]) -> None:
        """Append a finished case to the manifest (written at every case: an
        interrupted run stays usable)."""
        manifest = self.read_manifest()
        manifest['cases'].append(dict(entry))
        manifest['nb_cases_done'] = len(manifest['cases'])
        self.write_manifest(manifest)

    def close_manifest(self, total_wall_time_s: float) -> None:
        manifest = self.read_manifest()
        manifest['finished_utc'] = _utc_stamp()
        manifest['total_wall_time_s'] = round(total_wall_time_s, 1)
        self.write_manifest(manifest)

    # ------------------------------------------------------------------
    # Grid, fleets, worlds & results
    # ------------------------------------------------------------------

    def save_grid(self, spec) -> Path:
        """Persist the infrastructure shared by the whole campaign."""
        spec.save(str(self.grid_path))
        return self.grid_path

    def load_grid(self):
        from src.experiments.world import GridSpec
        return GridSpec.load(str(self.grid_path))

    def save_fleet(self, spec) -> Path:
        path = self.fleet_path(spec.nb_cars)
        spec.save(str(path))
        return path

    def load_fleet(self, nb_cars: int):
        from src.experiments.world import FleetSpec
        return FleetSpec.load(str(self.fleet_path(nb_cars)))

    def save_world(self, spec, scenario: str, nb_cars: int) -> Path:
        path = self.world_path(scenario, nb_cars)
        spec.save(str(path))
        return path

    def load_world(self, scenario: str, nb_cars: int):
        from src.experiments.world import WorldSpec
        return WorldSpec.load(str(self.world_path(scenario, nb_cars)))

    def save_result(self, case: CaseParams, result: Mapping[str, Any]) -> Path:
        path = self.result_path(case)
        _write_json(path, dict(result), default=str)
        return path

    def load_result(self, case: CaseParams) -> dict:
        return _read_json(self.result_path(case))

    def iter_results(self) -> Iterator[dict]:
        for path in sorted(self.results_dir.glob('*.json')):
            yield _read_json(path)

    def has_result(self, case: CaseParams) -> bool:
        return self.result_path(case).is_file()

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def write_table(self, case: CaseParams, table: str,
                    rows: Sequence[Mapping[str, Any]]) -> Path | None:
        if not rows:
            return None
        path = self.table_path(case, table)
        _write_csv(path, rows)
        return path

    def write_shared_table(self, name: str,
                           rows: Sequence[Mapping[str, Any]]) -> Path | None:
        """Write a campaign table (grid, fleet). `None` if empty."""
        if not rows:
            return None
        path = self.shared_table_path(name)
        _write_csv(path, rows)
        return path

    def read_shared_table(self, name: str) -> list[dict]:
        """Read back a campaign table; empty list if it does not exist."""
        path = self.shared_table_path(name)
        if not path.is_file():
            return []
        with path.open(encoding='utf-8', newline='') as fh:
            return [{k: _coerce(v) for k, v in row.items()}
                    for row in csv.DictReader(fh)]

    def root_table_path(self, name: str) -> Path:
        """Campaign table written at the root of the run (e.g. `ablation.csv`)."""
        return self.root / f'{name}.csv'

    def write_root_table(self, name: str, rows: Sequence[Mapping[str, Any]],
                         fieldnames: Sequence[str] | None = None) -> Path | None:
        """Write a campaign table at the root. `None` if it is empty."""
        if not rows:
            return None
        path = self.root_table_path(name)
        _write_csv(path, rows, fieldnames=fieldnames)
        return path

    def read_root_table(self, name: str) -> list[dict]:
        """Relit une table de racine ; liste vide si elle n'existe pas."""
        path = self.root_table_path(name)
        if not path.is_file():
            return []
        with path.open(encoding='utf-8', newline='') as fh:
            return [{k: _coerce(v) for k, v in row.items()}
                    for row in csv.DictReader(fh)]

    def write_summary(self, rows: Sequence[Mapping[str, Any]],
                      fieldnames: Sequence[str]) -> Path:
        _write_csv(self.summary_path, rows, fieldnames=fieldnames)
        return self.summary_path

    def read_summary(self) -> list[dict]:
        """Relit summary.csv en reconvertissant les nombres."""
        if not self.summary_path.is_file():
            return []
        with self.summary_path.open(encoding='utf-8', newline='') as fh:
            return [{k: _coerce(v) for k, v in row.items()}
                    for row in csv.DictReader(fh)]

    def __repr__(self) -> str:
        return f"RunStore({self.root})"


# ----------------------------------------------------------------------
# Low-level input/output
# ----------------------------------------------------------------------

def _write_json(path: Path, data: dict, default=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=default)
    # Atomic write: an interrupted run leaves no truncated JSON behind.
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    with Path(path).open(encoding='utf-8') as fh:
        return json.load(fh)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]],
               fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames),
                                extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _coerce(value: str):
    """Reconvertit une cellule CSV en int/float/bool/None quand c'est possible."""
    if value is None or value == '':
        return None
    low = value.lower()
    if low == 'true':
        return True
    if low == 'false':
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _slug(text: str) -> str:
    keep = [ch if (ch.isalnum() or ch in '-_') else '-' for ch in text.strip()]
    return ''.join(keep).strip('-').lower() or 'run'
