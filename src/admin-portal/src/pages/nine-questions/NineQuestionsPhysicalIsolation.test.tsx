import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Q1Detail from "./q1/Q1Detail";
import Q2Detail from "./q2/Q2Detail";
import Q3Detail from "./q3/Q3Detail";
import Q4Detail from "./q4/Q4Detail";
import Q5Detail from "./q5/Q5Detail";
import Q6Detail from "./q6/Q6Detail";
import Q7Detail from "./q7/Q7Detail";
import Q8Detail from "./q8/Q8Detail";
import Q9Detail from "./q9/Q9Detail";
import * as api from "./nineQuestionsApi";

// Mock API
vi.mock("./nineQuestionsApi", async (importOriginal) => {
  const actual = await importOriginal() as any;
  return {
    ...actual,
    fetchNineQuestionsReport: vi.fn().mockResolvedValue({
      report: {
        questions: [
          { 
            question_id: "q1", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t1", 
            mounted_plugins: [], 
            trace_id: "t1", 
            preprocessed_evidence: { 
              workspace_structure: { directory_tree_rows: [], suffix_distribution: {}, high_frequency_filename_keywords: {}, top_level_dirs: [], candidate_groups: [], directory_hierarchy_summary: "mock", obvious_risk_file_details: [], candidate_group_details: [] }, 
              workspace_content_sampling: { sample_count: 0, anomaly_count: 0, long_text_evidence: [] }, 
              physical_and_environment: { network_health: "ok", environment_summary: [], environment_event: {}, physical_host_state: {} } 
            }, 
            inference_result: { primary_domain: "mock", confidence: 0.9, secondary_domains: [], reasoning_summary: "mock", uncertainties: [], suggested_first_step: "mock" } 
          },
          { 
            question_id: "q2", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t2", 
            mounted_plugins: [], 
            trace_id: "t2",
            preprocessed_evidence: {
              q1_summary: { primary_domain: "mock", secondary_domains: [], uncertainties: [], risk_summary: "mock" },
              identity_kernel: { meta_motivation: "mock", values_prohibition: "mock", non_bypassable_constraints: [] }
            },
            inference_result: {
              role_profile: { identity_role: "mock", active_role: "mock", task_role: "mock" },
              mission_boundary: { current_mission: "mock mission", priority_duties: [], continuity_boundaries: [] }
            }
          },
          { 
            question_id: "q3", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t3", 
            mounted_plugins: [], 
            trace_id: "t3",
            preprocessed_evidence: {
              workspace_permission: { workspaces: [], tenant_permissions: [], execution_tokens: [] },
              tools_agents: { cognitive_tools: [], execution_tools: [], connected_agents: [] },
              memory_strategy: { experience_logs: [], strategy_patches: [] }
            },
            inference_result: {
              sufficiency_assessment: { resource_status: "充沛", missing_critical_assets: [], reasoning_summary: "mock" }
            }
          },
          { 
            question_id: "q4", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t4", 
            mounted_plugins: [], 
            trace_id: "t4", 
            preprocessed_evidence: { inherited_assets: [], active_roles: [] },
            inference_result: { capability_upper_limits: [], actionable_space: ["mock_action"], executable_strategies: [] } 
          },
          { 
            question_id: "q5", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t5", 
            mounted_plugins: [], 
            trace_id: "t5",
            preprocessed_evidence: { actionable_space: [], tenant_boundaries: [], agent_trust_status: {} },
            inference_result: { execution_tier: "mock", interaction_scope: "mock", explicitly_forbidden_actions: [], allowed_delegation_targets: [] }
          },
          { 
            question_id: "q6", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t6", 
            mounted_plugins: [], 
            trace_id: "t6",
            preprocessed_evidence: { actionable_space: [], authorization_boundaries: [], non_bypassable_constraints: [], historical_strategy_patches: [] },
            inference_result: { absolute_red_lines: [], performance_tradeoff_bans: [], prohibited_strategies: [], contamination_risks: [] }
          },
          { 
            question_id: "q7", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t7", 
            mounted_plugins: [], 
            trace_id: "t7",
            preprocessed_evidence: { resource_bottlenecks: [], capability_limits: [], permission_boundaries: [], absolute_red_lines: [], historical_failure_patches: [] },
            inference_result: { fallback_plans: [], degradation_strategies: [], collaboration_switches: [], exploratory_actions: [] }
          },
          { 
            question_id: "q8", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t8", 
            mounted_plugins: [], 
            trace_id: "t8", 
            preprocessed_evidence: {
              aggregated_context: { q1_to_q7_snapshot: {}, absolute_red_line_count: 0, capability_ceiling_count: 0 },
              runtime_state: { persistent_task_state: [], cognitive_agenda: [] }
            },
            inference_result: { 
              objective_profile: { current_primary_objective: "mock objectives", current_phase_tasks: [], priority_order: [] }, 
              task_queue: { next_self_tasks: [], blocked_self_tasks: [], proactive_actions: [] } 
            } 
          },
          { 
            question_id: "q9", 
            cache_status: "HIT", 
            provider_name: "MockGPT", 
            tool_id: "t9", 
            mounted_plugins: [], 
            trace_id: "t9", 
            preprocessed_evidence: { 
              cognitive_snapshot: { q1_to_q8_snapshot: { turn_id: 1 }, uncertainty_count: 0, absolute_red_line_count: 0 },
              self_model: { cognitive_load: "low", stability_level: "high", recent_weaknesses: [] }, 
              reasoning_budget: { compute_remaining_ratio: 1, token_remaining_ratio: 1, time_remaining_ratio: 1, budget_pressure: "low" } 
            }, 
            inference_result: { evaluation_style: "mock evaluation", risk_tolerance: "low", action_rhythm: "mock rhythm", confirmation_strategy: "mock", evolution_direction: "mock" } 
          },
        ],
      },
      notice: "Mock Notice",
    }),
    fetchNineQuestionTrace: vi.fn().mockResolvedValue({
      prompt: "Mock Prompt",
      result: { status: "success" },
      llm_trace_payload: { 
        provider_name: "Mock Provider",
        model: "gpt-4o",
        system_prompt: "Mock System Prompt", 
        prompt: "Mock User Prompt",
        raw_response: { text: "hello" },
        token_usage: { input_tokens: 100, output_tokens: 200, total_tokens: 300 },
        elapsed_ms: 1234
      },
    }),
    getQuestionDisplayLabel: actual.getQuestionDisplayLabel,
  };
});

