# Congestion pilot — 20260928T191459Z_seeds1-2-3_congestion_pilot

Reference: `20260926T223707Z_seeds1-2-3-4+6_ablation`, same seeds (1, 2, 3), same scenarios, fleet and methods.
Chargers in the network: pilot [80], reference [194, 199, 205] (one value per seed).

Occupancy = charger-slots still booked at their own slot / capacity; effective use = charger-slots actually spent charging / capacity; both network-wide, weighted by capacity. Refusal rates: *no offer* and *never confirmed* are per demand; *station-level refusals* are per (station, demand) request. MILP counts are summed over the seeds.

All CSVs are at full precision; the tables below are rounded for display. With 3 seeds the Student multiplier is 4.30: the intervals are wide by construction.

## balance — pilot, per method (mean ± 95 % CI half-width)

| Indicator | Nearest Available | Multi-Station Only | Multi-Station + Reputation | BRAM-EV Full |
|---|---:|---:|---:|---:|
| Energy delivered (MWh) | 23.97 ± 1.65 | 27.66 ± 1.06 | 27.65 ± 1.60 | 27.45 ± 1.33 |
| Share of need met per demand (%) | 34.13 ± 7.34 | 50.15 ± 5.38 | 50.62 ± 6.29 | 50.21 ± 5.47 |
| Demands served, even partially (%) | 59.17 ± 1.91 | 59.07 ± 0.52 | 59.41 ± 1.11 | 59.11 ± 1.02 |
| Demands fully satisfied (%) | 14.83 ± 7.76 | 32.04 ± 11.17 | 32.85 ± 12.98 | 32.36 ± 12.26 |
| Charger occupancy — held (%) | 46.64 ± 3.84 | 54.74 ± 2.70 | 54.48 ± 3.01 | 54.44 ± 2.24 |
| Charger effective use — charging (%) | 35.52 ± 3.44 | 41.20 ± 2.35 | 41.26 ± 2.80 | 40.88 ± 2.67 |
| Demands with no offer (%) | 0.63 ± 0.13 | 0.69 ± 0.28 | 0.65 ± 0.22 | 0.63 ± 0.20 |
| Demands never confirmed (%) | 0.63 ± 0.13 | 0.69 ± 0.28 | 0.65 ± 0.22 | 0.63 ± 0.20 |
| Station-level refusals (%) | 20.52 ± 7.38 | 15.11 ± 4.75 | 14.33 ± 5.28 | 14.72 ± 7.35 |
| Searches abandoned (%) | 0.41 ± 0.27 | 0.42 ± 0.19 | 0.35 ± 0.25 | 0.45 ± 0.27 |
| Mean waiting time (min) | 80.22 ± 19.23 | 26.77 ± 19.78 | 27.37 ± 16.46 | 28.09 ± 16.47 |
| Vehicles excluded (%) | 5.33 ± 4.02 | 4.27 ± 2.07 | 3.47 ± 2.50 | 4.53 ± 2.87 |
| MILP solves not proven optimal | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which feasible at time limit | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which failed (no solution) | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |

## balance — capacity effect (reference → pilot, paired Δ [95 % CI])

