"""Export two train papers as HTML for the unmodified upstream HTML reader."""

import hashlib
import html
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
data_dir = root / "data" / "t1"
archive = data_dir / "qasper-train-dev-v0.3.tgz"
with tarfile.open(archive) as bundle:
    with bundle.extractfile("qasper-train-v0.3.json") as stream:
        papers = json.load(stream)

manifest = {
    "split": "train",
    "source_url": "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz",
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "papers": [],
}
for paper_id in sorted(papers)[:2]:
    paper = papers[paper_id]
    blocks = [f"<h1>{html.escape(paper['title'])}</h1>"]
    blocks += [f"<p>{html.escape(paper['abstract'])}</p>"]
    for section in paper["full_text"]:
        blocks.append(f"<h2>{html.escape(section['section_name'])}</h2>")
        blocks.extend(f"<p>{html.escape(p)}</p>" for p in section["paragraphs"])
    path = data_dir / f"{paper_id}.html"
    path.write_text("<!doctype html><html><body>" + "\n".join(blocks) + "</body></html>")
    examples = []
    for qa in paper["qas"]:
        for annotation in qa["answers"]:
            answer = annotation["answer"]
            evidence = answer["evidence"]
            if not answer["unanswerable"] and evidence and all(
                "FLOAT SELECTED" not in p for p in evidence
            ):
                examples.append({
                    "question_id": qa["question_id"],
                    "question": qa["question"],
                    "reference": answer,
                })
                break
    manifest["papers"].append({
        "paper_id": paper_id,
        "title": paper["title"],
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "train_examples": examples,
    })
(data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
print(json.dumps({"papers": [{"id": p["paper_id"], "title": p["title"],
    "questions": [q["question"] for q in p["train_examples"]]} for p in manifest["papers"]]},
    indent=2, ensure_ascii=False))
