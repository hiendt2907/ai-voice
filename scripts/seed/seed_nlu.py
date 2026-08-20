#!/usr/bin/env python3
"""Seed the NLU store from nlu-dataset-vi.json.

Idempotent: skips (label, content) pairs that already exist, so it is safe to
re-run after editing the dataset. Newly inserted rows get embedded by asking
the voice worker to compute the vector — inserting a row without an embedding
leaves it invisible to vector NLU, since the store only indexes embedded docs.

Usage:
    python3 scripts/seed/seed_nlu.py --api-url http://localhost:13001/api/v1 \
                                     --voice-url http://127.0.0.1:18000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import urllib.error
import urllib.request

DATASET = Path(__file__).with_name("nlu-dataset-vi.json")


def _post(url: str, payload: dict, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read() or "{}")


def _get(url: str, timeout: float = 30.0) -> list:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read() or "[]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", required=True, help="NestJS base, e.g. http://localhost:13001/api/v1")
    ap.add_argument("--voice-url", required=True, help="Voice worker base, e.g. http://127.0.0.1:18000")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    wanted: list[tuple[str, str]] = []
    for group in ("intents", "inquiry_intents"):
        for label, examples in data.get(group, {}).items():
            wanted.extend((label, text) for text in examples)

    existing_docs = _get(f"{args.api_url}/internal/nlu/export")
    existing = {(d["label"], d["content"]) for d in existing_docs}
    print(f"Đã có trong store: {len(existing_docs)} docs")

    todo = [(lbl, txt) for lbl, txt in wanted if (lbl, txt) not in existing]
    print(f"Dataset: {len(wanted)} mẫu → cần thêm {len(todo)}")

    if args.dry_run:
        by_label: dict[str, int] = {}
        for lbl, _ in todo:
            by_label[lbl] = by_label.get(lbl, 0) + 1
        for lbl, n in sorted(by_label.items()):
            print(f"  + {lbl:22s} {n}")
        return 0

    added = 0
    for label, content in todo:
        try:
            doc = _post(
                f"{args.api_url}/nlu/documents",
                {"type": "intent", "label": label, "content": content},
            )
        except urllib.error.HTTPError as exc:
            print(f"  ! {label}: {content!r} → HTTP {exc.code} {exc.read()[:200]!r}")
            continue
        doc_id = doc.get("id")
        if doc_id:
            # Without this the row exists but carries no vector, so vector NLU
            # never sees it.
            try:
                _post(f"{args.voice_url}/nlu/embed", {"doc_id": doc_id, "content": content})
            except Exception as exc:  # noqa: BLE001
                print(f"  ! embed {doc_id} thất bại: {exc}")
        added += 1

    print(f"Đã thêm {added} mẫu")
    reloaded = _post(f"{args.voice_url}/nlu/reload", {})
    print(f"NLU store reload: {reloaded}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
