# Congestion pilot — 20260928T191459Z_seeds1-2-3_congestion_pilot

Reference: `20260926T223707Z_seeds1-2-3-4+6_ablation`, same seeds (1, 2, 3), same scenarios, fleet and methods.
Chargers in the network: pilot [80], reference [194, 199, 205] (one value per seed).

Definitions of the paper: U = executed charger-slots / capacity and O_m = held charger-slots / capacity, per station, U averaged with equal station weights; I_held pools held and executed slots within each run; E_tot sums the energy delivered over the request records. Refusal rates: *no offer* and *never confirmed* are per demand; *station-level refusals* are per (station, demand) request. MILP counts are summed over the seeds.

All CSVs are at full precision; the tables below are rounded for display. With 3 seeds the Student multiplier is 4.30: the intervals are wide by construction.

## balance — pilot, per method (mean ± 95 % CI half-width)

| Indicator | Nearest Available | Multi-Station Only | Multi-Station + Reputation | BRAM-EV Full |
|---|---:|---:|---:|---:|
| E_tot — energy delivered (MWh) | 23.97 ± 1.65 | 27.66 ± 1.06 | 27.65 ± 1.60 | 27.45 ± 1.33 |
| S_del — mean energy satisfaction (%) | 34.13 ± 7.34 | 50.15 ± 5.38 | 50.62 ± 6.29 | 50.21 ± 5.47 |
| S_full — fully satisfied requests (%) | 14.83 ± 7.76 | 32.04 ± 11.17 | 32.85 ± 12.98 | 32.36 ± 12.26 |
| Requests served, even partially (%) | 59.17 ± 1.91 | 59.07 ± 0.52 | 59.41 ± 1.11 | 59.11 ± 1.02 |
| U — executed utilization (%) | 35.52 ± 3.44 | 41.20 ± 2.35 | 41.26 ± 2.80 | 40.88 ± 2.67 |
| Mean O_m — held occupancy (%) | 46.64 ± 3.84 | 54.74 ± 2.70 | 54.48 ± 3.01 | 54.44 ± 2.24 |
| Max O_m — held occupancy (%) | 98.58 ± 1.27 | 97.99 ± 0.78 | 97.70 ± 1.47 | 98.11 ± 0.85 |
| I_held — unused share of held capacity (%) | 23.85 ± 1.14 | 24.73 ± 0.89 | 24.28 ± 1.19 | 24.92 ± 1.83 |
| Demands with no offer (%) | 0.63 ± 0.13 | 0.69 ± 0.28 | 0.65 ± 0.22 | 0.63 ± 0.20 |
| Demands never confirmed (%) | 0.63 ± 0.13 | 0.69 ± 0.28 | 0.65 ± 0.22 | 0.63 ± 0.20 |
| Station-level refusals (%) | 20.52 ± 7.38 | 15.11 ± 4.75 | 14.33 ± 5.28 | 14.72 ± 7.35 |
| Searches abandoned (%) | 0.41 ± 0.27 | 0.42 ± 0.19 | 0.35 ± 0.25 | 0.45 ± 0.27 |
| Scheduled delay (min) | 80.22 ± 19.23 | 26.77 ± 19.78 | 27.37 ± 16.46 | 28.09 ± 16.47 |
| Requests (N) | 3257.3 ± 379.4 | 2520.3 ± 127.2 | 2502.3 ± 147.3 | 2505.3 ± 125.6 |
| Permanent withdrawals | 13.3 ± 10.0 | 10.7 ± 5.2 | 8.7 ± 6.3 | 11.3 ± 7.2 |
| MILP solves not proven optimal | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which feasible at time limit | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which failed (no solution) | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |

## balance — capacity effect (reference → pilot, paired Δ [95 % CI])

