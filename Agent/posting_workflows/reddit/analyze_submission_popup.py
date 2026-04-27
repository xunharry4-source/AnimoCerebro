"""
Reddit node: analyze submission popup content.

Purpose:
    Analyze the popup content that appears immediately after clicking 'Post'.

Main responsibilities:
    - Capture post-submission popups (toasts, alerts).
    - Classify message as 'Success', 'Error', or 'Rate Limit'.
    - Provide structured analysis for the next verification/retry step.

Not responsible for:
    - Submitting the post.
    - Closing or revising after failed submission.
    - Replacing LLM popup interpretation with keyword-only classification.
"""

from __future__ import annotations

from typing import Any

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.reddit.node_diagnostics import capture_node_diagnostic


class AnalyzeSubmissionPopupNode:
    name = "reddit_analyze_submission_popup"

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
                "last_popup_analysis": result_state.last_popup_analysis,
                "latest_evidence": result_state.evidence[-1].data if result_state.evidence else {},
            },
        )
        return result_state

    def _run(self, context: Any, state: Any) -> Any:
        recognizer = context.reddit_recognizer
        if recognizer is None:
            raise PostingWorkflowError(
                "RedditVisualRecognizer is missing in context",
                node=self.name,
                code="recognizer_missing",
            )

        print(f"   🔍 [{self.name}] 正在分析发帖后的弹出框内容...")

        if not hasattr(recognizer, "detect_submission_popup_result"):
            raise PostingWorkflowError(
                "RedditVisualRecognizer cannot detect submission popup results",
                node=self.name,
                code="submission_popup_detector_missing",
            )

        popup_result = recognizer.detect_submission_popup_result(wait_time=2, use_ocr=True)
        if not isinstance(popup_result, dict):
            raise PostingWorkflowError(
                "Submission popup detector returned a non-dict result",
                node=self.name,
                code="submission_popup_detector_invalid_result",
                details={"result_type": type(popup_result).__name__},
            )

        if popup_result.get("status") == "none":
            state.last_popup_analysis = {
                "status": "none",
                "message": "",
                "should_retry": False,
                "needs_flair": False,
                "source": popup_result.get("source", "none"),
            }
            state.add_evidence(
                self.name,
                True,
                "No submission popup detected",
                analysis=state.last_popup_analysis,
                screenshot_path=popup_result.get("screenshot_path"),
            )
            return state

        analysis = {
            "status": popup_result.get("status") or "unknown",
            "message": popup_result.get("message") or "",
            "translated_message_zh": popup_result.get("translated_message_zh"),
            "summary_zh": popup_result.get("summary_zh"),
            "category": popup_result.get("category"),
            "should_retry": bool(popup_result.get("should_retry")),
            "needs_flair": bool(popup_result.get("needs_flair")),
            "recommended_action": popup_result.get("recommended_action"),
            "source": popup_result.get("source"),
            "llm_trace_id": popup_result.get("llm_trace_id"),
            "post_check_modal": popup_result.get("post_check_modal"),
        }
        if analysis["needs_flair"]:
            state.flair_required = True
        print(f"   💬 [{self.name}] 弹窗分析结果: {analysis}")
        state.last_popup_analysis = analysis
        state.add_evidence(
            self.name,
            True,
            "Submission popup analyzed",
            analysis=analysis,
            popup=popup_result,
            screenshot_path=popup_result.get("screenshot_path"),
        )
        return state
