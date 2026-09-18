#!/usr/bin/env python3
"""Validate frozen 36-candidate pool for crossbar_datapath_v2. Read-only: no EDA/optimizer."""
import json, hashlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
POOL = ROOT/"experiments/pools/pool_crossbar_v2_36_v1.json"
PROTO = ROOT/"experiments/crossbar_v2/eval_protocol_v2_frozen_36pool.json"
MAN = ROOT/"experiments/crossbar_v2/characterization_manifest_36pool.json"
PARENT = ROOT/"experiments/crossbar_v2/eval_protocol_v2_frozen.json"
FROZEN = ROOT/"experiments/crossbar_v2/frozen_manifest.json"
fails=[]
def check(c,m):
    if not c: fails.append(m)
pool=json.loads(POOL.read_text()); proto=json.loads(PROTO.read_text())
man=json.loads(MAN.read_text()); parent=json.loads(PARENT.read_text()); frozen=json.loads(FROZEN.read_text())
cands=pool["candidates"]
check(len(cands)==36, f"pool size {len(cands)} != 36")
check(len({json.dumps({k:c[k] for k in ('SYNTH_STRATEGY','PL_TARGET_DENSITY_PCT','GPL_CELL_PADDING','GRT_ADJUSTMENT')},sort_keys=True) for c in cands})==36, "duplicate knob tuples")
exp=[(s,d,p,g) for s in ["AREA 0","AREA 1","AREA 2"] for d in [35,45,55] for p in [0,2] for g in [0.2,0.3]]
got=[(c["SYNTH_STRATEGY"],c["PL_TARGET_DENSITY_PCT"],c["GPL_CELL_PADDING"],c["GRT_ADJUSTMENT"]) for c in cands]
check(got==exp, "ordering != lexicographic (SYNTH,DENSITY,PAD,GRT)")
check([c["candidate_id"] for c in cands]==[f"cb36_{i:03d}" for i in range(36)], "candidate_id sequence")
check([c["pool_index"] for c in cands]==list(range(36)), "pool_index sequence")
canon=json.dumps(cands,sort_keys=True,separators=(",",":")).encode()
check(hashlib.sha256(canon).hexdigest()==pool["canonical_hash"], "pool canonical hash mismatch")
check(pool["canonical_hash"]==proto["source_pool"]["canonical_hash"]==man["pool_canonical_hash"], "hash linkage pool/proto/manifest")
check(proto["status"]=="FROZEN-36-POOL-NO-OPTIMIZER-RUNS", "protocol status")
check(proto["frozen_design"]==parent["frozen_design"], "frozen_design drift")
check(proto["objective"]==parent["objective"], "objective/baselines drift")
check(proto["feasibility_rule"]==parent["feasibility_rule"] and proto["feasibility_checks"]==parent["feasibility_checks"], "feasibility drift")
check(proto["objective"]["baselines"]=={"min_crit_ns":19.891500132283074,"max_crit_ns":21.398575528307965,"min_wl_um":145247.0,"max_wl_um":152234.0,"min_area_um2":36947.9,"max_area_um2":37504.7}, "normalization constants drift")
check(man["counts"]=={"pool_total":36,"reusable_legacy_pending_verification":6,"unmeasured":30}, "manifest counts")
check(len(man["reusable_legacy_candidates"])==6 and len(man["unmeasured_candidates"])==30, "manifest list sizes")
old={(e["SYNTH_STRATEGY"],e["PL_TARGET_DENSITY_PCT"],e["GPL_CELL_PADDING"],e["GRT_ADJUSTMENT"]):e for e in frozen["candidate_pool"]}
for r in man["reusable_legacy_candidates"]:
    key=(r["knobs"]["SYNTH_STRATEGY"],r["knobs"]["PL_TARGET_DENSITY_PCT"],r["knobs"]["GPL_CELL_PADDING"],r["knobs"]["GRT_ADJUSTMENT"])
    check(key in old, f"reusable {r['pool_candidate_id']} not in legacy grid")
    check((ROOT/r["legacy_config_file"]).exists(), f"missing config {r['legacy_config_file']}")
    check(hashlib.sha256((ROOT/r["legacy_config_file"]).read_bytes()).hexdigest()==r["legacy_config_sha256"], f"config hash mismatch {r['legacy_config_file']}")
    o=old[key]
    s=r["legacy_metrics_snapshot"]
    check(o["candidate_id"]==r["legacy_candidate_id"] and o["trial_id"]==r["legacy_trial_id"], f"legacy id drift {r['pool_candidate_id']}")
    check(s["setup_ws"]==o["metrics"]["setup_ws"] and s["hold_ws"]==o["metrics"]["hold_ws"] and s["wirelength"]==o["metrics"]["wirelength"] and s["area"]==o["metrics"]["area"] and s["feasible"]==o["feasible"] and s["critical_delay_ns"]==o["critical_delay_ns"], f"metrics snapshot drift {r['pool_candidate_id']}")
print(f"pool={POOL.relative_to(ROOT)} hash={pool['canonical_hash']}")
print(f"candidates=36 reusable_pending_verification=6 unmeasured=30")
print("PASS" if not fails else "FAIL")
for f in fails: print(" -",f)
sys.exit(1 if fails else 0)
