# BRAM-EV against the baselines — paired gaps, percentage points

| Scenario | Fleet | Comparison | Indicator | Mean Δ (pp) | 95% CI (pp) | p | Improved | Verdict |
|---|---|---|---|---|---|---|---|---|
| balance | 50 | Load-Aware (load_aware → bramev) | Demands served (even partially) | -0.01 | [-0.31, +0.30] | 0.97 | 7/10 | ns |
| balance | 50 | Load-Aware (load_aware → bramev) | Demands fully satisfied | +0.34 | [-0.11, +0.79] | 0.12 | 8/10 | ns |
| balance | 50 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.05 | [-0.42, +0.31] | 0.741 | 5/10 | ns |
| balance | 50 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.08 | [-0.41, +0.25] | 0.597 | 3/10 | ns |
| balance | 50 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | +0.06 | [-0.08, +0.19] | 0.39 | 5/10 | ns |
| balance | 50 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | +0.32 | [-0.07, +0.71] | 0.0928 | 7/10 | ns |
| balance | 50 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.06 | [-0.29, +0.17] | 0.542 | 5/10 | ns |
| balance | 50 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.21 | [-0.46, +0.05] | 0.0981 | 2/10 | ns |
| balance | 50 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | +0.07 | [-0.05, +0.18] | 0.218 | 5/10 | ns |
| balance | 50 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +0.34 | [+0.05, +0.62] | 0.0257 | 7/10 | better |
| balance | 50 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +0.21 | [+0.09, +0.34] | 0.00374 | 9/10 | better |
| balance | 50 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +0.25 | [+0.07, +0.43] | 0.0106 | 10/10 | better |
| balance | 50 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.12 | [-0.41, +0.16] | 0.358 | 4/10 | ns |
| balance | 50 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.31 | [-0.22, +0.85] | 0.22 | 6/10 | ns |
| balance | 50 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | -0.11 | [-0.45, +0.23] | 0.482 | 5/10 | ns |
| balance | 50 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +0.02 | [-0.34, +0.38] | 0.901 | 5/10 | ns |
| balance | 150 | Load-Aware (load_aware → bramev) | Demands served (even partially) | -0.16 | [-0.41, +0.08] | 0.159 | 2/10 | ns |
| balance | 150 | Load-Aware (load_aware → bramev) | Demands fully satisfied | -1.09 | [-1.58, -0.61] | 0.000647 | 1/10 | worse |
| balance | 150 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.34 | [-0.63, -0.05] | 0.0253 | 1/10 | worse |
| balance | 150 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.30 | [-0.73, +0.13] | 0.147 | 3/10 | ns |
| balance | 150 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | -0.13 | [-0.19, -0.06] | 0.00132 | 1/10 | worse |
| balance | 150 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -0.89 | [-1.19, -0.59] | 8.51e-05 | 0/10 | worse |
| balance | 150 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.37 | [-0.52, -0.21] | 0.000461 | 0/10 | worse |
| balance | 150 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.41 | [-0.70, -0.11] | 0.0128 | 0/10 | worse |
| balance | 150 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | -0.20 | [-0.36, -0.03] | 0.0248 | 3/10 | worse |
| balance | 150 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +7.28 | [+5.63, +8.93] | 3.61e-06 | 10/10 | better |
| balance | 150 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +2.80 | [+1.92, +3.68] | 5.17e-05 | 10/10 | better |
| balance | 150 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +5.09 | [+3.69, +6.48] | 1.72e-05 | 10/10 | better |
| balance | 150 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.10 | [-0.28, +0.08] | 0.243 | 3/10 | ns |
| balance | 150 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.01 | [-0.35, +0.36] | 0.97 | 4/10 | ns |
| balance | 150 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | +0.02 | [-0.10, +0.14] | 0.69 | 5/10 | ns |
| balance | 150 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +0.21 | [-0.14, +0.55] | 0.205 | 6/10 | ns |
| balance | 250 | Load-Aware (load_aware → bramev) | Demands served (even partially) | -0.03 | [-0.20, +0.13] | 0.664 | 5/10 | ns |
| balance | 250 | Load-Aware (load_aware → bramev) | Demands fully satisfied | -3.19 | [-3.94, -2.44] | 4.94e-06 | 0/10 | worse |
| balance | 250 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.66 | [-0.86, -0.45] | 5.01e-05 | 1/10 | worse |
| balance | 250 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -1.06 | [-1.39, -0.73] | 4.36e-05 | 0/10 | worse |
| balance | 250 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | -0.05 | [-0.20, +0.10] | 0.484 | 4/10 | ns |
| balance | 250 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -2.61 | [-3.22, -2.01] | 4.32e-06 | 0/10 | worse |
| balance | 250 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.63 | [-0.80, -0.46] | 1.67e-05 | 0/10 | worse |
| balance | 250 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.99 | [-1.34, -0.63] | 0.000141 | 0/10 | worse |
| balance | 250 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | -0.08 | [-0.39, +0.22] | 0.548 | 4/10 | ns |
| balance | 250 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +16.23 | [+14.40, +18.05] | 8.6e-09 | 10/10 | better |
| balance | 250 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +8.81 | [+7.27, +10.34] | 3.87e-07 | 10/10 | better |
| balance | 250 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +15.08 | [+12.59, +17.57] | 2.49e-07 | 10/10 | better |
| balance | 250 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.01 | [-0.30, +0.28] | 0.918 | 3/10 | ns |
| balance | 250 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.72 | [-0.09, +1.53] | 0.0741 | 7/10 | ns |
| balance | 250 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | +0.83 | [+0.32, +1.33] | 0.0048 | 10/10 | better |
| balance | 250 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +1.44 | [+0.96, +1.93] | 8.7e-05 | 10/10 | better |
| optimistic | 50 | Load-Aware (load_aware → bramev) | Demands served (even partially) | -0.13 | [-0.45, +0.20] | 0.396 | 4/10 | ns |
| optimistic | 50 | Load-Aware (load_aware → bramev) | Demands fully satisfied | +0.16 | [-0.33, +0.64] | 0.49 | 6/10 | ns |
| optimistic | 50 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.15 | [-0.39, +0.10] | 0.207 | 4/10 | ns |
| optimistic | 50 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.03 | [-0.36, +0.30] | 0.86 | 6/10 | ns |
| optimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | -0.10 | [-0.29, +0.09] | 0.28 | 4/10 | ns |
| optimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | +0.20 | [-0.33, +0.72] | 0.418 | 8/10 | ns |
| optimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.12 | [-0.27, +0.04] | 0.119 | 2/10 | ns |
| optimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.03 | [-0.23, +0.17] | 0.738 | 5/10 | ns |
| optimistic | 50 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | -0.02 | [-0.15, +0.10] | 0.656 | 3/10 | ns |
| optimistic | 50 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +0.05 | [-0.33, +0.42] | 0.779 | 4/10 | ns |
| optimistic | 50 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +0.03 | [-0.16, +0.22] | 0.718 | 4/10 | ns |
| optimistic | 50 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +0.08 | [-0.08, +0.23] | 0.287 | 5/10 | ns |
| optimistic | 50 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.12 | [-0.38, +0.14] | 0.321 | 4/10 | ns |
| optimistic | 50 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.54 | [-0.20, +1.28] | 0.136 | 5/10 | ns |
| optimistic | 50 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | -0.06 | [-0.32, +0.21] | 0.644 | 4/10 | ns |
| optimistic | 50 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +0.09 | [-0.18, +0.35] | 0.47 | 5/10 | ns |
| optimistic | 150 | Load-Aware (load_aware → bramev) | Demands served (even partially) | +0.02 | [-0.18, +0.23] | 0.804 | 5/10 | ns |
| optimistic | 150 | Load-Aware (load_aware → bramev) | Demands fully satisfied | -0.43 | [-1.38, +0.52] | 0.329 | 5/10 | ns |
| optimistic | 150 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.12 | [-0.44, +0.19] | 0.399 | 5/10 | ns |
| optimistic | 150 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.20 | [-0.49, +0.09] | 0.148 | 3/10 | ns |
| optimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | +0.00 | [-0.17, +0.18] | 0.95 | 6/10 | ns |
| optimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -0.24 | [-0.87, +0.39] | 0.411 | 5/10 | ns |
| optimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.12 | [-0.43, +0.20] | 0.419 | 5/10 | ns |
| optimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.17 | [-0.45, +0.12] | 0.215 | 4/10 | ns |
| optimistic | 150 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | -0.06 | [-0.35, +0.23] | 0.65 | 5/10 | ns |
| optimistic | 150 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +6.96 | [+5.01, +8.92] | 2.11e-05 | 10/10 | better |
| optimistic | 150 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +2.64 | [+1.58, +3.71] | 0.000329 | 10/10 | better |
| optimistic | 150 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +3.68 | [+2.46, +4.90] | 7.68e-05 | 10/10 | better |
| optimistic | 150 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | +0.01 | [-0.18, +0.21] | 0.885 | 5/10 | ns |
| optimistic | 150 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.56 | [+0.11, +1.01] | 0.0212 | 9/10 | better |
| optimistic | 150 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | +0.32 | [+0.06, +0.57] | 0.022 | 7/10 | better |
| optimistic | 150 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +0.41 | [+0.03, +0.79] | 0.0364 | 9/10 | better |
| optimistic | 250 | Load-Aware (load_aware → bramev) | Demands served (even partially) | +0.02 | [-0.06, +0.11] | 0.562 | 6/10 | ns |
| optimistic | 250 | Load-Aware (load_aware → bramev) | Demands fully satisfied | -2.79 | [-3.52, -2.05] | 1.28e-05 | 0/10 | worse |
| optimistic | 250 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.68 | [-0.96, -0.40] | 0.000379 | 0/10 | worse |
| optimistic | 250 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.95 | [-1.39, -0.52] | 0.000746 | 0/10 | worse |
| optimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | +0.02 | [-0.08, +0.11] | 0.702 | 6/10 | ns |
| optimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -2.07 | [-2.82, -1.33] | 0.000147 | 1/10 | worse |
| optimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.49 | [-0.68, -0.30] | 0.000226 | 0/10 | worse |
| optimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.69 | [-0.98, -0.41] | 0.000373 | 0/10 | worse |
| optimistic | 250 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | +0.03 | [-0.12, +0.19] | 0.648 | 6/10 | ns |
| optimistic | 250 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +19.12 | [+16.66, +21.58] | 2.81e-08 | 10/10 | better |
| optimistic | 250 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +9.57 | [+7.87, +11.28] | 4.81e-07 | 10/10 | better |
| optimistic | 250 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +12.98 | [+10.64, +15.32] | 5.26e-07 | 10/10 | better |
| optimistic | 250 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | +0.03 | [-0.12, +0.18] | 0.671 | 6/10 | ns |
| optimistic | 250 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +1.53 | [+0.63, +2.44] | 0.00407 | 9/10 | better |
| optimistic | 250 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | +1.03 | [+0.56, +1.51] | 0.000813 | 10/10 | better |
| optimistic | 250 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +1.37 | [+0.80, +1.93] | 0.000385 | 10/10 | better |
| pessimistic | 50 | Load-Aware (load_aware → bramev) | Demands served (even partially) | +0.01 | [-0.35, +0.36] | 0.962 | 5/10 | ns |
| pessimistic | 50 | Load-Aware (load_aware → bramev) | Demands fully satisfied | +0.06 | [-0.50, +0.62] | 0.822 | 5/10 | ns |
| pessimistic | 50 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.12 | [-0.44, +0.19] | 0.393 | 3/10 | ns |
| pessimistic | 50 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.33 | [-0.80, +0.13] | 0.141 | 4/10 | ns |
| pessimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | -0.06 | [-0.23, +0.10] | 0.413 | 3/10 | ns |
| pessimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -0.01 | [-0.38, +0.35] | 0.938 | 5/10 | ns |
| pessimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.08 | [-0.24, +0.08] | 0.277 | 3/10 | ns |
| pessimistic | 50 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.05 | [-0.28, +0.18] | 0.637 | 6/10 | ns |
| pessimistic | 50 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | +0.01 | [-0.15, +0.17] | 0.878 | 4/10 | ns |
| pessimistic | 50 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +0.17 | [-0.11, +0.44] | 0.211 | 6/10 | ns |
| pessimistic | 50 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +0.04 | [-0.07, +0.15] | 0.467 | 5/10 | ns |
| pessimistic | 50 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +0.06 | [-0.34, +0.47] | 0.726 | 6/10 | ns |
| pessimistic | 50 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.08 | [-0.28, +0.13] | 0.419 | 5/10 | ns |
| pessimistic | 50 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.23 | [-0.33, +0.80] | 0.374 | 6/10 | ns |
| pessimistic | 50 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | -0.14 | [-0.33, +0.05] | 0.132 | 3/10 | ns |
| pessimistic | 50 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | -0.16 | [-0.64, +0.32] | 0.469 | 4/10 | ns |
| pessimistic | 150 | Load-Aware (load_aware → bramev) | Demands served (even partially) | -0.01 | [-0.11, +0.08] | 0.767 | 4/10 | ns |
| pessimistic | 150 | Load-Aware (load_aware → bramev) | Demands fully satisfied | -0.55 | [-1.07, -0.04] | 0.0384 | 1/10 | worse |
| pessimistic | 150 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.22 | [-0.46, +0.02] | 0.0648 | 2/10 | ns |
| pessimistic | 150 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -0.54 | [-1.16, +0.08] | 0.0811 | 3/10 | ns |
| pessimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | -0.00 | [-0.10, +0.09] | 0.923 | 7/10 | ns |
| pessimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -0.57 | [-1.01, -0.13] | 0.0164 | 2/10 | worse |
| pessimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.16 | [-0.40, +0.07] | 0.154 | 3/10 | ns |
| pessimistic | 150 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.41 | [-0.85, +0.02] | 0.0611 | 2/10 | ns |
| pessimistic | 150 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | +0.06 | [-0.22, +0.34] | 0.627 | 5/10 | ns |
| pessimistic | 150 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +5.32 | [+3.72, +6.93] | 3.71e-05 | 10/10 | better |
| pessimistic | 150 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +2.38 | [+1.52, +3.24] | 0.000143 | 10/10 | better |
| pessimistic | 150 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +5.90 | [+4.27, +7.52] | 1.79e-05 | 10/10 | better |
| pessimistic | 150 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.09 | [-0.24, +0.06] | 0.202 | 2/10 | ns |
| pessimistic | 150 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.42 | [-0.04, +0.87] | 0.0674 | 7/10 | ns |
| pessimistic | 150 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | +0.10 | [-0.02, +0.23] | 0.0869 | 9/10 | ns |
| pessimistic | 150 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +0.48 | [+0.18, +0.78] | 0.00546 | 9/10 | better |
| pessimistic | 250 | Load-Aware (load_aware → bramev) | Demands served (even partially) | -0.08 | [-0.27, +0.11] | 0.345 | 5/10 | ns |
| pessimistic | 250 | Load-Aware (load_aware → bramev) | Demands fully satisfied | -2.15 | [-2.71, -1.59] | 1.12e-05 | 0/10 | worse |
| pessimistic | 250 | Load-Aware (load_aware → bramev) | Share of energy need met (all demands) | -0.60 | [-0.86, -0.34] | 0.000583 | 0/10 | worse |
| pessimistic | 250 | Load-Aware (load_aware → bramev) | Share of energy need met (served demands) | -1.34 | [-1.74, -0.93] | 3.89e-05 | 0/10 | worse |
| pessimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Demands served (even partially) | +0.02 | [-0.13, +0.17] | 0.805 | 6/10 | ns |
| pessimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Demands fully satisfied | -1.61 | [-2.18, -1.04] | 0.000129 | 0/10 | worse |
| pessimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (all demands) | -0.33 | [-0.49, -0.17] | 0.0012 | 0/10 | worse |
| pessimistic | 250 | Minimum Waiting Time (min_waiting → bramev) | Share of energy need met (served demands) | -0.88 | [-1.22, -0.55] | 0.000214 | 1/10 | worse |
| pessimistic | 250 | Nearest Available (nearest_available → bramev) | Demands served (even partially) | -0.13 | [-0.42, +0.16] | 0.332 | 3/10 | ns |
| pessimistic | 250 | Nearest Available (nearest_available → bramev) | Demands fully satisfied | +10.60 | [+9.36, +11.84] | 1.24e-08 | 10/10 | better |
| pessimistic | 250 | Nearest Available (nearest_available → bramev) | Share of energy need met (all demands) | +5.96 | [+4.79, +7.13] | 1.06e-06 | 10/10 | better |
| pessimistic | 250 | Nearest Available (nearest_available → bramev) | Share of energy need met (served demands) | +15.48 | [+12.92, +18.04] | 2.5e-07 | 10/10 | better |
| pessimistic | 250 | Random Feasible (random_feasible → bramev) | Demands served (even partially) | -0.13 | [-0.25, -0.02] | 0.0265 | 1/10 | worse |
| pessimistic | 250 | Random Feasible (random_feasible → bramev) | Demands fully satisfied | +0.94 | [+0.24, +1.64] | 0.0144 | 8/10 | better |
| pessimistic | 250 | Random Feasible (random_feasible → bramev) | Share of energy need met (all demands) | +0.57 | [+0.30, +0.84] | 0.000962 | 10/10 | better |
| pessimistic | 250 | Random Feasible (random_feasible → bramev) | Share of energy need met (served demands) | +1.79 | [+1.02, +2.56] | 0.000523 | 10/10 | better |
