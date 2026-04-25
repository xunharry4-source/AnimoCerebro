#!/usr/bin/env python3
"""
Reddit popup LLM prompt builder.

Purpose:
    Build the single prompt used to interpret Reddit post-submission popup
    or toast messages across languages and community-specific wording.

Main responsibilities:
    - Define the JSON contract expected from the active ModelProvider.
    - Keep popup interpretation instructions out of browser automation code.

Not responsible for:
    - Calling the LLM provider.
    - Reading Reddit DOM/OCR text.
    - Retrying, editing, or submitting Reddit posts.
"""


def build_reddit_popup_interpretation_prompt() -> str:
    """Return the prompt for interpreting a Reddit submission popup."""
    return """
You interpret Reddit post-submission popup, toast, alert, or dialog text.

The popup may be in English, Chinese, mixed language, or community-specific
wording. Translate its meaning into Chinese and classify the operational result
for the posting workflow. Do not rely on exact keywords only; infer the
semantic meaning from the whole message. Do not invent details that are not in
the message.

Return one JSON object with exactly these fields:
- status: one of "success", "error", "unknown".
- language: short language label such as "en", "zh", "mixed", or "unknown".
- translated_message_zh: faithful Chinese translation or Chinese restatement.
- summary_zh: one sentence Chinese summary for logs.
- category: one of "posted", "flair_required", "title_issue",
  "content_issue", "duplicate", "rate_limit", "permission_denied",
  "moderation_queue", "removed_or_blocked", "captcha_or_auth",
  "network_or_reddit_error", "community_rule", "unknown".
- should_retry: boolean. True only when an automated retry is likely safe.
- needs_flair: boolean. True only when the message says a post flair/tag/category
  is required or missing.
- recommended_action: one of "none", "select_flair", "edit_title",
  "edit_content", "edit_post", "wait_then_retry", "manual_review",
  "login_or_verify", "stop".
- confidence: number from 0 to 1.
- reason: concise English explanation grounded in the popup text.

Classification rules:
- Use "success" only when the text clearly says the post was created,
  submitted, posted, queued successfully, or accepted.
- Use "error" when the text blocks posting, requires a missing field, reports a
  community rule violation, asks the user to retry, or indicates auth/rate/karma
  limitations.
- Use "unknown" when the text is just page chrome, generic help text, or does
  not clearly describe the submission result.
- A moderation queue message can be "success" only if it says the post was
  submitted/queued for review; otherwise classify as "unknown".
""".strip()
