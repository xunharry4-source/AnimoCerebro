#!/usr/bin/env python3
"""
GitHub Discussions 智能发帖入口。

文件用途:
    通过 GitHub GraphQL API 在目标仓库创建 Discussion，并用 API 读取结果做主动验证。

主要职责:
    - 校验目标仓库、Discussion 标题、正文、分类和 GitHub token。
    - 查询目标仓库 Discussion categories，选择真实存在的分类。
    - 创建 GitHub Discussion 作为项目发布/讨论帖。
    - 主动读回已创建 Discussion，验证 URL、标题、正文和 discussion number。
    - 返回带 trace_id、post_url、verified_at 的结构化证据。

不负责:
    - 不管理 GitHub token 或账号登录。
    - 不创建 Issue、Release、PR 或 Wiki 页面。
    - 不在缺少真实 GitHub API 响应时声明发帖成功。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from Agent.posting_workflows.verification_gate import is_platform_post_url


DEFAULT_GITHUB_REPOSITORY = "xunharry4-source/AnimoCerebro"
DEFAULT_GITHUB_REPOSITORY_URL = "https://github.com/xunharry4-source/AnimoCerebro"
DEFAULT_DISCUSSION_CATEGORY_PREFERENCES = (
    "General",
    "Announcements",
    "Ideas",
    "Show and tell",
    "Q&A",
)
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, Dict[str, Any]]]


class GitHubPostingError(RuntimeError):
    """GitHub 发帖结构化错误。"""

    def __init__(self, message: str, *, code: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
        }


class GitHubSmartPoster:
    """Create and verify GitHub Discussion posts with fail-closed evidence."""

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        api_base_url: str = "https://api.github.com",
        transport: Optional[Transport] = None,
    ) -> None:
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.api_base_url = api_base_url.rstrip("/")
        self.transport = transport

    def create_discussion_with_evidence(
        self,
        *,
        repository: str = DEFAULT_GITHUB_REPOSITORY,
        title: str,
        body: str,
        category_name: Optional[str] = None,
        category_preferences: Optional[Iterable[str]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a GitHub Discussion and verify it through a read-after-write GraphQL query."""
        trace_id = trace_id or self._new_trace_id()
        normalized_repo = self.normalize_repository(repository)
        clean_title = str(title or "").strip()
        clean_body = str(body or "").strip()

        self._require_token()
        if not clean_title:
            raise GitHubPostingError(
                "GitHub discussion title is required",
                code="github_discussion_title_missing",
                details={"repository": normalized_repo},
            )
        if not clean_body:
            raise GitHubPostingError(
                "GitHub discussion body is required",
                code="github_discussion_body_missing",
                details={"repository": normalized_repo},
            )

        repository_info = self.get_discussion_repository_info(repository=normalized_repo)
        category = self._select_discussion_category(
            repository=normalized_repo,
            categories=repository_info["categories"],
            category_name=category_name,
            category_preferences=category_preferences,
        )
        mutation = """
        mutation CreateDiscussion(
          $repositoryId: ID!,
          $categoryId: ID!,
          $title: String!,
          $body: String!,
          $clientMutationId: String
        ) {
          createDiscussion(input: {
            repositoryId: $repositoryId,
            categoryId: $categoryId,
            title: $title,
            body: $body,
            clientMutationId: $clientMutationId
          }) {
            clientMutationId
            discussion {
              id
              number
              title
              body
              url
              createdAt
              category {
                id
                name
              }
              repository {
                nameWithOwner
              }
            }
          }
        }
        """
        data = self._graphql(
            mutation,
            {
                "repositoryId": repository_info["repository_id"],
                "categoryId": category["id"],
                "title": clean_title,
                "body": clean_body,
                "clientMutationId": trace_id,
            },
        )
        created = ((data.get("createDiscussion") or {}).get("discussion") or {})
        post_url = str(created.get("url") or "")
        discussion_number = created.get("number")
        discussion_id = str(created.get("id") or "")
        if not isinstance(discussion_number, int):
            raise GitHubPostingError(
                "GitHub discussion creation response did not include a discussion number",
                code="github_discussion_number_missing",
                details={"repository": normalized_repo, "payload": self._safe_payload(created)},
            )
        if not discussion_id:
            raise GitHubPostingError(
                "GitHub discussion creation response did not include a discussion id",
                code="github_discussion_id_missing",
                details={"repository": normalized_repo, "payload": self._safe_payload(created)},
            )
        if not is_platform_post_url("github", post_url):
            raise GitHubPostingError(
                "GitHub discussion creation response did not include a verifiable discussion URL",
                code="github_discussion_url_invalid",
                details={"repository": normalized_repo, "post_url": post_url},
            )

        active_evidence = self.verify_discussion_with_evidence(
            repository=normalized_repo,
            discussion_number=discussion_number,
            expected_title=clean_title,
            expected_body=clean_body,
        )
        return {
            "success": True,
            "platform": "github",
            "trace_id": trace_id,
            "repository": normalized_repo,
            "title": clean_title,
            "content": clean_body,
            "category": {
                "id": category["id"],
                "name": category["name"],
            },
            "discussion_id": discussion_id,
            "discussion_number": discussion_number,
            "post_url": post_url,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "verification_source": "github_graphql_discussion_get",
            "active_evidence": active_evidence,
            "submission_result": {
                "post_url": post_url,
                "discussion_id": discussion_id,
                "discussion_number": discussion_number,
                "repository_id": repository_info["repository_id"],
                "category_id": category["id"],
                "category_name": category["name"],
                "graphql_mutation": "createDiscussion",
            },
        }

    def get_discussion_repository_info(self, *, repository: str) -> Dict[str, Any]:
        """Read repository id and available Discussion categories from GitHub GraphQL."""
        normalized_repo = self.normalize_repository(repository)
        owner, name = self._split_repository(normalized_repo)
        self._require_token()
        query = """
        query DiscussionRepositoryInfo($owner: String!, $name: String!) {
          repository(owner: $owner, name: $name) {
            id
            nameWithOwner
            discussionCategories(first: 25) {
              nodes {
                id
                name
                description
                isAnswerable
                emoji
              }
            }
          }
        }
        """
        data = self._graphql(query, {"owner": owner, "name": name})
        repository_node = data.get("repository")
        if not isinstance(repository_node, dict):
            raise GitHubPostingError(
                "GitHub repository was not found or Discussions are unavailable",
                code="github_repository_not_found",
                details={"repository": normalized_repo},
            )
        categories = ((repository_node.get("discussionCategories") or {}).get("nodes") or [])
        clean_categories = [
            {
                "id": str(category.get("id") or ""),
                "name": str(category.get("name") or ""),
                "description": str(category.get("description") or ""),
                "is_answerable": bool(category.get("isAnswerable")),
                "emoji": str(category.get("emoji") or ""),
            }
            for category in categories
            if isinstance(category, dict) and category.get("id") and category.get("name")
        ]
        if not clean_categories:
            raise GitHubPostingError(
                "GitHub repository did not return any Discussion categories",
                code="github_discussion_categories_missing",
                details={"repository": normalized_repo},
            )
        return {
            "repository": normalized_repo,
            "repository_id": str(repository_node.get("id") or ""),
            "name_with_owner": str(repository_node.get("nameWithOwner") or normalized_repo),
            "categories": clean_categories,
        }

    def verify_discussion_with_evidence(
        self,
        *,
        repository: str,
        discussion_number: int,
        expected_title: str,
        expected_body: str,
    ) -> Dict[str, Any]:
        """Read the Discussion through GitHub GraphQL and verify expected content."""
        normalized_repo = self.normalize_repository(repository)
        owner, name = self._split_repository(normalized_repo)
        self._require_token()
        query = """
        query VerifyDiscussion($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            nameWithOwner
            discussion(number: $number) {
              id
              number
              title
              body
              url
              createdAt
              category {
                id
                name
              }
            }
          }
        }
        """
        data = self._graphql(query, {"owner": owner, "name": name, "number": discussion_number})
        repository_node = data.get("repository")
        discussion = (repository_node or {}).get("discussion") if isinstance(repository_node, dict) else None
        if not isinstance(discussion, dict):
            raise GitHubPostingError(
                "GitHub discussion verification did not find the created discussion",
                code="github_discussion_verify_missing",
                details={"repository": normalized_repo, "discussion_number": discussion_number},
            )

        post_url = str(discussion.get("url") or "")
        actual_title = str(discussion.get("title") or "")
        actual_body = str(discussion.get("body") or "")
        if not is_platform_post_url("github", post_url):
            raise GitHubPostingError(
                "GitHub verification response did not include a verifiable discussion URL",
                code="github_discussion_verify_url_invalid",
                details={"repository": normalized_repo, "discussion_number": discussion_number, "post_url": post_url},
            )
        if actual_title.strip() != expected_title.strip():
            raise GitHubPostingError(
                "GitHub verification title did not match expected title",
                code="github_discussion_verify_title_mismatch",
                details={"repository": normalized_repo, "discussion_number": discussion_number},
            )
        if self._normalize(expected_body) not in self._normalize(actual_body):
            raise GitHubPostingError(
                "GitHub verification body did not contain expected content",
                code="github_discussion_verify_body_mismatch",
                details={"repository": normalized_repo, "discussion_number": discussion_number},
            )

        category = discussion.get("category") or {}
        return {
            "verification_source": "github_graphql_discussion_get",
            "repository": normalized_repo,
            "discussion_id": str(discussion.get("id") or ""),
            "discussion_number": discussion_number,
            "post_url": post_url,
            "category": {
                "id": str(category.get("id") or ""),
                "name": str(category.get("name") or ""),
            },
            "graphql_node_found": True,
            "title_match": True,
            "body_match": True,
            "body_snippet": actual_body[:500],
        }

    def normalize_repository(self, repository: str) -> str:
        """Accept owner/repo, repo URL, or repo Discussions URL and return owner/repo."""
        raw = str(repository or "").strip()
        if not raw:
            raw = DEFAULT_GITHUB_REPOSITORY
        if raw.startswith("http://") or raw.startswith("https://"):
            parsed = urlparse(raw)
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.netloc.lower().removeprefix("www.") != "github.com" or len(parts) < 2:
                raise GitHubPostingError(
                    "GitHub repository URL must look like https://github.com/owner/repo",
                    code="github_repository_invalid",
                    details={"repository": repository},
                )
            raw = f"{parts[0]}/{parts[1]}"
        parts = [part for part in raw.split("/") if part]
        if len(parts) != 2:
            raise GitHubPostingError(
                "GitHub repository must use owner/repo format",
                code="github_repository_invalid",
                details={"repository": repository},
            )
        return f"{parts[0]}/{parts[1]}"

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        status, payload = self._request_json(
            "POST",
            "/graphql",
            {
                "query": query,
                "variables": variables,
            },
        )
        if status != 200:
            raise GitHubPostingError(
                "GitHub GraphQL API did not return HTTP 200",
                code="github_graphql_status_error",
                details={"status": status, "payload": self._safe_payload(payload)},
            )
        if payload.get("errors"):
            raise GitHubPostingError(
                "GitHub GraphQL API returned errors",
                code="github_graphql_errors",
                details={"errors": self._safe_payload(payload.get("errors"))},
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GitHubPostingError(
                "GitHub GraphQL API response did not include a data object",
                code="github_graphql_data_missing",
                details={"payload": self._safe_payload(payload)},
            )
        return data

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]],
    ) -> Tuple[int, Dict[str, Any]]:
        url = path if path.startswith("http") else f"{self.api_base_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "AnimoCerebro-GitHubSmartPoster",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.transport:
            return self.transport(method, url, headers, body)

        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return int(response.status), parsed
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed_error = json.loads(error_body) if error_body else {}
            except json.JSONDecodeError:
                parsed_error = {"message": error_body[:500]}
            raise GitHubPostingError(
                "GitHub API returned an HTTP error",
                code="github_api_http_error",
                details={"status": exc.code, "payload": self._safe_payload(parsed_error), "url": url},
            ) from exc
        except URLError as exc:
            raise GitHubPostingError(
                f"GitHub API network error: {exc.reason}",
                code="github_api_network_error",
                details={"url": url},
            ) from exc
        except json.JSONDecodeError as exc:
            raise GitHubPostingError(
                "GitHub API returned invalid JSON",
                code="github_api_invalid_json",
                details={"url": url},
            ) from exc

    def _select_discussion_category(
        self,
        *,
        repository: str,
        categories: List[Dict[str, Any]],
        category_name: Optional[str],
        category_preferences: Optional[Iterable[str]],
    ) -> Dict[str, Any]:
        if not categories:
            raise GitHubPostingError(
                "GitHub repository did not return any Discussion categories",
                code="github_discussion_categories_missing",
                details={"repository": repository},
            )

        requested = str(category_name or "").strip()
        if requested:
            category = self._find_category(categories, requested)
            if not category:
                raise GitHubPostingError(
                    "Requested GitHub Discussion category was not found",
                    code="github_discussion_category_not_found",
                    details={
                        "repository": repository,
                        "requested_category": requested,
                        "available_categories": [item["name"] for item in categories],
                    },
                )
            return category

        for preferred in category_preferences or DEFAULT_DISCUSSION_CATEGORY_PREFERENCES:
            category = self._find_category(categories, preferred)
            if category:
                return category
        # Discussion categories are repository-defined; when no preference matches,
        # use the first API-returned category and record it in evidence.
        return categories[0]

    def _find_category(self, categories: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        target = self._category_key(name)
        for category in categories:
            if self._category_key(category.get("name")) == target:
                return category
        return None

    def _split_repository(self, repository: str) -> Tuple[str, str]:
        normalized_repo = self.normalize_repository(repository)
        owner, name = normalized_repo.split("/", 1)
        return owner, name

    def _require_token(self) -> None:
        if not self.token:
            raise GitHubPostingError(
                "GITHUB_TOKEN is required for real GitHub Discussions posting",
                code="github_token_missing",
                details={"env": "GITHUB_TOKEN"},
            )

    def _new_trace_id(self) -> str:
        return f"github-discussion-{int(time.time())}-{uuid.uuid4().hex[:8]}"

    def _normalize(self, text: str) -> str:
        return " ".join(str(text or "").split()).strip().lower()

    def _category_key(self, text: Any) -> str:
        return " ".join(str(text or "").replace("&", "and").lower().split())

    def _safe_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {key: self._safe_payload(value) for key, value in payload.items() if str(key).lower() not in {"token", "authorization"}}
        if isinstance(payload, list):
            return [self._safe_payload(item) for item in payload]
        return payload
