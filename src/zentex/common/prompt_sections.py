from __future__ import annotations

from typing import Any


def build_prompt_section(
    *,
    key: str,
    title: str,
    intent: str,
    purpose: str,
    content: str,
) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "intent": intent,
        "purpose": purpose,
        "content": str(content or "").strip(),
    }


def assemble_prompt_sections(sections: list[dict[str, str]]) -> str:
    rendered: list[str] = []
    for section in sections:
        title = str(section.get("title") or "").strip()
        intent = str(section.get("intent") or "").strip()
        purpose = str(section.get("purpose") or "").strip()
        content = str(section.get("content") or "").strip()

        lines: list[str] = []
        if title:
            lines.append(f"### {title}")
        if intent:
            lines.append(f"[Intent] {intent}")
        if purpose:
            lines.append(f"[Purpose] {purpose}")
        if content:
            lines.append(content)

        block = "\n".join(line for line in lines if line.strip()).strip()
        if block:
            rendered.append(block)
    return "\n\n".join(rendered).strip()


def trim_section_content(value: Any) -> str:
    return str(value or "(empty)").strip()
