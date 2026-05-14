import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import zhCN from "../../locales/zh-CN.json";
import enUS from "../../locales/en-US.json";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "ZentexTaskManager.tsx"), "utf-8");
const hookSource = readFileSync(resolve(testDir, "useTaskManagement.ts"), "utf-8");
const detailSource = readFileSync(resolve(testDir, "TaskDetailPage.tsx"), "utf-8");
const workflowSource = readFileSync(resolve(testDir, "TaskWorkflowPage.tsx"), "utf-8");
const appSource = readFileSync(resolve(testDir, "../../App.tsx"), "utf-8");

const expectedTaskGroups = [
  "all",
  "in_progress",
  "todo",
  "blocked",
  "waiting_confirmation",
  "completed",
  "failed",
  "suspended",
  "archived",
  "cancelled",
];

function getValue(locale: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((current, part) => {
    if (!current || typeof current !== "object") {
      return undefined;
    }
    return (current as Record<string, unknown>)[part];
  }, locale);
}

function expectLocalePath(path: string) {
  const zhValue = getValue(zhCN, path);
  const enValue = getValue(enUS, path);
  expect(zhValue, `missing zh-CN ${path}`).toEqual(expect.any(String));
  expect(enValue, `missing en-US ${path}`).toEqual(expect.any(String));
  expect(zhValue).not.toBe(path);
  expect(enValue).not.toBe(path);
}

function extractTabGroupsFromPage(): string[] {
  return [...pageSource.matchAll(/key:\s*'([^']+)'/g)].map((match) => match[1]);
}

function extractHookGroups(): string[] {
  const match = hookSource.match(/const TAB_GROUPS:[\s\S]*?=\s*\[([\s\S]*?)\];/);
  expect(match, "useTaskManagement TAB_GROUPS must be explicit").not.toBeNull();
  return [...(match?.[1] ?? "").matchAll(/'([^']+)'/g)].map((group) => group[1]);
}

