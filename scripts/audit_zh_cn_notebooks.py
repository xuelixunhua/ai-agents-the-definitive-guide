#!/usr/bin/env python3
"""Audit Jupyter notebooks for reader-facing English that may still need zh-CN translation.

The audit intentionally ignores saved outputs and focuses on:
- Markdown cells whose prose is still predominantly English.
- Human-facing code comments (including Colab # @title / #@title lines).

The report is conservative: it is an inventory for human review, not an instruction to
translate every English token. API names, identifiers, prompts, URLs, model names and
other behavior-sensitive strings may legitimately remain English.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
COMMENT_RE = re.compile(r"^\s*#(?:\s|@|$).*")


def cell_id(cell: dict[str, Any]) -> str | None:
    return cell.get("id") or cell.get("metadata", {}).get("id")


def source_text(cell: dict[str, Any]) -> str:
    source = cell.get("source", [])
    return "".join(source) if isinstance(source, list) else str(source)


def meaningful_english_markdown(text: str) -> bool:
    stripped = re.sub(r"https?://\S+", "", text)
    stripped = re.sub(r"<[^>]+>", "", stripped)
    latin = len(LATIN_RE.findall(stripped))
    cjk = len(CJK_RE.findall(stripped))
    if latin < 20:
        return False
    # Fully/mostly Chinese cells often retain English technical terms by design.
    if cjk >= 8 and cjk * 2 >= latin:
        return False
    # Skip cells that are essentially badges/links with little prose.
    prose = re.sub(r"[`*_#>\-\[\](){}|]", " ", stripped)
    words = re.findall(r"[A-Za-z]{2,}", prose)
    return len(words) >= 4


def english_comment_lines(text: str) -> list[str]:
    result: list[str] = []
    for line in text.splitlines():
        if not COMMENT_RE.match(line):
            continue
        # Ignore shebangs, commented-out code-ish lines, and bare separators.
        stripped = line.strip()
        if stripped.startswith("#!") or stripped in {"#", "##", "###"}:
            continue
        latin = len(LATIN_RE.findall(stripped))
        cjk = len(CJK_RE.findall(stripped))
        words = re.findall(r"[A-Za-z]{2,}", stripped)
        if latin >= 12 and len(words) >= 3 and not (cjk >= 6 and cjk * 2 >= latin):
            result.append(line)
    return result


def audit_notebook(path: Path) -> dict[str, Any] | None:
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"notebook": path.as_posix(), "error": str(exc), "entries": []}

    entries: list[dict[str, Any]] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        cid = cell_id(cell)
        text = source_text(cell)
        ctype = cell.get("cell_type")
        if ctype == "markdown" and meaningful_english_markdown(text):
            entries.append(
                {
                    "cell_index": index,
                    "cell_id": cid,
                    "cell_type": "markdown",
                    "source": text,
                }
            )
        elif ctype == "code":
            comments = english_comment_lines(text)
            if comments:
                entries.append(
                    {
                        "cell_index": index,
                        "cell_id": cid,
                        "cell_type": "code_comments",
                        "comments": comments,
                    }
                )

    if not entries:
        return None
    return {"notebook": path.as_posix(), "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("zh-cn/audit/english_notebook_inventory.json"),
    )
    args = parser.parse_args()

    root = args.root
    notebooks = sorted(
        p for p in root.rglob("*.ipynb")
        if ".git" not in p.parts and ".ipynb_checkpoints" not in p.parts
    )

    results = []
    for notebook in notebooks:
        audited = audit_notebook(notebook)
        if audited:
            results.append(audited)

    report = {
        "purpose": "Inventory of potentially untranslated reader-facing English. Review before translating behavior-sensitive strings.",
        "notebook_count_scanned": len(notebooks),
        "notebooks_with_candidates": len(results),
        "candidate_entry_count": sum(len(item.get("entries", [])) for item in results),
        "notebooks": results,
    }

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}: {report['candidate_entry_count']} candidate entries")


if __name__ == "__main__":
    main()
