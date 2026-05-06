import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import zhCN from "../../locales/zh-CN.json";
import enUS from "../../locales/en-US.json";
import {
  formatForbiddenActionsForEditor,
  formatTaskGoalsForEditor,
  formatTaskGoalsForList,
  serializeForbiddenActionsFromEditor,
  serializeTaskGoalsFromEditor,
  serializeTaskGoalsFromList,
} from "./SettingsPage";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../../App.tsx"), "utf-8");

function getValue(locale: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((current, part) => {
    if (!current || typeof current !== "object") {
      return undefined;
    }
    return (current as Record<string, unknown>)[part];
  }, locale);
}

describe("/console/settings frontend contract", () => {
  it("keeps the settings page route and navigation wired", () => {
    expect(appSource).toContain('lazy(() => import("./pages/settings/SettingsPage"))');
    expect(appSource).toContain('path: "/console/settings"');
    expect(appSource).toContain('<Route path="/console/settings" element={<SettingsPage />} />');
  });

  it("defines settings locale keys for supported languages", () => {
    expect(getValue(zhCN, "app.nav.settings.title")).toEqual(expect.any(String));
    expect(getValue(enUS, "app.nav.settings.title")).toEqual(expect.any(String));
    expect(getValue(zhCN, "settings.save")).toEqual(expect.any(String));
    expect(getValue(enUS, "settings.save")).toEqual(expect.any(String));
    expect(getValue(zhCN, "settings.addForbiddenAction")).toEqual(expect.any(String));
    expect(getValue(enUS, "settings.addForbiddenAction")).toEqual(expect.any(String));
    expect(getValue(zhCN, "settings.addTaskGoal")).toEqual(expect.any(String));
    expect(getValue(enUS, "settings.addTaskGoal")).toEqual(expect.any(String));
    expect(getValue(zhCN, "settings.removeTaskGoal")).toEqual(expect.any(String));
    expect(getValue(enUS, "settings.removeTaskGoal")).toEqual(expect.any(String));
  });

  it("normalizes task goals between stored JSON, editor text, and list state", () => {
    expect(formatTaskGoalsForEditor('["保持审计链完整","优先修复阻塞任务"]')).toBe(
      "保持审计链完整\n优先修复阻塞任务",
    );
    expect(formatTaskGoalsForList("- 保持审计链完整\n2. 优先修复阻塞任务")).toEqual([
      "保持审计链完整",
      "优先修复阻塞任务",
    ]);
    expect(serializeTaskGoalsFromEditor("保持审计链完整\n\n 优先修复阻塞任务 ")).toBe(
      '["保持审计链完整","优先修复阻塞任务"]',
    );
    expect(serializeTaskGoalsFromList(["保持审计链完整", "", " 优先修复阻塞任务 "])).toBe(
      '["保持审计链完整","优先修复阻塞任务"]',
    );
    expect(serializeTaskGoalsFromEditor(" \n ")).toBeUndefined();
    expect(serializeTaskGoalsFromList([" ", ""])).toBeUndefined();
  });

  it("normalizes forbidden actions between stored text and editor items", () => {
    expect(formatForbiddenActionsForEditor("- 删除生产数据\n2. 修改凭证\n绕过测试")).toEqual([
      "删除生产数据",
      "修改凭证",
      "绕过测试",
    ]);
    expect(formatForbiddenActionsForEditor('["删除生产数据"," 修改凭证 "]')).toEqual([
      "删除生产数据",
      "修改凭证",
    ]);
    expect(serializeForbiddenActionsFromEditor(["删除生产数据", "", " 修改凭证 "])).toBe(
      "删除生产数据\n修改凭证",
    );
    expect(serializeForbiddenActionsFromEditor([" ", ""])).toBeUndefined();
  });
});
