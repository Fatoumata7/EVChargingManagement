"""
seeding.py — Gestion centralisée de l'aléatoire.

Objectif : reproductibilité stricte des expériences et *common random numbers*
(CRN) entre les méthodes comparées.

Principe
--------
Une seule graine (`seed`) pilote toute l'expérience. Elle est déclinée en flux
indépendants via `numpy.random.SeedSequence`, un flux par (type, index) :

    hub = RngHub(seed=42)
    rng = hub.stream('car_move', car_idx)

Deux exécutions avec la même graine produisent :
  * le même monde initial (positions, capacités, préférences, comportements) ;
  * les mêmes tirages pour un véhicule donné, dans l'ordre de son propre flux.

Les flux sont séparés par usage (déplacement / comportement / requête) afin que
la divergence d'une méthode sur un usage ne décale pas les tirages des autres :
c'est ce qui permet de comparer BRAM-EV et Greedy sur le *même* aléa.

Indexation par clé, jamais par ordre
------------------------------------
Un flux est déterminé par `(kind, idx)`, pas par le rang de l'appel. C'est ce
qui permet à `world.py` de tirer la station `m` ou le véhicule `idx` sans que
le nombre d'entités déjà tirées n'influe sur le résultat : à graine égale, une
flotte de 100 véhicules commence exactement par les 50 véhicules d'une flotte
de 50.
"""

import random
import numpy as np


# Codes de flux — FIGÉS. Ne jamais réordonner ni réutiliser un code : cela
# changerait l'aléa de toutes les expériences déjà publiées.
STREAM_CODES = {
    'world':        1,   # génération monolithique du monde (hérité, cf. world.py)
    'car_move':     2,   # déplacement libre du véhicule
    'car_behavior': 3,   # tirage du comportement (pres/abs/early/late), vitesse
    'car_request':  4,   # paramètres de la requête (durée, rayon, patience)
    'station':      5,   # réservé (l'optimisation PLI est déterministe)
    'society_init': 6,   # tirage d'une société de la grille partagée
    'station_init': 7,   # tirage d'une station de la grille partagée
    'car_init':     8,   # tirage des attributs statiques d'un véhicule
    'car_lead':     9,   # horizon de planification d'une requête (l_n)
}

DEFAULT_SEED = 20260101

_UINT32 = 2 ** 32


def seed_everything(seed: int) -> int:
    """
    Fixe les générateurs globaux `random` et `numpy.random`.

    Nécessaire pour les rares appels qui ne passent pas par un flux dédié
    (dont `scipy.stats` sans `random_state`) et pour l'ordre d'itération des
    conteneurs aléatoires. Les flux de `RngHub` restent la source à privilégier.
    """
    seed = int(seed)
    random.seed(seed)
    np.random.seed(seed % _UINT32)
    return seed


class RngHub:
    """
    Fabrique de générateurs reproductibles et mutuellement indépendants.

    Parameters
    ----------
    seed : int | None
        Graine racine. `None` → `DEFAULT_SEED` (reste reproductible).
    """

    def __init__(self, seed: int | None = DEFAULT_SEED):
        if seed is None:
            seed = DEFAULT_SEED
        if not isinstance(seed, (int, np.integer)):
            raise TypeError(
                f"seed doit être un entier, reçu : {type(seed).__name__}"
            )
        self.seed = int(seed)
        seed_everything(self.seed)

    def stream(self, kind: str, idx: int = 0) -> np.random.Generator:
        """
        Retourne le générateur du flux (`kind`, `idx`).

        Deux appels identiques renvoient deux générateurs distincts mais
        produisant la même séquence : un flux est déterminé par sa clé, pas par
        l'ordre des appels.
        """
        if kind not in STREAM_CODES:
            raise KeyError(
                f"Flux inconnu : {kind!r}. Attendu parmi {sorted(STREAM_CODES)}"
            )
        seq = np.random.SeedSequence(
            entropy=self.seed,
            spawn_key=(STREAM_CODES[kind], int(idx))
        )
        return np.random.default_rng(seq)

    def __repr__(self):
        return f"RngHub(seed={self.seed})"


if __name__ == "__main__":
    hub_a = RngHub(42)
    hub_b = RngHub(42)
    # Même clé -> même séquence, quel que soit l'ordre des appels
    assert hub_a.stream('car_move', 7).random() == hub_b.stream('car_move', 7).random()
    # Clés différentes -> séquences décorrélées
    assert hub_a.stream('car_move', 7).random() != hub_a.stream('car_move', 8).random()
    print("seeding.py OK")
