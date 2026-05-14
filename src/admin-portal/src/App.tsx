import {
  Alert,
  Box,
  Drawer,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Toolbar,
  Typography,
} from "@mui/material";
import { Link as RouterLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import ErrorBoundary from "./components/ErrorBoundary";
import { fetchLlmStatus, type LLMStatus } from "./api/llmStatus";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

const DRAWER_WIDTH = 240;

import { useTranslation } from "react-i18next";

const RealtimeDashboard = lazy(() => import("./pages/dashboard/RealtimeDashboard"));
const MemoryReasoning = lazy(() => import("./pages/dashboard/MemoryReasoning"));
const SimulationExplorer = lazy(() => import("./pages/dashboard/SimulationExplorer"));
const HealthDashboard = lazy(() => import("./pages/dashboard/HealthDashboard"));
const WorkspacesPage = lazy(() => import("./pages/WorkspacesPage"));
const NineQuestionsReport = lazy(() => import("./pages/nine-questions/NineQuestionsReport"));
const Q1Detail = lazy(() => import("./pages/nine-questions/q1/Q1Detail"));
const Q1Test = lazy(() => import("./pages/nine-questions/q1/Q1Test"));
const Q2Detail = lazy(() => import("./pages/nine-questions/q2/Q2Detail"));
const Q2Test = lazy(() => import("./pages/nine-questions/q2/Q2Test"));
const Q3Detail = lazy(() => import("./pages/nine-questions/q3/Q3Detail"));
const Q3Test = lazy(() => import("./pages/nine-questions/q3/Q3Test"));
const Q4Detail = lazy(() => import("./pages/nine-questions/q4/Q4Detail"));
const Q4Test = lazy(() => import("./pages/nine-questions/q4/Q4Test"));
const Q5Detail = lazy(() => import("./pages/nine-questions/q5/Q5Detail"));
const Q5Test = lazy(() => import("./pages/nine-questions/q5/Q5Test"));
const Q6Detail = lazy(() => import("./pages/nine-questions/q6/Q6Detail"));
const Q6Test = lazy(() => import("./pages/nine-questions/q6/Q6Test"));
const Q7Detail = lazy(() => import("./pages/nine-questions/q7/Q7Detail"));
const Q7Test = lazy(() => import("./pages/nine-questions/q7/Q7Test"));
const Q8Detail = lazy(() => import("./pages/nine-questions/q8/Q8Detail"));
const Q8Test = lazy(() => import("./pages/nine-questions/q8/Q8Test"));
const Q9Detail = lazy(() => import("./pages/nine-questions/q9/Q9Detail"));
const Q9Test = lazy(() => import("./pages/nine-questions/q9/Q9Test"));
const NineQuestionDetailPage = lazy(() => import("./pages/nine-questions/NineQuestionDetailPage"));
const NineQuestionSandboxPage = lazy(() => import("./pages/nine-questions/NineQuestionSandboxPage"));
const NineQuestionWorkflowGraphPage = lazy(() => import("./pages/nine-questions/NineQuestionWorkflowGraphPage"));
const AgentAssetManager = lazy(() => import("./pages/agents/AgentAssetManager"));
const AgentDetail = lazy(() => import("./pages/agents/AgentDetail"));
const ZentexTaskManager = lazy(() => import("./pages/tasks/ZentexTaskManager"));
const TaskDetailPage = lazy(() => import("./pages/tasks/TaskDetailPage"));
const TaskLogsPage = lazy(() => import("./pages/tasks/TaskLogsPage"));
const TaskWorkflowPage = lazy(() => import("./pages/tasks/TaskWorkflowPage"));
const ModuleLogsPage = lazy(() => import("./pages/module-logs/ModuleLogsPage"));
const FunctionRuntimeLogsPage = lazy(() => import("./pages/function-logs/FunctionRuntimeLogsPage"));
const PluginManagement = lazy(() => import("./pages/plugins/PluginManagement"));
const CognitivePluginDetailPage = lazy(() => import("./pages/plugins/CognitivePluginDetailPage"));
const FunctionalPluginDetailPage = lazy(() => import("./pages/plugins/FunctionalPluginDetailPage"));
const UpgradeManagement = lazy(() => import("./pages/upgrades/UpgradeManagement"));
const UpgradeDetailPage = lazy(() => import("./pages/upgrades/UpgradeDetailPage"));
const CliAssetManager = lazy(() => import("./pages/cli/CliAssetManager"));
const CliToolDetailPage = lazy(() => import("./pages/cli/CliToolDetailPage"));
const ExternalConnectorCenter = lazy(() => import("./pages/external-connectors/ExternalConnectorCenter"));
const McpServerDashboard = lazy(() => import("./pages/mcp/McpServerDashboard"));
const McpServerDetail = lazy(() => import("./pages/mcp/McpServerDetail"));
const AuditReplay = lazy(() => import("./pages/audit/AuditReplay"));
const AuditTraceCenterPage = lazy(() => import("./pages/audit/AuditTraceCenterPage"));
const AuditTraceModePage = lazy(() => import("./pages/audit/AuditTraceModePage"));
const AuditReviewLedgerPage = lazy(() => import("./pages/audit/AuditReviewLedgerPage"));
const TranscriptReplayPage = lazy(() => import("./pages/audit/TranscriptReplayPage"));
const LearningDashboard = lazy(() => import("./pages/learning/LearningDashboard"));
const ReflectionDailyPage = lazy(() => import("./pages/reflections/ReflectionDailyPage"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));

const NAV_ITEMS = (t: any) => [
  {
    path: "/console/dashboard",
    matchPrefix: "/console/dashboard",
    title: t("app.nav.dashboard.title"),
    subtitle: t("app.nav.dashboard.subtitle"),
  },
  {
    path: "/console/core/function-logs",
    matchPrefix: "/console/core",
    title: "核心",
    subtitle: "核心功能运行日志",
  },
  {
    path: "/console/nine-questions",
    matchPrefix: "/console/nine-questions",
    title: t("app.nav.nineQuestions.title"),
    subtitle: t("app.nav.nineQuestions.subtitle"),
  },
  {
    path: "/console/agents",
    matchPrefix: "/console/agents",
    title: t("app.nav.agents.title"),
    subtitle: t("app.nav.agents.subtitle"),
  },
  {
    path: "/console/tasks",
    matchPrefix: "/console/tasks",
    title: t("app.nav.tasks.title"),
    subtitle: t("app.nav.tasks.subtitle"),
  },
  {
    path: "/console/memory",
    matchPrefix: "/console/memory",
    title: t("app.nav.memory.title"),
    subtitle: t("app.nav.memory.subtitle"),
  },
  {
    path: "/console/simulation",
    matchPrefix: "/console/simulation",
    title: t("app.nav.simulation.title"),
    subtitle: t("app.nav.simulation.subtitle"),
  },
  {
    path: "/console/plugins",
    matchPrefix: "/console/plugins",
    title: t("app.nav.plugins.title"),
    subtitle: t("app.nav.plugins.subtitle"),
  },
  {
    path: "/console/upgrades",
    matchPrefix: "/console/upgrades",
    title: t("app.nav.upgrades.title"),
    subtitle: t("app.nav.upgrades.subtitle"),
  },
  {
    path: "/console/cli-tools",
    matchPrefix: "/console/cli-tools",
    title: t("app.nav.cli.title"),
    subtitle: t("app.nav.cli.subtitle"),
  },
  {
    path: "/console/mcp-servers",
    matchPrefix: "/console/mcp-servers",
    title: t("app.nav.mcp.title"),
    subtitle: t("app.nav.mcp.subtitle"),
  },
  {
    path: "/console/external-connectors",
    matchPrefix: "/console/external-connectors",
    title: "外部应用连接器",
    subtitle: "Office / SaaS / 文件应用",
  },
  {
    path: "/console/audit",
    matchPrefix: "/console/audit",
    title: t("app.nav.audit.title"),
    subtitle: t("app.nav.audit.subtitle"),
  },
  {
    path: "/console/learning",
    matchPrefix: "/console/learning",
    title: t("app.nav.learning.title"),
    subtitle: t("app.nav.learning.subtitle"),
  },
  {
    path: "/console/health",
    matchPrefix: "/console/health",
    title: t("app.nav.health.title"),
    subtitle: t("app.nav.health.subtitle"),
  },
  {
    path: "/console/workspaces",
    matchPrefix: "/console/workspaces",
    title: t("app.nav.workspaces.title"),
    subtitle: t("app.nav.workspaces.subtitle"),
  },
  {
    path: "/console/settings",
    matchPrefix: "/console/settings",
    title: t("app.nav.settings.title"),
    subtitle: t("app.nav.settings.subtitle"),
  },
];

export default function App() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const navItems = useMemo(() => NAV_ITEMS(t), [t]);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [llmStatusError, setLlmStatusError] = useState<string | null>(null);

  useEffect(() => {
    const loadLlmStatus = async () => {
      try {
        // Startup should only verify baseline provider availability/configuration.
        // Live probes are better triggered explicitly in diagnostic pages.
        const status = await fetchLlmStatus(false);
        setLlmStatus(status);
        setLlmStatusError(null);
      } catch (err) {
        setLlmStatus(null);
        setLlmStatusError(err instanceof Error ? err.message : "LLM 状态检查失败，请检查后端。");
      }
    };
    void loadLlmStatus();
  }, []);

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "background.default" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
          },
        }}
      >
        <Toolbar>
          <Stack spacing={0.5}>
            <Typography variant="h6">{t("app.title")}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t("app.subtitle")}
            </Typography>
          </Stack>
        </Toolbar>
        <List sx={{ px: 1 }}>
          {navItems.map((item) => (
            <ListItemButton
              key={item.path}
              component={RouterLink}
              to={item.path}
              selected={location.pathname.startsWith(item.matchPrefix)}
              sx={{ borderRadius: 2, mb: 0.5 }}
            >
              <ListItemText primary={item.title} secondary={item.subtitle} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        {llmStatusError ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="global-llm-status-alert">
            启动前 LLM 探针执行失败：{llmStatusError}
          </Alert>
        ) : llmStatus && !llmStatus.available ? (
          <Alert severity="error" sx={{ mb: 2 }} data-testid="global-llm-status-alert">
            启动前 LLM 检查未通过。
            {llmStatus.provider_name ? ` Provider: ${llmStatus.provider_name}。` : ""}
            {llmStatus.hint ? ` ${llmStatus.hint}` : ""}
          </Alert>
        ) : null}
        <ErrorBoundary>
          <Suspense
            fallback={
              <Stack alignItems="center" justifyContent="center" sx={{ py: 8 }}>
                <Typography variant="body2" color="text.secondary">
                  {t("common.loading")}
                </Typography>
              </Stack>
            }
          >
          <Routes>
          <Route path="/" element={<Navigate to="/console/dashboard" replace />} />
          <Route path="/console/core" element={<Navigate to="/console/core/function-logs" replace />} />
          <Route path="/console/core/function-logs" element={<FunctionRuntimeLogsPage />} />
          <Route path="/console/dashboard" element={<RealtimeDashboard />} />
          <Route path="/console/nine-questions" element={<NineQuestionsReport />} />
          
          {/* Q1-Q9 Dedicated & Isolated Audit Routes */}
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
          <Route path="/console/nine-questions/q1/test" element={<Q1Test />} />

          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
          <Route path="/console/nine-questions/q2/test" element={<Q2Test />} />

          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
          <Route path="/console/nine-questions/q3/test" element={<Q3Test />} />

          <Route path="/console/nine-questions/q4" element={<Q4Detail />} />
          <Route path="/console/nine-questions/q4/test" element={<Q4Test />} />

          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
          <Route path="/console/nine-questions/q5/test" element={<Q5Test />} />

          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
          <Route path="/console/nine-questions/q6/test" element={<Q6Test />} />

          <Route path="/console/nine-questions/q7" element={<Q7Detail />} />
          <Route path="/console/nine-questions/q7/test" element={<Q7Test />} />

          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
          <Route path="/console/nine-questions/q8/test" element={<Q8Test />} />

          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
          <Route path="/console/nine-questions/q9/test" element={<Q9Test />} />

          {/* Workflow graph — shared across all q1-q9 */}
          <Route path="/console/nine-questions/:q_id/workflow" element={<NineQuestionWorkflowGraphPage />} />

          {/* Legacy/Generic routes (deprecated but kept for absolute fallback) */}
          <Route path="/console/nine-questions/:q_id" element={<NineQuestionDetailPage />} />
          <Route path="/console/nine-questions/:q_id/sandbox" element={<NineQuestionSandboxPage />} />
          <Route path="/console/agents" element={<AgentAssetManager />} />
          <Route path="/console/agents/function-logs" element={<FunctionRuntimeLogsPage />} />
          <Route path="/console/module-logs" element={<ModuleLogsPage />} />
          <Route path="/console/module-logs/:moduleId" element={<ModuleLogsPage />} />
          <Route path="/console/agents/:agentId" element={<AgentDetail />} />
          <Route path="/console/tasks" element={<ZentexTaskManager />} />
          <Route path="/console/tasks/logs" element={<TaskLogsPage />} />
          <Route path="/console/tasks/:task_id/logs" element={<TaskLogsPage />} />
          <Route path="/console/tasks/:task_id/workflow" element={<TaskWorkflowPage />} />
          <Route path="/console/tasks/:task_id" element={<TaskDetailPage />} />
          <Route path="/console/memory" element={<MemoryReasoning />} />
          <Route path="/console/simulation" element={<SimulationExplorer />} />
          <Route path="/console/plugins" element={<PluginManagement />} />
          <Route path="/console/plugins/function-logs" element={<FunctionRuntimeLogsPage />} />
          <Route path="/console/plugins/cognitive/:pluginId" element={<CognitivePluginDetailPage />} />
          <Route path="/console/plugins/functional/:pluginId" element={<FunctionalPluginDetailPage />} />
          <Route path="/console/upgrades" element={<UpgradeManagement />} />
          <Route path="/console/upgrades/:record_id" element={<UpgradeDetailPage />} />
          <Route path="/console/cli-tools" element={<CliAssetManager />} />
          <Route path="/console/cli-tools/function-logs" element={<FunctionRuntimeLogsPage />} />
          <Route path="/console/cli-tools/:toolName" element={<CliToolDetailPage />} />
          <Route path="/console/mcp-servers" element={<McpServerDashboard />} />
          <Route path="/console/mcp-servers/function-logs" element={<FunctionRuntimeLogsPage />} />
          <Route path="/console/mcp-servers/:server_id" element={<McpServerDetail />} />
          <Route path="/console/external-connectors" element={<ExternalConnectorCenter />} />
          <Route path="/console/external-connectors/function-logs" element={<FunctionRuntimeLogsPage />} />
          <Route path="/console/audit" element={<AuditTraceCenterPage />} />
          <Route path="/console/audit/model-provider" element={<AuditReplay />} />
          <Route path="/console/audit/review-ledger" element={<AuditReviewLedgerPage />} />
          <Route path="/console/audit/transcript-replay/:event_id" element={<TranscriptReplayPage />} />
          <Route path="/console/audit/:mode/:view" element={<AuditTraceModePage />} />
          <Route path="/console/learning" element={<LearningDashboard />} />
          <Route path="/console/reflections" element={<ReflectionDailyPage />} />
          <Route path="/console/reflections/plugin" element={<ReflectionDailyPage initialSource="plugin" />} />
          <Route path="/console/health" element={<HealthDashboard />} />
          <Route path="/console/workspaces" element={<WorkspacesPage />} />
          <Route path="/console/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/console/dashboard" replace />} />
        </Routes>
          </Suspense>
        </ErrorBoundary>
      </Box>
    </Box>
  );
}
