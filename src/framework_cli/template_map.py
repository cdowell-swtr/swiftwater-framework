"""Best-guess mapping from rendered finding paths back to template-source paths.

Used by `framework template-map` as a triage aid for template audits.
Non-authoritative: it does a
basename-anchored search of the template payload (a template file `foo.py.jinja`
renders to `foo.py`), ranked by path-tail overlap after substituting the rendered
package_name back to `{{package_name}}`. Line numbers are NOT mapped — Jinja
rendering shifts them — so the report carries an explicit caveat.
"""

from __future__ import annotations

import json
from pathlib import Path

_JINJA_SUFFIX = ".jinja"


def _rendered_name(name: str) -> str:
    return name[: -len(_JINJA_SUFFIX)] if name.endswith(_JINJA_SUFFIX) else name


def _template_files_by_basename(template_root: Path) -> dict[str, list[Path]]:
    """Index every template payload file by its *rendered* basename."""
    index: dict[str, list[Path]] = {}
    for p in template_root.rglob("*"):
        if p.is_file():
            index.setdefault(_rendered_name(p.name), []).append(p)
    return index


def _tail_overlap(
    want_parts: list[str], template_path: Path, template_root: Path
) -> int:
    """Count matching trailing path segments between the desired rendered-relative
    path and a candidate template path (with the last segment de-jinja'd)."""
    tparts = list(template_path.relative_to(template_root).parts)
    if tparts:
        tparts[-1] = _rendered_name(tparts[-1])
    n = 0
    for a, b in zip(reversed(want_parts), reversed(tparts)):
        if a == b:
            n += 1
        else:
            break
    return n


def map_finding_path(
    rendered_path: str,
    *,
    package_name: str,
    template_root: Path,
    index: dict[str, list[Path]],
) -> dict:
    """Map one rendered finding path to a best-guess template-source path.

    Returns {'rendered', 'status' in {'unique','candidates','unresolved'},
             'template_source': str|None, 'candidates': [str, ...]}.
    """
    rp = Path(rendered_path)
    cands = index.get(rp.name, [])
    if not cands:
        return {
            "rendered": rendered_path,
            "status": "unresolved",
            "template_source": None,
            "candidates": [],
        }

    want_parts = [
        "{{package_name}}" if seg == package_name else seg for seg in rp.parts
    ]
    scored = sorted(
        cands, key=lambda c: _tail_overlap(want_parts, c, template_root), reverse=True
    )
    rels = [str(c.relative_to(template_root)) for c in scored]
    top = _tail_overlap(want_parts, scored[0], template_root)
    tied = [c for c in scored if _tail_overlap(want_parts, c, template_root) == top]

    if len(cands) == 1 or (len(tied) == 1 and top >= 2):
        return {
            "rendered": rendered_path,
            "status": "unique",
            "template_source": rels[0],
            "candidates": rels,
        }
    return {
        "rendered": rendered_path,
        "status": "candidates",
        "template_source": None,
        "candidates": rels,
    }


def map_findings(
    findings_dir: Path, template_root: Path, package_name: str
) -> list[dict]:
    """Map every finding under findings_dir/*.json. Returns rows for the report."""
    index = _template_files_by_basename(template_root)
    rows: list[dict] = []
    for fp in sorted(findings_dir.glob("*.json")):
        data = json.loads(fp.read_text())
        for f in data.get("findings", []):
            mapped = map_finding_path(
                f.get("path") or "",
                package_name=package_name,
                template_root=template_root,
                index=index,
            )
            rows.append(
                {
                    "agent": data.get("agent"),
                    "line": f.get("line"),
                    "severity": f.get("severity"),
                    **mapped,
                }
            )
    return rows


def render_markdown(rows: list[dict]) -> str:
    """Render the path-map table with the line-number caveat."""
    lines = [
        "# Template-source path map",
        "",
        "> Line numbers are **as-rendered**, not template-source — Jinja shifts them.",
        "> Mappings are best-effort (basename-anchored); verify before triaging.",
        "",
        "| agent | rendered path:line | status | template source / candidates |",
        "|---|---|---|---|",
    ]
    for r in rows:
        line_suffix = f":{r['line']}" if r.get("line") is not None else ""
        loc = f"`{r['rendered']}{line_suffix}`"
        if r["status"] == "unique":
            tgt = f"`{r['template_source']}`"
        elif r["status"] == "candidates":
            tgt = "candidates: " + ", ".join(f"`{c}`" for c in r["candidates"])
        else:
            tgt = "UNRESOLVED"
        lines.append(f"| {r['agent']} | {loc} | {r['status']} | {tgt} |")
    return "\n".join(lines) + "\n"
