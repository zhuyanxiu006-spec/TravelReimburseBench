#!/usr/bin/env python3
"""Check frozen ground truth, PNG layout/dimensions and release checksums."""
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(root, check_hashes=True):
    gt_path = root / "gt/cases.jsonl"
    records = [json.loads(s) for s in gt_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    gold = {r["case_id"]: r for r in records}
    if len(records) != 540 or len(gold) != 540:
        raise ValueError("Expected 540 unique cases")
    if Counter(r["gold_action"] for r in records) != Counter(process=180, defer=180, reject=180):
        raise ValueError("Unexpected action distribution")
    if Counter(r["subset"] for r in records) != Counter(S1=180, S2=180, S3=180):
        raise ValueError("Unexpected scenario distribution")
    if Counter((r["subset"], r["gold_action"]) for r in records) != Counter({(s, a): 60 for s in ("S1", "S2", "S3") for a in ("process", "defer", "reject")}):
        raise ValueError("Expected 60 cases per scenario/action combination")
    files = sorted(p for p in (root / "data").rglob("*") if p.is_file())
    if len(files) != 3087 or any(p.suffix.lower() != ".png" for p in files):
        raise ValueError("Expected exactly 3,087 PNG files and no other data files")
    seen = Counter()
    for path in files:
        parts = path.relative_to(root / "data").parts
        if len(parts) != 4 or parts[2] != "png" or parts[1] not in gold:
            raise ValueError(f"Unexpected evidence path: {path}")
        if gold[parts[1]]["subset"] != parts[0]:
            raise ValueError(f"Scenario mismatch: {path}")
        with path.open("rb") as handle:
            header = handle.read(24)
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            raise ValueError(f"Invalid PNG header: {path}")
        if struct.unpack(">II", header[16:24]) != (1191, 794):
            raise ValueError(f"Unexpected PNG dimensions: {path}")
        seen[parts[1]] += 1
    if set(seen) != set(gold):
        raise ValueError("Evidence/GT case sets differ")
    manifest = json.loads((root / "release_manifest.json").read_text(encoding="utf-8"))
    if check_hashes:
        for item in manifest["files"]:
            relative = Path(item["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe manifest path")
            path = root / relative
            if not path.is_file() or sha256(path) != item["sha256"]:
                raise ValueError(f"Checksum mismatch or missing file: {relative}")
    return {"cases": len(gold), "pngs": len(files), "dimensions": [1191, 794],
            "gt_sha256": sha256(gt_path), "manifest_files": len(manifest["files"]),
            "checksums_verified": check_hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-hashes", action="store_true", help="Check layout only after intentionally editing release files.")
    args = parser.parse_args()
    print(json.dumps(validate(args.root.resolve(), not args.skip_hashes), indent=2))


if __name__ == "__main__":
    main()
