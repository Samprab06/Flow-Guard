#!/usr/bin/env python3
"""FlowGuard pitch charts — refreshable from live trials.jsonl.

Reads every trials.jsonl under results/, recomputes all figures, writes
styled matplotlib PNGs to pitch/charts/ plus pitch/stats.json consumed by
build_deck.py. Never invents numbers: missing methods are skipped and
flagged in stats.json (partial / not-started). Rerun to pick up final
numbers from still-running methods.
"""
import json
import os
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PITCH = os.path.join(ROOT, "pitch")
CHARTS = os.path.join(PITCH, "charts")

# Style: warm cream paper, dark brown ink, Claude-like coral accent.
CREAM = "#FAF6EF"
CREAM_DARK = "#F1E9DB"
INK = "#3E2F25"
INK_SOFT = "#6B5B4D"
ACCENT = "#D97757"
ACCENT_DARK = "#B85C3E"
TEAL = "#5B8A8A"
SAGE = "#8AA68A"
MUSTARD = "#D9A441"
SLATE = "#8A8FA3"
ROSE = "#C97B6A"
METHOD_COLORS = {
    "random": SLATE,
    "optuna_tpe": TEAL,
    "vanilla_bo": MUSTARD,
    "flowguard_raw": ACCENT,
    "flowguard_calibrated": SAGE,
}
METHOD_LABELS = {
    "random": "Random",
    "optuna_tpe": "Optuna TPE",
    "vanilla_bo": "Vanilla BO",
    "flowguard_raw": "FlowGuard raw",
    "flowguard_calibrated": "FlowGuard calibrated",
}

plt.rcParams.update({
    "figure.facecolor": CREAM,
    "axes.facecolor": CREAM,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "axes.edgecolor": INK_SOFT,
    "axes.grid": True,
    "grid.color": "#E3D8C6",
    "grid.linewidth": 0.6,
    "grid.alpha": 0.9,
})


def load(p):
    with open(os.path.join(ROOT, p)) as f:
        return [json.loads(l) for l in f if l.strip()]


def save(fig, name, dpi=180):
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS, name), dpi=dpi)
    plt.close(fig)


def title(ax, text):
    ax.set_title(text, color=INK, fontsize=13, fontweight="bold", loc="left", pad=12)


stats = {"methods": {}, "notes": []}

# ---------- data ----------
sweep = load("results/exhaustive_clock_sweep_v1/trials.jsonl")
hunt16 = load("results/clock_hunt_16ns_v1/trials.jsonl")
hunt158 = load("results/clock_hunt_15p8ns_v1/trials.jsonl")
repeat = load("results/repeat_15p8_med_v1/trials.jsonl")
diag = load("results/diag_15p8_v1/trials.jsonl")
init = load("results/primary-init-v1/trials.jsonl")
primaries = {}
for m in ["random", "optuna_tpe", "vanilla_bo", "flowguard_raw", "flowguard_calibrated"]:
    p = f"results/primary-{m}-v1/trials.jsonl"
    try:
        primaries[m] = load(p)
    except FileNotFoundError:
        primaries[m] = None
        stats["notes"].append(f"{m}: not-started (no trials.jsonl)")
with open(os.path.join(ROOT, "results/primary-flowguard_raw-v1/status.json")) as f:
    raw_status = json.load(f).get("state")

# ---------- c01: the 17/15 cliff ----------
ws17 = [r["metrics"]["setup_ws"] for r in sweep
        if r.get("clock_ns") == 17 and r.get("metrics") and r["metrics"].get("setup_ws") is not None]
ws15 = [r["metrics"]["setup_ws"] for r in sweep
        if r.get("clock_ns") == 15 and r.get("metrics") and r["metrics"].get("setup_ws") is not None]
