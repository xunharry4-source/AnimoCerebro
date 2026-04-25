#!/usr/bin/env python3
"""
GitHub Discussions real posting runner.

文件用途:
    使用 Agent/social_promotion/github_smart_poster.py 在真实 GitHub 仓库创建 Discussion，
    并保存 GraphQL 读回验证结果。

主要职责:
    - 从环境变量读取目标仓库、标题、正文、Discussion 分类。
    - 调用 GitHubSmartPoster.create_discussion_with_evidence()。
    - 将成功或失败结果写入 Agent/data/github_discussion_post_last_result.json。

不负责:
    - 不生成或保存 GitHub token。
    - 不在缺少 GITHUB_TOKEN 时伪造成功。
    - 不自动关闭或删除已创建的 Discussion。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from Agent.social_promotion.github_smart_poster import (  # noqa: E402
    DEFAULT_GITHUB_REPOSITORY_URL,
    GitHubPostingError,
    GitHubSmartPoster,
)


RESULT_PATH = Path("Agent/data/github_discussion_post_last_result.json")


def main() -> bool:
    repository = os.environ.get(
        "GITHUB_POST_REPOSITORY",
        f"{DEFAULT_GITHUB_REPOSITORY_URL}/discussions",
    )
    title = os.environ.get("GITHUB_DISCUSSION_TITLE", f"AnimoCerebro GitHub Discussions verification {int(time.time())}")
    body = os.environ.get(
        "GITHUB_DISCUSSION_BODY",
        (
            "This discussion was created by the AnimoCerebro GitHubSmartPoster real runner "
            "and verified through the GitHub GraphQL API."
        ),
    )
    category_name = os.environ.get("GITHUB_DISCUSSION_CATEGORY") or None
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = GitHubSmartPoster().create_discussion_with_evidence(
            repository=repository,
            title=title,
            body=body,
            category_name=category_name,
        )
    except GitHubPostingError as exc:
        result = {
            "success": False,
            "platform": "github",
            "target": "discussions",
            "repository": repository,
            "title": title,
            "category_name": category_name,
            "error": exc.to_dict(),
            "post_url": None,
        }

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"结果文件: {RESULT_PATH}")
    return bool(result.get("success"))


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
