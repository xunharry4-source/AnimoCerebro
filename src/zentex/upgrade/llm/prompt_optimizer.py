from __future__ import annotations

from collections.abc import Callable
import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from zentex.foundation.specs.model_provider import ModelProviderCallerContext
from zentex.llm.gateway import LLMGateway
from zentex.upgrade.llm.models import LLMUpgradeCandidate


class SectionAwarePromptOptimizerRunner:
    """File-backed prompt optimizer runner with section-level guardrails."""

    def __init__(
        self,
        *,
        section_mutator: Callable[[dict[str, Any]], dict[str, Any]] = None,
        write_back: bool = True,
    ) -> None:
        self._section_mutator = section_mutator
        self._write_back = write_back

    def __call__(self, candidate: LLMUpgradeCandidate) -> dict[str, Any]:
        metadata = self._candidate_metadata(candidate)
        prompt_file_path = Path(str(metadata.get("prompt_file_path") or "").strip())
        if not str(prompt_file_path):
            raise RuntimeError("Prompt optimization candidate is missing prompt_file_path metadata.")
        if not prompt_file_path.exists():
            raise RuntimeError(f"Prompt optimization target does not exist: {prompt_file_path}")
        if self._section_mutator is None:
            raise RuntimeError(
                "Section-aware prompt optimization requires a real section mutator; "
                "rule-based fallback is not allowed."
            )

        source_text = prompt_file_path.read_text(encoding="utf-8")
        prompt_contract = metadata.get("prompt_contract")
        if not isinstance(prompt_contract, dict):
            raise RuntimeError("Prompt optimization candidate is missing prompt_contract metadata.")

        editable_sections = {
            str(item).strip()
            for item in prompt_contract.get("editable_prompt_sections", [])
            if str(item).strip()
        }
        immutable_sections = {
            str(item).strip()
            for item in prompt_contract.get("immutable_prompt_sections", [])
            if str(item).strip()
        }
        known_sections = set(extract_prompt_section_map(source_text))
        unknown_sections = (Union[editable_sections, immutable_sections]) - known_sections
        if unknown_sections:
            raise RuntimeError(
                f"Prompt contract references sections not found in source: {sorted(unknown_sections)}"
            )

        mutation_result = self._section_mutator(
            {
                "candidate": candidate,
                "metadata": metadata,
                "prompt_contract": prompt_contract,
                "source_text": source_text,
                "known_sections": sorted(known_sections),
                "editable_sections": sorted(editable_sections),
                "immutable_sections": sorted(immutable_sections),
            }
        )
        optimized_text = str(mutation_result.get("optimized_text") or "")
        edited_section_keys = {
            str(item).strip()
            for item in mutation_result.get("edited_section_keys", [])
            if str(item).strip()
        }

        unknown_edited = edited_section_keys - known_sections
        if unknown_edited:
            raise RuntimeError(f"Prompt optimization attempted unknown prompt sections: {sorted(unknown_edited)}")
        immutable_edited = edited_section_keys & immutable_sections
        if immutable_edited:
            raise RuntimeError(
                f"Prompt optimization attempted immutable prompt sections: {sorted(immutable_edited)}"
            )
        non_editable = edited_section_keys - editable_sections
        if non_editable:
            raise RuntimeError(
                f"Prompt optimization attempted sections outside editable scope: {sorted(non_editable)}"
            )
        if edited_section_keys and optimized_text == source_text:
            raise RuntimeError("Prompt optimization reported section edits but produced no source change.")

        if self._write_back:
            prompt_file_path.write_text(optimized_text, encoding="utf-8")

        return {
            "status": "prompt-updated",
            "modified_files": [str(prompt_file_path)],
            "prompt_guardrails": {
                "preserved_intent": True,
                "forbidden_change_violations": [],
                "edited_section_keys": sorted(edited_section_keys),
                "editable_prompt_sections": sorted(editable_sections),
                "immutable_prompt_sections": sorted(immutable_sections),
            },
            "candidate_prompt_bundle": {
                "updated_file": str(prompt_file_path),
                "edited_section_keys": sorted(edited_section_keys),
                "known_sections": sorted(known_sections),
                "notes": list(mutation_result.get("notes", []))
                if isinstance(mutation_result.get("notes"), list)
                else [],
            },
        }

    def _candidate_metadata(self, candidate: LLMUpgradeCandidate) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if isinstance(candidate.execution_plan.metadata, dict):
            metadata.update(candidate.execution_plan.metadata)
        if isinstance(candidate.metadata, dict):
            metadata.update(candidate.metadata)
        return metadata