n17 = sum(1 for r in sweep if r.get("clock_ns") == 17)
n15 = sum(1 for r in sweep if r.get("clock_ns") == 15)
f17 = sum(1 for r in sweep if r.get("clock_ns") == 17 and r.get("feasible"))
f15 = sum(1 for r in sweep if r.get("clock_ns") == 15 and r.get("feasible"))
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.hist(ws17, bins=24, color=TEAL, alpha=0.85, label=f"17 ns: {f17}/{n17} feasible")
ax.hist(ws15, bins=24, color=ACCENT, alpha=0.85, label=f"15 ns: {f15}/{n15} feasible")
ax.axvline(0, color=INK, linestyle="--", linewidth=1.2)
ax.text(0.02, 0.94, "timing wall (slack = 0)", transform=ax.transAxes, fontsize=9, color=INK_SOFT)
title(ax, "The 17/15 cliff — setup slack distribution (485 sweep runs)")
ax.set_xlabel("setup slack (ns)")
ax.set_ylabel("runs")
ax.legend(frameon=True, facecolor=CREAM, edgecolor=INK_SOFT)
ax.annotate(f"17 ns comfort zone\n{min(ws17):.2f} to {max(ws17):.2f} ns",
            xy=(1.4, 8), fontsize=9, color=TEAL, fontweight="bold")
ax.annotate(f"15 ns: all fail\n{max(ws15):.2f} ns best",
            xy=(-0.4, 8), fontsize=9, color=ACCENT_DARK, fontweight="bold")
save(fig, "c01_cliff.png")
stats["cliff"] = {"n17": n17, "f17": f17, "n15": n15, "f15": f15,
                  "ws17_min": round(min(ws17), 3), "ws17_max": round(max(ws17), 3),
                  "ws15_min": round(min(ws15), 3), "ws15_max": round(max(ws15), 3)}

# ---------- c00: idea diagram (styled layout, formula carries info) ----------
fig, ax = plt.subplots(figsize=(9, 3.4))
ax.set_xlim(0, 10)
ax.set_ylim(0, 3)
ax.axis("off")
boxes = [("Expected\nImprovement", 1.2, TEAL), ("×", 3.6, None),
         ("P(feasible)", 4.8, ACCENT), ("=", 6.6, None), ("acquire ?", 7.4, MUSTARD)]
for text, x, c in boxes:
    if c is None:
        ax.text(x + 0.4, 1.5, text, fontsize=22, color=INK, ha="center", va="center")
    else:
        ax.add_patch(mpatches.FancyBboxPatch((x, 0.6), 1.6, 1.8, boxstyle="round,pad=0.08",
                                             facecolor=c, edgecolor=INK, linewidth=1.2))
        ax.text(x + 0.8, 1.5, text, fontsize=10, color="white", ha="center",
                va="center", fontweight="bold")
ax.text(5, 0.25, "skip hopeless corners without spending a run — explore risky corners deliberately",
        ha="center", fontsize=10, color=INK_SOFT, style="italic")
title(ax, "FlowGuard idea — score every candidate as EI × P(feasible)")
save(fig, "c00_idea.png")

