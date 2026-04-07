import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import RealtimeDashboard from "./RealtimeDashboard";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    queueMicrotask(() => {
      if (this.onopen) {
        this.onopen();
      }
    });
  }

  close() {
    if (this.onclose) {
      this.onclose();
    }
  }

  emitMessage(payload: unknown) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(payload) } as MessageEvent<string>);
    }
  }
}

describe("RealtimeDashboard", () => {
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;
  const overviewPayload = {
    runtime: {
      runtime_id: "runtime-test",
      active_session_ids: ["session-1"],
      transcript_store_status: "ready",
      memory_store_status: "ready",
      degraded_mode: false,
      manual_confirmation_required: false,
    },
    session: {
      session_id: "session-1",
      turn_count: 1,
      active_goal_titles: ["goal-a"],
      current_focus_summary: "初始焦点",
      current_reasoning_mode: "inspection",
      degraded_flags: [],
    },
    working_memory: {
      active_focus_titles: ["初始任务"],
      current_focus_summary: "初始焦点",
    },
    metacognition: {
      scheduler_status: "polling_transcript",
      current_reasoning_mode: "inspection",
    },
    living_self_model: {
      load_level: "medium",
      reasoning_posture: "observant",
    },
    temporal_agenda: {
      review_now_item_titles: ["立即复查 A"],
      overdue_item_titles: ["超期任务 B"],
    },
    active_weight_plugin_id: "risk_balanced_weight",
    weight_fallback_occurred: false,
    weight_profile: {
      active_weight_plugin_id: "risk_balanced_weight",
      weight_fallback_occurred: false,
      fallback_reason: null,
      purpose: "Balance upside exploration against bounded operational risk.",
      risk_tolerance: 0.45,
      cost_sensitivity: 0.2,
      creativity_bias: 0.15,
      continuity_bias: 0.2,
      rationale_tags: ["balanced"],
    },
  };
  const pluginsPayload = [
    {
      tool_id: "risk-comparator",
      plugin_kind: "cognitive_tool",
      status: "active",
      health_status: "healthy",
      usage_count: 2,
      failure_count: 0,
      rollback_conditions: ["runtime_regression_detected"],
      trigger_conditions: ["metacognition"],
    },
  ];
  const conflictsPayload = {
    conflicts: [
      {
        conflict_id: "conflict-1",
        conflict_type: "semantic_identity_conflict",
        severity: "critical",
        suggested_resolution: "pause_expansion_reasoning_and_review_identity_constraints",
        source_plugin_id: "semantic-conflict",
        status: "unresolved",
      },
    ],
  };
  const interactionMindPayload = {
    state: {
      entity_id: "session-1",
      brain_scope: "web-console",
      snapshot_version: 1,
      clarification_mode: false,
      model: {
        entity_id: "session-1",
        role_hint: "人工验收操作者",
        current_goal_hypothesis: "希望快速核对系统状态并定位风险点",
        knowledge_depth: "high",
        tolerance_for_detail: "medium",
        current_engagement_state: "high",
        trust_estimate: 0.78,
        last_updated_at: "2026-01-01T00:00:00+00:00",
      },
      knowledge_gap: {
        entity_id: "session-1",
        known_topics: ["插件状态"],
        uncertain_topics: ["多分支推演细节"],
        likely_missing_topics: ["误解风险来源"],
        confidence: 0.72,
      },
      communication_fit: {
        entity_id: "session-1",
        preferred_style: "evidence_first",
        detail_level: "medium",
        clarification_bias: 0.65,
        risk_of_misunderstanding: 0.82,
      },
      misunderstanding_signals: [
        {
          signal_id: "signal-1",
          entity_id: "session-1",
          signal_type: "correction",
          severity: "high",
          observed_at: "2026-01-01T00:00:00+00:00",
        },
      ],
    },
  };

  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/web/overview") {
        return Promise.resolve({
          ok: true,
          json: async () => overviewPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/plugins/cognitive") {
        return Promise.resolve({
          ok: true,
          json: async () => pluginsPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/cognitive-conflicts") {
        return Promise.resolve({
          ok: true,
          json: async () => conflictsPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/interaction-mind/session-1") {
        return Promise.resolve({
          ok: true,
          json: async () => interactionMindPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/interventions" && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ ok: true }),
        } satisfies Partial<Response> as Response);
      }
      return Promise.resolve({
        ok: false,
        json: async () => ({}),
      } satisfies Partial<Response> as Response);
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
  });

  it("maps real API overview and websocket events into dashboard widgets", async () => {
    render(<RealtimeDashboard />);

    await waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });
    await act(async () => {
      MockWebSocket.instances[0].emitMessage({
        type: "transcript_event",
        event: {
          entry_id: "entry-1",
          session_id: "session-1",
          turn_id: "turn-1",
          entry_type: "working_memory_updated",
          timestamp: "2026-01-01T00:00:00+00:00",
          source: "think_loop",
          trace_id: "trace-1",
          payload: { summary: "ok" },
        },
        overview: {
          ...overviewPayload,
          runtime: {
            ...overviewPayload.runtime,
            degraded_mode: true,
          },
          session: {
            ...overviewPayload.session,
            current_focus_summary: "优先确认 replay 路径是否稳定",
            degraded_flags: ["llm_unavailable"],
          },
          working_memory: {
            active_focus_titles: ["修复 replay 漏洞", "核对风险证据"],
            current_focus_summary: "优先确认 replay 路径是否稳定",
          },
          living_self_model: {
            load_level: "high",
            reasoning_posture: "conservative",
          },
          temporal_agenda: {
            review_now_item_titles: ["立即复查假设 A"],
            overdue_item_titles: ["超期任务 B"],
          },
          active_weight_plugin_id: "default_conservative_weight",
          weight_fallback_occurred: true,
          weight_profile: {
            active_weight_plugin_id: "default_conservative_weight",
            weight_fallback_occurred: true,
            fallback_reason: "G25 rejected drifted weights",
            purpose: "Bias toward safety, cost control, and continuity under uncertainty.",
            risk_tolerance: 0.2,
            cost_sensitivity: 0.35,
            creativity_bias: 0.1,
            continuity_bias: 0.35,
            rationale_tags: ["safety_first"],
          },
        },
      });
    });

    expect(await screen.findByTestId("llm-degraded-alert")).toHaveTextContent("运行时当前处于降级模式。");
    expect(screen.getByTestId("critical-conflict-alert")).toHaveTextContent(
      "检测到高危认知冲突，系统已触发保守降级并暂停扩展推理。"
    );
    expect(screen.getByTestId("weight-fallback-alert")).toHaveTextContent(
      "检测到权重漂移或审计拒绝，已安全回退至保守默认权重"
    );
    expect(screen.getByTestId("focus-summary")).toHaveTextContent("优先确认 replay 路径是否稳定");
    expect(screen.getByText("修复 replay 漏洞")).toBeInTheDocument();
    expect(screen.getByText("核对风险证据")).toBeInTheDocument();
    expect(screen.getByText("认知负荷: 高")).toBeInTheDocument();
    expect(screen.getByText("推理姿态: conservative")).toBeInTheDocument();
    expect(screen.getByTestId("interaction-mind-alert")).toHaveTextContent(
      "检测到误解风险，优先进行意图澄清"
    );
    expect(screen.getByText("表达偏好:")).toBeInTheDocument();
    expect(screen.getByText("证据优先")).toBeInTheDocument();
    expect(screen.getByText("立即复查假设 A")).toBeInTheDocument();
    expect(screen.getByText("超期任务 B")).toBeInTheDocument();
    expect(screen.getByText("working_memory_updated · think_loop")).toBeInTheDocument();
    expect(screen.getByText("risk-comparator")).toBeInTheDocument();
    expect(screen.getByText("semantic-conflict")).toBeInTheDocument();
  });

  it("renders the warning alert when overview reports weight fallback", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/web/overview") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...overviewPayload,
            active_weight_plugin_id: "default_conservative_weight",
            weight_fallback_occurred: true,
            weight_profile: {
              active_weight_plugin_id: "default_conservative_weight",
              weight_fallback_occurred: true,
              fallback_reason: "audit rejected",
              purpose: "Bias toward safety, cost control, and continuity under uncertainty.",
              risk_tolerance: 0.2,
              cost_sensitivity: 0.35,
              creativity_bias: 0.1,
              continuity_bias: 0.35,
              rationale_tags: ["safety_first"],
            },
          }),
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/plugins/cognitive") {
        return Promise.resolve({
          ok: true,
          json: async () => pluginsPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/cognitive-conflicts") {
        return Promise.resolve({
          ok: true,
          json: async () => conflictsPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/interaction-mind/session-1") {
        return Promise.resolve({
          ok: true,
          json: async () => interactionMindPayload,
        } satisfies Partial<Response> as Response);
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ ok: true }),
      } satisfies Partial<Response> as Response);
    }));

    render(<RealtimeDashboard />);

    expect(
      await screen.findByText("检测到权重漂移或审计拒绝，已安全回退至保守默认权重")
    ).toBeInTheDocument();
  });

  it("shows backend error alert instead of crashing when conflict API is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/web/overview") {
        return Promise.resolve({
          ok: true,
          json: async () => overviewPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/plugins/cognitive") {
        return Promise.resolve({
          ok: true,
          json: async () => pluginsPayload,
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/cognitive-conflicts") {
        return Promise.resolve({
          ok: false,
          json: async () => ({}),
        } satisfies Partial<Response> as Response);
      }
      if (url === "/api/web/interaction-mind/session-1") {
        return Promise.resolve({
          ok: true,
          json: async () => interactionMindPayload,
        } satisfies Partial<Response> as Response);
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ ok: true }),
      } satisfies Partial<Response> as Response);
    }));

    render(<RealtimeDashboard />);

    expect(
      await screen.findByText("无法连接到 Zentex 后端，请检查服务状态。")
    ).toBeInTheDocument();
  });

  it("posts a real intervention request when pause is submitted", async () => {
    const fetchMock = vi.mocked(globalThis.fetch);
    render(<RealtimeDashboard />);

    fireEvent.click(screen.getByRole("button", { name: "紧急熔断 / 暂停" }));
    fireEvent.change(screen.getByLabelText("干预原因"), {
      target: { value: "人工确认到异常循环" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/web/interventions",
        expect.objectContaining({
          method: "POST",
        })
      );
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/web/interventions",
      expect.objectContaining({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          action: "pause",
          reason: "人工确认到异常循环",
        }),
      })
    );

    expect(await screen.findByText("已提交暂停干预。")).toBeInTheDocument();
  });
});
