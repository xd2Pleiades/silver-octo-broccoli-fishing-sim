#!/usr/bin/env python3
"""Dependency-free release gate for Fishing Simulator v13.2.13.

Checks version consistency, docs placement/link targets, conflict markers,
Python compilation, required evidence files, and an optional ZIP archive.
"""
from __future__ import annotations

import argparse
import compileall
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

VERSION = "13.2.13"
REQUIRED_DOCS = (
    "CHANGELOG_V13_2_13.md",
    "V13_2_13_IMPLEMENTATION_STATUS.md",
    "Roadmap_V13_2_Optimized.md",
    "Plan 13.2.xx.md",
    "PLAYER_ASSIST_RESCUE_V13_2_13.md",
    "TEST_RESULTS_V13_2_13.txt",
)

LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
CONFLICT_PREFIXES = ("<<<<<<< ", ">>>>>>> ", "||||||| ")


def markdown_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def local_link_target(link: str) -> str | None:
    link = link.strip().strip("<>")
    if not link or link.startswith("#"):
        return None
    parsed = urlparse(link)
    if parsed.scheme or parsed.netloc:
        return None
    target = parsed.path
    if not target:
        return None
    return unquote(target)


def audit_docs(root: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        return ["missing docs/ directory"], {"markdown_files": 0, "links_checked": 0}
    md_files = markdown_files(root)
    outside = [p for p in md_files if p.parent != docs_dir]
    if outside:
        errors.extend(f"Markdown outside docs/: {p.relative_to(root)}" for p in outside)
    missing = [name for name in REQUIRED_DOCS if not (docs_dir / name).is_file()]
    errors.extend(f"missing required release document: docs/{name}" for name in missing)
    links_checked = 0
    for source in md_files:
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"Markdown is not UTF-8: {source.relative_to(root)}")
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if any(line.startswith(prefix) for prefix in CONFLICT_PREFIXES):
                errors.append(f"merge conflict marker: {source.relative_to(root)}:{line_no}")
            for raw in LINK_PATTERN.findall(line):
                target = local_link_target(raw)
                if target is None:
                    continue
                links_checked += 1
                dest = (source.parent / target).resolve()
                try:
                    dest.relative_to(root.resolve())
                except ValueError:
                    errors.append(f"link escapes project: {source.relative_to(root)}:{line_no} -> {raw}")
                    continue
                if not dest.exists():
                    errors.append(f"broken local link: {source.relative_to(root)}:{line_no} -> {raw}")
    return errors, {"markdown_files": len(md_files), "links_checked": links_checked}


def check_version(root: Path) -> list[str]:
    errors = []
    init_file = root / "fishing_sim" / "__init__.py"
    if not init_file.is_file():
        return ["missing fishing_sim/__init__.py"]
    text = init_file.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*[\"\']([^\"\']+)', text, re.M)
    if not match:
        return ["cannot parse package version"]
    if match.group(1) != VERSION:
        errors.append(f"package version is {match.group(1)}, expected {VERSION}")
    changelog = root / "docs" / f"CHANGELOG_V13_2_{VERSION.split('.')[-1]}.md"
    if changelog.exists() and f"v{VERSION}" not in changelog.read_text(encoding="utf-8").lower():
        errors.append("changelog does not mention the release version")
    return errors


def check_archive(archive: Path, root: Path) -> list[str]:
    errors = []
    if not archive.is_file():
        return [f"archive not found: {archive}"]
    try:
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
            if bad:
                errors.append(f"ZIP CRC failure: {bad}")
            names = zf.namelist()
            md = [n for n in names if n.lower().endswith(".md")]
            outside = [n for n in md if Path(n).parent.as_posix() != "docs"]
            if outside:
                errors.append(f"archive has Markdown outside docs/: {outside[:5]}")
            if not any(n == "fishing_sim/__init__.py" for n in names):
                errors.append("archive missing fishing_sim/__init__.py")
            archived_version = zf.read("fishing_sim/__init__.py").decode("utf-8")
            match = re.search(r'^__version__\s*=\s*[\"\']([^\"\']+)', archived_version, re.M)
            if not match or match.group(1) != VERSION:
                errors.append("archive package version does not match expected release")
            if "docs/CHANGELOG_V13_2_13.md" not in names:
                errors.append("archive missing v13.2.13 changelog")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        errors.append(f"cannot inspect ZIP: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--skip-compile", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    errors = check_version(root)
    doc_errors, counts = audit_docs(root)
    errors.extend(doc_errors)
    print(f"Version: expected {VERSION}")
    print(f"Docs: {counts['markdown_files']} Markdown files; {counts['links_checked']} local links checked")
    if not args.skip_compile:
        ok = compileall.compile_dir(str(root / "fishing_sim"), quiet=1)
        ok = compileall.compile_dir(str(root / "tools"), quiet=1) and ok
        ok = compileall.compile_file(str(root / "run_fishing_sim.py"), quiet=1) and ok
        if not ok:
            errors.append("Python compilation failed")
        else:
            print("Compilation: PASS")
    if args.archive:
        errors.extend(check_archive(args.archive.resolve(), root))
        if not errors:
            print("Archive: PASS")
    if errors:
        print("RELEASE GATE: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    print("RELEASE GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
