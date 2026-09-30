"""
Compare the rebuilt outputs with the shipped ones, and check that the two
campaigns use the same indicator definitions.

    python scripts/compare_outputs.py outputs rebuilt

CSV files must have the same header and the same rows; numeric cells may
differ by at most 1e-12 (relative) — in practice they are identical. Markdown
tables must be identical. Figures are only checked for presence: their pixels
depend on the fonts and the FreeType build of the machine.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

REL_TOL = 1e-12


def _num(text: str):
    try:
        return float(text)
    except ValueError:
        return None


def _same_cell(a: str, b: str) -> bool:
    if a == b:
        return True
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return False
    if math.isnan(x) and math.isnan(y):
        return True
    return math.isclose(x, y, rel_tol=REL_TOL, abs_tol=1e-15)


def compare_csv(shipped: Path, rebuilt: Path) -> list[str]:
    with shipped.open(newline='') as fa, rebuilt.open(newline='') as fb:
        ra, rb = list(csv.reader(fa)), list(csv.reader(fb))
    if not ra or not rb or ra[0] != rb[0]:
        return [f'{shipped.name}: header differs']
    if len(ra) != len(rb):
        return [f'{shipped.name}: {len(ra) - 1} rows shipped, {len(rb) - 1} rebuilt']
    errors = []
    for i, (x, y) in enumerate(zip(ra[1:], rb[1:]), start=2):
        for col, a, b in zip(ra[0], x, y):
            if not _same_cell(a, b):
                errors.append(f'{shipped.name}:{i} {col}: {a!r} != {b!r}')
    return errors[:20]


def compare_tree(shipped: Path, rebuilt: Path) -> tuple[int, list[str]]:
    errors, checked = [], 0
    for path in sorted(shipped.rglob('*')):
        if path.is_dir():
            continue
        other = rebuilt / path.relative_to(shipped)
        rel = path.relative_to(shipped.parent)
        if not other.is_file():
            errors.append(f'{rel}: missing from the rebuild')
            continue
        checked += 1
        if path.suffix == '.csv':
            errors += [f'{rel.parent}/{e}' for e in compare_csv(path, other)]
        elif path.suffix == '.md':
            if path.read_text() != other.read_text():
                errors.append(f'{rel}: text differs')
        elif path.name == 'manifest.json':
            a, b = json.loads(path.read_text()), json.loads(other.read_text())
            a.pop('created_utc', None), b.pop('created_utc', None)
            if a != b:
                errors.append(f'{rel}: content differs')
    return checked, errors


def check_definitions(root: Path) -> list[str]:
    """Pilot and main campaign: same columns, same rows for the shared cases."""
    def load(path):
        with path.open(newline='') as fh:
            rows = list(csv.DictReader(fh))
        return (list(rows[0].keys()) if rows else []), rows

    main_cols, main_rows = load(root / 'ablation_modified' / 'summary.csv')
    pilot_cols, _ = load(root / 'congestion_pilot' / 'summary.csv')
    ref_cols, ref_rows = load(root / 'congestion_pilot' / 'reference_summary.csv')
    errors = []
    if pilot_cols != main_cols:
        errors.append('pilot summary.csv columns differ from ablation_modified')
    if ref_cols != main_cols:
        errors.append('pilot reference_summary.csv columns differ from ablation_modified')
    if len(set(main_cols)) != len(main_cols):
        errors.append('duplicate columns in ablation_modified/summary.csv')
    key = lambda r: (r['scenario'], r['nb_cars'], r['method'], r['world_seed'])
    by_key = {key(r): r for r in main_rows}
    for r in ref_rows:
        if by_key.get(key(r)) != r:
            errors.append(f'reference row {key(r)} differs from ablation_modified')
    for col in ('served_rate', 'fully_satisfied_rate', 'service_ratio_mean',
                'nb_ilp_not_optimal', 'nb_ilp_feasible_time_limit', 'nb_ilp_failed'):
        if col not in main_cols:
            errors.append(f'missing column {col}')
    return errors


def main(shipped: str, rebuilt: str) -> int:
    shipped_root, rebuilt_root = Path(shipped), Path(rebuilt)
    total, errors = 0, []
    for sub in ('ablation_modified', 'congestion_pilot'):
        n, e = compare_tree(shipped_root / sub, rebuilt_root / sub)
        total += n
        errors += e
    errors += check_definitions(rebuilt_root)
    print(f'{total} files compared')
    if errors:
        print(f'{len(errors)} difference(s):')
        for e in errors:
            print('  ' + e)
        return 1
    print('OK: every shipped table is reproduced, and both campaigns use the '
          'same indicator definitions.')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
