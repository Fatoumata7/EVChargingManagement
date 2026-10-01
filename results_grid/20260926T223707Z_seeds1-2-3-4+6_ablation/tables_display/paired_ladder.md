# Ablation ladder — paired gaps, percentage points

| Scenario | Fleet | Comparison | Indicator | Mean Δ (pp) | 95% CI (pp) | p | Improved | Verdict |
|---|---|---|---|---|---|---|---|---|
| balance | 50 | Multi-station search (greedy → multistation) | Demands served (even partially) | -0.08 | [-0.21, +0.04] | 0.171 | 3/10 | ns |
| balance | 50 | Multi-station search (greedy → multistation) | Demands fully satisfied | +0.31 | [-0.10, +0.72] | 0.121 | 7/10 | ns |
| balance | 50 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +0.04 | [-0.13, +0.22] | 0.583 | 6/10 | ns |
| balance | 50 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +0.22 | [-0.06, +0.50] | 0.114 | 7/10 | ns |
| balance | 50 | Reputation (multistation → multistation_rep) | Demands served (even partially) | +0.15 | [+0.03, +0.27] | 0.0221 | 7/10 | better |
| balance | 50 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.03 | [-0.18, +0.24] | 0.746 | 6/10 | ns |
| balance | 50 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.11 | [-0.03, +0.24] | 0.109 | 6/10 | ns |
| balance | 50 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | -0.07 | [-0.21, +0.08] | 0.321 | 4/10 | ns |
| balance | 50 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.02 | [-0.14, +0.10] | 0.712 | 3/10 | ns |
| balance | 50 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | +0.00 | [-0.20, +0.21] | 0.961 | 4/10 | ns |
| balance | 50 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.00 | [-0.19, +0.19] | 0.987 | 5/10 | ns |
| balance | 50 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | +0.03 | [-0.19, +0.25] | 0.765 | 5/10 | ns |
| balance | 150 | Multi-station search (greedy → multistation) | Demands served (even partially) | +0.14 | [-0.14, +0.42] | 0.301 | 6/10 | ns |
| balance | 150 | Multi-station search (greedy → multistation) | Demands fully satisfied | +6.90 | [+5.25, +8.56] | 5.83e-06 | 10/10 | better |
| balance | 150 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +3.11 | [+2.32, +3.90] | 9.25e-06 | 10/10 | better |
| balance | 150 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +5.09 | [+3.78, +6.40] | 1.04e-05 | 10/10 | better |
| balance | 150 | Reputation (multistation → multistation_rep) | Demands served (even partially) | +0.05 | [-0.11, +0.20] | 0.52 | 7/10 | ns |
| balance | 150 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.18 | [-0.43, +0.78] | 0.525 | 6/10 | ns |
| balance | 150 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.04 | [-0.14, +0.22] | 0.653 | 7/10 | ns |
| balance | 150 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | -0.01 | [-0.19, +0.16] | 0.864 | 4/10 | ns |
| balance | 150 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.01 | [-0.13, +0.11] | 0.823 | 4/10 | ns |
| balance | 150 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | -0.12 | [-0.62, +0.39] | 0.616 | 4/10 | ns |
| balance | 150 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.08 | [-0.24, +0.08] | 0.277 | 4/10 | ns |
| balance | 150 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | -0.12 | [-0.33, +0.10] | 0.256 | 5/10 | ns |
| balance | 250 | Multi-station search (greedy → multistation) | Demands served (even partially) | +1.21 | [+0.66, +1.76] | 0.000791 | 9/10 | better |
| balance | 250 | Multi-station search (greedy → multistation) | Demands fully satisfied | +15.00 | [+12.64, +17.37] | 1.64e-07 | 10/10 | better |
| balance | 250 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +8.68 | [+6.93, +10.44] | 1.37e-06 | 10/10 | better |
| balance | 250 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +13.05 | [+10.34, +15.77] | 1.77e-06 | 10/10 | better |
| balance | 250 | Reputation (multistation → multistation_rep) | Demands served (even partially) | -0.07 | [-0.21, +0.07] | 0.274 | 3/10 | ns |
| balance | 250 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.14 | [-0.23, +0.51] | 0.411 | 7/10 | ns |
| balance | 250 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.01 | [-0.15, +0.18] | 0.875 | 5/10 | ns |
| balance | 250 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | +0.14 | [-0.14, +0.42] | 0.295 | 8/10 | ns |
| balance | 250 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | +0.03 | [-0.11, +0.17] | 0.596 | 5/10 | ns |
| balance | 250 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | -0.32 | [-0.73, +0.10] | 0.119 | 4/10 | ns |
| balance | 250 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.08 | [-0.21, +0.05] | 0.183 | 3/10 | ns |
| balance | 250 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | -0.19 | [-0.40, +0.01] | 0.0618 | 3/10 | ns |
| optimistic | 50 | Multi-station search (greedy → multistation) | Demands served (even partially) | -0.08 | [-0.15, -0.00] | 0.0437 | 0/10 | worse |
| optimistic | 50 | Multi-station search (greedy → multistation) | Demands fully satisfied | -0.06 | [-0.32, +0.19] | 0.588 | 4/10 | ns |
| optimistic | 50 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | -0.02 | [-0.11, +0.06] | 0.572 | 3/10 | ns |
| optimistic | 50 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +0.07 | [-0.06, +0.20] | 0.23 | 4/10 | ns |
| optimistic | 50 | Reputation (multistation → multistation_rep) | Demands served (even partially) | +0.01 | [-0.04, +0.06] | 0.604 | 1/10 | ns |
| optimistic | 50 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.05 | [-0.25, +0.34] | 0.736 | 3/10 | ns |
| optimistic | 50 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.04 | [-0.03, +0.10] | 0.222 | 4/10 | ns |
| optimistic | 50 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | +0.04 | [-0.05, +0.13] | 0.38 | 3/10 | ns |
| optimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.01 | [-0.06, +0.04] | 0.604 | 1/10 | ns |
| optimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | -0.06 | [-0.20, +0.07] | 0.309 | 1/10 | ns |
| optimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.03 | [-0.07, +0.01] | 0.121 | 3/10 | ns |
| optimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | -0.03 | [-0.11, +0.05] | 0.474 | 4/10 | ns |
| optimistic | 150 | Multi-station search (greedy → multistation) | Demands served (even partially) | +0.10 | [-0.14, +0.34] | 0.382 | 6/10 | ns |
| optimistic | 150 | Multi-station search (greedy → multistation) | Demands fully satisfied | +6.71 | [+4.73, +8.69] | 3.06e-05 | 10/10 | better |
| optimistic | 150 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +2.82 | [+1.64, +3.99] | 0.000412 | 10/10 | better |
| optimistic | 150 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +3.72 | [+2.32, +5.11] | 0.000196 | 10/10 | better |
| optimistic | 150 | Reputation (multistation → multistation_rep) | Demands served (even partially) | -0.03 | [-0.13, +0.08] | 0.559 | 3/10 | ns |
| optimistic | 150 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.06 | [-0.31, +0.43] | 0.728 | 6/10 | ns |
| optimistic | 150 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.02 | [-0.09, +0.13] | 0.678 | 6/10 | ns |
| optimistic | 150 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | +0.07 | [-0.12, +0.25] | 0.431 | 6/10 | ns |
| optimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | +0.06 | [-0.03, +0.14] | 0.162 | 5/10 | ns |
| optimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | -0.06 | [-0.39, +0.28] | 0.72 | 5/10 | ns |
| optimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | +0.01 | [-0.03, +0.05] | 0.661 | 7/10 | ns |
| optimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | -0.06 | [-0.20, +0.07] | 0.322 | 5/10 | ns |
| optimistic | 250 | Multi-station search (greedy → multistation) | Demands served (even partially) | +1.10 | [+0.49, +1.70] | 0.00268 | 10/10 | better |
| optimistic | 250 | Multi-station search (greedy → multistation) | Demands fully satisfied | +18.08 | [+15.31, +20.85] | 1.28e-07 | 10/10 | better |
| optimistic | 250 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +9.56 | [+7.66, +11.45] | 1.18e-06 | 10/10 | better |
| optimistic | 250 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +11.75 | [+9.61, +13.90] | 5.84e-07 | 10/10 | better |
| optimistic | 250 | Reputation (multistation → multistation_rep) | Demands served (even partially) | +0.05 | [-0.08, +0.18] | 0.414 | 5/10 | ns |
| optimistic | 250 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.22 | [-0.23, +0.68] | 0.295 | 6/10 | ns |
| optimistic | 250 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.12 | [-0.17, +0.41] | 0.385 | 7/10 | ns |
| optimistic | 250 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | +0.10 | [-0.23, +0.42] | 0.509 | 6/10 | ns |
| optimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.08 | [-0.20, +0.04] | 0.175 | 3/10 | ns |
| optimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | -0.01 | [-0.51, +0.49] | 0.956 | 5/10 | ns |
| optimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.05 | [-0.24, +0.13] | 0.539 | 2/10 | ns |
| optimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | +0.03 | [-0.18, +0.24] | 0.757 | 6/10 | ns |
| pessimistic | 50 | Multi-station search (greedy → multistation) | Demands served (even partially) | +0.09 | [-0.20, +0.38] | 0.514 | 6/10 | ns |
| pessimistic | 50 | Multi-station search (greedy → multistation) | Demands fully satisfied | +0.22 | [-0.20, +0.64] | 0.271 | 7/10 | ns |
| pessimistic | 50 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +0.09 | [-0.20, +0.38] | 0.501 | 7/10 | ns |
| pessimistic | 50 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +0.02 | [-0.27, +0.31] | 0.891 | 5/10 | ns |
| pessimistic | 50 | Reputation (multistation → multistation_rep) | Demands served (even partially) | -0.03 | [-0.15, +0.08] | 0.516 | 3/10 | ns |
| pessimistic | 50 | Reputation (multistation → multistation_rep) | Demands fully satisfied | -0.15 | [-0.30, +0.00] | 0.0553 | 2/10 | ns |
| pessimistic | 50 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | -0.06 | [-0.10, -0.01] | 0.0188 | 1/10 | worse |
| pessimistic | 50 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | -0.06 | [-0.30, +0.18] | 0.571 | 4/10 | ns |
| pessimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.04 | [-0.09, +0.01] | 0.101 | 1/10 | ns |
| pessimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | +0.15 | [-0.05, +0.36] | 0.116 | 6/10 | ns |
| pessimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.00 | [-0.07, +0.07] | 0.996 | 4/10 | ns |
| pessimistic | 50 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | +0.09 | [-0.11, +0.29] | 0.325 | 7/10 | ns |
| pessimistic | 150 | Multi-station search (greedy → multistation) | Demands served (even partially) | +0.24 | [-0.20, +0.68] | 0.248 | 6/10 | ns |
| pessimistic | 150 | Multi-station search (greedy → multistation) | Demands fully satisfied | +4.86 | [+3.88, +5.85] | 1.41e-06 | 10/10 | better |
| pessimistic | 150 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +2.37 | [+1.74, +3.00] | 1.28e-05 | 10/10 | better |
| pessimistic | 150 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +5.43 | [+4.29, +6.58] | 1.96e-06 | 10/10 | better |
| pessimistic | 150 | Reputation (multistation → multistation_rep) | Demands served (even partially) | +0.01 | [-0.15, +0.17] | 0.899 | 7/10 | ns |
| pessimistic | 150 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.14 | [-0.06, +0.35] | 0.15 | 6/10 | ns |
| pessimistic | 150 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | +0.01 | [-0.12, +0.13] | 0.931 | 6/10 | ns |
| pessimistic | 150 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | -0.01 | [-0.20, +0.18] | 0.901 | 5/10 | ns |
| pessimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.03 | [-0.17, +0.11] | 0.634 | 4/10 | ns |
| pessimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | -0.09 | [-0.45, +0.27] | 0.575 | 4/10 | ns |
| pessimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.01 | [-0.22, +0.20] | 0.893 | 6/10 | ns |
| pessimistic | 150 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | +0.04 | [-0.33, +0.40] | 0.818 | 6/10 | ns |
| pessimistic | 250 | Multi-station search (greedy → multistation) | Demands served (even partially) | +0.73 | [+0.38, +1.08] | 0.00106 | 10/10 | better |
| pessimistic | 250 | Multi-station search (greedy → multistation) | Demands fully satisfied | +9.20 | [+8.22, +10.18] | 5.52e-09 | 10/10 | better |
| pessimistic | 250 | Multi-station search (greedy → multistation) | Share of energy need met (all demands) | +5.64 | [+4.77, +6.51] | 1.4e-07 | 10/10 | better |
| pessimistic | 250 | Multi-station search (greedy → multistation) | Share of energy need met (served demands) | +12.81 | [+10.84, +14.77] | 1.32e-07 | 10/10 | better |
| pessimistic | 250 | Reputation (multistation → multistation_rep) | Demands served (even partially) | +0.05 | [-0.12, +0.21] | 0.521 | 5/10 | ns |
| pessimistic | 250 | Reputation (multistation → multistation_rep) | Demands fully satisfied | +0.11 | [-0.25, +0.47] | 0.51 | 6/10 | ns |
| pessimistic | 250 | Reputation (multistation → multistation_rep) | Share of energy need met (all demands) | -0.05 | [-0.17, +0.08] | 0.423 | 5/10 | ns |
| pessimistic | 250 | Reputation (multistation → multistation_rep) | Share of energy need met (served demands) | -0.23 | [-0.64, +0.18] | 0.231 | 3/10 | ns |
| pessimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Demands served (even partially) | -0.10 | [-0.30, +0.11] | 0.311 | 5/10 | ns |
| pessimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Demands fully satisfied | +0.03 | [-0.36, +0.41] | 0.882 | 6/10 | ns |
| pessimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (all demands) | -0.01 | [-0.19, +0.17] | 0.917 | 7/10 | ns |
| pessimistic | 250 | Cross-station adaptation (multistation_rep → bramev) | Share of energy need met (served demands) | +0.21 | [-0.08, +0.49] | 0.132 | 6/10 | ns |