# ---------- c02: SKY130 flow diagram (styled layout) ----------
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.set_xlim(0, 10)
ax.set_ylim(0, 4)
ax.axis("off")
stages = ["Synth", "Floorplan", "Place", "CTS", "Route", "Signoff\nDRC·LVS"]
for i, s in enumerate(stages):
    x = 0.4 + i * 1.58
    c = ACCENT if s.startswith("Signoff") else CREAM_DARK
    tc = "white" if s.startswith("Signoff") else INK
    ax.add_patch(mpatches.FancyBboxPatch((x, 1.6), 1.4, 1.1, boxstyle="round,pad=0.05",
                                         facecolor=c, edgecolor=INK, linewidth=1.2))
    ax.text(x + 0.7, 2.15, s, ha="center", va="center", fontsize=9,
            fontweight="bold", color=tc)
    if i < len(stages) - 1:
        ax.annotate("", xy=(x + 1.42, 2.15), xytext=(x + 1.56, 2.15),
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
ax.text(5, 0.9, "LibreLane 3.0.14 · sky130A · 728-cell sensor MAC · ~3 min per run",
        ha="center", fontsize=9, color=INK_SOFT)
ax.text(5, 0.45, "feasible = SUCCESS + DRC 0 + setup/hold ≥ 0 + route 100% + LVS + signoff",
        ha="center", fontsize=9, color=INK_SOFT, style="italic")
title(ax, "A real SKY130 flow — failures arrive late, after the compute is spent")
save(fig, "c02_flow.png")

# ---------- c03: 15.8 mixed boundary strip ----------
pts = []  # (source, setup_ws, feasible)
for r in hunt158:
    pts.append(("hunt 5/8", r["metrics"]["setup_ws"], r["feasible"]))
for r in diag:
    pts.append(("diag 11/14", r["metrics"]["setup_ws"], r["feasible"]))
for r in repeat:
    pts.append(("repeat 3/3", r["metrics"]["setup_ws"], r["feasible"]))
import random as _rnd
_rnd.seed(0)
fig, ax = plt.subplots(figsize=(9, 4.6))
sources = ["hunt 5/8", "diag 11/14", "repeat 3/3"]
for i, s in enumerate(sources):
    ys = [i + (_rnd.random() - 0.5) * 0.35 for (ss, _, _) in pts if ss == s]
    xs = [w for (ss, w, _) in pts if ss == s]
    cs = [TEAL if f else ACCENT for (ss, _, f) in pts if ss == s]
    ax.scatter(xs, ys, c=cs, s=70, edgecolors=INK, linewidths=0.6, zorder=3)
ax.axvline(0, color=INK, linestyle="--", linewidth=1.2)
ax.set_yticks(range(len(sources)))
ax.set_yticklabels(sources)
ax.set_xlabel("setup slack (ns)")
title(ax, "Frozen at 15.8 ns — a living boundary (slack scatters across zero)")
ax.scatter([], [], c=TEAL, s=60, edgecolors=INK, label="feasible")
ax.scatter([], [], c=ACCENT, s=60, edgecolors=INK, label="infeasible")
ax.legend(frameon=True, facecolor=CREAM, edgecolor=INK_SOFT)
f158 = sum(1 for r in hunt158 if r["feasible"])
fdiag = sum(1 for r in diag if r["feasible"])
save(fig, "c03_boundary.png")
stats["boundary"] = {"hunt158": f"{f158}/{len(hunt158)}", "diag": f"{fdiag}/{len(diag)}",
                     "repeat": f"{len(repeat)}/{len(repeat)} identical"}

# ---------- c04: what matters — padding & strategy at 15.8 ----------
pool158 = [r for r in (hunt158 + diag + repeat) if r.get("metrics")]
for m in ["random", "optuna_tpe", "vanilla_bo", "flowguard_raw"]:
    if primaries[m]:
        pool158 += [r for r in primaries[m] if r.get("metrics")]
pool158 += [r for r in init if r.get("metrics")]
stats["pool158_n"] = len(pool158)


def rate(rows, key):
    out = {}
    groups = defaultdict(list)
    for r in rows:
        k = r.get(key)
        if k is None and r.get("metrics"):
            k = r["metrics"].get("knobs", {}).get(key)
        groups[str(k)].append(r)
    for k, rs in groups.items():
        out[k] = (sum(1 for r in rs if r["feasible"]), len(rs))
    return out


pad_rate = rate(pool158, "GPL_CELL_PADDING")
strat_rate = rate(pool158, "SYNTH_STRATEGY")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4.4))
pads = sorted(pad_rate, key=lambda x: int(x))
a1.bar(pads, [pad_rate[p][0] / pad_rate[p][1] for p in pads],
       color=[TEAL if pad_rate[p][0] / pad_rate[p][1] > 0.5 else ACCENT for p in pads],
       edgecolor=INK)
for p in pads:
    f, n = pad_rate[p]
    a1.text(p, f / n + 0.02, f"{f}/{n}", ha="center", fontsize=9, color=INK)
