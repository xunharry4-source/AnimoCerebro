import { extractApiErrorMessage, readResponseBody } from "./httpError";

export type LLMStatus = {
  available: boolean;
  probe_checked: boolean;
  provider_name?: string | null;
  api_base?: string | null;
  api_key_env?: string | null;
  health_status?: string | null;
  reason?: string | null;
  missing_env?: string[];
  hint?: string | null;
  provider_error_type?: string | null;
};

export async function fetchLlmStatus(probeLive = true): Promise<LLMStatus> {
  const query = probeLive ? "?probe_live=1" : "";
  const resp = await fetch(`/api/web/llm/status${query}`, {
    headers: { Accept: "application/json" },
  });
  const data = await readResponseBody(resp);

  if (!resp.ok) {
    throw new Error(extractApiErrorMessage(data, "LLM 状态检查失败，请检查后端。"));
  }

  return data as LLMStatus;
}
