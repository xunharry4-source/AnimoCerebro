#!/usr/bin/env python3
"""
GitHub Discussions posting workflow contract tests.

文件用途:
    验证 GitHub Discussions 发帖模块、URL 闸门和节点证据链，不触碰真实 GitHub API。

主要职责:
    - 覆盖正常创建 Discussion 后 GraphQL 读回验证。
    - 覆盖缺 token、无效 URL、缺验证证据等失败路径。
    - 明确这些测试是非真实运行结果，不作为 GitHub Discussions 发帖成功证据。

不负责:
    - 不创建真实 GitHub Discussion。
    - 不检查真实仓库权限。
    - 不伪造 Agent/data/real_posting_success_evidence.json。
"""

import json
from pathlib import Path

import pytest

from Agent.posting_workflows.errors import PostingWorkflowError
from Agent.posting_workflows.github.submit_discussion import SubmitGitHubDiscussionNode
from Agent.posting_workflows.github.update_document import UpdateGitHubPostingDocumentNode
from Agent.posting_workflows.github.verify_success import VerifyGitHubDiscussionSuccessNode
from Agent.posting_workflows.state import GitHubPostingState, WorkflowContext
from Agent.posting_workflows.verification_gate import is_platform_post_url
from Agent.social_promotion.github_smart_poster import GitHubPostingError, GitHubSmartPoster


DISCUSSION_URL = "https://github.com/xunharry4-source/AnimoCerebro/discussions/7"


def _repository_info_payload():
    return {
        "data": {
            "repository": {
                "id": "repo-1",
                "nameWithOwner": "xunharry4-source/AnimoCerebro",
                "discussionCategories": {
                    "nodes": [
                        {
                            "id": "category-1",
                            "name": "General",
                            "description": "General project discussion",
                            "isAnswerable": False,
                            "emoji": "",
                        }
                    ]
                },
            }
        }
    }


def test_github_smart_poster_normal_creates_discussion_and_verifies_fixture():
    calls = []

    def transport(method, url, headers, body):
        calls.append({"method": method, "url": url, "headers": headers, "body": body})
        assert headers["Authorization"] == "Bearer test-token"
        payload = json.loads(body.decode("utf-8"))
        query = payload["query"]
        variables = payload["variables"]
        if "DiscussionRepositoryInfo" in query:
            return 200, _repository_info_payload()
        if "CreateDiscussion" in query:
            assert variables["title"] == "Project update"
            assert variables["body"] == "Useful body"
            assert variables["categoryId"] == "category-1"
            return 200, {
                "data": {
                    "createDiscussion": {
                        "clientMutationId": "trace-github-test",
                        "discussion": {
                            "id": "discussion-7",
                            "number": 7,
                            "title": "Project update",
                            "body": "Useful body",
                            "url": DISCUSSION_URL,
                            "createdAt": "2026-04-25T00:00:00Z",
                            "category": {"id": "category-1", "name": "General"},
                            "repository": {"nameWithOwner": "xunharry4-source/AnimoCerebro"},
                        },
                    }
                }
            }
        return 200, {
            "data": {
                "repository": {
                    "nameWithOwner": "xunharry4-source/AnimoCerebro",
                    "discussion": {
                        "id": "discussion-7",
                        "number": 7,
                        "title": "Project update",
                        "body": "Useful body",
                        "url": DISCUSSION_URL,
                        "createdAt": "2026-04-25T00:00:00Z",
                        "category": {"id": "category-1", "name": "General"},
                    },
                }
            }
        }

    result = GitHubSmartPoster(token="test-token", transport=transport).create_discussion_with_evidence(
        repository="https://github.com/xunharry4-source/AnimoCerebro/discussions",
        title="Project update",
        body="Useful body",
        category_name="General",
        trace_id="trace-github-test",
    )

    assert result["success"] is True
    assert result["post_url"] == DISCUSSION_URL
    assert result["verification_source"] == "github_graphql_discussion_get"
    assert result["active_evidence"]["title_match"] is True
    assert [call["method"] for call in calls] == ["POST", "POST", "POST"]