describe("Zentex G31A Full-Spectrum Physical Isolation & Transparency Audit", () => {
  it("should prove Q1 has its own dedicated detail component with separate routing", async () => {
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/Q1_Where_Am_I.*正式审计页/)).toBeInTheDocument();
  });

  it("should prove Q8 uses strategic decision profile and is isolated", async () => {
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/Q8_What_Should_I_Do_Now.*正式审计页/)).toBeInTheDocument();
    expect(await screen.findByText(/任务名称/)).toBeInTheDocument();
    expect(await screen.findByText(/议程内容/)).toBeInTheDocument();
    expect(await screen.findByText(/mock objectives/)).toBeInTheDocument();
  });

  it("should prove Q9 has Action Posture Profile and is isolated", async () => {
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/Q9_How_Should_I_Act.*正式审计页/)).toBeInTheDocument();
    expect(await screen.findByText(/评价风格/)).toBeInTheDocument();
    expect(await screen.findByText(/mock evaluation/)).toBeInTheDocument();
    expect(await screen.findByText(/mock rhythm/)).toBeInTheDocument();
  });

  it("should prove ALL 9 stages have the mandatory LLM Trace Panel for 100% traceability", async () => {
    const components = [
       { path: "/console/nine-questions/q1", element: <Q1Detail />, label: /Q1_Where_Am_I/ },
       { path: "/console/nine-questions/q2", element: <Q2Detail />, label: /Q2_Who_Am_I/ },
       { path: "/console/nine-questions/q3", element: <Q3Detail />, label: /Q3_What_Do_I_Have/ },
       { path: "/console/nine-questions/q4", element: <Q4Detail />, label: /Q4_What_Can_I_Do/ },
       { path: "/console/nine-questions/q5", element: <Q5Detail />, label: /Q5_What_Am_I_Allowed_To_Do/ },
       { path: "/console/nine-questions/q6", element: <Q6Detail />, label: /Q6_What_Should_I_Not_Do/ },
       { path: "/console/nine-questions/q7", element: <Q7Detail />, label: /Q7_What_Else_Can_I_Do/ },
       { path: "/console/nine-questions/q8", element: <Q8Detail />, label: /Q8_What_Should_I_Do_Now/ },
       { path: "/console/nine-questions/q9", element: <Q9Detail />, label: /Q9_How_Should_I_Act/ },
    ];

    for (const comp of components) {
      const { unmount } = render(
        <MemoryRouter initialEntries={[comp.path]}>
          <Routes>
            <Route path={comp.path} element={comp.element} />
          </Routes>
        </MemoryRouter>
      );
      // Ensure page title is loaded
      expect(await screen.findByText(new RegExp(`${comp.label.source}.*正式审计页`))).toBeInTheDocument();
      // Check for the LLM Trace Panel header
      expect(await screen.findByText(/大模型交互溯源区/)).toBeInTheDocument();
      // Check for the closed accordions headers (inputs/outputs)
      expect(await screen.findByText(/输入 Prompt/)).toBeInTheDocument();
      expect(await screen.findByText(/输出 Raw Response/)).toBeInTheDocument();
      unmount();
    }
  });

  it("should prove Q5/Q6 high-intensity alerts are physically rendered", async () => {
    // Q5
    const { unmount: unmount5 } = render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5"]}>
        <Routes>
          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/合规警戒/)).toBeInTheDocument();
    unmount5();

    // Q6
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q6"]}>
        <Routes>
          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/核心告警/)).toBeInTheDocument();
  });
});
