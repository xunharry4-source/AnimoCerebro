export interface SystemIdentityConfig {
  role_name: string;
  mission?: string;
  core_values?: string[];
}

export interface SystemIdentityResponse {
  role_name: string;
  identity_role: string;
  mission: string;
  core_values: string[];
  user_configured: boolean;
  source?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  identity_kernel_snapshot: Record<string, unknown>;
}

const API_BASE = "http://127.0.0.1:8000/api/web/system-identity";

async function parseError(response: Response, fallback: string): Promise<Error> {
  try {
    const payload = await response.json();
    return new Error(payload.detail || fallback);
  } catch {
    return new Error(fallback);
  }
}

export async function fetchSystemIdentity(): Promise<SystemIdentityResponse> {
  const response = await fetch(`${API_BASE}/`);
  if (!response.ok) {
    throw await parseError(response, "Failed to fetch system identity");
  }
  return response.json();
}

export async function updateSystemIdentity(
  config: SystemIdentityConfig,
): Promise<SystemIdentityResponse> {
  const response = await fetch(`${API_BASE}/`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    throw await parseError(response, "Failed to update system identity");
  }
  return response.json();
}

export async function resetSystemIdentity(): Promise<SystemIdentityResponse> {
  const response = await fetch(`${API_BASE}/`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw await parseError(response, "Failed to reset system identity");
  }
  return response.json();
}
