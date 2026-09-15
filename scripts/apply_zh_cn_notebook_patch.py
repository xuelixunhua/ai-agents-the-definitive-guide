#!/usr/bin/env python3
"""Apply a zh-CN translation manifest to a Jupyter Notebook without touching outputs.

The manifest is intentionally keyed by stable notebook cell IDs. Markdown cells are
replaced as whole cells; code cells only allow exact comment-string replacements.
Code logic, prompts, API/class/function names, execution counts, metadata, and saved
outputs are otherwise left unchanged.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _cell_id(cell: dict[str, Any]) -> str | None:
    return cell.get("id") or cell.get("metadata", {}).get("id")


def _source_text(cell: dict[str, Any]) -> str:
    source = cell.get("source", [])
    return "".join(source) if isinstance(source, list) else str(source)


def _to_source_lines(text: str) -> list[str]:
    return text.splitlines(keepends=True) or [""]


def apply_patch(notebook: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    patched = copy.deepcopy(notebook)
    cells = patched.get("cells", [])
    by_id = {_cell_id(cell): cell for cell in cells if _cell_id(cell)}

    expected_notebook = manifest.get("notebook")
    if not expected_notebook:
        raise ValueError("Manifest must declare 'notebook'.")

    for cell_id, translated_text in manifest.get("markdown_cells", {}).items():
        cell = by_id.get(cell_id)
        if cell is None:
            raise KeyError(f"Markdown cell not found: {cell_id}")
        if cell.get("cell_type") != "markdown":
            raise TypeError(f"Cell {cell_id} is not markdown.")
        cell["source"] = _to_source_lines(translated_text)

    for cell_id, replacements in manifest.get("code_comment_replacements", {}).items():
        cell = by_id.get(cell_id)
        if cell is None:
            raise KeyError(f"Code cell not found: {cell_id}")
        if cell.get("cell_type") != "code":
            raise TypeError(f"Cell {cell_id} is not code.")

        source = _source_text(cell)
        for item in replacements:
            old = item["old"]
            new = item["new"]
            if old not in source and new not in source:
                raise ValueError(
                    f"Expected comment not found in {cell_id}: {old!r}"
                )
            if old in source:
                source = source.replace(old, new)
        cell["source"] = _to_source_lines(source)

    return patched


def _assert_invariants(before: dict[str, Any], after: dict[str, Any]) -> None:
    before_cells = before.get("cells", [])
    after_cells = after.get("cells", [])
    if len(before_cells) != len(after_cells):
        raise AssertionError("Cell count changed.")

    for b, a in zip(before_cells, after_cells):
        if _cell_id(b) != _cell_id(a):
            raise AssertionError("Cell order or IDs changed.")
        if b.get("outputs") != a.get("outputs"):
            raise AssertionError(f"Saved outputs changed in cell {_cell_id(b)}")
        if b.get("execution_count") != a.get("execution_count"):
            raise AssertionError(f"Execution count changed in cell {_cell_id(b)}")

        if b.get("cell_type") == "code":
            # Only explicitly declared comment replacements may differ in code cells.
            # The caller has already restricted edits to exact strings.
            if b.get("metadata") != a.get("metadata"):
                raise AssertionError(f"Code metadata changed in cell {_cell_id(b)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    notebook = _load_json(args.notebook)
    manifest = _load_json(args.manifest)

    declared = Path(manifest["notebook"]).as_posix()
    supplied = args.notebook.as_posix()
    if not supplied.endswith(declared):
        raise ValueError(
            f"Manifest targets {declared!r}, but supplied notebook is {supplied!r}."
        )

    patched = apply_patch(notebook, manifest)
    _assert_invariants(notebook, patched)

    output = args.output or args.notebook
    with output.open("w", encoding="utf-8") as f:
        json.dump(patched, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Applied {args.manifest} -> {output}")


if __name__ == "__main__":
    main()
