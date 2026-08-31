"""
store.py — Disposition et persistance des artefacts d'un run.

Un run est un dossier autonome : les paramètres, les mondes initiaux, les
résultats, les tables et les figures y cohabitent, de sorte qu'un run puisse
être archivé, transmis ou re-analysé sans dépendre de la commande qui l'a créé.

    <output_root>/<horodatage>_seed<seed>[_<label>]/
        params.json                      paramètres de la campagne
        manifest.json                    environnement, progression, timings
        summary.csv                      une ligne par cas (table pivot)
        grid.json                        infrastructure partagée par TOUS les cas
        fleets/fleet_<n>cars.json        population de véhicules, par flotte
        worlds/<scenario>_<n>cars.json   monde composé (grille + flotte + scénario)
        results/<tag>.json               métriques complètes d'un cas
        tables/grid_stations.csv         grille, à plat : positions, sociétés, alpha
        tables/grid_societies.csv        sociétés : position et stratégie de points
        tables/fleet_<n>cars.csv         flotte, à plat : positions initiales…
        tables/<tag>_<table>.csv         tables tidy d'un cas (latence, stations…)
        logs/<tag>.txt                   journal détaillé (option --keep-logs)
        figures/*.png                    figures régénérables sans re-simuler

`grid.json` et `fleets/` sont les *primitives* : les mondes de `worlds/` en sont
entièrement dérivés (cf. `src/experiments/world.compose_world_spec`) et ne sont
persistés que pour la traçabilité.

`RunStore` est la seule à connaître cette disposition : aucun autre module ne
construit de chemin à la main.
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
    """Commit courant, pour tracer le code qui a produit les résultats."""
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
    """Accès en lecture/écriture aux artefacts d'un run."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ------------------------------------------------------------------
    # Création / ouverture
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, params: ExperimentParams) -> "RunStore":
        """Crée le dossier du run et y écrit les paramètres et le manifeste."""
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
            raise FileNotFoundError(f"Aucun run trouvé dans {output_root}")
        return cls.open(runs[-1])

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
        """Table de campagne (grille, flotte), par opposition à celle d'un cas."""
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
    # Paramètres & manifeste
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
        """Ajoute un cas terminé au manifeste (écrit à chaque cas : un run
        interrompu reste exploitable)."""
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
    # Grille, flottes, mondes & résultats
    # ------------------------------------------------------------------

    def save_grid(self, spec) -> Path:
        """Persiste l'infrastructure partagée par toute la campagne."""
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
        """Écrit une table de campagne (grille, flotte). `None` si vide."""
        if not rows:
            return None
        path = self.shared_table_path(name)
        _write_csv(path, rows)
        return path

    def read_shared_table(self, name: str) -> list[dict]:
        """Relit une table de campagne ; liste vide si elle n'existe pas."""
        path = self.shared_table_path(name)
        if not path.is_file():
            return []
        with path.open(encoding='utf-8', newline='') as fh:
            return [{k: _coerce(v) for k, v in row.items()}
                    for row in csv.DictReader(fh)]

    def root_table_path(self, name: str) -> Path:
        """Table de campagne écrite à la racine du run (ex. `ablation.csv`)."""
        return self.root / f'{name}.csv'

    def write_root_table(self, name: str, rows: Sequence[Mapping[str, Any]],
                         fieldnames: Sequence[str] | None = None) -> Path | None:
        """Écrit une table de campagne à la racine. `None` si elle est vide."""
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
# Entrées/sorties de bas niveau
# ----------------------------------------------------------------------

def _write_json(path: Path, data: dict, default=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=default)
    # Écriture atomique : un run interrompu ne laisse pas de JSON tronqué.
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