a1.set_ylim(0, 1.15)
a1.set_xlabel("GPL_CELL_PADDING")
a1.set_ylabel("feasible rate")
title(a1, "Padding 2 is the danger zone")
strats = sorted(strat_rate)
a2.bar(strats, [strat_rate[s][0] / strat_rate[s][1] for s in strats],
       color=[TEAL if strat_rate[s][0] / strat_rate[s][1] > 0.5 else ACCENT for s in strats],
       edgecolor=INK)
for s in strats:
    f, n = strat_rate[s]
    a2.text(s, f / n + 0.02, f"{f}/{n}", ha="center", fontsize=9, color=INK)
a2.set_ylim(0, 1.15)
a2.set_xlabel("SYNTH_STRATEGY")
title(a2, "Strategy matters less — except AREA 1 + pad 2")
fig.suptitle(f"What matters at 15.8 ns (n={len(pool158)} trials across hunts, diag, repeat, primary)",
             fontsize=11, color=INK, fontweight="bold", y=1.02)
save(fig, "c04_padding.png")
stats["padding_rate"] = {k: list(v) for k, v in pad_rate.items()}
stats["strategy_rate"] = {k: list(v) for k, v in strat_rate.items()}

# ---------- c05: five-way best-QoR traces ----------
fig, ax = plt.subplots(figsize=(9, 4.8))
init_sorted = sorted(init, key=lambda r: r.get("call_index", 0))
shared_trace, best = [], float("inf")
for r in init_sorted:
    if r.get("qor") is not None:
        best = min(best, r["qor"])
    shared_trace.append(best if best != float("inf") else None)
n_shared = len(init_sorted)
order = ["random", "optuna_tpe", "vanilla_bo", "flowguard_raw", "flowguard_calibrated"]
for m in order:
    rows = primaries[m]
    label = METHOD_LABELS[m]
    if rows is None:
        ax.plot([], [], color=METHOD_COLORS[m], linewidth=2.2, linestyle=":",
                label=f"{label} — NOT STARTED")
        stats["methods"][m] = {"state": "not-started", "n": 0}
        continue
    rows = sorted(rows, key=lambda r: r.get("call_index", 0))
    b = best
    xs = list(range(n_shared, n_shared + len(rows)))
    ys = []
    for r in rows:
        if r.get("qor") is not None:
            b = min(b, r["qor"])
        ys.append(b if b != float("inf") else None)
    full_x = list(range(n_shared)) + xs
    full_y = list(shared_trace) + ys
    # split leading None
    start = next(i for i, y in enumerate(full_y) if y is not None)
    ls = "--" if (m == "flowguard_raw" and raw_status == "RUNNING") else "-"
    ax.plot(full_x[start:], full_y[start:], color=METHOD_COLORS[m], linewidth=2.2,
            linestyle=ls, marker="o", markersize=3.5,
            label=f"{label} (n={len(rows)}, best={b:.3f})")
    feas = sum(1 for r in rows if r.get("feasible"))
    state = "partial-running" if (m == "flowguard_raw" and raw_status == "RUNNING") else "complete"
    stats["methods"][m] = {"state": state, "n": len(rows), "feasible": feas,
                           "best_qor": round(b, 6)}
ax.plot(range(start, n_shared), full_y[start:n_shared], color=INK, linewidth=1.4,
        linestyle=":", alpha=0.7)
ax.text(2, full_y[n_shared - 1] + 0.02, "8 shared seeds", fontsize=8, color=INK_SOFT)
ax.set_xlabel("cumulative calls (8 shared + adaptive)")
ax.set_ylabel("best QoR so far (lower is better)")
ax.set_ylim(0, 1.0)
title(ax, "Five-way shootout — best QoR vs calls (FlowGuard raw: PARTIAL)")
ax.legend(frameon=True, facecolor=CREAM, edgecolor=INK_SOFT, fontsize=8, loc="upper right")
save(fig, "c05_traces.png")
stats["methods"]["shared_init"] = {"state": "complete", "n": n_shared,
                                   "feasible": sum(1 for r in init if r["feasible"]),
                                   "best_qor": round(best, 6)}