| Indicator | nearest_available | multistation | multistation_rep | bramev |
|---|---|---|---|---|
| E_tot — energy delivered (MWh) | 27.13 → 23.97; Δ -3.16 [-3.61, -2.71] | 28.68 → 27.66; Δ -1.03 [-1.23, -0.83] | 28.61 → 27.65; Δ -0.96 [-1.91, -0.01] | 28.65 → 27.45; Δ -1.20 [-2.05, -0.35] |
| S_del — mean energy satisfaction (%) | 48.60 → 34.13; Δ -14.47 [-15.43, -13.52] | 57.73 → 50.15; Δ -7.58 [-11.79, -3.37] | 57.70 → 50.62; Δ -7.07 [-12.35, -1.80] | 57.59 → 50.21; Δ -7.38 [-11.71, -3.05] |
| S_full — fully satisfied requests (%) | 31.43 → 14.83; Δ -16.59 [-18.58, -14.61] | 49.00 → 32.04; Δ -16.96 [-27.21, -6.71] | 48.93 → 32.85; Δ -16.08 [-27.02, -5.15] | 48.72 → 32.36; Δ -16.36 [-25.36, -7.36] |
| Requests served, even partially (%) | 59.47 → 59.17; Δ -0.29 [-1.33, +0.74] | 59.19 → 59.07; Δ -0.12 [-0.93, +0.69] | 59.06 → 59.41; Δ +0.35 [+0.08, +0.63] | 59.07 → 59.11; Δ +0.04 [-0.23, +0.30] |
| U — executed utilization (%) | 16.47 → 35.52; Δ +19.05 [+14.88, +23.22] | 17.33 → 41.20; Δ +23.87 [+20.23, +27.51] | 17.31 → 41.26; Δ +23.94 [+20.18, +27.71] | 17.36 → 40.88; Δ +23.51 [+19.68, +27.35] |
| Mean O_m — held occupancy (%) | 21.91 → 46.64; Δ +24.73 [+19.54, +29.92] | 23.13 → 54.74; Δ +31.61 [+26.79, +36.43] | 23.07 → 54.48; Δ +31.41 [+26.68, +36.15] | 23.18 → 54.44; Δ +31.26 [+27.13, +35.40] |
| Max O_m — held occupancy (%) | 95.41 → 98.58; Δ +3.16 [-1.70, +8.02] | 86.42 → 97.99; Δ +11.56 [+3.04, +20.09] | 85.20 → 97.70; Δ +12.50 [+8.19, +16.81] | 86.18 → 98.11; Δ +11.93 [+3.37, +20.50] |
| I_held — unused share of held capacity (%) | 24.74 → 23.85; Δ -0.89 [-1.79, +0.01] | 25.07 → 24.73; Δ -0.34 [-1.30, +0.63] | 25.05 → 24.28; Δ -0.77 [-1.40, -0.13] | 25.10 → 24.92; Δ -0.18 [-0.63, +0.27] |
| Demands with no offer (%) | 0.46 → 0.63; Δ +0.17 [-0.24, +0.57] | 0.60 → 0.69; Δ +0.09 [-0.27, +0.44] | 0.66 → 0.65; Δ -0.01 [-0.37, +0.35] | 0.60 → 0.63; Δ +0.02 [-0.37, +0.42] |
| Demands never confirmed (%) | 0.46 → 0.63; Δ +0.17 [-0.24, +0.57] | 0.60 → 0.69; Δ +0.09 [-0.27, +0.44] | 0.66 → 0.65; Δ -0.01 [-0.37, +0.35] | 0.60 → 0.63; Δ +0.02 [-0.37, +0.42] |
| Station-level refusals (%) | 5.60 → 20.52; Δ +14.92 [+12.64, +17.20] | 5.13 → 15.11; Δ +9.98 [+0.30, +19.66] | 6.39 → 14.33; Δ +7.94 [+4.05, +11.83] | 5.45 → 14.72; Δ +9.27 [-0.17, +18.71] |
| Scheduled delay (min) | 35.54 → 80.22; Δ +44.67 [+37.56, +51.78] | 3.81 → 26.77; Δ +22.96 [+4.10, +41.82] | 3.95 → 27.37; Δ +23.41 [+7.48, +39.35] | 3.94 → 28.09; Δ +24.15 [+8.46, +39.83] |
| Requests (N) | 2560.3 → 3257.3; Δ +697.0 [+546.3, +847.7] | 2269.3 → 2520.3; Δ +251.0 [+75.7, +426.3] | 2265.3 → 2502.3; Δ +237.0 [+26.7, +447.3] | 2271.3 → 2505.3; Δ +234.0 [+65.5, +402.5] |
| Permanent withdrawals | 7.3 → 13.3; Δ +6.0 [+3.5, +8.5] | 8.0 → 10.7; Δ +2.7 [-7.4, +12.7] | 8.3 → 8.7; Δ +0.3 [-6.8, +7.5] | 7.3 → 11.3; Δ +4.0 [-1.0, +9.0] |

