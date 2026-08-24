"""
run.py — Point d'entrée d'une simulation unique (avec visualisation).

Pour lancer une campagne d'expériences, utiliser le pipeline :

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
    Construit (cars, stations, societies) de façon reproductible.

    Le monde est d'abord décrit par un `WorldSpec` tiré à partir de `seed`, puis
    matérialisé sans aucun tirage supplémentaire. Deux appels avec la même graine
    et la même config renvoient donc deux mondes **identiques et indépendants** :
    c'est ce qui permet d'évaluer Greedy et BRAM-EV sur exactement le même
    environnement (positions, capacités, autonomies, préférences, comportements).

    Parameters
    ----------
    config : SimulationConfig
    seed : int | None
        Graine. Par défaut `config.SEED`, sinon `DEFAULT_SEED`.
    return_spec : bool
        Si True, renvoie aussi la spécification du monde (à enregistrer avec les
        résultats).

    Returns
    -------
    (cars, stations, societies) ou (cars, stations, societies, spec)
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
    """Matérialise un monde déjà spécifié (rejouer une expérience à l'identique)."""
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

        # FIX : les agents n'étaient construits qu'une fois pour l'affichage
        # et une seconde fois pour la simulation — le résumé décrivait donc des
        # agents qui ne tournaient pas.
        cars, stations, societies, spec = define_agents(
            config, seed=SEED, return_spec=True)
        spec.save(f'{LOG_DIR}/world_spec_{SIM_ID}.json')

        _dump_agents(cars, stations, societies, config, summary_file)

        print(f"\n=== Lancement simulation (seed={SEED}) : {config.NB_CARS} voitures, "
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