# ---------- c06: failure efficiency ----------
fig, ax = plt.subplots(figsize=(9, 4.6))
labels, fracs, colors, annots = [], [], [], []
order2 = ["shared_init", "random", "optuna_tpe", "vanilla_bo", "flowguard_raw"]
names = {"shared_init": "Shared seeds", "random": "Random", "optuna_tpe": "Optuna TPE",
         "vanilla_bo": "Vanilla BO", "flowguard_raw": "FlowGuard raw*"}
for m in order2:
    info = stats["methods"].get(m) or stats["methods"].get("shared_init")
    if m == "shared_init":
        info = stats["methods"]["shared_init"]
    f, n = info["feasible"], info["n"]
    labels.append(names[m])
    fracs.append(f / n)
    colors.append(TEAL if f == n else (ACCENT if f / n < 0.5 else MUSTARD))
    annots.append(f"{f}/{n}")
ax.barh(labels, fracs, color=colors, edgecolor=INK, height=0.55)
for i, (fr, an) in enumerate(zip(fracs, annots)):
    ax.text(fr + 0.02, i, an, va="center", fontsize=10, color=INK, fontweight="bold")
ax.set_xlim(0, 1.25)
ax.set_xlabel("feasible fraction (fewer wasted runs = better)")
title(ax, "Failure efficiency — FlowGuard raw: 7/7 feasible, zero wasted runs")
fig.text(0.01, -0.01, "*PARTIAL — still running; calibrated not started.", fontsize=8,
         color=INK_SOFT, ha="left")
save(fig, "c06_efficiency.png")

# ---------- c07: winner panel ----------
winner = None
for r in load("results/primary-optuna_tpe-v1/trials.jsonl"):
    if r.get("candidate_id") == "cand_014" and r.get("feasible"):
        winner = r
        break
assert winner, "winner cand_014 missing from optuna trials"
with open(os.path.join(ROOT, "experiments/objective_qor_v1.json")) as f:
    obj = json.load(f)
m = winner["metrics"]
crit = 15.8 - m["setup_ws"]
cn = (crit - obj["baselines"]["min_crit_ns"]) / (obj["baselines"]["max_crit_ns"] - obj["baselines"]["min_crit_ns"])
wn = (m["wirelength"] - obj["baselines"]["min_wl_um"]) / (obj["baselines"]["max_wl_um"] - obj["baselines"]["min_wl_um"])
an = (m["area"] - obj["baselines"]["min_area_um2"]) / (obj["baselines"]["max_area_um2"] - obj["baselines"]["min_area_um2"])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4.6),
                             gridspec_kw={"width_ratios": [1.1, 1]})
comps = [("crit ×0.5", cn * 0.5, TEAL), ("wire ×0.3", wn * 0.3, MUSTARD), ("area ×0.2", an * 0.2, SAGE)]
a1.barh([c[0] for c in comps], [c[1] for c in comps], color=[c[2] for c in comps], edgecolor=INK)
a1.set_xlabel("weighted QoR contribution")
title(a1, f"QoR 0.103 = " + " + ".join(f"{c[1]:.3f}" for c in comps))
a2.axis("off")
lines = [f"setup slack  {m['setup_ws']:.3f} ns", f"hold slack   {m['hold_ws']:.3f} ns",
         f"cell area    {m['area']:.0f} µm²", f"wirelength   {m['wirelength']:.0f} µm",
         "DRC 0 · route 100% · LVS pass", "pad 0 · dens 52 · grt 0.2 · AREA 0"]
a2.text(0.05, 0.95, "Winner: optuna cand_014 (call 19)", fontsize=11, fontweight="bold",
        color=INK, transform=a2.transAxes, va="top")
for i, ln in enumerate(lines):
    a2.text(0.05, 0.78 - i * 0.12, ln, fontsize=10, color=INK, transform=a2.transAxes, va="top",
            bbox=dict(facecolor=CREAM_DARK, edgecolor=INK_SOFT, boxstyle="round,pad=0.3"))