## balance — components within the pilot (paired Δ [95 % CI], worlds improved, verdict)

| Indicator | Reputation (multistation → multistation_rep) | Cross-station adaptation (multistation_rep → bramev) | BRAM-EV vs Nearest Available (nearest_available → bramev) |
|---|---|---|---|
| E_tot — energy delivered (MWh) | -0.01 [-0.61, +0.59] 2/3 ns | -0.20 [-0.49, +0.09] 0/3 ns | +3.48 [+2.79, +4.16] 3/3 better |
| S_del — mean energy satisfaction (%) | +0.47 [-0.46, +1.41] 3/3 ns | -0.41 [-1.33, +0.51] 0/3 ns | +16.08 [+14.04, +18.12] 3/3 better |
| S_full — fully satisfied requests (%) | +0.81 [-1.04, +2.67] 3/3 ns | -0.49 [-1.26, +0.28] 0/3 ns | +17.52 [+12.93, +22.12] 3/3 better |
| Requests served, even partially (%) | +0.35 [-0.68, +1.37] 2/3 ns | -0.31 [-1.04, +0.42] 0/3 ns | -0.07 [-1.25, +1.12] 1/3 ns |
| U — executed utilization (%) | +0.05 [-0.69, +0.80] 2/3 ns | -0.38 [-0.56, -0.19] 0/3 worse | +5.36 [+4.30, +6.42] 3/3 better |
| Mean O_m — held occupancy (%) | -0.26 [-1.05, +0.53] 1/3 ns | -0.04 [-0.92, +0.84] 2/3 ns | +7.80 [+6.04, +9.56] 3/3 better |
| Max O_m — held occupancy (%) | -0.29 [-2.50, +1.92] 1/3 ns | +0.42 [-1.74, +2.58] 2/3 ns | -0.46 [-1.09, +0.16] 0/3 ns |
| I_held — unused share of held capacity (%) | -0.45 [-0.74, -0.16] 3/3 better | +0.64 [-0.55, +1.83] 0/3 ns | +1.07 [+0.13, +2.02] 0/3 worse |
| Demands with no offer (%) | -0.04 [-0.37, +0.29] 2/3 ns | -0.03 [-0.44, +0.38] 2/3 ns | -0.01 [-0.15, +0.13] 1/3 ns |
| Demands never confirmed (%) | -0.04 [-0.37, +0.29] 2/3 ns | -0.03 [-0.44, +0.38] 2/3 ns | -0.01 [-0.15, +0.13] 1/3 ns |
| Station-level refusals (%) | -0.78 [-8.63, +7.07] 2/3 ns | +0.39 [-7.47, +8.25] 2/3 ns | -5.79 [-9.22, -2.37] 3/3 better |
| Scheduled delay (min) | +0.59 [-3.31, +4.50] 1/3 ns | +0.72 [-0.46, +1.90] 0/3 ns | -52.13 [-54.88, -49.37] 3/3 better |
| Requests (N) | -18.0 [-63.6, +27.6] | +3.0 [-18.7, +24.7] | -752.0 [-1006.2, -497.8] |
| Permanent withdrawals | -2.0 [-13.4, +9.4] 2/3 ns | +2.7 [-7.4, +12.7] 1/3 ns | -2.0 [-6.3, +2.3] 3/3 ns |

