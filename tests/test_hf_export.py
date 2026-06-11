import json

from libpulse.hf_export import build_dataset


def test_build_dataset(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    entries = [
        {"package": "demo", "old_version": "1.0.0", "new_version": "2.0.0", "title": "x"},
        {"package": "demo", "old_version": "2.0.0", "new_version": "3.0.0", "title": "y"},
    ]
    (corpus / "demo.json").write_text(json.dumps({"entries": entries}))

    out = build_dataset(tmp_path / "hf", corpus=corpus)
    lines = (out / "data" / "train.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["package"] == "demo"
    card = (out / "README.md").read_text()
    assert card.startswith("---\nlicense: cc-by-4.0")
    assert "Rows: 2" in card
    assert "Disclaimer" in card
