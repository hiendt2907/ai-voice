#!/usr/bin/env python3
"""Seed NLU docs straight into Postgres, embeddings included.

Alternative to seed_nlu.py for when the NestJS API can't be authenticated
against (POST /nlu/documents requires a JWT). Embeddings are computed locally
with the same model the worker uses (rag.embedder →
paraphrase-multilingual-MiniLM-L12-v2), so the rows land fully indexed and a
plain `POST /nlu/reload` is enough to pick them up.

Emits SQL to stdout or a file; apply with psql. Idempotent by (label, content):
pass --existing with a JSON export to skip what's already there.

Usage:
    python3 scripts/seed/seed_nlu_sql.py --existing /tmp/nlu_export.json -o /tmp/seed.sql
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "voice"))

DATASET = Path(__file__).with_name("nlu-dataset-vi.json")


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--existing", help="JSON array from /internal/nlu/export, to skip duplicates")
    ap.add_argument("-o", "--out", required=True, help="Write SQL here")
    args = ap.parse_args()

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    wanted: list[tuple[str, str]] = []
    for group in ("intents", "inquiry_intents"):
        for label, examples in data.get(group, {}).items():
            wanted.extend((label, text) for text in examples)

    existing: set[tuple[str, str]] = set()
    if args.existing:
        for doc in json.loads(Path(args.existing).read_text(encoding="utf-8")):
            existing.add((doc["label"], doc["content"]))

    todo = [(lbl, txt) for lbl, txt in wanted if (lbl, txt) not in existing]
    print(f"dataset={len(wanted)} existing={len(existing)} to_insert={len(todo)}", file=sys.stderr)
    if not todo:
        Path(args.out).write_text("-- nothing to insert\n", encoding="utf-8")
        return 0

    from rag.embedder import embed_query  # noqa: PLC0415

    lines = ["BEGIN;"]
    for i, (label, content) in enumerate(todo, 1):
        vec = embed_query(content)
        lines.append(
            'INSERT INTO nlu_documents (type, label, content, meta, "embeddingJson", "isActive") '
            f"VALUES ('intent', {_sql_str(label)}, {_sql_str(content)}, '{{}}'::jsonb, "
            f"{_sql_str(json.dumps(vec))}, true);"
        )
        if i % 50 == 0:
            print(f"  embedded {i}/{len(todo)}", file=sys.stderr)
    lines.append("COMMIT;")

    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(todo)} INSERTs → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
