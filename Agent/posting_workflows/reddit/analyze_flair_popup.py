"""
Reddit node: analyze Flair popup content.

Purpose:
    Specifically analyze the content of the open Reddit Flair dialog.

Main responsibilities:
    - Capture the visual state of the flair dialog.
    - Extract candidates using OCR.
    - Use LLM to classify and select the most semantically appropriate flair.

Not responsible for:
    - Opening or closing the Flair dialog.
    - Clicking the selected Flair.
    - Falling back to static rules when OCR or LLM selection fails.
"""

from __future__ import annotations

import time
from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.reddit.node_diagnostics import capture_node_diagnostic


class AnalyzeFlairPopupNode:
    name = "reddit_analyze_flair_popup"

    def run(self, context: Any, state: Any) -> Any:
        capture_node_diagnostic(context, state, node=self.name, stage="before")
        try:
            result_state = self._run(context, state)
        except Exception as exc:
            capture_node_diagnostic(context, state, node=self.name, stage="error", error=exc)
            raise
        capture_node_diagnostic(
            context,
            result_state,
            node=self.name,
            stage="after",
            result={
                "selected_flair": result_state.selected_flair,
                "flair_options": result_state.flair_options,
                "latest_evidence": result_state.evidence[-1].data if result_state.evidence else {},
            },
        )
        return result_state

    def _run(self, context: Any, state: Any) -> Any:
        recognizer = context.reddit_recognizer
        if recognizer is None:
            raise PostingWorkflowError("Recognizer missing", node=self.name, code="recognizer_missing")

        dom_candidates = recognizer.extract_flair_candidates_from_dom()
        candidates = []
        screenshot_path = ""
        source = "none"
        attempted_visual = False
        expanded_all_options = False

        if not recognizer._is_flair_dialog_open():
            if dom_candidates:
                candidates = _filter_required_flair_candidates(dom_candidates, state.flair_required)
                state.flair_options = [dict(candidate) for candidate in candidates]
                source = "dom"
            elif state.flair_required:
                raise PostingWorkflowError(
                    "Flair is required but the Flair popup is not open for analysis",
                    node=self.name,
                    code="required_flair_popup_missing",
                )
            else:
                state.add_evidence(self.name, True, "No flair popup detected to analyze")
                return state
        else:
            print(f"   🔍 [{self.name}] 正在分析标记弹出框内容...")
            if hasattr(recognizer, "expand_all_flair_options"):
                expanded_all_options = bool(recognizer.expand_all_flair_options())
                if expanded_all_options:
                    dom_candidates = recognizer.extract_flair_candidates_from_dom()

            screenshot_path = str(recognizer.screenshot_dir / f"flair_analysis_{int(time.time())}.png")
            recognizer.page.screenshot(path=screenshot_path, full_page=False)

            # Prefer visual extraction when available; keep DOM candidates as
            # evidence-backed fallback instead of fabricating a static choice.
            if hasattr(recognizer, "extract_visible_flair_candidates"):
                attempted_visual = True
                candidates = recognizer.extract_visible_flair_candidates(screenshot_path=screenshot_path)
                source = "visual"

            if not candidates and getattr(recognizer, "ocr_helper", None) is not None:
                ocr_results = recognizer.ocr_helper.recognize_with_position(screenshot_path, lang='chi_sim+eng')
                grouped = recognizer._group_nearby_texts(ocr_results)
                candidates = recognizer._extract_flair_candidates(grouped)
                source = "ocr"

            if not candidates and dom_candidates:
                candidates = dom_candidates
                source = "dom"

            candidates = _filter_required_flair_candidates(candidates, state.flair_required)
            if (
                not candidates
                and getattr(recognizer, "ocr_helper", None) is None
                and not attempted_visual
                and state.flair_required
            ):
                raise PostingWorkflowError(
                    "Flair is required but OCR is unavailable and no DOM Flair candidates were found",
                    node=self.name,
                    code="required_flair_ocr_unavailable",
                    details={"screenshot_path": screenshot_path},
                )

            state.flair_options = [dict(candidate) for candidate in candidates]

        if not candidates:
            print(f"   ⚠️ [{self.name}] 未识别到任何有效的标记选项")
            if state.flair_required:
                raise PostingWorkflowError(
                    "Flair is required but OCR did not find any selectable Flair candidates",
                    node=self.name,
                    code="required_flair_candidates_missing",
                    details={"screenshot_path": screenshot_path},
                )
            state.add_evidence(self.name, False, "No candidates found", screenshot_path=screenshot_path)
            return state

        flair_texts = [str(candidate.get("text") or "").strip() for candidate in candidates if candidate.get("text")]

        # Semantic selection via LLM
        llm = context.require_llm(self.name)
        payload = llm.generate_json(
            prompt=(
                "You are an expert Reddit community manager. Your task is to choose the most appropriate Reddit Flair for the following post. "
                "The target community is r/{subreddit}. "
                "Post Title: {title} "
                "Post Content: {content_preview} "
                "\nAvailable Flair Options (from OCR): {flair_options} "
                "\n\nReturn JSON: {{\"selected_flair\": \"Exact Flair Text\", \"reason\": \"...\"}}"
            ).format(
                subreddit=state.subreddit or "Unknown",
                title=state.title or "Unknown",
                content_preview=(state.content or "")[:500],
                flair_options=flair_texts
            ),
            context={
                "subreddit": state.subreddit,
                "title": state.title,
                "content": state.content,
                "flair_options": flair_texts,
            },
            node=self.name,
            trace_id=context.trace_id,
            phase="reddit_flair_selection",
        )

        state.selected_flair = str(payload.get("selected_flair") or "").strip()
        if not state.selected_flair and state.flair_required:
            raise PostingWorkflowError(
                "LLM did not select a required Reddit Flair",
                node=self.name,
                code="required_flair_llm_selection_missing",
                details={"payload": payload, "flair_options": flair_texts},
            )
        state.add_evidence(
            self.name,
            True,
            "Flair popup content analyzed",
            options=flair_texts,
            selected=state.selected_flair,
            llm_payload=payload,
            screenshot_path=screenshot_path,
            source=source,
            expanded_all_options=expanded_all_options,
        )
        return state


def _filter_required_flair_candidates(candidates: list[dict], flair_required: bool | None) -> list[dict]:
    """Remove Reddit's explicit no-flair choice when the page requires a Flair."""
    if not flair_required:
        return [dict(candidate) for candidate in candidates]

    filtered = []
    for candidate in candidates:
        text = str(candidate.get("text") or "").strip().lower()
        is_none = bool(candidate.get("is_none_option")) or text in {"无标识", "no flair", "none"}
        if not is_none:
            filtered.append(dict(candidate))
    return filtered
