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

import RealtimeDashboard from "./pages/dashboard/RealtimeDashboard";
import MemoryReasoning from "./pages/dashboard/MemoryReasoning";
import SimulationExplorer from "./pages/dashboard/SimulationExplorer";
import HealthDashboard from "./pages/dashboard/HealthDashboard";
import WorkspacesPage from "./pages/WorkspacesPage";
import NineQuestionsReport from "./pages/nine-questions/NineQuestionsReport";

// Q1-Q9 Isolated Audit Components (Zentex G31A Compliance)
import Q1Detail from "./pages/nine-questions/q1/Q1Detail";
import Q1Test from "./pages/nine-questions/q1/Q1Test";
import Q2Detail from "./pages/nine-questions/q2/Q2Detail";
import Q2Test from "./pages/nine-questions/q2/Q2Test";
import Q3Detail from "./pages/nine-questions/q3/Q3Detail";
import Q3Test from "./pages/nine-questions/q3/Q3Test";
import Q4Detail from "./pages/nine-questions/q4/Q4Detail";
import Q4Test from "./pages/nine-questions/q4/Q4Test";
import Q5Detail from "./pages/nine-questions/q5/Q5Detail";
import Q5Test from "./pages/nine-questions/q5/Q5Test";
import Q6Detail from "./pages/nine-questions/q6/Q6Detail";
import Q6Test from "./pages/nine-questions/q6/Q6Test";
import Q7Detail from "./pages/nine-questions/q7/Q7Detail";
import Q7Test from "./pages/nine-questions/q7/Q7Test";
import Q8Detail from "./pages/nine-questions/q8/Q8Detail";
import Q8Test from "./pages/nine-questions/q8/Q8Test";
import Q9Detail from "./pages/nine-questions/q9/Q9Detail";
import Q9Test from "./pages/nine-questions/q9/Q9Test";

import NineQuestionDetailPage from "./pages/nine-questions/NineQuestionDetailPage";
import NineQuestionSandboxPage from "./pages/nine-questions/NineQuestionSandboxPage";
import AgentAssetManager from "./pages/agents/AgentAssetManager";
import AgentDetail from "./pages/agents/AgentDetail";
import ZentexTaskManager from "./pages/tasks/ZentexTaskManager";
import PluginManagement from "./pages/plugins/PluginManagement";
import CognitivePluginDetailPage from "./pages/plugins/CognitivePluginDetailPage";
import FunctionalPluginDetailPage from "./pages/plugins/FunctionalPluginDetailPage";
import UpgradeManagement from "./pages/upgrades/UpgradeManagement";
import UpgradeDetailPage from "./pages/upgrades/UpgradeDetailPage";
import CliAssetManager from "./pages/cli/CliAssetManager";
import CliToolDetailPage from "./pages/cli/CliToolDetailPage";
import McpServerDashboard from "./pages/mcp/McpServerDashboard";
import McpServerDetail from "./pages/mcp/McpServerDetail";
import AuditReplay from "./pages/audit/AuditReplay";
import LearningDashboard from "./pages/learning/LearningDashboard";
import { fetchLlmStatus, type LLMStatus } from "./api/llmStatus";
import { useEffect, useMemo, useState } from "react";

const DRAWER_WIDTH = 240;

import { useTranslation } from "react-i18next";

const NAV_ITEMS = (t: any) => [
  {
    path: "/console/dashboard",
    matchPrefix: "/console/dashboard",
    title: t("app.nav.dashboard.title"),
    subtitle: t("app.nav.dashboard.subtitle"),
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
        const status = await fetchLlmStatus(true);
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
        <Routes>
          <Route path="/" element={<Navigate to="/console/dashboard" replace />} />
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

          {/* Legacy/Generic routes (deprecated but kept for absolute fallback) */}
          <Route path="/console/nine-questions/:q_id" element={<NineQuestionDetailPage />} />
          <Route path="/console/nine-questions/:q_id/sandbox" element={<NineQuestionSandboxPage />} />
          <Route path="/console/agents" element={<AgentAssetManager />} />
          <Route path="/console/agents/:agentId" element={<AgentDetail />} />
          <Route path="/console/tasks" element={<ZentexTaskManager />} />
          <Route path="/console/memory" element={<MemoryReasoning />} />
          <Route path="/console/simulation" element={<SimulationExplorer />} />
          <Route path="/console/plugins" element={<PluginManagement />} />
          <Route path="/console/plugins/cognitive/:pluginId" element={<CognitivePluginDetailPage />} />
          <Route path="/console/plugins/functional/:pluginId" element={<FunctionalPluginDetailPage />} />
          <Route path="/console/upgrades" element={<UpgradeManagement />} />
          <Route path="/console/upgrades/:record_id" element={<UpgradeDetailPage />} />
          <Route path="/console/cli-tools" element={<CliAssetManager />} />
          <Route path="/console/cli-tools/:toolName" element={<CliToolDetailPage />} />
          <Route path="/console/mcp-servers" element={<McpServerDashboard />} />
          <Route path="/console/mcp-servers/:server_id" element={<McpServerDetail />} />
          <Route path="/console/audit" element={<AuditReplay />} />
          <Route path="/console/learning" element={<LearningDashboard />} />
          <Route path="/console/health" element={<HealthDashboard />} />
          <Route path="/console/workspaces" element={<WorkspacesPage />} />
          <Route path="*" element={<Navigate to="/console/dashboard" replace />} />
        </Routes>
      </Box>
    </Box>
  );
}
