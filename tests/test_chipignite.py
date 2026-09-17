import json
from pathlib import Path

from chipignite.inventory import inventory_path
from chipignite.report import migration_report
from chipignite.scoring import score_candidate


def test_scoring_preserves_metadata_and_decisions():
    candidates = json.loads(Path("tests/fixtures/chipignite_metadata.json").read_text())
    report = migration_report(candidates)
    assert [x["scoring"]["decision"] for x in report["candidates"]] == ["GO", "HOLD", "NO-GO"]
    assert report["candidates"][0]["artifact_extra"] == "preserve"


def test_inventory_is_offline_and_hashes_rtl(tmp_path):
    (tmp_path / "top.v").write_text("module top; endmodule\n")
    (tmp_path / "notes.txt").write_text("ignored")
    result = inventory_path(tmp_path)
    assert result["file_count"] == 1
    assert result["files"][0]["path"] == "top.v"


def test_score_missing_repository_is_no_go():
    assert score_candidate({"commit": {}, "license": {}, "artifacts": []})["decision"] == "NO-GO"
