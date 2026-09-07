"""
run.py — Entry point of a single simulation (with visualization).

To launch a campaign of experiments, use the pipeline:

    python main.py run --config experiments/full_grid.yaml
"""

import os
from dotenv import load_dotenv

import src.experiments.config as cfg_module
import src.experiments.simulation as sim_module
from src.experiments.seeding import DEFAULT_SEED
from src.experiments.world import WorldSpec, generate_world_spec, build_world


def define_agents(config, seed=None, return_spec=False):
    """
    Build (cars, stations, societies) reproducibly.

    The world is first described by a `WorldSpec` drawn from `seed`, then
    materialised without any further draw. Two calls with the same seed and the
    same config therefore return two **identical and independent** worlds: that
    is what allows Greedy and BRAM-EV to be evaluated on exactly the same
    environment (positions, capacities, autonomies, preferences, behaviours).

    Parameters
    ----------
    config : SimulationConfig
    seed : int | None
        Seed. Defaults to `config.SEED`, otherwise `DEFAULT_SEED`.
    return_spec : bool
        If True, also return the world specification (to record with the
        results).

    Returns
    -------
    (cars, stations, societies) or (cars, stations, societies, spec)
    """
    if seed is None:
        seed = config.SEED if config.SEED is not None else DEFAULT_SEED
    if config.SEED is None:
        config.set_seed(int(seed))

    spec = generate_world_spec(config, seed)
    cars, stations, societies = build_world(spec, config)

    if return_spec:
        return cars, stations, societies, spec
    return cars, stations, societies


def define_agents_from_spec(spec, config):
    """Materialise an already specified world (replay an experiment identically)."""
    if isinstance(spec, str):
        spec = WorldSpec.load(spec)
    return build_world(spec, config)


def _dump_agents(cars, stations, societies, config, file):
    print('\n--------- AGENTS DEFINITION', file=file)
    print(f'\n--- {config.NB_CARS} CAR ---', file=file)
    for car in cars:
        print('\n', file=file)
        car.display_parameters(file=file)

    print(f'\n--- {config.NB_SOCIETIES} SOCIETIES ---', file=file)
    for count, society in enumerate(societies, start=1):
        print(f'\n --------------- SOCIETY {count}/{config.NB_SOCIETIES} '
              f'---------------', file=file)
        society.display_parameters(file=file)
        print('\n -------- ATTACHED STATIONS:', file=file)
        for station in society.stations:
            print('\n', file=file)
            station.display_parameters(file=file)

    print(f"\nSimulation started with {len(cars)} cars and "
          f"{len(stations)} stations.", file=file)


if __name__ == "__main__":

    SIM_ID = 'A'
    SEED = int(os.getenv("SEED", DEFAULT_SEED))

    config = cfg_module.SimulationConfig()
    config.set_seed(SEED)
    load_dotenv()

    ROOT_PATH = os.getenv("ROOT_PATH") or '.'
    OUTPUT_DIR = 'outputs'
    os.makedirs(f'{ROOT_PATH}/{OUTPUT_DIR}', exist_ok=True)

    # ---- OPEN LOG FILES
    LOG_DIR = f'{ROOT_PATH}/{OUTPUT_DIR}/viz_run'
    os.makedirs(LOG_DIR, exist_ok=True)

    with open(f'{LOG_DIR}/summary_agents_{SIM_ID}.txt', 'w', encoding='utf-8') as summary_file, \
         open(f'{LOG_DIR}/outputs_{SIM_ID}.txt', 'w', encoding='utf-8') as outputs_file:

        # FIX: the agents used to be built once for the summary and a second
        # time for the simulation — the summary therefore described agents that
        # were not the ones running.
        cars, stations, societies, spec = define_agents(
            config, seed=SEED, return_spec=True)
        spec.save(f'{LOG_DIR}/world_spec_{SIM_ID}.json')

        _dump_agents(cars, stations, societies, config, summary_file)

        print(f"\n=== Simulation start (seed={SEED}): {config.NB_CARS} cars, "
              f"{config.NB_STATIONS} stations, {config.TOTAL_TIME} slots ===",
              file=summary_file)

        simulation = sim_module.Simulation(
            cars=cars,
            stations=stations,
            societies=societies,
            t_max=config.TOTAL_TIME,
            config=config,
            mode='bramev'
        )
        simulation.run(outputs_file)
