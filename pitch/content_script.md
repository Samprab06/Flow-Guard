# FlowGuard — Hackathon Pitch Content Script

Audience: mixed/general, Purdue CHIPSandAI hackathon. Tone: light editorial, plain language.
Every figure below is pinned to the frozen dossier and audit artifacts. Raw EDA ledgers remain server-local; running methods are marked PARTIAL.
No numbers are invented. The committed visual is a verified layout render under `pitch/renders/`.

---

## Slide 1 — FlowGuard: stop burning silicon before it exists

### The hook
Every chip team burns weeks of compute on synthesis and place-and-route runs that were doomed from the start. FlowGuard is a feasibility-aware optimizer for the open-source SKY130 flow that learns which knob settings can actually close timing, and spends the budget there instead of on guaranteed failures and empty signoff reports.

### What we show today
We froze a genuinely hard operating point at a 15.8 nanosecond clock and ran a partial four-method optimizer comparison on real LibreLane runs. The headline result is a signoff-clean candidate with a quality score of 0.103 and a verified layout render committed with the pitch.

---

## Slide 2 — The wasted-EDA problem

### Trial-and-error is the default flow
Tuning an RTL-to-GDS flow means sweeping cell padding, density, routing adjustments, and synthesis strategies by hand or by blind random search. Each attempt costs about three minutes of tools, and failures arrive late, at the signoff stage, after the compute is already spent on a hopeless corner of the space.

### Failures are expensive and silent
In our 485-run clock sweep, every single 15 nanosecond attempt failed timing after full place and route, consuming hours of machine time for zero usable data. Standard optimizers treat a crash and a near-miss identically, so they keep re-sampling dead regions instead of learning the boundary.

---

## Slide 3 — The FlowGuard idea: expected improvement times probability of feasibility

### Two models instead of one
FlowGuard pairs a quality predictor with a separate feasibility classifier. Each candidate is scored as expected improvement multiplied by the probability it will actually close timing, so risky, high-upside corners are explored deliberately rather than stumbled into, and hopeless corners are skipped entirely without spending a single tool run.

### Calibration with a safety catch
The feasibility model self-calibrates only once each outcome class has at least three observations; before that it declares itself uncalibrated and the system runs in raw mode. Every decision is logged with scores, model versions, and training hashes, so any pick can be replayed and audited later.

---

## Slide 4 — A real SKY130 flow, not a toy model

### Open PDK, open tools, frozen versions
All results come from the LibreLane 3.0.14 container on the sky130A PDK with pinned library and environment files. The design is a sensor-MAC stress block of 728 synthesis cells, and feasibility demands the full checklist: success status, zero DRC, non-negative setup and hold slack, full routing, and passing LVS and signoff.

### Frozen benchmark, fixed budget
The primary benchmark fixes the clock at 15.8 nanoseconds with eight shared seed runs plus sixteen adaptive picks per method from a seventy-two candidate pool. Quality blends critical delay, wirelength, and cell area with frozen normalization constants, so every method is scored on identical ground.

---

## Slide 5 — The 17/15 cliff

### Comfortable at seventeen, dead at fifteen
Across the exhaustive sweep, 310 of 325 runs at a 17 nanosecond clock passed with setup slack between 0.86 and 1.92 nanoseconds, a wide comfort zone. At 15 nanoseconds, all 160 attempts failed, 159 with explicit timing failure and setup slack as bad as minus 1.14 nanoseconds. There is no gradual slope between these regimes.

### The boundary is somewhere between
A two-nanosecond tightening flips the flow from near-certain success to certain failure, which is exactly why hand-tuning stalls: intuition trained at relaxed clocks gives no guidance near the wall. The honest engineering response is to hunt the boundary empirically rather than guess, which is what the next experiments do.

---

## Slide 6 — Frozen at 15.8: a living boundary

### Half the map is red
Targeted hunts at 15.8 nanoseconds returned five feasible runs out of eight, and a fourteen-run diagnostic grid returned eleven out of fourteen. Setup slack scatters across zero, from minus 0.34 to plus 0.72 nanoseconds, so the operating point is genuinely mixed: the same clock that passes with one knob combination fails with another.

