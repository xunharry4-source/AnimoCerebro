export async function readResponseBody(resp: Response): Promise<any> {
  const raw = await resp.text();
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return { detail: raw };
  }
}

export function extractApiErrorMessage(data: any, fallback: string): string {
  const detail = data?.detail;
  if (typeof detail?.user_message === "string" && detail.user_message.trim()) {
    return detail.user_message;
  }
  if (typeof data?.user_message === "string" && data.user_message.trim()) {
    return data.user_message;
  }
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (typeof detail?.error === "string" && detail.error.trim()) {
    return detail.error;
  }
  if (typeof detail?.reason === "string" && detail.reason.trim()) {
    return detail.reason;
  }
  if (typeof data?.error === "string" && data.error.trim()) {
    return data.error;
  }
  return fallback;
}
