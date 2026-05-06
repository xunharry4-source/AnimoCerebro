import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LLMTracePanel from "./LLMTracePanel";

describe("LLMTracePanel", () => {
  it("renders real prompt context and response fields when trace data is present", () => {
    render(
      <LLMTracePanel
        trace={{
          trace_id: "q3:acceptance",
          question_id: "q3",
          provider_name: "ollama",
          model: "qwen2.5:7b",
          system_prompt: "REAL TRACE SYSTEM PROMPT",
          prompt: "REAL TRACE PROMPT for q3",
          context_data: {
            question_id: "q3",
            source: "real_acceptance_transcript_insert",
          },
          raw_response: {
            answer: "real trace response for q3",
            confidence: 0.91,
          },
          result: {
            answer: "validated structured result for q3",
          },
          token_usage: {
            input_tokens: 12,
            output_tokens: 7,
            total_tokens: 19,
          },
          elapsed_ms: 345,
        } as any}
      />,
    );

    expect(screen.getByText("大模型交互溯源区")).toBeInTheDocument();
    expect(screen.getAllByText("Provider: ollama").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Model: qwen2.5:7b").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("输入 tokens: 12")).toBeInTheDocument();
    expect(screen.getByText("输出 tokens: 7")).toBeInTheDocument();
    expect(screen.getAllByText("总 tokens: 19").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("耗时: 345 ms")).toBeInTheDocument();
    expect(screen.getByText("LLM 调用次数: 1")).toBeInTheDocument();
    expect(screen.getByText("输入 System Prompt")).toBeInTheDocument();
    expect(screen.getByText(/REAL TRACE SYSTEM PROMPT/)).toBeInTheDocument();
    expect(screen.getByText("输入 Prompt")).toBeInTheDocument();
    expect(screen.getByText(/REAL TRACE PROMPT for q3/)).toBeInTheDocument();
    expect(screen.getByText(/real_acceptance_transcript_insert/)).toBeInTheDocument();
    expect(screen.getByText(/real trace response for q3/)).toBeInTheDocument();
    expect(screen.getByText("输出 Result")).toBeInTheDocument();
    expect(screen.getByText(/validated structured result for q3/)).toBeInTheDocument();
  });

  it("renders every LLM invocation instead of collapsing multi-call traces", () => {
    render(
      <LLMTracePanel
        trace={{
          trace_id: "q8:multi",
          question_id: "q8",
          provider_name: "ollama",
          model: "qwen2.5:7b",
          context_data: {},
          token_usage: {
            input_tokens: 30,
            output_tokens: 15,
            total_tokens: 45,
          },
          elapsed_ms: 1200,
          invocations: [
            {
              request_id: "req-1",
              decision_id: "decision-1",
              provider_name: "ollama",
              model: "qwen2.5:7b",
              invocation_phase: "q8_candidate_generation",
              prompt: "FIRST REAL PROMPT",
              context_data: { phase: "first" },
              raw_response: { answer: "first raw response" },
              token_usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
              elapsed_ms: 400,
            },
            {
              request_id: "req-2",
              decision_id: "decision-2",
              provider_name: "ollama",
              model: "qwen2.5:7b",
              invocation_phase: "q8_final_selection",
              prompt: "SECOND REAL PROMPT",
              context_data: { phase: "second" },
              raw_response: { answer: "second raw response" },
              token_usage: { input_tokens: 20, output_tokens: 10, total_tokens: 30 },
              elapsed_ms: 800,
            },
          ],
        } as any}
      />,
    );

    expect(screen.getByText("LLM 调用次数: 2")).toBeInTheDocument();
    expect(screen.getAllByText("执行1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("执行2").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/FIRST REAL PROMPT/)).toBeInTheDocument();
    expect(screen.getByText(/first raw response/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "执行2" }));
    expect(screen.getByText(/SECOND REAL PROMPT/)).toBeInTheDocument();
    expect(screen.getByText(/second raw response/)).toBeInTheDocument();
  });

  it("labels Q8 internal and external LLM invocations as separate records", () => {
    render(
      <LLMTracePanel
        trace={{
          provider_name: "ollama",
          model: "qwen2.5:7b",
          context_data: {},
          token_usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
          invocations: [
            {
              provider_name: "ollama",
              model: "qwen2.5:7b",
              invocation_phase: "nine_question_q8_internal_decision",
              prompt: "Q8 INTERNAL INPUT PROMPT",
              context_data: { scope: "internal" },
              raw_response: { q8_internal_llm_output: "internal output" },
              token_usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
            },
            {
              provider_name: "ollama",
              model: "qwen2.5:7b",
              invocation_phase: "nine_question_q8_external_decision",
              prompt: "Q8 EXTERNAL INPUT PROMPT",
              context_data: { scope: "external" },
              raw_response: { q8_external_llm_output: "external output" },
              token_usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
            },
          ],
        } as any}
      />,
    );

    expect(screen.getByText("LLM 调用次数: 2")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "内部1" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "外部2" })).toBeInTheDocument();
    expect(screen.getByText(/Q8 INTERNAL INPUT PROMPT/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "外部2" }));
    expect(screen.getByText(/Q8 EXTERNAL INPUT PROMPT/)).toBeInTheDocument();
    expect(screen.getByText(/external output/)).toBeInTheDocument();
  });

  it("shows trace-missing diagnostics instead of a normal empty provenance view", () => {
    render(
      <LLMTracePanel
        trace={{
          trace_id: "q6:acceptance",
          question_id: "q6",
          error_type: "llm_trace_missing",
          error_message: "No live LLM trace payload is available for q6; production answer must be refreshed.",
          context_data: {},
          token_usage: {
            input_tokens: 0,
            output_tokens: 0,
            total_tokens: 0,
          },
        } as any}
      />,
    );

    expect(screen.getByText(/llm_trace_missing/)).toBeInTheDocument();
    expect(screen.getByText(/production answer must be refreshed/)).toBeInTheDocument();
    expect(screen.queryByText("当前展示的是原始 System Prompt / Prompt / Context / Raw Response 溯源数据。")).not.toBeInTheDocument();
  });
});
