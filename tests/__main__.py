"""
Run every test suite.

    python -m tests

Deliberately without an external test dependency: the suites are plain modules
exposing `main() -> int`.
"""

import sys

from tests import (test_ablation, test_pipeline, test_priority1,
                   test_shared_world)

SUITES = (
    ('model (priority-1 fixes)', test_priority1),
    ('shared world (grid, fleets, scenarios)', test_shared_world),
    ('pipeline (parameters, storage, CLI)', test_pipeline),
    ("ablation (components, variants, decomposition)", test_ablation),
)


def main() -> int:
    failed = 0
    for title, module in SUITES:
        print(f'\n=== {title} ===')
        failed += module.main()
    print('\n' + ('FAILED' if failed else 'All suites passed'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
