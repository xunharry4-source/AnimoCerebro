import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "./FunctionRuntimeLogsPage.tsx"), "utf-8");
const appSource = readFileSync(resolve(testDir, "../../App.tsx"), "utf-8");

const executionLaneRoutes = [
  "/console/agents/function-logs",
  "/console/plugins/function-logs",
  "/console/cli-tools/function-logs",
  "/console/mcp-servers/function-logs",
  "/console/external-connectors/function-logs",
];

describe("function runtime logs frontend contract", () => {
  it("wires separate function log pages for core and every execution lane", () => {
    const routes = ["/console/core/function-logs", ...executionLaneRoutes];

    for (const route of routes) {
      expect(appSource).toContain(`<Route path="${route}" element={<FunctionRuntimeLogsPage />} />`);
    }
  });

  it("keeps old generic module-log routes out of the execution-lane buttons", () => {
    const forbiddenRoutes = [
      "/console/module-logs/agents",
      "/console/module-logs/plugins",
      "/console/module-logs/cli-tools",
      "/console/module-logs/mcp-servers",
      "/console/module-logs/external-connectors",
    ];

    for (const route of forbiddenRoutes) {
      expect(appSource).not.toContain(route);
    }
  });

  it("groups runtime logs by function identity instead of showing a flat module log table", () => {
    expect(pageSource).toContain("function functionKey(entry: LogEntry, kind: LogKind): string");
    expect(pageSource).toContain('title: "核心功能运行日志"');
    expect(pageSource).toContain('sourceModules: ["core", "kernel", "nine_questions", "task", "learning", "reflection", "memory", "simulation", "upgrade", "audit"]');
    expect(pageSource).toContain('sourceModule: "cli"');
    expect(pageSource).toContain('sourceModule: "agent"');
    expect(pageSource).toContain('sourceModule: "mcp"');
    expect(pageSource).toContain('sourceModule: "connector"');
    expect(pageSource).toContain('sourceModule: "plugin"');
    expect(pageSource).toContain("Promise.all(");
  });

  it("keeps the grouped function-log page read-only; row log buttons live on management pages", () => {
    expect(pageSource).not.toContain('field: "actions"');
    expect(pageSource).not.toContain('headerName: "操作"');
    expect(pageSource).not.toContain("查看日志");
    expect(pageSource).toContain("function_key");
    expect(pageSource).toContain("function_prefix");
  });
});