def test_github_smart_poster_abnormal_missing_token_is_fail_closed_fixture():
    poster = GitHubSmartPoster(token="", transport=lambda *args: (500, {}))

    with pytest.raises(GitHubPostingError) as exc_info:
        poster.create_discussion_with_evidence(
            repository="xunharry4-source/AnimoCerebro",
            title="Project update",
            body="Useful body",
        )

    assert exc_info.value.code == "github_token_missing"


def test_github_smart_poster_edge_rejects_invalid_discussion_url_fixture():
    def transport(method, url, headers, body):
        payload = json.loads(body.decode("utf-8"))
        if "DiscussionRepositoryInfo" in payload["query"]:
            return 200, _repository_info_payload()
        if "CreateDiscussion" in payload["query"]:
            return 200, {
                "data": {
                    "createDiscussion": {
                        "discussion": {
                            "id": "discussion-7",
                            "number": 7,
                            "title": "Project update",
                            "body": "Useful body",
                            "url": "https://github.com/xunharry4-source/AnimoCerebro/issues/7",
                            "category": {"id": "category-1", "name": "General"},
                        }
                    }
                }
            }
        return 200, {"data": {}}

    poster = GitHubSmartPoster(token="test-token", transport=transport)

    with pytest.raises(GitHubPostingError) as exc_info:
        poster.create_discussion_with_evidence(
            repository="xunharry4-source/AnimoCerebro",
            title="Project update",
            body="Useful body",
        )

    assert exc_info.value.code == "github_discussion_url_invalid"


def test_github_nodes_normal_record_verified_discussion_fixture(tmp_path: Path):
    class FakePoster:
        def create_discussion_with_evidence(self, **kwargs):
            return {
                "success": True,
                "platform": "github",
                "trace_id": "trace-github-test",
                "repository": kwargs["repository"],
                "title": kwargs["title"],
                "content": kwargs["body"],
                "category": {"id": "category-1", "name": kwargs["category_name"] or "General"},
                "discussion_id": "discussion-7",
                "discussion_number": 7,
                "post_url": DISCUSSION_URL,
                "verified_at": "2026-04-25T00:00:00+00:00",
                "verification_source": "github_graphql_discussion_get",
                "active_evidence": {
                    "verification_source": "github_graphql_discussion_get",
                    "post_url": DISCUSSION_URL,
                    "title_match": True,
                    "body_match": True,
                },
            }

    context = WorkflowContext(
        github_poster=FakePoster(),
        ledger_path=tmp_path / "ledger.json",
        status_doc_path=tmp_path / "status.md",
    )
    state = GitHubPostingState(
        repository="xunharry4-source/AnimoCerebro",
        title="Project update",
        content="Useful body",
        category_name="General",
    )

    SubmitGitHubDiscussionNode().run(context, state)
    VerifyGitHubDiscussionSuccessNode().run(context, state)
    UpdateGitHubPostingDocumentNode().run(context, state)

    assert state.status == "success"
    assert state.discussion_number == 7
    assert is_platform_post_url("github", state.post_url)
    status_doc = context.status_doc_path.read_text(encoding="utf-8")
    assert "GitHub 发帖成功" in status_doc
    assert DISCUSSION_URL in status_doc


def test_github_update_document_abnormal_rejects_missing_verify_evidence_fixture(tmp_path: Path):
    context = WorkflowContext(
        ledger_path=tmp_path / "ledger.json",
        status_doc_path=tmp_path / "status.md",
    )
    state = GitHubPostingState(
        repository="xunharry4-source/AnimoCerebro",
        title="Project update",
        content="Useful body",
        post_url=DISCUSSION_URL,
        discussion_number=7,
        status="success",
        attempts=1,
    )
    state.add_evidence("github_submit_discussion", True, "GitHub Discussion created", result={"post_url": DISCUSSION_URL})

    with pytest.raises(PostingWorkflowError) as exc_info:
        UpdateGitHubPostingDocumentNode().run(context, state)

    assert exc_info.value.code == "success_evidence_missing"
    assert not context.status_doc_path.exists()
