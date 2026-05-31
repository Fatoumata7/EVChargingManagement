# Behavior and Reputation-Aware Multi-Agent EV Charging (BRAM-EV)

**BRAM-EV (Behavior and Reputation-Aware Multi-Agent EV Charging)** is a multi-agent system for electric vehicle charging reservation management. The approach combines:

* behavior-aware user reputation,
* local station optimization,
* collective learning between charging stations,
* multi-criteria decision making for charging allocation.

The objective is to improve charging station utilization while reducing the impact of no-shows, late cancellations, and unreliable user behavior.

The project includes:

* a complete Python implementation of the BRAM-EV model;
* a simulation engine;
* visualization tools;
* experimental notebooks reproducing all results presented in the report.


## Description

This project proposes a multi-agent approach for optimizing electric vehicle (EV) charging in a distributed network of charging stations.

Vehicles send charging requests to nearby stations, which respond with optimized offers based on their capacity, profit strategy, and estimated user no-show risk derived from behavioral scoring. Each vehicle then selects the offer that maximizes its utility (distance, waiting time, cost, and energy demand).

The system includes:
- reservation management and no-show handling,
- user behavioral scoring system,
- reinforcement learning for station strategy optimization,
- intra-company cooperation between stations to share performance and improve policies.

The goal is to jointly optimize charging allocation, user satisfaction, and operator profitability.


# Repository Structure

```text
.
├── results/                  # Experimental notebooks and analysis
│   ├── Optimistic.ipynb
│   ├── Balanced.ipynb
│   └── Pessimistic.ipynb
│
├── outputs/                    # Simulation logs and exported results
│   ├── optimistic/
│   ├── balanced/
│   └── pessimistic/
│
├── src/
│   ├── agents/                 # Vehicle, station and company agents
│   ├── optimization/           # Station optimization models
│   ├── simulation/             # Simulation engine
│   ├── visualization/          # Real-time visualizer
│   ├── experiments/
│   │   ├── config.py           # Experiment configuration
│   │   └── run.py              # Main simulation entry point
│   └── ...
│
├── pyproject.toml
├── uv.lock
└── README.md
```


# Installation

The project uses **uv** for dependency management.

Install all dependencies:

```bash
uv sync
```


# Running the Experimental Notebooks

All experiments used in the report can be reproduced from the notebooks.

First install dependencies:

```bash
uv sync
```

Open and execute:

* `notebooks/Optimistic.ipynb`
* `notebooks/Balanced.ipynb`
* `notebooks/Pessimistic.ipynb`

These notebooks reproduce all simulations, figures and metrics presented in the report.


# Running a Simulation

A default simulation can be executed with:

```bash
uv sync

python -m src.experiments.run
```

Default parameters are defined in:

```text
src/experiments/config.py
```

You can modify this file to change:

* number of vehicles;
* number of stations;
* simulation duration;
* scenario parameters;
* charging station configuration;
* learning parameters;
* optimization settings;
* scenario parameters.


# Running the Visualization Tool

The project includes a visualizer allowing the evolution of the simulation to be observed in real time.

Install dependencies:

```bash
uv sync
```

Then start the visualization:

```bash
python -m src.experiments.run
```

The visualizer will display:

* vehicle movements on the 2D grid;
* charging station locations;
* charging requests;
* charging sessions;
* simulation evolution over time.


# Scenarios

Three behavioral scenarios are available:

| Scenario    | Description                                                     |
| ----------- | --------------------------------------------------------------- |
| Optimistic  | Most users honor their reservations. Low no-show rate.          |
| Balanced    | Intermediate behavior with moderate cancellations and absences. |
| Pessimistic | High rate of no-shows and late cancellations.                   |

Each vehicle is assigned behavior probabilities governing:

* reservation fulfillment;
* early cancellation;
* late cancellation;
* absence.


## Main Components

### Vehicle Agents

Vehicle agents:

* move continuously on a 2D grid;
* generate charging requests when necessary;
* evaluate charging offers according to:

  * energy satisfaction,
  * travel distance,
  * waiting time.

### Charging Stations

Charging stations:

* receive charging requests;
* solve a local optimization problem;
* balance:

  * charging infrastructure utilization,
  * cancellation risk.

### Companies

Companies:

* own charging stations;
* maintain reputation systems;
* periodically update station strategies through collective learning.


## Reproducibility

All simulations presented in the accompanying report can be reproduced using:

* the notebooks contained in `notebooks/`;
* the default simulation launcher `src.experiments.run`;
* the configuration file `src.experiments.config.py`.

Simulation logs are stored in the `outputs/` directory.


## Author

Fatoumata WADIOU
