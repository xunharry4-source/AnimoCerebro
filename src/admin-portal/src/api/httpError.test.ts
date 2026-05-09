import { describe, expect, it } from "vitest";

import { extractApiErrorMessage } from "./httpError";

describe("extractApiErrorMessage", () => {
  it("prefers user_message over developer-facing provider errors", () => {
    const message = extractApiErrorMessage(
      {
        detail: {
          user_message: "大模型调用失败，请检查 provider 服务状态。",
          developer_message: "Remote provider ollama failed with status 404",
        },
      },
      "fallback",
    );

    expect(message).toBe("大模型调用失败，请检查 provider 服务状态。");
  });
});
