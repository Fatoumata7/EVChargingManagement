"""
pipeline — Orchestration des expériences BRAM-EV.

Séparation des responsabilités :

    params.py    paramètres d'expérience (dataclasses, validation, fichier/CLI)
    store.py     disposition et persistance des artefacts d'un run
    runner.py    exécution d'un cas et de la grille
    tables.py    extraction de tables « tidy » (simulation ou disque)
    figures.py   figures à partir des tables, sans re-simuler
    cli.py       interface en ligne de commande

Point d'entrée :

    python -m src.pipeline.cli run --scenarios pessimistic --cars 50 100
"""

from src.pipeline.params import ExperimentParams, CaseParams
from src.pipeline.store import RunStore

__all__ = ['ExperimentParams', 'CaseParams', 'RunStore']
