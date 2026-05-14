import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const pagesDir = resolve(testDir, "..");

function source(path: string): string {
  return readFileSync(resolve(pagesDir, path), "utf-8");
}

describe("management page function-log entry buttons", () => {
  it("adds 查看日志 on CLI tool rows and passes the exact command function key", () => {
    const cli = source("cli/CliAssetManager.tsx");
    expect(cli).toContain("查看日志");
    expect(cli).toContain("/console/cli-tools/function-logs?function_key=");
    expect(cli).toContain("(params.row as CliToolItem).command_name");
  });

  it("adds 查看日志 on Agent cards and passes the agent function prefix", () => {
    const agents = source("agents/AgentAssetManager.tsx");
    expect(agents).toContain("查看日志");
    expect(agents).toContain("/console/agents/function-logs?function_prefix=");
    expect(agents).toContain("agent.agent_id");
  });

  it("adds 查看日志 on MCP server rows and passes the server function prefix", () => {
    const mcp = source("mcp/McpServerDashboard.tsx");
    expect(mcp).toContain("查看日志");
    expect(mcp).toContain("/console/mcp-servers/function-logs?function_prefix=");
    expect(mcp).toContain("(params.row as McpServerItem).server_id");
  });

  it("adds 查看日志 on external connector rows and passes the connector function prefix", () => {
    const externalConnectors = source("external-connectors/ExternalConnectorCenter.tsx");
    expect(externalConnectors).toContain("查看日志");
    expect(externalConnectors).toContain("/console/external-connectors/function-logs?function_prefix=");
    expect(externalConnectors).toContain("params.row.connector_id");
  });

  it("adds 查看日志 on internal plugin rows and passes the plugin function prefix", () => {
    const plugins = source("plugins/PluginManagement.tsx");
    expect(plugins).toContain("查看日志");
    expect(plugins).toContain("/console/plugins/function-logs?function_prefix=");
    expect(plugins).toContain("plugin.tool_id");
    expect(plugins).toContain("onViewLogs(row)");
  });
});
