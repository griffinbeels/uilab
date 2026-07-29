"""Read a stylesheet's responsive structure without a CSS parser dependency.

Two jobs: find every size-conditional block, and classify what it styles. Both
feed the viewport matrix and the container-query law.

The one thing this must get right is that a COMMENT IS NOT CODE. Stylesheets
explain themselves by quoting real conditions — "moved out of
`@media (max-width: 760px)` because the pane there is 725px" — and a naive scan
reads that sentence as a block with twelve rules in it. That happened, inflated
a violation count the build depended on, and is why strip_comments() runs first
everywhere and has a test of its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Block:
    kind: str                 # "media" | "container" | "supports"
    condition: str            # "(max-width: 760px)"
    line: int                 # 1-based, within the stylesheet text
    selectors: list[str] = field(default_factory=list)


def strip_comments(css: str) -> str:
    """Blank comments, preserving line numbers (each comment keeps its \\n)."""
    return re.sub(r"/\*.*?\*/",
                  lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)


def blank_comments(css: str) -> str:
    """Blank comments, preserving LENGTH as well — for index-based slicing."""
    return re.sub(r"/\*.*?\*/",
                  lambda m: "".join(c if c == "\n" else " " for c in m.group(0)),
                  css, flags=re.S)


def stylesheet_text(path: Path) -> str:
    """The CSS in `path`: the whole file, or the <style> block if it is HTML."""
    text = path.read_text(encoding="utf-8")
    if "<style>" not in text:
        return text
    start = text.index("<style>") + len("<style>")
    return text[start:text.index("</style>", start)]


def parse_blocks(css: str) -> list[Block]:
    """Every @media/@container/@supports block, brace-matched, with selectors."""
    css = strip_comments(css)
    blocks: list[Block] = []
    for match in re.finditer(r"@(media|container|supports)\s*(\([^{]*)\{", css):
        depth, index = 1, match.end()
        while depth and index < len(css):
            depth += {"{": 1, "}": -1}.get(css[index], 0)
            index += 1
        body = css[match.end():index - 1]
        blocks.append(Block(
            kind=match.group(1),
            condition=match.group(2).strip(),
            line=css[:match.start()].count("\n") + 1,
            selectors=[s.strip() for s in
                       re.findall(r"(?m)^\s*([^@{}/\n][^{}\n]*?)\s*\{", body)]))
    return blocks


def size_blocks(blocks: list[Block]) -> list[Block]:
    """Blocks gated on SIZE, not on a user preference."""
    return [b for b in blocks if "prefers-" not in b.condition]


def thresholds(block: Block) -> list[tuple[str, int]]:
    """Every `(min|max)-(width|height): Npx` in the condition."""
    return [(f"{bound}-{axis}", int(value)) for bound, axis, value in
            re.findall(r"(min|max)-(width|height)\s*:\s*(\d+)px", block.condition)]


def is_shell(selector: str, shell_selectors: tuple[str, ...]) -> bool:
    """True when this selector only ever styles the application shell.

    Judged on the selector's HEAD — the element it is anchored to. A descendant
    like `.mobile-nav .nav-item` is shell because the shell owns where it
    lives; `.detail-grid > .analysis-card` is not, however shell-ish its
    ancestors read.
    """
    if not shell_selectors:
        return True                       # rule disabled for this project
    head = selector.split()[0].split(">")[0].strip()
    if head in ("html", "body", ":root", "*"):
        return True
    return any(name.startswith(prefix)
               for name in re.findall(r"\.([A-Za-z0-9_-]+)", head)
               for prefix in shell_selectors)