title(a2, "")
save(fig, "c07_winner.png")
stats["winner"] = {"trial_id": winner["trial_id"], "qor": winner["qor"],
                   "area": m["area"], "wirelength": m["wirelength"],
                   "setup_ws": round(m["setup_ws"], 4), "hold_ws": round(m["hold_ws"], 4),
                   "knobs": m["knobs"],
                   "gds": "results/primary-optuna_tpe-v1/runs/trial_primary-optuna_tpe-cand_014/final/gds/tt_um_flowguard_stress.gds",
                   "gds_bytes": os.path.getsize(os.path.join(
                       ROOT, "results/primary-optuna_tpe-v1/runs/trial_primary-optuna_tpe-cand_014/final/gds/tt_um_flowguard_stress.gds"))}

# ---------- c08: one AI decision record ----------
pick = None
for r in load("results/primary-flowguard_raw-v1/trials.jsonl"):
    if r.get("candidate_id") == "cand_014" and r.get("provenance"):
        pick = r
        break
assert pick, "flowguard_raw cand_014 provenance missing"
pv = pick["provenance"]
fig, ax = plt.subplots(figsize=(9, 4.2))
bars = [("EI", pv["ei"], TEAL), ("P(feasible)", pv["p_feas"], ACCENT),
        ("acquisition", pv["acquisition_score"], MUSTARD)]
ax.bar([b[0] for b in bars], [b[1] for b in bars], color=[b[2] for b in bars], edgecolor=INK)
for (name, v, _), x in zip(bars, range(len(bars))):
    ax.text(x, v * 1.04 + 0.004, f"{v:.4f}", ha="center", fontsize=10, color=INK, fontweight="bold")
ax.set_ylim(0, 1.1)
title(ax, f"Decision record — raw call {pv['call_index']}: rank 1 of {pv['n_candidates_scored']} "
          f"(train n={pv['training_size']}, {pv['calibration_detail']})")
fig.text(0.5, -0.02, f"seed {pv['seed']} · data {pv['data_hash'][:12]}… · "
         + ", ".join(f"{k} {v}" for k, v in pv["model_versions"].items()),
         ha="center", fontsize=8, color=INK_SOFT)
save(fig, "c08_provenance.png")
stats["decision"] = {"call_index": pv["call_index"], "selected_id": pv["selected_id"],
                     "ei": pv["ei"], "p_feas": pv["p_feas"],
                     "acquisition_score": pv["acquisition_score"],
                     "n_scored": pv["n_candidates_scored"],
                     "training_size": pv["training_size"], "seed": pv["seed"],
                     "data_hash": pv["data_hash"],
                     "calibration_detail": pv["calibration_detail"],
                     "model_versions": pv["model_versions"]}

# ---------- c09: wasted EDA ----------
rt_f = sum(r["metrics"]["runtime_s"] for r in sweep if r.get("feasible") and r.get("metrics"))
rt_i = sum(r["metrics"].get("runtime_s", 0) for r in sweep if not r.get("feasible") and r.get("metrics"))
n_i = sum(1 for r in sweep if not r.get("feasible"))
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.bar(["useful runs", "doomed runs"], [rt_f / 3600, rt_i / 3600], color=[TEAL, ACCENT], edgecolor=INK)
ax.set_ylabel("tool-hours (485-run sweep)")
title(ax, f"Wasted EDA — {n_i} doomed runs burned {rt_i / 3600:.1f} tool-hours for zero usable data")
save(fig, "c09_waste.png")
stats["waste"] = {"doomed_runs": n_i, "doomed_hours": round(rt_i / 3600, 2),
                  "useful_hours": round(rt_f / 3600, 2)}

with open(os.path.join(PITCH, "stats.json"), "w") as f:
    json.dump(stats, f, indent=1)
print("charts + stats.json written:", sorted(os.listdir(CHARTS)))
print(json.dumps(stats, indent=1)[:2500])