## pessimistic — pilot, per method (mean ± 95 % CI half-width)

| Indicator | Nearest Available | Multi-Station Only | Multi-Station + Reputation | BRAM-EV Full |
|---|---:|---:|---:|---:|
| E_tot — energy delivered (MWh) | 19.99 ± 3.00 | 24.02 ± 2.41 | 23.85 ± 1.98 | 24.01 ± 2.36 |
| S_del — mean energy satisfaction (%) | 22.51 ± 5.06 | 33.51 ± 5.35 | 33.57 ± 5.05 | 33.40 ± 6.10 |
| S_full — fully satisfied requests (%) | 10.06 ± 4.80 | 21.65 ± 8.92 | 22.30 ± 9.95 | 22.09 ± 10.06 |
| Requests served, even partially (%) | 39.71 ± 2.52 | 39.72 ± 2.44 | 40.08 ± 2.11 | 39.77 ± 2.79 |
| U — executed utilization (%) | 29.09 ± 4.69 | 35.29 ± 3.93 | 35.00 ± 3.95 | 35.22 ± 4.21 |
| Mean O_m — held occupancy (%) | 45.77 ± 6.41 | 55.64 ± 5.35 | 54.95 ± 4.69 | 55.50 ± 3.55 |
| Max O_m — held occupancy (%) | 96.91 ± 0.38 | 94.80 ± 1.37 | 94.26 ± 4.07 | 95.36 ± 1.84 |
| I_held — unused share of held capacity (%) | 36.46 ± 1.33 | 36.58 ± 1.26 | 36.33 ± 1.95 | 36.57 ± 3.56 |
| Demands with no offer (%) | 0.48 ± 0.36 | 0.64 ± 0.32 | 0.49 ± 0.14 | 0.42 ± 0.32 |
| Demands never confirmed (%) | 0.48 ± 0.36 | 0.64 ± 0.32 | 0.49 ± 0.14 | 0.42 ± 0.32 |
| Station-level refusals (%) | 18.85 ± 8.78 | 15.90 ± 3.35 | 13.71 ± 4.77 | 12.38 ± 2.24 |
| Searches abandoned (%) | 0.36 ± 0.39 | 0.39 ± 0.26 | 0.36 ± 0.12 | 0.26 ± 0.12 |
| Scheduled delay (min) | 75.35 ± 14.21 | 27.47 ± 18.93 | 28.03 ± 17.60 | 28.39 ± 17.26 |
| Requests (N) | 3979.7 ± 319.2 | 3168.0 ± 165.0 | 3131.0 ± 153.4 | 3166.7 ± 222.6 |
| Permanent withdrawals | 14.3 ± 15.0 | 12.3 ± 7.6 | 11.3 ± 3.8 | 8.3 ± 3.8 |
| MILP solves not proven optimal | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which feasible at time limit | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |
|   of which failed (no solution) | 0 (sum) | 0 (sum) | 0 (sum) | 0 (sum) |

## pessimistic — capacity effect (reference → pilot, paired Δ [95 % CI])