| Indicator | nearest_available | multistation | multistation_rep | bramev |
|---|---|---|---|---|
| Energy delivered (MWh) | 27.13 → 23.97; Δ -3.16 [-3.61, -2.71] | 28.68 → 27.66; Δ -1.03 [-1.23, -0.83] | 28.61 → 27.65; Δ -0.96 [-1.91, -0.01] | 28.65 → 27.45; Δ -1.20 [-2.05, -0.35] |
| Share of need met per demand (%) | 48.60 → 34.13; Δ -14.47 [-15.43, -13.52] | 57.73 → 50.15; Δ -7.58 [-11.79, -3.37] | 57.70 → 50.62; Δ -7.07 [-12.35, -1.80] | 57.59 → 50.21; Δ -7.38 [-11.71, -3.05] |
| Demands served, even partially (%) | 59.47 → 59.17; Δ -0.29 [-1.33, +0.74] | 59.19 → 59.07; Δ -0.12 [-0.93, +0.69] | 59.06 → 59.41; Δ +0.35 [+0.08, +0.63] | 59.07 → 59.11; Δ +0.04 [-0.23, +0.30] |
| Demands fully satisfied (%) | 31.43 → 14.83; Δ -16.59 [-18.58, -14.61] | 49.00 → 32.04; Δ -16.96 [-27.21, -6.71] | 48.93 → 32.85; Δ -16.08 [-27.02, -5.15] | 48.72 → 32.36; Δ -16.36 [-25.36, -7.36] |
| Charger occupancy — held (%) | 21.57 → 46.64; Δ +25.07 [+21.10, +29.03] | 22.94 → 54.74; Δ +31.80 [+28.34, +35.26] | 22.87 → 54.48; Δ +31.61 [+28.01, +35.21] | 22.93 → 54.44; Δ +31.52 [+28.63, +34.40] |
| Charger effective use — charging (%) | 16.24 → 35.52; Δ +19.29 [+16.17, +22.40] | 17.19 → 41.20; Δ +24.01 [+21.49, +26.54] | 17.14 → 41.26; Δ +24.11 [+21.23, +27.00] | 17.17 → 40.88; Δ +23.71 [+20.85, +26.56] |
| Demands with no offer (%) | 0.46 → 0.63; Δ +0.17 [-0.24, +0.57] | 0.60 → 0.69; Δ +0.09 [-0.27, +0.44] | 0.66 → 0.65; Δ -0.01 [-0.37, +0.35] | 0.60 → 0.63; Δ +0.02 [-0.37, +0.42] |
| Demands never confirmed (%) | 0.46 → 0.63; Δ +0.17 [-0.24, +0.57] | 0.60 → 0.69; Δ +0.09 [-0.27, +0.44] | 0.66 → 0.65; Δ -0.01 [-0.37, +0.35] | 0.60 → 0.63; Δ +0.02 [-0.37, +0.42] |
| Station-level refusals (%) | 5.60 → 20.52; Δ +14.92 [+12.64, +17.20] | 5.13 → 15.11; Δ +9.98 [+0.30, +19.66] | 6.39 → 14.33; Δ +7.94 [+4.05, +11.83] | 5.45 → 14.72; Δ +9.27 [-0.17, +18.71] |
| Mean waiting time (min) | 35.54 → 80.22; Δ +44.67 [+37.56, +51.78] | 3.81 → 26.77; Δ +22.96 [+4.10, +41.82] | 3.95 → 27.37; Δ +23.41 [+7.48, +39.35] | 3.94 → 28.09; Δ +24.15 [+8.46, +39.83] |
| Vehicles excluded (%) | 2.93 → 5.33; Δ +2.40 [+1.41, +3.39] | 3.20 → 4.27; Δ +1.07 [-2.95, +5.08] | 3.33 → 3.47; Δ +0.13 [-2.74, +3.00] | 2.93 → 4.53; Δ +1.60 [-0.39, +3.59] |

## balance — components within the pilot (paired Δ [95 % CI], worlds improved, verdict)

| Indicator | Reputation (multistation → multistation_rep) | Cross-station adaptation (multistation_rep → bramev) | BRAM-EV vs Nearest Available (nearest_available → bramev) |
|---|---|---|---|
| Energy delivered (MWh) | -0.01 [-0.61, +0.59] 2/3 ns | -0.20 [-0.49, +0.09] 0/3 ns | +3.48 [+2.79, +4.16] 3/3 better |
| Share of need met per demand (%) | +0.47 [-0.46, +1.41] 3/3 ns | -0.41 [-1.33, +0.51] 0/3 ns | +16.08 [+14.04, +18.12] 3/3 better |
| Demands served, even partially (%) | +0.35 [-0.68, +1.37] 2/3 ns | -0.31 [-1.04, +0.42] 0/3 ns | -0.07 [-1.25, +1.12] 1/3 ns |
| Demands fully satisfied (%) | +0.81 [-1.04, +2.67] 3/3 ns | -0.49 [-1.26, +0.28] 0/3 ns | +17.52 [+12.93, +22.12] 3/3 better |
| Charger occupancy — held (%) | -0.26 [-1.05, +0.53] 1/3 ns | -0.04 [-0.92, +0.84] 2/3 ns | +7.80 [+6.04, +9.56] 3/3 better |
| Charger effective use — charging (%) | +0.05 [-0.69, +0.80] 2/3 ns | -0.38 [-0.56, -0.19] 0/3 worse | +5.36 [+4.30, +6.42] 3/3 better |
| Demands with no offer (%) | -0.04 [-0.37, +0.29] 2/3 ns | -0.03 [-0.44, +0.38] 2/3 ns | -0.01 [-0.15, +0.13] 1/3 ns |
| Demands never confirmed (%) | -0.04 [-0.37, +0.29] 2/3 ns | -0.03 [-0.44, +0.38] 2/3 ns | -0.01 [-0.15, +0.13] 1/3 ns |
| Station-level refusals (%) | -0.78 [-8.63, +7.07] 2/3 ns | +0.39 [-7.47, +8.25] 2/3 ns | -5.79 [-9.22, -2.37] 3/3 better |
| Mean waiting time (min) | +0.59 [-3.31, +4.50] 1/3 ns | +0.72 [-0.46, +1.90] 0/3 ns | -52.13 [-54.88, -49.37] 3/3 better |
| Vehicles excluded (%) | -0.80 [-5.35, +3.75] 2/3 ns | +1.07 [-2.95, +5.08] 1/3 ns | -0.80 [-2.52, +0.92] 3/3 ns |