### Determinism you can trust
Three exact repeats of one configuration returned bit-identical results, the same slack, wirelength, and area every time. That determinism means the mixed outcome is signal, not tool noise: feasibility differences between candidates reflect the knobs, which is precisely what an optimizer needs to learn.

---

## Slide 7 — What matters: padding and strategy

### Padding two is the danger zone
Grouped across all 15.8 nanosecond trials, configurations with a cell padding of two fail far more often than padding zero or one, and synthesis strategy AREA 1 paired with high padding produced the diagnostic grid's only failures. Low padding with AREA 0 passes consistently, making placement spreading the single most predictive choice at this clock.

### Small knobs, large consequences
Density and routing-adjustment settings move slack by tenths of a nanosecond, enough to flip feasibility at the boundary. The lesson for the shootout is that the search space is not flat noise: it has learnable structure, with a few knobs dominating the outcome, which is the regime where a feasibility model should beat blind search.

---

## Slide 8 — Five-way shootout: quality versus budget

### Four methods are recorded; calibration is queued
Random search, Optuna TPE, vanilla Bayesian optimization, and FlowGuard raw each started from the same eight shared seeds and added sixteen adaptive picks, with best-quality-so-far tracked per call. Vanilla BO and Optuna both reached 0.103, FlowGuard raw reached 0.103 at adaptive call 11, and random trailed at 0.169.

### The calibrated sibling is missing
The fifth method, FlowGuard calibrated, has not started, because calibration requires three observations per outcome class and the harness gates on that threshold. Its trace is shown as not-started rather than zero, since inventing a curve would misrepresent the experiment, and a rerun of the deck builder will pick it up automatically.

---

## Slide 9 — Failure efficiency: learning what not to run

### Feasibility rates diverge
Vanilla BO finished sixteen for sixteen feasible, FlowGuard raw eleven of sixteen, Optuna thirteen of sixteen, random twelve of sixteen, and the shared seeds only two of eight. The seeds confirm the point is hard; this comparison does not support a general fewer-failures claim.

### Fewer corpses, same winner
FlowGuard raw reached the best quality at adaptive call 11, while vanilla BO reached it earlier in this frozen comparison. FlowGuard raw also recorded five timing failures, so the defensible claim is discovery-speed evidence for this seed, not fewer failures. At three minutes per run, each avoided failure remains measurable budget.

---

## Slide 10 — The winner and its GDS

### Candidate fourteen
The winning configuration pairs zero cell padding with density fifty-two, maximum routing adjustment, and AREA 0 synthesis at thirty percent utilization. It closes with 0.616 nanoseconds of setup slack, 0.112 nanoseconds of hold slack, 15,137 square microns of cell area, and 27,229 microns of routed wire, for a quality score of 0.103 under the frozen weights.

### Pixels on disk
The verified winner layout render is committed under `pitch/renders/`; the raw GDS remains in the server-local results tree. The audit records that raw ledgers and full GDS provenance are not reconstructable from Git alone.

---

## Slide 11 — One AI decision, fully replayable

### The pick, with receipts
At its eleventh call, FlowGuard raw scored sixty-one pool candidates and selected candidate fourteen, ranking it first with an expected improvement of 0.025, a feasibility probability of 0.90, and a combined acquisition score of 0.023 from eleven training points. The record carries the data hash, random seed, model versions, and the explicit flag that calibration was inactive.

### Why this matters beyond chips
Anyone can re-resolve this decision: same training set hash, same code versions, same selected identifier. Optimizer choices in EDA are usually lore reconstructed after the fact; here the eleventh decision is a row in a file, auditable by a judge with a laptop, which is the standard every AI-assisted engineering claim should meet.

---

## Slide 12 — Integrity and the ask

### What we will not claim
All running-method traces are labeled partial, the calibrated variant has not started, and the die tile is documented as an assumed two-by-one placement unvalidated against full TinyTapeout integration. Methods that finished report their full sixteen adaptive calls; nothing is extrapolated, smoothed, or cherry-picked, and rerunning the builder refreshes every number from source.

### What we want
We are asking for collaborators and compute: help us finish the calibrated arm, extend the benchmark to a second design, and harden the provenance log into a standard artifact. If you have tuned an EDA flow by hand and felt the pain this deck describes, come talk to us about never running a doomed job again.
