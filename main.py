"""
Entry point of the BRAM-EV pipeline.

    python main.py run --scenarios pessimistic --cars 50 100 --seed 42
    python main.py report --latest
    python main.py --help

Equivalent to `python -m src.pipeline.cli`.
"""

import sys

from src.pipeline.cli import main

if __name__ == '__main__':
    sys.exit(main())