| Indicator | nearest_available | multistation | multistation_rep | bramev |
|---|---|---|---|---|
| E_tot — energy delivered (MWh) | 23.45 → 19.99; Δ -3.46 [-4.15, -2.77] | 25.41 → 24.02; Δ -1.38 [-2.20, -0.56] | 25.36 → 23.85; Δ -1.51 [-1.81, -1.21] | 25.49 → 24.01; Δ -1.48 [-2.19, -0.77] |
| S_del — mean energy satisfaction (%) | 31.96 → 22.51; Δ -9.45 [-11.71, -7.20] | 38.72 → 33.51; Δ -5.21 [-7.85, -2.57] | 38.72 → 33.57; Δ -5.16 [-7.27, -3.04] | 38.85 → 33.40; Δ -5.45 [-8.68, -2.22] |
| S_full — fully satisfied requests (%) | 20.78 → 10.06; Δ -10.71 [-14.70, -6.73] | 32.36 → 21.65; Δ -10.71 [-15.16, -6.25] | 32.57 → 22.30; Δ -10.27 [-15.06, -5.48] | 32.82 → 22.09; Δ -10.74 [-16.36, -5.11] |
| Requests served, even partially (%) | 39.81 → 39.71; Δ -0.10 [-0.29, +0.10] | 39.94 → 39.72; Δ -0.22 [-0.65, +0.21] | 39.83 → 40.08; Δ +0.25 [-0.55, +1.06] | 39.89 → 39.77; Δ -0.12 [-0.86, +0.61] |
| U — executed utilization (%) | 13.96 → 29.09; Δ +15.13 [+10.98, +19.28] | 15.07 → 35.29; Δ +20.22 [+16.03, +24.41] | 15.01 → 35.00; Δ +19.99 [+15.86, +24.12] | 15.11 → 35.22; Δ +20.11 [+15.72, +24.50] |
| Mean O_m — held occupancy (%) | 22.09 → 45.77; Δ +23.68 [+17.06, +30.29] | 23.80 → 55.64; Δ +31.84 [+25.42, +38.26] | 23.74 → 54.95; Δ +31.21 [+25.32, +37.09] | 23.86 → 55.50; Δ +31.64 [+26.70, +36.57] |
| Max O_m — held occupancy (%) | 93.73 → 96.91; Δ +3.18 [-0.10, +6.45] | 87.24 → 94.80; Δ +7.57 [-1.69, +16.82] | 84.79 → 94.26; Δ +9.47 [+9.33, +9.60] | 84.50 → 95.36; Δ +10.86 [-2.38, +24.10] |
| I_held — unused share of held capacity (%) | 36.66 → 36.46; Δ -0.20 [-2.31, +1.90] | 36.62 → 36.58; Δ -0.04 [-1.77, +1.70] | 36.53 → 36.33; Δ -0.20 [-1.64, +1.23] | 36.54 → 36.57; Δ +0.03 [-0.35, +0.41] |
| Demands with no offer (%) | 0.55 → 0.48; Δ -0.07 [-0.49, +0.35] | 0.33 → 0.64; Δ +0.31 [+0.16, +0.45] | 0.46 → 0.49; Δ +0.03 [-0.74, +0.80] | 0.37 → 0.42; Δ +0.05 [-0.23, +0.33] |
| Demands never confirmed (%) | 0.55 → 0.48; Δ -0.07 [-0.49, +0.35] | 0.33 → 0.64; Δ +0.31 [+0.16, +0.45] | 0.46 → 0.49; Δ +0.03 [-0.74, +0.80] | 0.37 → 0.42; Δ +0.05 [-0.23, +0.33] |
| Station-level refusals (%) | 6.47 → 18.85; Δ +12.38 [+2.84, +21.93] | 1.54 → 15.90; Δ +14.36 [+10.00, +18.71] | 3.74 → 13.71; Δ +9.97 [+2.94, +16.99] | 3.16 → 12.38; Δ +9.22 [+6.30, +12.14] |
| Scheduled delay (min) | 36.57 → 75.35; Δ +38.78 [+33.86, +43.70] | 5.05 → 27.47; Δ +22.43 [+6.41, +38.44] | 4.98 → 28.03; Δ +23.05 [+8.04, +38.06] | 5.01 → 28.39; Δ +23.37 [+8.16, +38.59] |
| Requests (N) | 3244.0 → 3979.7; Δ +735.7 [+644.1, +827.2] | 2891.0 → 3168.0; Δ +277.0 [+131.4, +422.6] | 2885.7 → 3131.0; Δ +245.3 [+81.0, +409.7] | 2891.3 → 3166.7; Δ +275.3 [+63.5, +487.2] |
| Permanent withdrawals | 13.7 → 14.3; Δ +0.7 [-18.0, +19.3] | 6.0 → 12.3; Δ +6.3 [+2.5, +10.1] | 10.0 → 11.3; Δ +1.3 [-12.3, +15.0] | 8.7 → 8.3; Δ -0.3 [-4.1, +3.5] |

