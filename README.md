# EV Charging Optimization (Multi-Agent System)

## Description

This project proposes a multi-agent approach for optimizing electric vehicle (EV) charging in a distributed network of charging stations.

Vehicles send charging requests to nearby stations, which respond with optimized offers based on their capacity, profit strategy, and estimated user no-show risk derived from behavioral scoring. Each vehicle then selects the offer that maximizes its utility (distance, waiting time, cost, and energy demand).

The system includes:
- reservation management and no-show handling,
- user behavioral scoring system,
- reinforcement learning for station strategy optimization,
- intra-company cooperation between stations to share performance and improve policies.

The goal is to jointly optimize charging allocation, user satisfaction, and operator profitability.