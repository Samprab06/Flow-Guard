from experiments.v3_analysis import leave_one_out, summarize


def row(trial, feasible, knobs=None, area=100, wns=1):
    return {"trial_id": trial, "feasible": feasible, "knobs": knobs or {"FP_CORE_UTIL": 30}, "area": area, "WNS": wns, "TNS": -2, "DRC": 0 if feasible else 3, "wirelength": 10}


def test_summary_ranges_balance_and_repeatability_warning():
    report = summarize([row("a", True), row("b", True, area=110), row("c", False)])
    assert report["metric_ranges"]["area"] == {"min": 100.0, "max": 110.0, "count": 2}
    assert report["feasibility_balance"]["counts"] == {"false": 1, "true": 2}
    assert report["repeatability"]["undersized_groups"] == 2
    assert not any("one feasibility class" in warning for warning in report["warnings"])


def test_one_class_warning_and_loo_baseline():
    records = [row("a", True, area=10), row("b", True, area=14, wns=3)]
    report = summarize(records)
    assert any("one feasibility class" in warning for warning in report["warnings"])
    loo = leave_one_out(records)
    assert loo["claim"].startswith("sanity baseline")
    assert loo["metrics"]["area"]["evaluated"] == 2
    assert loo["metrics"]["area"]["mae"] == 4.0


def test_empty_and_alias_fields():
    report = summarize([])
    assert report["records"] == 0
    assert report["metric_ranges"]["area"] is None


def test_reports_missing_evidence_and_failure_stages():
    report = summarize([{
        **row("missing", False),
        "missing_metrics": ["hold_wns", "routing_completion"],
        "failure_stage": "MISSING_METRICS",
    }])
    assert report["evidence_gaps"]["missing_metrics"] == {
        "hold_wns": 1,
        "routing_completion": 1,
    }
    assert report["evidence_gaps"]["failure_stages"] == {"MISSING_METRICS": 1}
