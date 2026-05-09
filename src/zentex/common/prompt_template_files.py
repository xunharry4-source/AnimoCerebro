from __future__ import annotations

import re
from pathlib import Path

_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z0-9_]+)\s*}}")


def read_prompt_template(template_dir: Path, name: str, *, error_prefix: str) -> str:
    path = template_dir / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"{error_prefix}_prompt_template_missing:{path}") from exc


def render_prompt_template(
    template_dir: Path,
    name: str,
    values: dict[str, str],
    *,
    error_prefix: str,
) -> str:
    template = read_prompt_template(template_dir, name, error_prefix=error_prefix)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise RuntimeError(f"{error_prefix}_prompt_template_placeholder_missing:{name}:{key}")
        return values[key]

    return _PLACEHOLDER_RE.sub(replace, template).strip()


def prompt_template_files(template_dir: Path, names: list[str]) -> dict[str, str | list[str]]:
    return {
        "template_dir": str(template_dir),
        "templates": [str(template_dir / name) for name in names],
    }
