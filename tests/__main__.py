"""
Lance toutes les suites de tests.

    python -m tests

Volontairement sans dépendance de test externe : les suites sont de simples
modules exposant `main() -> int`.
"""

import sys

from tests import (test_ablation, test_pipeline, test_priority1,
                   test_shared_world)

SUITES = (
    ('modèle (corrections priorité 1)', test_priority1),
    ('monde partagé (grille, flottes, scénarios)', test_shared_world),
    ('pipeline (paramètres, stockage, CLI)', test_pipeline),
    ("ablation (composants, variantes, décomposition)", test_ablation),
)


def main() -> int:
    failed = 0
    for title, module in SUITES:
        print(f'\n=== {title} ===')
        failed += module.main()
    print('\n' + ('ÉCHEC' if failed else 'Toutes les suites réussies'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
