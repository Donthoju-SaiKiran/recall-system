import csv
import json
from pathlib import Path

import pytest

from recallsim.config import SEED
from recallsim.export import generate, hash_tree, load_seed_sql, sha256_file, verify
from recallsim.schema import TABLES

NAMES = [t.name for t in TABLES]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("o") / "ds"
    manifest = generate("starter", SEED, d)
    return d, manifest


def test_exact_file_set(out):
    d, _ = out
    expected = {f"{kind}/{n}.{ext}" for n in NAMES for kind, ext in
                (("csv", "csv"), ("csv_clean", "csv"), ("json", "json"))}
    expected |= {"sql/seed.sql", "sql/schema.sql", "docs/DATA_DICTIONARY.md", "manifest.json", "README.md",
                 "ground_truth/ground_truth.csv", "ground_truth/ground_truth.json",
                 "ground_truth/recall_answer_key.json",
                 "validation/shipped/validation_summary.json", "validation/shipped/validation_summary.md",
                 "validation/clean/validation_summary.json", "validation/clean/validation_summary.md",
                 "validation/detection_score.json", "metrics/recall_metrics.json"}
    assert set(hash_tree(d)) == expected


def test_csv_counts_headers_and_json_match(out):
    d, m = out
    for t in TABLES:
        with open(d / "csv" / f"{t.name}.csv", encoding="utf-8", newline="") as fh:
            got = list(csv.reader(fh))
        assert got[0] == [c.name for c in t.cols]
        assert len(got) - 1 == m["row_counts"][t.name]
        js = json.loads((d / "json" / f"{t.name}.json").read_text(encoding="utf-8"))
        assert len(js) == len(got) - 1
        for row, rec in zip(got[1:], js):
            assert row == ["" if rec[c.name] is None else str(rec[c.name]) for c in t.cols]
    assert b"\r" not in (d / "csv" / "delivery.csv").read_bytes()


def test_manifest_checksums_match_files(out):
    d, m = out
    assert set(m["files"]) == set(hash_tree(d)) - {"manifest.json", "README.md"}
    for rel, info in m["files"].items():
        assert sha256_file(d / rel) == info["sha256"]
        assert (d / rel).stat().st_size == info["bytes"]
    assert json.loads((d / "manifest.json").read_text()) == m
    assert m["provenance"]["external_data"] == "none" and m["seed"] == SEED


def test_sql_seed_loads_and_matches(out):
    d, m = out
    conn = load_seed_sql(d / "sql" / "seed.sql")
    for name in NAMES:
        assert conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == m["row_counts"][name]
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # only the planted orphan input lots break foreign keys
    assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == m["anomalies"]["ORPHAN_INPUT_LOT"]


def test_ground_truth_kept_apart(out):
    d, _ = out
    for rel in hash_tree(d):
        if rel.startswith(("csv/", "csv_clean/", "json/")) or rel == "sql/seed.sql":
            assert b"ANOM-" not in (d / rel).read_bytes(), rel
    gt = json.loads((d / "ground_truth" / "ground_truth.json").read_text())
    assert len(gt) == sum(json.loads((d / "manifest.json").read_text())["anomalies"].values())


def test_clean_and_shipped_differ_only_where_planted(out):
    _, m = out
    diff = {t for t in NAMES if m["row_counts"][t] != m["clean_row_counts"][t]}
    assert diff == {"recall_action"}


def test_readme_numbers_come_from_manifest(out):
    d, m = out
    text = (d / "README.md").read_text(encoding="utf-8")
    for t, n in m["row_counts"].items():
        assert f"| {t} | {n:,} |" in text
    for k, v in m["anomalies"].items():
        assert f"| {k} | {v} |" in text
    assert "—" not in text and str(d) not in text


def test_no_machine_specific_text(out):
    d, _ = out
    assert str(d.parent) not in (d / "manifest.json").read_text()


def test_regenerate_in_place_and_refuse_foreign_folder(out, tmp_path):
    d, m = out
    assert generate("starter", SEED, d) == m
    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "notes.txt").write_text("keep me")
    with pytest.raises(FileExistsError):
        generate("starter", SEED, foreign)
    assert (foreign / "notes.txt").exists()


def test_seed_changes_output(out, tmp_path):
    d, _ = out
    generate("starter", SEED + 1, tmp_path / "other")
    assert hash_tree(tmp_path / "other") != hash_tree(d)


def test_reproducible_across_processes_starter():
    r = verify("starter")
    assert r["identical"] and r["differences"] == [] and r["files"] == 50


def test_reproducible_across_processes_full():
    r = verify("full")
    assert r["identical"], r["differences"]
    assert r["row_counts"]["delivery"] == 20_000 and r["row_counts"]["supplier"] == 500


def test_committed_starter_data_is_current(out):
    root = Path(__file__).resolve().parent.parent / "data"
    d, _ = out
    assert hash_tree(root / "starter") == hash_tree(d)


def test_committed_full_manifest_is_current(tmp_path):
    root = Path(__file__).resolve().parent.parent / "data"
    m = generate("full", SEED, tmp_path / "full")
    assert json.loads((root / "full_manifest.json").read_text()) == m
