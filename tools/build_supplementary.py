"""
Build the anonymised supplementary archive of the paper.

    python tools/build_supplementary.py <git ref of the analysis code> <work dir>

Stages `<work dir>/supplementary/`, fills `outputs/` by running the archived
analysis code on the archived data (so the shipped outputs are exactly what
`scripts/rebuild_all.sh` produces), scans the tree for identifying strings and
writes `<work dir>/supplementary.tar.xz`. Nothing is simulated.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / 'tools' / 'supplementary'

ABLATION_RUN = '20260926T223707Z_seeds1-2-3-4+6_ablation'
PILOT_RUN = '20260928T191459Z_seeds1-2-3_congestion_pilot'

#: Commits the two campaigns ran on. The ablation ran on a clean tree; the
#: pilot on `PILOT_BASE` plus local changes, committed as `PILOT_TREE` — every
#: module it loaded was last modified before its start (see PROVENANCE).
ABLATION_COMMIT = '01d7a25'
PILOT_BASE = '63bd63f'
PILOT_TREE = '269a92a'

#: Modules imported by `python -m src.pipeline.cli run` (sys.modules after
#: import): the code a campaign actually executes.
EXECUTED_MODULES = (
    'src/__init__.py', 'src/env/__init__.py', 'src/env/car.py',
    'src/env/offer.py', 'src/env/society.py', 'src/env/station.py',
    'src/env/utils.py', 'src/experiments/__init__.py',
    'src/experiments/config.py', 'src/experiments/methods.py',
    'src/experiments/seeding.py', 'src/experiments/simulation.py',
    'src/experiments/world.py', 'src/metrics/__init__.py',
    'src/metrics/metrics.py', 'src/pipeline/__init__.py',
    'src/pipeline/ablation.py', 'src/pipeline/aggregate.py',
    'src/pipeline/cli.py', 'src/pipeline/figures.py',
    'src/pipeline/params.py', 'src/pipeline/runner.py',
    'src/pipeline/store.py', 'src/pipeline/tables.py',
)

CODE_PATHS = ('src', 'tests', 'main.py', 'pyproject.toml', 'uv.lock',
              '.python-version', 'experiments')

#: Run files shipped as input data. Root-level tables of the raw runs
#: (summary_mean, paired, ablation*) and their figures use the former
#: indicator names and are superseded by `outputs/`; logs are not shipped.
RUN_ITEMS = ('params.json', 'manifest.json', 'summary.csv', 'results',
             'tables', 'grids', 'fleets', 'worlds')

#: Strings that must not appear anywhere in the archive.
FORBIDDEN = re.compile(
    r'fatoumata|wadiou|milesmorales|/Users/|/home/|/private/|/var/folders|'
    r'github\.com|gitlab|ING3|PFE|EVChargingManagement|evchargingmanagement|'
    r'63bd63f|01d7a25|269a92a',
    re.IGNORECASE)


def sh(*args: str, **kw) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          **kw).stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_show(ref: str, path: str) -> bytes:
    return subprocess.run(['git', 'show', f'{ref}:{path}'], cwd=REPO,
                          check=True, capture_output=True).stdout


def export_tree(ref: str, paths, dest: Path, exclude=()) -> None:
    """`git archive` of `paths` at `ref` into `dest`, anonymised."""
    data = subprocess.run(['git', 'archive', '--format=tar', ref, *paths],
                          cwd=REPO, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        members = [m for m in tar.getmembers() if m.name not in exclude]
        tar.extractall(dest, members=members, filter='data')
    anonymise_project(dest)


def anonymise_project(dest: Path) -> None:
    """The project name is the name of the (nominative) repository."""
    for name in ('pyproject.toml', 'uv.lock'):
        path = dest / name
        if path.is_file():
            text = path.read_text()
            text = text.replace('name = "evchargingmanagement"',
                                'name = "ev-charging-supplementary"')
            text = text.replace('description = "Add your description here"',
                                'description = "Supplementary material: code"')
            path.write_text(text)


def provenance() -> dict:
    """Hash of every executed module, per campaign, against the shipped code."""
    out = {}
    for campaign, ref in (('ablation_campaign', ABLATION_COMMIT),
                          ('congestion_pilot', PILOT_TREE)):
        modules = {}
        for path in EXECUTED_MODULES:
            executed = sha256(git_show(ref, path))
            modules[path] = {'sha256': executed,
                             'identical_to_code_dir':
                                 executed == sha256(git_show('HEAD', path))}
        out[campaign] = modules
    same = all(out['ablation_campaign'][p]['sha256']
               == out['congestion_pilot'][p]['sha256']
               for p in EXECUTED_MODULES
               if p.startswith(('src/env', 'src/experiments', 'src/metrics')))
    out['simulator_identical_across_campaigns'] = same
    return out


def sanitise_manifest(path: Path, campaign: str) -> None:
    manifest = json.loads(path.read_text())
    manifest.pop('git_commit', None)
    manifest['code'] = (f'code_executed/{campaign}/ (see PROVENANCE.md); '
                        'commit identifiers removed for anonymity')
    path.write_text(json.dumps(manifest, indent=2) + '\n')


def main(ref: str, work: Path) -> int:
    work = Path(work).resolve()
    stage = work / 'supplementary'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    # --- Code: analysis code (frozen ref), and the code each campaign executed.
    export_tree(ref, CODE_PATHS, stage / 'code')
    export_tree(ABLATION_COMMIT, ('src', 'main.py', 'pyproject.toml', 'uv.lock',
                                  '.python-version', 'experiments/ablation.yaml'),
                stage / 'code_executed' / 'ablation_campaign')
    # The pilot tree minus the two post-processing modules it never imported
    # (edited after its launch).
    export_tree(PILOT_TREE, ('src', 'main.py', 'pyproject.toml', 'uv.lock',
                             '.python-version', 'experiments/congestion_pilot.yaml'),
                stage / 'code_executed' / 'congestion_pilot',
                exclude=('src/pipeline/reanalysis.py', 'src/pipeline/congestion.py'))
    prov = provenance()
    (stage / 'code_executed' / 'provenance.json').write_text(
        json.dumps(prov, indent=2) + '\n')

    # --- Configurations.
    configs = stage / 'configs'
    configs.mkdir()
    for name in ('ablation.yaml', 'congestion_pilot.yaml'):
        shutil.copy2(REPO / 'experiments' / name, configs / name)
    shutil.copy2(REPO / 'results_grid' / ABLATION_RUN / 'params.json',
                 configs / 'ablation_params.json')
    shutil.copy2(REPO / 'results_grid' / PILOT_RUN / 'params.json',
                 configs / 'congestion_pilot_params.json')

    # --- Data: raw per-case results and per-request tables.
    for kind, run, campaign in (('ablation_run', ABLATION_RUN, 'ablation_campaign'),
                                ('pilot_run', PILOT_RUN, 'congestion_pilot')):
        src_dir, dst = REPO / 'results_grid' / run, stage / 'data' / kind / run
        dst.mkdir(parents=True)
        for item in RUN_ITEMS:
            path = src_dir / item
            (shutil.copytree if path.is_dir() else shutil.copy2)(path, dst / item)
        sanitise_manifest(dst / 'manifest.json', campaign)

    # --- Scripts and README.
    shutil.copytree(TEMPLATE / 'scripts', stage / 'scripts')
    os.chmod(stage / 'scripts' / 'rebuild_all.sh', 0o755)
    shutil.copy2(TEMPLATE / 'README.md', stage / 'README.md')
    shutil.copy2(TEMPLATE / 'PROVENANCE.md', stage / 'code_executed' / 'PROVENANCE.md')

    # --- Outputs: produced by the archived code on the archived data.
    subprocess.run([str(stage / 'scripts' / 'rebuild_all.sh'), 'outputs_tmp'],
                   cwd=stage, check=True,
                   env={**os.environ, 'PYTHON': sys.executable,
                        'PYTHONDONTWRITEBYTECODE': '1'})
    (stage / 'outputs_tmp').rename(stage / 'outputs')
    for cache in list(stage.rglob('__pycache__')):
        shutil.rmtree(cache)

    # --- Anonymity scan (text files; PNG metadata only names matplotlib).
    hits = []
    for path in stage.rglob('*'):
        if path.is_file() and path.suffix != '.png':
            text = path.read_bytes().decode('utf-8', errors='ignore')
            for m in FORBIDDEN.finditer(text):
                hits.append(f'{path.relative_to(stage)}: {m.group(0)!r}')
            if FORBIDDEN.search(str(path.relative_to(stage))):
                hits.append(f'path: {path.relative_to(stage)}')
    if hits:
        print('IDENTIFYING STRINGS FOUND:\n  ' + '\n  '.join(hits[:50]))
        return 1

    # --- Checksums and archive.
    lines = []
    for path in sorted(p for p in stage.rglob('*') if p.is_file()):
        lines.append(f'{sha256(path.read_bytes())}  {path.relative_to(stage)}')
    (stage / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    archive = work / 'supplementary.tar.xz'
    with tarfile.open(archive, 'w:xz') as tar:
        tar.add(stage, arcname='supplementary',
                filter=lambda ti: _anonymous_tarinfo(ti))
    print(json.dumps({'archive': str(archive),
                      'size_mb': round(archive.stat().st_size / 1e6, 1),
                      'sha256': sha256(archive.read_bytes()),
                      'simulator_identical_across_campaigns':
                          prov['simulator_identical_across_campaigns']}, indent=2))
    return 0


def _anonymous_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """No user or group names in the archive headers."""
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    return info


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
