"""Collect related SKILL.md files from cloned repositories.

Usage:
  python tools/collect_related_skills.py
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = ROOT / "external_skills"
OUT = ROOT / "related_skills"

KEYWORDS = [
    "python",
    "selenium",
    "playwright",
    "automation",
    "automate",
    "browser",
    "whatsapp",
    "scrape",
    "crawler",
    "agent",
    "workflow",
    "testing",
    "qa",
    "ci",
    "ops",
    "monitor",
    "reliability",
    "debug",
    "error",
    "retry",
    "wait",
    "webdriver",
    "gspread",
    "google sheets",
]

NAME_HINTS = [
    "python",
    "selenium",
    "playwright",
    "automation",
    "browser",
    "whatsapp",
    "testing",
    "agent",
    "workflow",
    "ci",
    "debug",
    "reliability",
    "retry",
    "wait",
    "webdriver",
    "scrape",
    "crawl",
]


@dataclass
class SkillHit:
    source_repo: str
    source_path: Path
    score: int
    matched_keywords: list[str]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def score_skill(path: Path) -> tuple[int, list[str]]:
    rel = path.as_posix().lower()
    score = 0
    matched: list[str] = []

    for hint in NAME_HINTS:
        if hint in rel:
            score += 2
            matched.append(f"name:{hint}")

    try:
        content = normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return 0, []

    for kw in KEYWORDS:
        if kw in content:
            score += 3
            matched.append(f"content:{kw}")

    if "use this skill when" in content:
        score += 2
        matched.append("content:use this skill when")

    return score, matched


def collect_hits() -> list[SkillHit]:
    hits: list[SkillHit] = []
    for skill_file in EXTERNAL.glob("**/SKILL.md"):
        score, matched = score_skill(skill_file)
        if score < 8:
            continue

        try:
            source_repo = skill_file.relative_to(EXTERNAL).parts[0]
        except Exception:
            source_repo = "unknown"

        hits.append(
            SkillHit(
                source_repo=source_repo,
                source_path=skill_file,
                score=score,
                matched_keywords=sorted(set(matched)),
            )
        )

    hits.sort(key=lambda h: (-h.score, h.source_path.as_posix()))
    return hits


def safe_slug(path: Path) -> str:
    return path.as_posix().replace("/", "__").replace("\\", "__")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"

    hits = collect_hits()
    copied = []

    for hit in hits:
        rel_from_external = hit.source_path.relative_to(EXTERNAL)
        dest_name = safe_slug(rel_from_external)
        if not dest_name.endswith(".md"):
            dest_name += ".md"
        dest = OUT / dest_name
        shutil.copy2(hit.source_path, dest)

        copied.append(
            {
                "source_repo": hit.source_repo,
                "source": rel_from_external.as_posix(),
                "destination": dest.name,
                "score": hit.score,
                "matched": hit.matched_keywords,
            }
        )

    index_path.write_text(
        json.dumps(
            {
                "total": len(copied),
                "keywords": KEYWORDS,
                "name_hints": NAME_HINTS,
                "items": copied,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Collected {len(copied)} related skills into: {OUT}")
    print(f"Index: {index_path}")


if __name__ == "__main__":
    main()