## pessimistic — pilot, per method (mean ± 95 % CI half-width)

| Indicator | Nearest Available | Multi-Station Only | Multi-Station + Reputation | BRAM-EV Full |
|---|---:|---:|---:|---:|
| Energy delivered (MWh) | 19.99 ± 3.00 | 24.02 ± 2.41 | 23.85 ± 1.98 | 24.01 ± 2.36 |
| Share of need met per demand (%) | 22.51 ± 5.06 | 33.51 ± 5.35 | 33.57 ± 5.05 | 33.40 ± 6.10 |
| Demands served, even partially (%) | 39.71 ± 2.52 | 39.72 ± 2.44 | 40.08 ± 2.11 | 39.77 ± 2.79 |
| Demands fully satisfied (%) | 10.06 ± 4.80 | 21.65 ± 8.92 | 22.30 ± 9.95 | 22.09 ± 10.06 |
| Charger occupancy — held (%) | 45.77 ± 6.41 | 55.64 ± 5.35 | 54.95 ± 4.69 | 55.50 ± 3.55 |
| Charger effective use — charging (%) | 29.09 ± 4.69 | 35.29 ± 3.93 | 35.00 ± 3.95 | 35.22 ± 4.21 |
| Demands with no offer (%) | 0.48 ± 0.36 | 0.64 ± 0.32 | 0.49 ± 0.14 | 0.42 ± 0.32 |
| Demands never confirmed (%) | 0.48 ± 0.36 | 0.64 ± 0.32 | 0.49 ± 0.14 | 0.42 ± 0.32 |
| Station-level refusals (%) | 18.85 ± 8.78 | 15.90 ± 3.35 | 13.71 ± 4.77 | 12.38 ± 2.24 |
| Searches abandoned (%) | 0.36 ± 0.39 | 0.39 ± 0.26 | 0.36 ± 0.12 | 0.26 ± 0.12 |
| Mean waiting time (min) | 75.35 ± 14.21 | 27.47 ± 18.93 | 28.03 ± 17.60 | 28.39 ± 17.26 |
| Vehicles excluded (%) | 5.73 ± 5.99 | 4.93 ± 3.04 | 4.53 ± 1.52 | 3.33 ± 1.52 |
| MILP solves not proven optimal | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which feasible at time limit | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which failed (no solution) | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |

## pessimistic — capacity effect (reference → pilot, paired Δ [95 % CI])

