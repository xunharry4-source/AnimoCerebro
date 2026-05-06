import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { getPluginLifecycleActionState } from "./PluginManagement";
import type { PluginRow } from "./pluginsApi";
import zhCN from "../../locales/zh-CN.json";
import enUS from "../../locales/en-US.json";

function pluginRow(overrides: Partial<PluginRow>): PluginRow {
  return {
    tool_id: "document_router",
    feature_code: "document_router",
    supports_multiple_plugins: false,
    plugin_kind: "functional",
    version: "1.0.0",
    lifecycle_status: "active",
    operational_status: "enabled",
    health_status: null,
    purpose: "route documents",
    description: "route documents",
    used_in: [],
    is_default: false,
    is_official_release: true,
    can_force_enable: true,
    can_force_disable: true,
    can_delete: true,
    usage_count: 0,
    failure_count: 0,
    rollback_conditions: [],
    trigger_conditions: [],
    required_context: [],
    created_at: null,
    updated_at: null,
    started_at: null,
    stopped_at: null,
    last_used_at: null,
    ...overrides,
  };
}

describe("getPluginLifecycleActionState", () => {
  it("hides force-enable for plugins that are already active and enabled", () => {
    expect(
      getPluginLifecycleActionState(
        pluginRow({
          lifecycle_status: "active",
          operational_status: "enabled",
          can_force_enable: true,
          can_force_disable: true,
        }),
      ),
    ).toEqual({ canShowForceEnable: false, canShowForceDisable: true });
  });

  it("shows force-enable only when backend permission is true and plugin is not active-enabled", () => {
    expect(
      getPluginLifecycleActionState(
        pluginRow({
          lifecycle_status: "active",
          operational_status: "stopped",
          can_force_enable: true,
          can_force_disable: false,
        }),
      ),
    ).toEqual({ canShowForceEnable: true, canShowForceDisable: false });
  });

  it("does not invent actions when backend permissions are false", () => {
    expect(
      getPluginLifecycleActionState(
        pluginRow({
          lifecycle_status: "sandbox_verified",
          operational_status: "unavailable",
          can_force_enable: false,
          can_force_disable: false,
        }),
      ),
    ).toEqual({ canShowForceEnable: false, canShowForceDisable: false });
  });
});

describe("PluginManagement i18n contract", () => {
  it("defines every plugins.* key rendered by the management page for zh-CN and en-US", () => {
    const source = readFileSync(resolve(__dirname, "PluginManagement.tsx"), "utf-8");
    const keys = [...source.matchAll(/t\("plugins\.([A-Za-z0-9_]+)"\)/g)].map((match) => match[1]);
    expect(keys.length).toBeGreaterThan(0);

    for (const key of new Set(keys)) {
      const zhValue = (zhCN.plugins as Record<string, unknown>)[key];
      const enValue = (enUS.plugins as Record<string, unknown>)[key];
      expect(zhValue, `missing zh-CN plugins.${key}`).toEqual(expect.any(String));
      expect(enValue, `missing en-US plugins.${key}`).toEqual(expect.any(String));
      expect(zhValue).not.toBe(`plugins.${key}`);
      expect(enValue).not.toBe(`plugins.${key}`);
    }
  });
});
