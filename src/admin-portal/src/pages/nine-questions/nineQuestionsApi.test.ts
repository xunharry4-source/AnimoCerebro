import { describe, expect, it, vi, afterEach } from "vitest";

import {
  executeNineQuestionRecoveryAction,
  retryNineQuestionModule,
  rollbackSingleNineQuestion,
  runSingleNineQuestion,
} from "./nineQuestionsApi";

describe("runSingleNineQuestion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to the isolated single-question run endpoint without downstream-only flags", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          started: true,
          trace_id: "trace-q1",
          refresh_reason: "single_nine_question_reexecuted:q1",
          snapshot_version: 1,
          revision: 1,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await runSingleNineQuestion("q1", true);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/web/nine-questions/q1/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ force_refresh: true }),
      }),
    );
  });

  it("posts to the rollback endpoint for a single question", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          started: true,
          trace_id: "trace-q1",
          refresh_reason: "single_nine_question_rolled_back:q1",
          snapshot_version: 1,
          revision: 1,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await rollbackSingleNineQuestion("q1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/web/nine-questions/q1/rollback",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("executes a recovery action through its declared path", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          started: true,
          trace_id: "trace-q8",
          refresh_reason: "q8_task_persistence_recovered",
          snapshot_version: 2,
          revision: 1,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await executeNineQuestionRecoveryAction({
      action_id: "q8-recover-task-persistence",
      label: "补写 Q8 任务到 Task Service",
      kind: "partial_replace",
      executable: true,
      path: "/api/web/nine-questions/q8/recover-task-persistence",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/web/nine-questions/q8/recover-task-persistence",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("posts to the module retry endpoint", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          started: true,
          trace_id: "trace-q8",
          refresh_reason: "single_nine_question_module_retried:q8:q8_task_persistence",
          snapshot_version: 2,
          revision: 1,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await retryNineQuestionModule("q8", "q8_task_persistence");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/web/nine-questions/q8/modules/q8_task_persistence/retry",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });
});
