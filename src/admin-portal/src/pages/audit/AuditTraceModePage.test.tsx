import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../nine-questions/NineQuestionsWorkflowPage", () => ({ default: () => <div>nine-questions-workflow-table</div> }));
vi.mock("../nine-questions/NineQuestionReflectionsPage", () => ({ default: () => <div>reflection-workflow-table</div> }));
vi.mock("../learning/LearningDashboard", () => ({ default: () => <div>learning-workflow-table</div> }));
vi.mock("./auditApi", () => ({
  fetchAuditTraceGraph: vi.fn(async (mode: string) => ({
    mode,
    title: "审计工作流",
    subtitle: "数据库驱动",
    database_backed: true,
    generated_at: "2026-04-20T00:00:00Z",
    summary: { audit_event_count: 12, model_trace_count: 4 },
    lanes: [
      {
        lane_id: "start",
        title: "起点层",
        subtitle: "起点",
        nodes: [{ node_id: "start", title: "起点", lane: "start", status: "ready", description: "from db", metrics: {} }],
      },
      {
        lane_id: "drivers",
        title: "驱动层",
        subtitle: "drivers",
        nodes: [{ node_id: "driver-q5", title: "Q5", lane: "drivers", status: "active", description: "question ref", href: "/console/nine-questions/q5", metrics: { question_ref: "q5" } }],
      },
      {
        lane_id: "modules",
        title: "模块层",
        subtitle: "模块",
        nodes: [{ node_id: "family-memory", title: "Memory", lane: "modules", status: "active", description: "events", href: "/console/memory", metrics: { event_count: 2 } }],
      },
      {
        lane_id: "execution",
        title: "执行层",
        subtitle: "execution",
        nodes: [{ node_id: "execution-memory-1", title: "memory.service", lane: "execution", status: "running", description: "memory_query | from db", href: "/console/audit/transcript-replay/trace-1", metrics: { entry_id: "e1" } }],
      },
      {
        lane_id: "traces",
        title: "Trace 层",
        subtitle: "trace",
        nodes: [{ node_id: "trace-1", title: "trace-1", lane: "traces", status: "completed", description: "done", href: "/console/audit/transcript-replay/trace-1", metrics: {} }],
      },
      {
        lane_id: "outcomes",
        title: "结果层",
        subtitle: "outcomes",
        nodes: [{ node_id: "outcome-1", title: "结果", lane: "outcomes", status: "completed", description: "persisted", metrics: {} }],
      },
    ],
    edges: [{ edge_id: "edge-1", source: "start", target: "family-memory", label: "关联模块" }],
  })),
}));

import AuditTraceModePage from "./AuditTraceModePage";

describe("AuditTraceModePage", () => {
  it("renders database-backed workflow canvas for a selected mode", async () => {
    render(
      <MemoryRouter initialEntries={["/console/audit/nine_questions/workflow"]}>
        <Routes>
          <Route path="/console/audit/:mode/:view" element={<AuditTraceModePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("audit-trace-mode-page")).toBeInTheDocument();
    expect(await screen.findByTestId("audit-trace-workflow-board")).toBeInTheDocument();
    expect(screen.getByTestId("audit-trace-node-start-start")).toHaveTextContent("起点");
    expect(screen.getByTestId("audit-trace-node-drivers-driver-q5")).toHaveTextContent("Q5");
    expect(screen.getByTestId("audit-trace-node-modules-family-memory")).toHaveTextContent("Memory");
    expect(screen.getByTestId("audit-trace-node-execution-execution-memory-1")).toHaveTextContent("memory.service");
    expect(screen.getByTestId("audit-trace-node-traces-trace-1")).toHaveTextContent("trace-1");
    expect(screen.getByTestId("audit-trace-node-outcomes-outcome-1")).toHaveTextContent("结果");
    expect(screen.getByRole("link", { name: "表格视图" })).toHaveAttribute("href", "/console/audit/nine_questions/table");
  });

  it("renders table view for a selected mode", () => {
    render(
      <MemoryRouter initialEntries={["/console/audit/reflection/table"]}>
        <Routes>
          <Route path="/console/audit/:mode/:view" element={<AuditTraceModePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("reflection-workflow-table")).toBeInTheDocument();
  });
});
