export type ModuleErrorInfo = {
  message: string;
  code: string;
  status?: number;
  retryable: boolean;
};

export class ModuleRequestError extends Error {
  code: string;
  status?: number;
  retryable: boolean;

  constructor(message: string, code: string, status?: number, retryable: boolean = true) {
    super(message);
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

export async function fetchJsonWithTimeout<T>(
  url: string,
  timeoutMs: number = 8000,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new ModuleRequestError(
        `request_failed:${response.status}`,
        "http_error",
        response.status,
        response.status >= 500 || response.status === 429,
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ModuleRequestError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ModuleRequestError("request_timeout", "timeout", undefined, true);
    }

    throw new ModuleRequestError("network_error", "network", undefined, true);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function runWithRetry<T>(
  operation: () => Promise<T>,
  retries: number = 1,
  delayMs: number = 400,
): Promise<T> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt >= retries) {
        break;
      }
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    }
  }
  throw lastError;
}

export function normalizeModuleError(error: unknown, fallbackMessage: string): ModuleErrorInfo {
  if (error instanceof ModuleRequestError) {
    return {
      message: fallbackMessage,
      code: error.code,
      status: error.status,
      retryable: error.retryable,
    };
  }

  return {
    message: fallbackMessage,
    code: "unknown",
    retryable: true,
  };
}