describe("/console/tasks frontend contract", () => {
  it("keeps the route wired to the task manager lazy module", () => {
    expect(appSource).toContain('lazy(() => import("./pages/tasks/ZentexTaskManager"))');
    expect(appSource).toContain('lazy(() => import("./pages/tasks/TaskWorkflowPage"))');
    expect(appSource).toContain('<Route path="/console/tasks" element={<ZentexTaskManager />} />');
    expect(appSource).toContain('<Route path="/console/tasks/:task_id/workflow" element={<TaskWorkflowPage />} />');
  });

  it("keeps rendered tabs aligned with the paginated tasks/page API groups", () => {
    expect(extractTabGroupsFromPage()).toEqual(expectedTaskGroups);
    expect(extractHookGroups()).toEqual(expectedTaskGroups);
    expect(hookSource).toContain("params.set(\"group\", group)");
    expect(hookSource).toContain("params.set(\"limit\", String(paginationModel.pageSize))");
    expect(hookSource).toContain("params.set(\"offset\", String(paginationModel.page * paginationModel.pageSize))");
    expect(hookSource).toContain("const url = `/api/web/tasks/page?${params.toString()}`");
  });

  it("fails visibly instead of leaving the page in infinite loading when tasks/page hangs", () => {
    expect(hookSource).toContain("const TASK_PAGE_FETCH_TIMEOUT_MS = 10000");
    expect(hookSource).toContain("new AbortController()");
    expect(hookSource).toContain("fetch(url, { signal: controller.signal })");
    expect(hookSource).toContain("获取任务列表超时");
    expect(hookSource).toContain("window.clearTimeout(timeoutId)");
  });

  it("defines every static tasks.* key rendered by the task manager for zh-CN and en-US", () => {
    const staticTaskKeys = [...`${pageSource}\n${detailSource}\n${workflowSource}`.matchAll(/t\('tasks\.([A-Za-z0-9_.]+)'/g)].map(
      (match) => `tasks.${match[1]}`,
    );
    expect(staticTaskKeys.length).toBeGreaterThan(0);

    for (const path of new Set(staticTaskKeys)) {
      expectLocalePath(path);
    }
  });

  it("keeps the visible task grid limited to the requested business columns plus view action", () => {
    const columnsMatch = pageSource.match(/const columns: GridColDef\[\] = \[([\s\S]*?)\n  \];/);
    expect(columnsMatch, "task grid columns must stay explicit").not.toBeNull();
    const fields = [...(columnsMatch?.[1] ?? "").matchAll(/field:\s*'([^']+)'/g)].map((match) => match[1]);

    expect(fields).toEqual([
      "task_id",
      "title",
      "created_at",
      "objective",
      "source_module",
      "trigger_event",
      "status",
      "actions",
    ]);
    expect(pageSource).toContain("headerName: t('tasks.createdAt')");
    expect(pageSource).toContain("formatTaskDateTime(row.created_at)");
    expect(pageSource).toContain("navigate(`/console/tasks/${task.task_id}`)");
    expect(pageSource).toContain("navigate(`/console/tasks/${task.task_id}/workflow`)");
    expect(pageSource).toContain("t('tasks.viewWorkflow')");
    expect(pageSource).not.toContain("<Dialog open={Boolean(viewTask)}");
    expect(hookSource).toContain('params.set("root_only", "true")');
  });

  it("renders task workflow through React Flow with real detail and audit-log data", () => {
    expect(workflowSource).toContain('from \'@xyflow/react\'');
    expect(workflowSource).toContain('import \'@xyflow/react/dist/style.css\'');
    expect(workflowSource).toContain('<ReactFlow');
    expect(workflowSource).toContain('<Background');
    expect(workflowSource).toContain('<Controls');
    expect(workflowSource).toContain('<MiniMap');
    expect(workflowSource).toContain('fetch(`/api/web/tasks/${task_id}/detail`)');
    expect(workflowSource).toContain('fetch(`/api/web/tasks/${taskId}/logs?limit=50`)');
    expect(workflowSource).toContain('buildTaskNodeData(detail.task');
    expect(workflowSource).toContain('buildTaskNodeData(subtask');
    expect(workflowSource).toContain('execution_output');
    expect(workflowSource).toContain('contract');
    expect(workflowSource).toContain('metadata');
    expect(workflowSource).toContain('metadata?.react_execution');
    expect(workflowSource).toContain('graph_runs');
    expect(workflowSource).toContain('buildReactNodeData');
    expect(workflowSource).toContain("t('tasks.workflowReactNode')");
    expect(workflowSource).toContain('execution_assignment');
    expect(workflowSource).toContain("t('tasks.exceptionReason')");
  });

  it("renders task detail subtasks as a flow table with execution and exception fields", () => {
    expect(detailSource).toContain("t('tasks.subtaskFlow')");
    expect(detailSource).toContain("t('tasks.subtaskName')");
    expect(detailSource).toContain("t('tasks.verificationMethod')");
    expect(detailSource).toContain("t('tasks.exceptionReason')");
    expect(detailSource).toContain("formatSubtaskObjective(subtask)");
    expect(detailSource).toContain("formatTaskVerificationMethod(subtask, t)");
    expect(detailSource).toContain("formatExecutionParty(subtask, t)");
    expect(detailSource).toContain("formatTaskDateTime(taskStartTime(subtask))");
    expect(detailSource).toContain("formatTaskDateTime(taskEndTime(subtask))");
    expect(detailSource).toContain("formatTaskExceptionReason(subtask, t)");
    expect(detailSource).not.toContain("subtasks.length > 0 && (");
  });

  it("defines task status and source-module labels used by the visible filters", () => {
    const sourceFilters = [...pageSource.matchAll(/const TASK_SOURCE_FILTERS = \[([\s\S]*?)\];/g)]
      .flatMap((match) => [...match[1].matchAll(/'([^']+)'/g)].map((source) => source[1]));

    expect(sourceFilters).toEqual(["nine_questions", "nine_questions.q8", "nine_questions.q9", "reflection", "learning", "upgrade", "manual"]);

    for (const group of expectedTaskGroups) {
      if (["all", "in_progress", "waiting_confirmation", "completed", "failed", "cancelled"].includes(group)) {
        continue;
      }
      expectLocalePath(`tasks.statuses.${group}`);
    }

    for (const source of sourceFilters) {
      expectLocalePath(`tasks.sourceModules.${source.replace(/\./g, "_")}`);
    }
  });
});