| Indicator | nearest_available | multistation | multistation_rep | bramev |
|---|---|---|---|---|
| Energy delivered (MWh) | 23.45 → 19.99; Δ -3.46 [-4.15, -2.77] | 25.41 → 24.02; Δ -1.38 [-2.20, -0.56] | 25.36 → 23.85; Δ -1.51 [-1.81, -1.21] | 25.49 → 24.01; Δ -1.48 [-2.19, -0.77] |
| Share of need met per demand (%) | 31.96 → 22.51; Δ -9.45 [-11.71, -7.20] | 38.72 → 33.51; Δ -5.21 [-7.85, -2.57] | 38.72 → 33.57; Δ -5.16 [-7.27, -3.04] | 38.85 → 33.40; Δ -5.45 [-8.68, -2.22] |
| Demands served, even partially (%) | 39.81 → 39.71; Δ -0.10 [-0.29, +0.10] | 39.94 → 39.72; Δ -0.22 [-0.65, +0.21] | 39.83 → 40.08; Δ +0.25 [-0.55, +1.06] | 39.89 → 39.77; Δ -0.12 [-0.86, +0.61] |
| Demands fully satisfied (%) | 20.78 → 10.06; Δ -10.71 [-14.70, -6.73] | 32.36 → 21.65; Δ -10.71 [-15.16, -6.25] | 32.57 → 22.30; Δ -10.27 [-15.06, -5.48] | 32.82 → 22.09; Δ -10.74 [-16.36, -5.11] |
| Charger occupancy — held (%) | 21.78 → 45.77; Δ +23.99 [+18.54, +29.44] | 23.66 → 55.64; Δ +31.97 [+26.70, +37.25] | 23.58 → 54.95; Δ +31.37 [+26.74, +35.99] | 23.71 → 55.50; Δ +31.79 [+28.16, +35.42] |
| Charger effective use — charging (%) | 13.80 → 29.09; Δ +15.29 [+11.90, +18.69] | 15.00 → 35.29; Δ +20.29 [+16.93, +23.65] | 14.97 → 35.00; Δ +20.03 [+16.72, +23.33] | 15.05 → 35.22; Δ +20.17 [+16.64, +23.71] |
| Demands with no offer (%) | 0.55 → 0.48; Δ -0.07 [-0.49, +0.35] | 0.33 → 0.64; Δ +0.31 [+0.16, +0.45] | 0.46 → 0.49; Δ +0.03 [-0.74, +0.80] | 0.37 → 0.42; Δ +0.05 [-0.23, +0.33] |
| Demands never confirmed (%) | 0.55 → 0.48; Δ -0.07 [-0.49, +0.35] | 0.33 → 0.64; Δ +0.31 [+0.16, +0.45] | 0.46 → 0.49; Δ +0.03 [-0.74, +0.80] | 0.37 → 0.42; Δ +0.05 [-0.23, +0.33] |
| Station-level refusals (%) | 6.47 → 18.85; Δ +12.38 [+2.84, +21.93] | 1.54 → 15.90; Δ +14.36 [+10.00, +18.71] | 3.74 → 13.71; Δ +9.97 [+2.94, +16.99] | 3.16 → 12.38; Δ +9.22 [+6.30, +12.14] |
| Mean waiting time (min) | 36.57 → 75.35; Δ +38.78 [+33.86, +43.70] | 5.05 → 27.47; Δ +22.43 [+6.41, +38.44] | 4.98 → 28.03; Δ +23.05 [+8.04, +38.06] | 5.01 → 28.39; Δ +23.37 [+8.16, +38.59] |
| Vehicles excluded (%) | 5.47 → 5.73; Δ +0.27 [-7.19, +7.72] | 2.40 → 4.93; Δ +2.53 [+1.02, +4.05] | 4.00 → 4.53; Δ +0.53 [-4.94, +6.01] | 3.47 → 3.33; Δ -0.13 [-1.65, +1.38] |

## pessimistic — components within the pilot (paired Δ [95 % CI], worlds improved, verdict)

| Indicator | Reputation (multistation → multistation_rep) | Cross-station adaptation (multistation_rep → bramev) | BRAM-EV vs Nearest Available (nearest_available → bramev) |
|---|---|---|---|
| Energy delivered (MWh) | -0.17 [-0.75, +0.40] 1/3 ns | +0.16 [-0.22, +0.54] 2/3 ns | +4.02 [+3.36, +4.67] 3/3 better |
| Share of need met per demand (%) | +0.06 [-0.41, +0.52] 1/3 ns | -0.17 [-1.21, +0.88] 1/3 ns | +10.89 [+9.60, +12.17] 3/3 better |
| Demands served, even partially (%) | +0.36 [-0.02, +0.74] 3/3 ns | -0.32 [-1.00, +0.37] 0/3 ns | +0.05 [-0.26, +0.36] 2/3 ns |
| Demands fully satisfied (%) | +0.65 [-0.69, +1.99] 3/3 ns | -0.22 [-0.51, +0.08] 0/3 ns | +12.02 [+6.73, +17.31] 3/3 better |
| Charger occupancy — held (%) | -0.69 [-1.69, +0.31] 0/3 ns | +0.55 [-0.61, +1.71] 3/3 ns | +9.73 [+6.78, +12.68] 3/3 better |
| Charger effective use — charging (%) | -0.29 [-0.96, +0.37] 0/3 ns | +0.22 [-0.19, +0.63] 3/3 ns | +6.13 [+5.62, +6.63] 3/3 better |
| Demands with no offer (%) | -0.15 [-0.51, +0.20] 3/3 ns | -0.07 [-0.47, +0.33] 2/3 ns | -0.06 [-0.12, +0.00] 3/3 ns |
| Demands never confirmed (%) | -0.15 [-0.51, +0.20] 3/3 ns | -0.07 [-0.47, +0.33] 2/3 ns | -0.06 [-0.12, +0.00] 3/3 ns |
| Station-level refusals (%) | -2.19 [-8.75, +4.37] 2/3 ns | -1.33 [-7.06, +4.40] 2/3 ns | -6.48 [-13.03, +0.07] 3/3 ns |
| Mean waiting time (min) | +0.55 [-1.64, +2.75] 1/3 ns | +0.36 [-0.01, +0.73] 0/3 ns | -46.96 [-50.18, -43.75] 3/3 better |
| Vehicles excluded (%) | -0.40 [-4.73, +3.93] 2/3 ns | -1.20 [-4.18, +1.78] 2/3 ns | -2.40 [-6.95, +2.15] 3/3 ns |
