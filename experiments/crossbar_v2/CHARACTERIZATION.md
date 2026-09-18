# Crossbar v2 Characterization

The RTL, `320 x 200 um` footprint, and `FP_CORE_UTIL=30` were held fixed. All
runs used SKY130/LibreLane 3.0.14 and completed routing, DRC, LVS, and signoff;
feasibility is determined by setup and hold slack plus the configured parser
rule. The first 20 ns preflight caught and fixed a Verilator multi-driven loop
variable in v2 before physical characterization.

| Trial | Clock | Density | Padding | Synth | GRT | Setup WS (ns) | Hold WS (ns) | Wirelength (um) | Feasible |
|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| `crossbar-v2-baseline-20ns-u30-d45-r2` | 20.0 | 45 | 0 | AREA 0 | 0.3 | +0.0885 | +0.1287 | 148572 | yes |
| `crossbar-v2-char-19p5-u30-d45-r2` | 19.5 | 45 | 0 | AREA 0 | 0.3 | -0.3115 | +0.1287 | 148572 | no |
| `crossbar-v2-char-20p0-u30-d35` | 20.0 | 35 | 0 | AREA 0 | 0.3 | +0.0885 | +0.1287 | 148572 | yes |
| `crossbar-v2-char-20p0-u30-d55` | 20.0 | 55 | 0 | AREA 0 | 0.3 | +0.0885 | +0.1287 | 148572 | yes |
| `crossbar-v2-char-19p9-u30-d45-p0` | 19.9 | 45 | 0 | AREA 0 | 0.3 | +0.0085 | +0.1287 | 148572 | yes |
| `crossbar-v2-char-19p9-u30-d45-p2` | 19.9 | 45 | 2 | AREA 0 | 0.3 | -0.0410 | +0.1326 | 150774 | no |
| `crossbar-v2-char-19p9-u30-d45-area1` | 19.9 | 45 | 0 | AREA 1 | 0.3 | -1.4986 | +0.1340 | 152234 | no |
| `crossbar-v2-char-19p9-u30-d45-grt02` | 19.9 | 45 | 0 | AREA 0 | 0.2 | -0.6711 | +0.1274 | 145247 | no |
| `crossbar-v2-char-19p9-u30-d35-p0` | 19.9 | 35 | 0 | AREA 0 | 0.3 | +0.0085 | +0.1287 | 148572 | yes |
| `crossbar-v2-char-19p9-u30-d55-p0` | 19.9 | 55 | 0 | AREA 0 | 0.3 | +0.0085 | +0.1287 | 148572 | yes |

The fixed mixed-feasibility operating point is `19.9 ns`, `320 x 200 um`,
with the candidate bounds recorded in `frozen_manifest.json`. The six-candidate
comparison pool and equal-budget replay are in `frozen_manifest.json` and
`comparison_results.json`. Canonical GDS/PNG artifacts are in `artifacts/`.