class LLMSectionContentMutator:
    """LLM-backed mutator that rewrites only prompt section content expressions."""

    def __init__(
        self,
        *,
        gateway: Optional[LLMGateway] = None,
        model: Optional[str] = None,
        provider_key: Optional[str] = None,
    ) -> None:
        self._gateway = gateway or LLMGateway()
        self._model = model
        self._provider_key = provider_key

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate = payload.get("candidate")
        if not isinstance(candidate, LLMUpgradeCandidate):
            raise RuntimeError("LLM section mutator requires a valid LLMUpgradeCandidate.")
        prompt_contract = payload.get("prompt_contract")
        if not isinstance(prompt_contract, dict):
            raise RuntimeError("LLM section mutator requires prompt_contract.")

        source_text = str(payload.get("source_text") or "")
        editable_sections = {
            str(item).strip() for item in payload.get("editable_sections", []) if str(item).strip()
        }
        immutable_sections = {
            str(item).strip() for item in payload.get("immutable_sections", []) if str(item).strip()
        }
        section_map = extract_prompt_section_map(source_text)

        updated_source = source_text
        offset = 0
        edited_section_keys: list[str] = []
        notes: list[str] = []
        section_policy = {
            str(item.get("section_key") or "").strip(): item
            for item in prompt_contract.get("section_change_policy", [])
            if isinstance(item, dict) and str(item.get("section_key") or "").strip()
        }

        for section_key in sorted(editable_sections):
            section = section_map.get(section_key)
            if section is None:
                continue
            policy = section_policy.get(section_key, {})
            response = self._gateway.invoke_generate_json(
                prompt=self._build_section_prompt(
                    candidate=candidate,
                    section=section,
                    policy=policy,
                    immutable_sections=sorted(immutable_sections),
                ),
                context={
                    "question_id": prompt_contract.get("question_id"),
                    "expected_output_key": prompt_contract.get("expected_output_key"),
                    "section": {
                        "key": section["key"],
                        "title": section["title"],
                        "intent": section["intent"],
                        "purpose": section["purpose"],
                        "content_source": section["content_source"],
                    },
                    "policy": policy,
                    "immutable_intent": payload.get("metadata", {}).get("immutable_intent"),
                    "forbidden_prompt_changes": payload.get("metadata", {}).get("forbidden_prompt_changes", []),
                },
                caller_context=ModelProviderCallerContext(
                    source_module="llm_prompt_optimizer",
                    invocation_phase="nine_question_prompt_section_upgrade",
                    question_driver_refs=[str(prompt_contract.get("question_id") or "")],
                    decision_id=f"{candidate.program_id}:{section_key}",
                ),
                provider_key=self._provider_key,
                model=self._model,
                system_prompt=(
                    "You optimize a single prompt section. "
                    "You must preserve the original question intent and only rewrite the section content expression. "
                    "Return JSON only."
                ),
                temperature=0.0,
                max_output_tokens=1200,
            )
            output = response.output
            new_content_source = str(output.get("content_source") or "").strip()
            if not new_content_source:
                continue
            self._validate_content_source(new_content_source)
            if new_content_source == section["content_source"]:
                continue

            start = int(section["content_start"]) + offset
            end = int(section["content_end"]) + offset
            updated_source = updated_source[:start] + new_content_source + updated_source[end:]
            delta = len(new_content_source) - (end - start)
            offset += delta
            edited_section_keys.append(section_key)
            note = str(output.get("note") or "").strip()
            if note:
                notes.append(f"{section_key}: {note}")

        return {
            "optimized_text": updated_source,
            "edited_section_keys": edited_section_keys,
            "notes": notes,
        }

    @staticmethod
    def _build_section_prompt(
        *,
        candidate: LLMUpgradeCandidate,
        section: dict[str, Any],
        policy: dict[str, Any],
        immutable_sections: list[str],
    ) -> str:
        return (
            "Rewrite only the Python source expression used by this prompt section's `content=` field.\n"
            "Do not rewrite key/title/intent/purpose.\n"
            "Return JSON with:\n"
            '- `content_source`: a valid Python expression string for `content=`\n'
            '- `note`: short summary of what improved\n\n'
            f"Candidate objective: {candidate.objective_summary}\n"
            f"Section key: {section['key']}\n"
            f"Section title: {section['title']}\n"
            f"Section intent: {section['intent']}\n"
            f"Section purpose: {section['purpose']}\n"
            f"Current content source:\n{section['content_source']}\n\n"
            f"Immutable sections: {immutable_sections}\n"
            f"Section policy: {policy}\n"
            "Constraints:\n"
            "- keep the original question meaning intact\n"
            "- keep the same section purpose\n"
            "- do not reference sections outside the existing prompt contract\n"
            "- prefer clearer, tighter, lower-noise wording\n"
            "- output only a replacement Python expression for content=\n"
        )

    @staticmethod
    def _validate_content_source(content_source: str) -> None:
        try:
            ast.parse(content_source, mode="eval")
        except SyntaxError as exc:
            raise RuntimeError(f"LLM section mutator returned invalid Python expression: {exc}") from exc


def extract_prompt_section_map(source_text: str) -> dict[str, dict[str, Any]]:
    """Extract build_prompt_section call metadata from Python source."""
    tree = ast.parse(source_text)
    sections: dict[str, dict[str, Any]] = {}
    source_lines = source_text.splitlines(keepends=True)
    line_offsets: list[int] = []
    running = 0
    for line in source_lines:
        line_offsets.append(running)
        running += len(line)

    def _abs_pos(lineno: int, col: int) -> int:
        return line_offsets[lineno - 1] + col

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "build_prompt_section":
            continue
        keyword_map = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        key_node = keyword_map.get("key")
        title_node = keyword_map.get("title")
        intent_node = keyword_map.get("intent")
        purpose_node = keyword_map.get("purpose")
        content_node = keyword_map.get("content")
        if not all([key_node, title_node, intent_node, purpose_node, content_node]):
            continue
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        if not isinstance(title_node, ast.Constant) or not isinstance(title_node.value, str):
            continue
        if not isinstance(intent_node, ast.Constant) or not isinstance(intent_node.value, str):
            continue
        if not isinstance(purpose_node, ast.Constant) or not isinstance(purpose_node.value, str):
            continue

        content_start = _abs_pos(content_node.lineno, content_node.col_offset)
        content_end = _abs_pos(content_node.end_lineno, content_node.end_col_offset)
        key = str(key_node.value)
        sections[key] = {
            "key": key,
            "title": str(title_node.value),
            "intent": str(intent_node.value),
            "purpose": str(purpose_node.value),
            "content_source": source_text[content_start:content_end],
            "content_start": content_start,
            "content_end": content_end,
        }
    return sections
