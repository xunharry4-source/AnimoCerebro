import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Q1EvidencePanel from "./Q1EvidencePanel";
import { Q1PreprocessedEvidence, WorkspaceDomainInferenceView } from "./nineQuestionsApi";

const mockEvidence: Q1PreprocessedEvidence = {
  physical_and_environment: {
    environment_event: { kind: "sandbox_run", summary: "manual inspection" },
    physical_host_state: {
      memory_pressure: "high",
      network_health: "degraded",
      cwd: "/tmp/q1-sandbox",
    },
    memory_pressure: "high",
    network_health: "degraded",
    memory_pressure_status: "high",
    network_health_status: "degrade",
    environment_summary: ["cwd=/tmp/q1-sandbox", "environment_kind=sandbox_run"],
  },
  workspace_structure: {
    directory_hierarchy_summary: "src/, docs/, logs/",
    top_level_dirs: ["src", "docs", "logs"],
    file_total_count: 18,
    suffix_distribution: { ".py": 9, ".md": 4, ".log": 2 },
    high_frequency_filename_keywords: { api: 3, invoice: 2 },
    candidate_groups: ["python_code", "documentation"],
    obvious_risk_files: ["logs/error.log"],
    directory_tree_rows: [
      { row_id: "dir-1", path: "src", label: "src", depth: 0, kind: "directory", file_count: 9 },
      { row_id: "dir-2", path: "src/api", label: "api", depth: 1, kind: "directory", file_count: 4 },
    ],
    candidate_group_details: [
      { group_id: "group-1", label: "python_code", file_count: 9, summary: "核心代码目录" },
    ],
    obvious_risk_file_details: [
      { path: "logs/error.log", severity: "high", reason: "存在 ERROR 片段" },
    ],
    analyzer_snapshot: {},
  },
  workspace_content_sampling: {
    sampled_file_summaries: [
      {
        path: "logs/error.log",
        summary: "启动日志样本",
        snippet: "ERROR sandbox validation failed because network degraded",
      },
    ],
    log_anomaly_snippets: ["ERROR sandbox validation failed because network degraded"],
    long_text_evidence: [
      {
        evidence_id: "sample-1-snippet",
        label: "logs/error.log · 样本行",
        kind: "snippet",
        source: "workspace_content_sampler",
        path: "logs/error.log",
        text: "ERROR sandbox validation failed because network degraded",
      },
    ],
    sample_count: 1,
    anomaly_count: 1,
    sampler_snapshot: {},
  },
};

const mockInference: WorkspaceDomainInferenceView = {
  primary_domain: "sandbox_console",
  secondary_domains: ["ops_console", "billing_workspace"],
  confidence: 0.94,
  reasoning_summary: "目录、日志和采样文本共同显示当前是独立测试控制台。",
  uncertainties: ["缺少 data/ 目录更深采样"],
  suggested_first_step: "inspect sandbox output",
};

describe("Q1EvidencePanel", () => {
  it("renders chips for structure evidence and keeps long text inside collapsed accordions", () => {
    render(
      <Q1EvidencePanel
        evidence={mockEvidence}
        inference={mockInference}
        providerName="provider-tools-default"
        elapsedMs={321}
      />,
    );

    expect(screen.getByText("物理与环境态势区")).toBeInTheDocument();
    expect(screen.getByText("工作区本地统计与结构区")).toBeInTheDocument();
    expect(screen.getByText("内容采样与证据区")).toBeInTheDocument();
    expect(screen.getByText("大模型终极推断区")).toBeInTheDocument();

    expect(screen.getByText("文件总数: 18")).toBeInTheDocument();
    expect(screen.getByText(".py: 9")).toBeInTheDocument();
    expect(screen.getByText(".md: 4")).toBeInTheDocument();
    expect(screen.getByText(".log: 2")).toBeInTheDocument();
    expect(screen.getByText("api: 3")).toBeInTheDocument();
    expect(screen.getByText("invoice: 2")).toBeInTheDocument();
    expect(screen.getAllByTestId("q1-long-text-accordion")).toHaveLength(1);

    const accordionButton = screen.getByRole("button", { name: /logs\/error\.log · 样本行/i });
    expect(accordionButton).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(accordionButton);

    expect(accordionButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/ERROR sandbox validation failed because network degraded/)).toBeInTheDocument();
  });
});
