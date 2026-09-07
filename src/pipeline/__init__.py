"""
pipeline — Orchestration of the BRAM-EV experiments.

Separation of concerns:

    params.py    experiment parameters (dataclasses, validation, file/CLI)
    store.py     layout and persistence of the artifacts of a run
    runner.py    execution of a case and of the grid
    tables.py    extraction of tidy tables (from a simulation or from disk)
    figures.py   figures built from the tables, without re-simulating
    cli.py       command line interface

Entry point:

    python -m src.pipeline.cli run --scenarios pessimistic --cars 50 100
"""

from src.pipeline.params import ExperimentParams, CaseParams
from src.pipeline.store import RunStore

__all__ = ['ExperimentParams', 'CaseParams', 'RunStore']
