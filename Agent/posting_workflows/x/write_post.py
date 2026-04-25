"""
X node 4: write and submit the post.

Purpose:
    Generate X post content with LLM and submit it through the browser.

Main responsibilities:
    - Ask the active ModelProvider for platform-sized content.
    - Fill the X composer and click the post button inside the composer.
    - Confirm that the click caused a submission transition before moving on.

Not responsible for:
    - Verifying final publication permalink.
    - Choosing the daily topic.
    - Using static template text when the LLM fails.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

from Agent.posting_workflows.errors import PostingWorkflowError


class WriteXPostNode:
    name = "x_write_post"

    TEXTBOX_SELECTORS = (
        'div[role="dialog"] div[role="textbox"][data-testid="tweetTextarea_0"]',
        'div[role="dialog"] div[contenteditable="true"][data-testid="tweetTextarea_0"]',
        'div[role="textbox"][data-testid="tweetTextarea_0"]',
        'div[contenteditable="true"][data-testid="tweetTextarea_0"]',
    )
    POST_BUTTON_SELECTORS = (
        'div[role="dialog"] button[data-testid="tweetButton"]',
        'div[role="dialog"] button[data-testid="tweetButtonInline"]',
        'div[role="dialog"] [role="button"][data-testid="tweetButton"]',
        'div[role="dialog"] [role="button"][data-testid="tweetButtonInline"]',
        'main button[data-testid="tweetButtonInline"]',
        'main [role="button"][data-testid="tweetButtonInline"]',
    )
    SUBMISSION_TIMEOUT_SECONDS = 20.0

    def run(self, context: Any, state: Any) -> Any:
        if not state.topic:
            raise PostingWorkflowError(
                "Daily topic is required before writing X content",
                node=self.name,
                code="missing_topic",
            )
        page = context.require_page(self.name)
        duplicate_contents: list[str] = []
        max_content_attempts = max(1, min(int(getattr(context, "max_retries", 3) or 3), 3))
        for content_attempt in range(1, max_content_attempts + 1):
            state.content = self._generate_content(context, state, avoid_contents=duplicate_contents)
            try:
                submission_evidence = self._fill_and_submit(page, state.content, trace_id=context.trace_id)
            except PostingWorkflowError as exc:
                if self._error_includes_clicked_submit(exc):
                    state.attempts += 1
                if exc.code == "x_duplicate_content_rejected" and content_attempt < max_content_attempts:
                    duplicate_contents.append(state.content)
                    state.add_evidence(
                        self.name,
                        False,
                        "X rejected duplicate content; retrying with new LLM content",
                        content=state.content,
                        error=exc.to_dict(),
                        content_attempt=content_attempt,
                    )
                    continue
                raise
            state.attempts += 1
            state.add_evidence(
                self.name,
                True,
                "X composer submitted and transition confirmed",
                content=state.content,
                submission=submission_evidence,
                content_attempt=content_attempt,
            )
            return state
        raise PostingWorkflowError(
            "X content submission exhausted duplicate retries",
            node=self.name,
            code="x_duplicate_retry_exhausted",
            details={"attempts": max_content_attempts},
        )

    def _generate_content(self, context: Any, state: Any, *, avoid_contents: Iterable[str] = ()) -> str:
        avoid_list = self._recent_x_contents(context) + [
            str(content).strip() for content in avoid_contents if str(content).strip()
        ]
        duplicate_payloads: list[dict[str, Any]] = []
        for generation_attempt in range(1, 4):
            payload = context.require_llm(self.name).generate_json(
                prompt=(
                    "Write one X.com post for the given topic. Return JSON with content only. "
                    "The content must be <= 260 characters, specific, non-spammy, and useful. "
                    "If avoid_recent_contents is not empty, do not reuse its sentences, claims, or wording; "
                    "choose a different concrete angle."
                ),
                context={
                    "topic": state.topic,
                    "topic_details": state.topic_details,
                    "platform": "x",
                    "date": context.today.isoformat(),
                    "generation_attempt": generation_attempt,
                    "avoid_recent_contents": avoid_list[-8:],
                },
                node=self.name,
                trace_id=context.trace_id,
                phase="x_content_generation",
                temperature=0.7,
            )
            content = str(payload.get("content") or payload.get("post") or payload.get("text") or "").strip()
            if not content:
                raise PostingWorkflowError(
                    "LLM did not return X content",
                    node=self.name,
                    code="missing_content",
                    details={"payload": payload},
                )
            if len(content) > 280:
                raise PostingWorkflowError(
                    "X content exceeds 280 characters",
                    node=self.name,
                    code="x_content_too_long",
                    details={"length": len(content)},
                )
            if self._matches_recent_content(content, avoid_list):
                duplicate_payloads.append({"attempt": generation_attempt, "content": content, "payload": payload})
                avoid_list.append(content)
                continue
            return content
        raise PostingWorkflowError(
            "LLM repeatedly generated content matching recent X posts",
            node=self.name,
            code="x_generated_duplicate_content",
            details={"duplicate_payloads": duplicate_payloads[-3:]},
        )

    def _recent_x_contents(self, context: Any, *, limit: int = 8) -> list[str]:
        ledger_path = Path(getattr(context, "ledger_path", Path("Agent/data/social_posting_ledger.json")))
        if not ledger_path.exists():
            return []
        try:
            records = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not read recent X contents from posting ledger: {exc}",
                node=self.name,
                code="x_recent_content_read_failed",
                details={"path": str(ledger_path)},
            ) from exc
        if not isinstance(records, list):
            raise PostingWorkflowError(
                "Posting ledger must be a JSON array when reading recent X contents",
                node=self.name,
                code="x_recent_content_invalid",
                details={"path": str(ledger_path)},
            )
        contents: list[str] = []
        for record in reversed(records):
            if not isinstance(record, dict) or record.get("platform") != "x":
                continue
            data = record.get("data") if isinstance(record.get("data"), dict) else {}
            content = str(data.get("content") or "").strip()
            if content:
                contents.append(content)
            if len(contents) >= limit:
                break
        return list(reversed(contents))

    def _matches_recent_content(self, content: str, recent_contents: Iterable[str]) -> bool:
        normalized = self._normalize_text(content)
        return any(normalized == self._normalize_text(recent) for recent in recent_contents)

    def _normalize_text(self, content: str) -> str:
        return " ".join(str(content or "").lower().split())

    def _fill_and_submit(self, page: Any, content: str, *, trace_id: str = "manual") -> dict[str, Any]:
        self._open_composer(page)
        textbox = self._first_usable_locator(page, self.TEXTBOX_SELECTORS, require_enabled=False)
        if textbox is None:
            raise PostingWorkflowError(
                "Could not find X composer textbox",
                node=self.name,
                code="x_textbox_missing",
            )
        textbox.click()
        textbox.fill(content)
        if hasattr(page, "wait_for_timeout"):
            page.wait_for_timeout(500)
        typeahead_evidence = self._dismiss_typeahead_overlay(page, textbox, content)

        before_snapshot = self._snapshot_submission_state(page, content, stage="before_click")
        before_snapshot["typeahead_dismissal"] = typeahead_evidence
        before_snapshot["screenshot"] = self._capture_screenshot(page, trace_id, "before_submit")
        if not before_snapshot.get("composer_content_visible"):
            raise PostingWorkflowError(
                "X content was not confirmed inside the composer after fill",
                node=self.name,
                code="x_content_not_visible_in_composer",
                details={"snapshot": before_snapshot},
            )

        button = self._first_usable_locator(page, self.POST_BUTTON_SELECTORS, require_enabled=True)
        if button is None:
            disabled_button = self._first_usable_locator(page, self.POST_BUTTON_SELECTORS, require_enabled=False)
            raise PostingWorkflowError(
                "Could not find enabled X post button",
                node=self.name,
                code="x_post_button_missing",
                details={"button_present_but_disabled": bool(disabled_button), "snapshot": before_snapshot},
            )

        diagnostics = {
            "before": before_snapshot,
            "click_attempts": [],
        }
        confirmed = self._click_until_submission_transition(page, button, content, diagnostics)
        after_snapshot = self._snapshot_submission_state(page, content, stage="after_click")
        after_snapshot["screenshot"] = self._capture_screenshot(page, trace_id, "after_submit")
        if not confirmed.get("confirmed") and after_snapshot.get("duplicate_platform_message"):
            confirmed = {
                "confirmed": False,
                "reason": "duplicate_content_rejected",
                "platform_message": after_snapshot["duplicate_platform_message"],
                "observed_stage": "after_click_snapshot",
            }
        diagnostics["after"] = after_snapshot
        diagnostics["confirmed"] = confirmed
        if not confirmed.get("confirmed"):
            error_code = (
                "x_duplicate_content_rejected"
                if confirmed.get("reason") == "duplicate_content_rejected"
                else "x_post_submit_not_confirmed"
            )
            raise PostingWorkflowError(
                "X post button click did not produce a confirmed submission transition",
                node=self.name,
                code=error_code,
                details=diagnostics,
            )
        return diagnostics

    def _click_until_submission_transition(
        self,
        page: Any,
        button: Any,
        content: str,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        methods = (
            ("locator_click", lambda: button.click(timeout=10000)),
            ("page_mouse_center_click", lambda: self._click_button_center(page, button)),
            ("locator_force_click", lambda: button.click(force=True, timeout=5000)),
        )
        for method_name, submit in methods:
            result: dict[str, Any] = {"method": method_name}
            try:
                if hasattr(button, "scroll_into_view_if_needed"):
                    button.scroll_into_view_if_needed(timeout=5000)
                submit()
                result["clicked"] = True
            except Exception as exc:
                result["clicked"] = False
                result["error"] = f"{exc.__class__.__name__}: {str(exc)[:500]}"
                diagnostics["click_attempts"].append(result)
                continue
            confirmed = self._wait_for_submission_transition(page, content)
            result["confirmation"] = confirmed
            diagnostics["click_attempts"].append(result)
            if confirmed.get("confirmed"):
                return confirmed
            if self._is_terminal_submission_rejection(confirmed):
                return confirmed
            fresh_button = self._first_usable_locator(page, self.POST_BUTTON_SELECTORS, require_enabled=True)
            if fresh_button is not None:
                button = fresh_button
        return {"confirmed": False, "reason": "no_submission_transition"}

    def _is_terminal_submission_rejection(self, confirmation: dict[str, Any]) -> bool:
        return confirmation.get("reason") in {"duplicate_content_rejected"}

    def _click_button_center(self, page: Any, button: Any) -> None:
        if not hasattr(button, "bounding_box") or not hasattr(page, "mouse"):
            raise RuntimeError("button bounding box or page mouse is unavailable")
        try:
            box = button.bounding_box(timeout=5000)
        except TypeError:
            box = button.bounding_box()
        if not box:
            raise RuntimeError("button bounding box is empty")
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    def _wait_for_submission_transition(self, page: Any, content: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.SUBMISSION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            visible_status_url = self._find_visible_status_url(page, content)
            if visible_status_url:
                return {
                    "confirmed": True,
                    "reason": "visible_status_url",
                    "status_url": visible_status_url,
                }
            if self._has_sent_toast(page):
                return {"confirmed": True, "reason": "sent_toast_visible"}
            duplicate_message = self._read_duplicate_platform_message(page)
            if duplicate_message:
                return {
                    "confirmed": False,
                    "reason": "duplicate_content_rejected",
                    "platform_message": duplicate_message,
                }
            if not self._is_composer_content_visible(page, content):
                return {"confirmed": True, "reason": "composer_content_cleared_or_closed"}
            if hasattr(page, "wait_for_timeout"):
                page.wait_for_timeout(500)
            else:
                time.sleep(0.5)
        return {"confirmed": False, "reason": "timeout_waiting_for_submission_transition"}

    def _open_composer(self, page: Any) -> None:
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise PostingWorkflowError(
                f"Could not open X composer: {exc}",
                node=self.name,
                code="x_compose_navigation_failed",
            ) from exc

    def _first_usable_locator(self, page: Any, selectors: Iterable[str], *, require_enabled: bool) -> Any:
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            found_disabled = None
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if hasattr(locator, "wait_for"):
                        locator.wait_for(state="visible", timeout=1000)
                    if locator.count() <= 0:
                        continue
                    if hasattr(locator, "is_visible") and not locator.is_visible():
                        continue
                    if require_enabled and hasattr(locator, "is_enabled") and not locator.is_enabled():
                        found_disabled = locator
                        continue
                    return locator
                except Exception:
                    continue
            if not require_enabled and found_disabled is not None:
                return found_disabled
            if hasattr(page, "wait_for_timeout"):
                page.wait_for_timeout(500)
            else:
                time.sleep(0.5)
        return None

    def _snapshot_submission_state(self, page: Any, content: str, *, stage: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "stage": stage,
            "url": str(getattr(page, "url", "") or ""),
            "composer_content_visible": self._is_composer_content_visible(page, content),
            "visible_status_url": self._find_visible_status_url(page, content),
            "sent_toast_visible": self._has_sent_toast(page),
            "duplicate_platform_message": self._read_duplicate_platform_message(page),
            "typeahead_overlay_visible": self._has_typeahead_overlay(page),
            "buttons": [],
        }
        for selector in self.POST_BUTTON_SELECTORS:
            button_state = {"selector": selector}
            try:
                locator = page.locator(selector).first
                count = locator.count()
                button_state["count"] = count
                if count <= 0:
                    snapshot["buttons"].append(button_state)
                    continue
                button_state["visible"] = locator.is_visible() if hasattr(locator, "is_visible") else None
                if button_state["visible"] is False:
                    snapshot["buttons"].append(button_state)
                    continue
                button_state["enabled"] = locator.is_enabled() if hasattr(locator, "is_enabled") else None
                if hasattr(locator, "inner_text"):
                    button_state["text"] = str(locator.inner_text(timeout=1000) or "")[:80]
            except Exception as exc:
                button_state["error"] = f"{exc.__class__.__name__}: {str(exc)[:200]}"
            snapshot["buttons"].append(button_state)
        try:
            snapshot["body_excerpt"] = str(page.locator("body").inner_text(timeout=1000) or "")[:1000]
        except Exception as exc:
            snapshot["body_error"] = f"{exc.__class__.__name__}: {str(exc)[:200]}"
        return snapshot

    def _is_composer_content_visible(self, page: Any, content: str) -> bool:
        if not hasattr(page, "evaluate"):
            return False
        script = """
        (expected) => {
          const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const expectedText = normalize(expected);
          const prefix = expectedText.slice(0, Math.min(80, expectedText.length));
          const nodes = Array.from(document.querySelectorAll(
            'div[role="dialog"] [data-testid="tweetTextarea_0"], ' +
            'div[role="dialog"] div[role="textbox"], ' +
            '[data-testid="tweetTextarea_0"]'
          ));
          return nodes.some((node) => {
            const text = normalize(node.innerText || node.textContent || '');
            return text.includes(expectedText) || text.includes(prefix);
          });
        }
        """
        try:
            return bool(page.evaluate(script, content))
        except Exception:
            return False

    def _dismiss_typeahead_overlay(self, page: Any, textbox: Any, content: str) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "detected_before": self._has_typeahead_overlay(page),
            "actions": [],
        }
        if not evidence["detected_before"]:
            evidence["detected_after"] = False
            return evidence

        # X hashtag suggestions can sit above the composer controls. A real
        # adjacent click matches the manual recovery path and avoids focusing
        # the same hashtag token again.
        for _ in range(2):
            if not self._has_typeahead_overlay(page):
                break
            try:
                if self._click_adjacent_to_textbox(page, textbox):
                    evidence["actions"].append("adjacent_composer_click")
            except Exception as exc:
                evidence["actions"].append(f"adjacent_composer_click_failed:{exc.__class__.__name__}")
            if hasattr(page, "wait_for_timeout"):
                page.wait_for_timeout(300)
            if not self._has_typeahead_overlay(page):
                break
            try:
                if hasattr(page, "keyboard"):
                    page.keyboard.press("Escape")
                    evidence["actions"].append("keyboard_escape")
            except Exception as exc:
                evidence["actions"].append(f"keyboard_escape_failed:{exc.__class__.__name__}")
            if hasattr(page, "wait_for_timeout"):
                page.wait_for_timeout(300)

        if self._has_typeahead_overlay(page):
            try:
                textbox.click(position={"x": 8, "y": 8})
                evidence["actions"].append("textbox_inner_click")
            except Exception as exc:
                evidence["actions"].append(f"textbox_inner_click_failed:{exc.__class__.__name__}")
            if hasattr(page, "wait_for_timeout"):
                page.wait_for_timeout(300)

        evidence["detected_after"] = self._has_typeahead_overlay(page)
        evidence["content_visible_after"] = self._is_composer_content_visible(page, content)
        if evidence["detected_after"]:
            raise PostingWorkflowError(
                "X hashtag/typeahead suggestion overlay did not close",
                node=self.name,
                code="x_typeahead_overlay_not_dismissed",
                details=evidence,
            )
        return evidence

    def _click_adjacent_to_textbox(self, page: Any, textbox: Any) -> bool:
        if not hasattr(page, "mouse"):
            return False
        point = self._find_adjacent_textbox_point(page)
        if point is None and hasattr(textbox, "bounding_box"):
            try:
                box = textbox.bounding_box(timeout=3000)
            except TypeError:
                box = textbox.bounding_box()
            if box:
                point = {"x": box["x"] + box["width"] + 16, "y": box["y"] + min(24, max(8, box["height"] / 2))}
        if point is None:
            return False
        page.mouse.click(point["x"], point["y"])
        return True

    def _find_adjacent_textbox_point(self, page: Any) -> dict[str, float] | None:
        if not hasattr(page, "evaluate"):
            return None
        script = """
        () => {
          const textbox = document.querySelector(
            'div[role="dialog"] [data-testid="tweetTextarea_0"], ' +
            'div[role="dialog"] div[role="textbox"], ' +
            '[data-testid="tweetTextarea_0"]'
          );
          if (!textbox) return null;
          const dialog = textbox.closest('div[role="dialog"]') || textbox.closest('[aria-modal="true"]');
          const textRect = textbox.getBoundingClientRect();
          const dialogRect = (dialog || document.body).getBoundingClientRect();
          const inside = (point, rect, pad = 4) =>
            point.x >= rect.left - pad &&
            point.x <= rect.right + pad &&
            point.y >= rect.top - pad &&
            point.y <= rect.bottom + pad;
          const candidates = [
            { x: Math.min(dialogRect.right - 24, textRect.right + 24), y: textRect.top + 16 },
            { x: dialogRect.left + 24, y: Math.min(dialogRect.bottom - 88, textRect.bottom + 18) },
            { x: dialogRect.right - 24, y: dialogRect.top + 24 }
          ];
          return candidates.find((point) =>
            point.x > 0 &&
            point.y > 0 &&
            point.x < window.innerWidth - 1 &&
            point.y < window.innerHeight - 1 &&
            !inside(point, textRect)
          ) || null;
        }
        """
        try:
            point = page.evaluate(script)
        except Exception:
            return None
        if not isinstance(point, dict):
            return None
        try:
            return {"x": float(point["x"]), "y": float(point["y"])}
        except (KeyError, TypeError, ValueError):
            return None

    def _has_typeahead_overlay(self, page: Any) -> bool:
        if not hasattr(page, "evaluate"):
            return False
        script = """
        () => {
          const selectors = [
            '[data-testid="typeaheadResult"]',
            '[data-testid="typeaheadDropdown"]',
            '[role="listbox"]'
          ];
          const nodes = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
          return nodes.some((node) => {
            const rect = node.getBoundingClientRect();
            const text = String(node.innerText || node.textContent || '');
            const testId = String(node.getAttribute('data-testid') || '');
            const role = String(node.getAttribute('role') || '');
            const typeaheadNode = /typeahead/i.test(testId);
            const listboxSuggestion = role === 'listbox' && text.trim().length > 0;
            return rect.width > 0 && rect.height > 0 && (typeaheadNode || listboxSuggestion);
          });
        }
        """
        try:
            return bool(page.evaluate(script))
        except Exception:
            return False

    def _find_visible_status_url(self, page: Any, content: str) -> str | None:
        if not hasattr(page, "evaluate"):
            return None
        script = """
        (expected) => {
          const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const expectedText = normalize(expected);
          const prefix = expectedText.slice(0, Math.min(80, expectedText.length));
          const matchesExpected = (text) => {
            const normalized = normalize(text);
            return normalized.includes(expectedText) || normalized.includes(prefix);
          };
          const toAbsolute = (href) => {
            try { return new URL(href, window.location.origin).href; } catch (_) { return ''; }
          };
          for (const article of Array.from(document.querySelectorAll('article'))) {
            if (!matchesExpected(article.innerText || article.textContent || '')) continue;
            const href = Array.from(article.querySelectorAll('a[href*="/status/"]'))
              .map((node) => toAbsolute(node.getAttribute('href')))
              .find((candidate) => /https:\\/\\/(x|twitter)\\.com\\/[^/]+\\/status\\/\\d+/.test(candidate));
            if (href) return href;
          }
          return null;
        }
        """
        try:
            recovered = page.evaluate(script, content)
        except Exception:
            return None
        return str(recovered) if recovered else None

    def _has_sent_toast(self, page: Any) -> bool:
        if not hasattr(page, "evaluate"):
            return False
        script = """
        () => {
          const text = String(document.body ? document.body.innerText : '');
          return /Your post was sent|Your Post was sent|Your post has been sent|已发送|已发布|帖子已发送/i.test(text);
        }
        """
        try:
            return bool(page.evaluate(script))
        except Exception:
            return False

    def _read_duplicate_platform_message(self, page: Any) -> str | None:
        if not hasattr(page, "evaluate"):
            return None
        script = """
        () => {
          const text = String(document.body ? document.body.innerText : '');
          const patterns = [
            /Whoops! You already said that\\./i,
            /You already said that/i,
            /你已经说过/i
          ];
          const matched = patterns.find((pattern) => pattern.test(text));
          return matched ? (text.match(matched) || ['duplicate content'])[0] : null;
        }
        """
        try:
            message = page.evaluate(script)
        except Exception:
            return None
        return str(message).strip() if message else None

    def _error_includes_clicked_submit(self, exc: PostingWorkflowError) -> bool:
        click_attempts = exc.details.get("click_attempts")
        if not isinstance(click_attempts, list):
            return False
        return any(isinstance(item, dict) and item.get("clicked") for item in click_attempts)

    def _capture_screenshot(self, page: Any, trace_id: str, stage: str) -> dict[str, Any]:
        screenshot_path = Path("Agent/data") / f"x_write_post_{trace_id}_{stage}.png"
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            return {"path": str(screenshot_path)}
        except Exception as exc:
            return {"error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}