## pessimistic — components within the pilot (paired Δ [95 % CI], worlds improved, verdict)

| Indicator | Reputation (multistation → multistation_rep) | Cross-station adaptation (multistation_rep → bramev) | BRAM-EV vs Nearest Available (nearest_available → bramev) |
|---|---|---|---|
| E_tot — energy delivered (MWh) | -0.17 [-0.75, +0.40] 1/3 ns | +0.16 [-0.22, +0.54] 2/3 ns | +4.02 [+3.36, +4.67] 3/3 better |
| S_del — mean energy satisfaction (%) | +0.06 [-0.41, +0.52] 1/3 ns | -0.17 [-1.21, +0.88] 1/3 ns | +10.89 [+9.60, +12.17] 3/3 better |
| S_full — fully satisfied requests (%) | +0.65 [-0.69, +1.99] 3/3 ns | -0.22 [-0.51, +0.08] 0/3 ns | +12.02 [+6.73, +17.31] 3/3 better |
| Requests served, even partially (%) | +0.36 [-0.02, +0.74] 3/3 ns | -0.32 [-1.00, +0.37] 0/3 ns | +0.05 [-0.26, +0.36] 2/3 ns |
| U — executed utilization (%) | -0.29 [-0.96, +0.37] 0/3 ns | +0.22 [-0.19, +0.63] 3/3 ns | +6.13 [+5.62, +6.63] 3/3 better |
| Mean O_m — held occupancy (%) | -0.69 [-1.69, +0.31] 0/3 ns | +0.55 [-0.61, +1.71] 3/3 ns | +9.73 [+6.78, +12.68] 3/3 better |
| Max O_m — held occupancy (%) | -0.54 [-4.93, +3.84] 2/3 ns | +1.10 [-4.68, +6.88] 2/3 ns | -1.55 [-3.18, +0.08] 0/3 ns |
| I_held — unused share of held capacity (%) | -0.25 [-0.96, +0.45] 3/3 ns | +0.24 [-1.62, +2.10] 1/3 ns | +0.11 [-2.13, +2.35] 1/3 ns |
| Demands with no offer (%) | -0.15 [-0.51, +0.20] 3/3 ns | -0.07 [-0.47, +0.33] 2/3 ns | -0.06 [-0.12, +0.00] 3/3 ns |
| Demands never confirmed (%) | -0.15 [-0.51, +0.20] 3/3 ns | -0.07 [-0.47, +0.33] 2/3 ns | -0.06 [-0.12, +0.00] 3/3 ns |
| Station-level refusals (%) | -2.19 [-8.75, +4.37] 2/3 ns | -1.33 [-7.06, +4.40] 2/3 ns | -6.48 [-13.03, +0.07] 3/3 ns |
| Scheduled delay (min) | +0.55 [-1.64, +2.75] 1/3 ns | +0.36 [-0.01, +0.73] 0/3 ns | -46.96 [-50.18, -43.75] 3/3 better |
| Requests (N) | -37.0 [-50.8, -23.2] | +35.7 [-33.8, +105.1] | -813.0 [-987.9, -638.1] |
| Permanent withdrawals | -1.0 [-11.8, +9.8] 2/3 ns | -3.0 [-10.5, +4.5] 2/3 ns | -6.0 [-17.4, +5.4] 3/3 ns |
