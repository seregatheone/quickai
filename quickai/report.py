from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from . import query


def write_html_report(
    db_path: Path,
    *,
    output: Path | None = None,
    project: str | None = None,
) -> Path:
    output = output or db_path.with_name("quickai-report.html")
    output.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "stats": query.stats(db_path, project=project),
        "projects": query.projects(db_path),
        "models": query.models(db_path),
        "tools": query.tools(db_path, project=project),
        "sessions": query.list_sessions(db_path, project=project, by="tokens", limit=100),
        "slow": query.list_sessions(db_path, project=project, by="time", limit=20),
    }
    output.write_text(render_html(data, project=project), encoding="utf-8")
    return output


def render_html(data: dict[str, Any], *, project: str | None = None) -> str:
    stats = data["stats"]
    title = "quickai Codex report" + (f" - {project}" if project else "")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101214;
      --panel: #181b1f;
      --panel2: #20242a;
      --text: #f2f4f7;
      --muted: #aeb6c2;
      --line: #343a44;
      --accent: #62c4a4;
      --warn: #e6b450;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header, main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    header {{ padding-top: 36px; }}
    h1 {{ margin: 0 0 6px; font-size: 32px; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; letter-spacing: 0; }}
    .muted {{ color: var(--muted); }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 10px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); background: var(--panel2); font-weight: 600; }}
    tr:last-child td {{ border-bottom: 0; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .title {{ max-width: 520px; }}
    .accent {{ color: var(--accent); }}
    .warn {{ color: var(--warn); }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div class="muted">Generated {escape(generated_at)} from local derived SQLite data.</div>
  </header>
  <main>
    <section class="cards">
      {card("Sessions", fmt_int(stats["sessions"]))}
      {card("Projects", fmt_int(stats["projects"]))}
      {card("Tokens", fmt_int(stats["total_tokens"]))}
      {card("Cache read", fmt_int(stats["cached_input_tokens"]))}
      {card("Output", fmt_int(stats["output_tokens"]))}
      {card("Wall time", fmt_duration(stats["wall_ms"]))}
      {card("Tool calls", fmt_int(stats["tool_calls"]))}
      {card("Rate limit", fmt_rate(stats))}
    </section>
    {section_table("Projects", data["projects"], ["name", "sessions", "total_tokens", "wall_ms", "tool_calls"])}
    {section_table("Models", data["models"], ["name", "sessions", "total_tokens", "wall_ms", "tool_calls"])}
    {section_table("Tools", data["tools"], ["name", "calls", "errors", "sessions"])}
    {section_table("Slow Sessions", data["slow"], ["session_id", "project", "title", "wall_ms", "total_tokens", "tool_call_count"])}
    {section_table("Top Sessions", data["sessions"], ["session_id", "project", "title", "model", "total_tokens", "wall_ms", "tool_call_count"])}
  </main>
</body>
</html>
"""


def card(label: str, value: str) -> str:
    return f'<div class="card"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div></div>'


def section_table(title: str, rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return f"<h2>{escape(title)}</h2><p class=\"muted\">No data.</p>"
    head = "".join(f"<th>{escape(humanize(column))}</th>" for column in columns)
    body = "\n".join(
        "<tr>"
        + "".join(
            f"<td class=\"{cell_class(column)}\">{format_cell(column, row.get(column))}</td>"
            for column in columns
        )
        + "</tr>"
        for row in rows
    )
    return f"<h2>{escape(title)}</h2><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def format_cell(column: str, value: Any) -> str:
    if value is None:
        return ""
    if column.endswith("tokens") or column in {"sessions", "calls", "errors", "tool_calls", "tool_call_count"}:
        return escape(fmt_int(value))
    if column == "wall_ms":
        return escape(fmt_duration(value))
    return escape(str(value))


def cell_class(column: str) -> str:
    if column.endswith("tokens") or column in {"sessions", "calls", "errors", "tool_calls", "tool_call_count", "wall_ms"}:
        return "num"
    if column == "title":
        return "title"
    return ""


def humanize(value: str) -> str:
    return value.replace("_", " ").title()


def fmt_int(value: Any) -> str:
    return f"{int(value or 0):,}"


def fmt_duration(ms: Any) -> str:
    seconds = int((ms or 0) / 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def fmt_rate(stats: dict[str, Any]) -> str:
    primary = stats.get("primary_used_percent")
    secondary = stats.get("secondary_used_percent")
    parts = []
    if primary is not None:
        parts.append(f"P {primary:g}%")
    if secondary is not None:
        parts.append(f"S {secondary:g}%")
    return " / ".join(parts) if parts else "n/a"
