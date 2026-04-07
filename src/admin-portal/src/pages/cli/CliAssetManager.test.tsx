import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CliAssetManager from "./CliAssetManager";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;
globalThis.alert = vi.fn();

describe("CliAssetManager", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("registers a CLI tool and executes a test call", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          command_name: "echo_probe",
          description: "Echo",
          mapped_domain: "cognitive",
          plugin_id: "cli:echo_probe",
          feature_code: "cli.echo_probe",
          read_only: true,
          side_effect_free: true,
          mutates_state: false,
          requires_cloud_audit: false,
          status: "active",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            command_name: "echo_probe",
            description: "Echo",
            mapped_domain: "cognitive",
            plugin_id: "cli:echo_probe",
            feature_code: "cli.echo_probe",
            read_only: true,
            side_effect_free: true,
            mutates_state: false,
            requires_cloud_audit: false,
            status: "active",
          },
        ],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          tool_name: "echo_probe",
          status: "success",
          trace_id: "trace-1",
          exit_code: 0,
          stdout: "hello-zentex\n",
          stderr: "",
          command_line: ["/bin/echo", "hello-zentex"],
        }),
      } as Response);

    render(<CliAssetManager />);

    await waitFor(() => expect(screen.getByText("注册新工具")).toBeInTheDocument());

    fireEvent.click(screen.getByText("注册新工具"));
    fireEvent.change(screen.getByLabelText("工具名称 (tool_name)"), { target: { value: "echo_probe" } });
    fireEvent.change(screen.getByLabelText("执行命令 (command_executable)"), { target: { value: "/bin/echo" } });
    fireEvent.change(screen.getByLabelText("功能说明 (description)"), { target: { value: "Echo" } });
    fireEvent.click(screen.getByText("确认注册"));

    await waitFor(() => expect(screen.getByText("echo_probe")).toBeInTheDocument());

    fireEvent.click(screen.getByText("测试调用"));
    fireEvent.change(screen.getByLabelText("参数 (空格分隔)"), { target: { value: "hello-zentex" } });
    fireEvent.click(screen.getByText("执行测试"));

    await waitFor(() => expect(screen.getByText(/hello-zentex/)).toBeInTheDocument());
  });
});
