import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import NineQuestionReflectionsPage from "./NineQuestionReflectionsPage";

describe("NineQuestionReflectionsPage", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/web/reflections/reflect-1")) {
          return {
            ok: true,
            json: async () => ({
              reflection_id: "reflect-1",
              trace_id: "reflection-trace-1",
              session_id: "session-1",
              subject: "Q8 反思",
              summary: "需要检查任务落地是否成功",
              created_at: "2026-04-20T10:00:00Z",
              context: {
                question_id: "q8",
                analysis: {
                  need_upgrade: true,
                  effectiveness_score: 0.3,
                  missing_data: ["task persistence"],
                  useless_data: [],
                  missing_for_goal: "真实任务状态",
                },
              },
            }),
          } as Response;
        }
        if (url.includes("/api/web/reflections")) {
          return {
            ok: true,
            json: async () => ({
              items: [
                {
                  reflection_id: "reflect-1",
                  trace_id: "reflection-trace-1",
                  session_id: "session-1",
                  summary: "需要检查任务落地是否成功",
                  created_at: "2026-04-20T10:00:00Z",
                  context: {
                    question_id: "q8",
                    analysis: {
                      effective: false,
                      effectiveness_score: 0.3,
                    },
                  },
                },
              ],
            }),
          } as Response;
        }
        return { ok: false, json: async () => ({}) } as Response;
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it("renders traceability links for reflection detail", async () => {
    render(
      <MemoryRouter initialEntries={["/console/audit"]}>
        <NineQuestionReflectionsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("九问反思结果")).toBeInTheDocument();
    expect(screen.getByText("反思固定问题")).toBeInTheDocument();
    expect(screen.getByText("1. 我今天做了什么？")).toBeInTheDocument();
    expect(screen.getByText("6. 明天我要优先改进什么？")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "查看本问工作流" })).toHaveAttribute(
      "href",
      "/console/nine-questions/q8/workflow",
    );
    expect(screen.getAllByRole("link", { name: "查看 trace 回放" })[0]).toHaveAttribute(
      "href",
      "/console/audit/transcript-replay/reflection-trace-1",
    );
  });
});
