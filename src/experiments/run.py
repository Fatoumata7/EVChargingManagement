"""
run.py — Point d'entrée de la simulation
"""

import random
import os
from dotenv import load_dotenv


import experiments.config as cfg_module
import env.station as st
import env.car as car_module
import env.society as sct
import experiments.simulation as sim_module


def define_agents(config):
    # Sociétés
    societies = [sct.Society(f_id=i, config=config)
                 for i in range(config.NB_SOCIETIES)]

    # Stations (assignées aléatoirement à une société)
    stations = []
    for i in range(config.NB_STATIONS):
        sct_idx = random.randint(0, config.NB_SOCIETIES - 1)
        new_station = st.Station(m=i, society_id=sct_idx, config=config)
        societies[sct_idx].add_station(new_station)
        stations.append(new_station)

    # Voitures
    cars = [car_module.Car(idx=i, nb_society=config.NB_SOCIETIES, config=config)
            for i in range(config.NB_CARS)]

    return cars, stations, societies


if __name__ == "__main__":

    SIM_ID = 'A'
    config = cfg_module.SimulationConfig()
    load_dotenv()

    ROOT_PATH = os.getenv("ROOT_PATH")
    OUTPUT_DIR = 'outputs'
    os.makedirs(f'{ROOT_PATH}/{OUTPUT_DIR}', exist_ok=True)

    # ---- OPEN LOG FILES

    summary_file = open(f'{ROOT_PATH}/{OUTPUT_DIR}/summary_agents_{SIM_ID}.txt', 'w', 
                        encoding='utf-8') # init file: init state of agents

    print('\n--------- AGENTS DEFINITION', file=summary_file)

    cars, stations, societies = define_agents(config)
    print(f'\n--- {config.NB_CARS} CAR ---', file=summary_file)
    for car in cars:
        print('\n', file=summary_file)
        car.display_parameters(file=summary_file)

    print(f'\n--- {config.NB_SOCIETIES} SOCIETIES ---', file=summary_file)
    count_society = 1
    for society in societies:
        print(f'\n --------------- SOCIETY {count_society}/{config.NB_SOCIETIES} ---------------', file=summary_file)
        count_society += 1
        society.display_parameters(file=summary_file)
        print('\n -------- ATTACHED STATIONS:', file=summary_file)
        for station in society.stations:
            print('\n', file=summary_file)
            station.display_parameters(file=summary_file)

    print(f"\nSimulation started with {len(cars)} cars and {len(stations)} stations.", file=summary_file)

    print("=== Initialisation des agents ===")
    cars, stations, societies = define_agents(config)

    # ----- AFFICHAGE DES AGENTS (sociétés, station et véhicules)
    for c in cars:
        c.display_parameters(file=summary_file)
    for society in societies:
        society.display_parameters(file=summary_file)
        for s in society.stations:
            s.display_parameters(file=summary_file)

    # ----- LANCEMENT SIMULATION
    print(f"\n=== Lancement simulation : {config.NB_CARS} voitures, "
          f"{config.NB_STATIONS} stations, {config.TOTAL_TIME} slots ===",
          file=summary_file)

    simulation = sim_module.Simulation(
        cars=cars,
        stations=stations,
        societies=societies,
        t_max=config.TOTAL_TIME,
        config=config
    )
    simulation.run()
