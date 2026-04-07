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
import ZentexTaskManager from "./pages/tasks/ZentexTaskManager";
import PluginManagement from "./pages/plugins/PluginManagement";
import UpgradeManagement from "./pages/upgrades/UpgradeManagement";
import CliAssetManager from "./pages/cli/CliAssetManager";
import McpServerDashboard from "./pages/mcp/McpServerDashboard";
import AuditReplay from "./pages/audit/AuditReplay";
import LearningDashboard from "./pages/learning/LearningDashboard";
import { fetchLlmStatus, type LLMStatus } from "./api/llmStatus";
import { useEffect, useState } from "react";

const DRAWER_WIDTH = 240;

const NAV_ITEMS: Array<{ path: string; matchPrefix: string; title: string; subtitle: string }> = [
  {
    path: "/console/dashboard",
    matchPrefix: "/console/dashboard",
    title: "实时指挥台",
    subtitle: "运行态总览",
  },
  {
    path: "/console/nine-questions",
    matchPrefix: "/console/nine-questions",
    title: "9问测试页",
    subtitle: "列表 / 详情 / 沙箱",
  },
  {
    path: "/console/agents",
    matchPrefix: "/console/agents",
    title: "Agent 管理",
    subtitle: "资产与任务流水",
  },
  {
    path: "/console/tasks",
    matchPrefix: "/console/tasks",
    title: "任务管理",
    subtitle: "状态机与人工干预",
  },
  {
    path: "/console/memory",
    matchPrefix: "/console/memory",
    title: "记忆与推理",
    subtitle: "内部待办与复查",
  },
  {
    path: "/console/simulation",
    matchPrefix: "/console/simulation",
    title: "多分支模拟",
    subtitle: "世界模型对比",
  },
  {
    path: "/console/plugins",
    matchPrefix: "/console/plugins",
    title: "插件管理",
    subtitle: "认知工具验收",
  },
  {
    path: "/console/upgrades",
    matchPrefix: "/console/upgrades",
    title: "升级管理",
    subtitle: "LLM / 插件演化",
  },
  {
    path: "/console/cli-tools",
    matchPrefix: "/console/cli-tools",
    title: "CLI 管理",
    subtitle: "外部命令接入",
  },
  {
    path: "/console/mcp-servers",
    matchPrefix: "/console/mcp-servers",
    title: "MCP 管理",
    subtitle: "外部能力接入",
  },
  {
    path: "/console/audit",
    matchPrefix: "/console/audit",
    title: "审计与回放",
    subtitle: "大模型通信调试",
  },
  {
    path: "/console/learning",
    matchPrefix: "/console/learning",
    title: "受控学习",
    subtitle: "学习引擎与溯源",
  },
];

export default function App() {
  const location = useLocation();
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
            <Typography variant="h6">Zentex Pro Mode</Typography>
            <Typography variant="body2" color="text.secondary">
              核心器官插件管理台
            </Typography>
          </Stack>
        </Toolbar>
        <List sx={{ px: 1 }}>
          {NAV_ITEMS.map((item) => (
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
          <Route path="/console/tasks" element={<ZentexTaskManager />} />
          <Route path="/console/memory" element={<MemoryReasoning />} />
          <Route path="/console/simulation" element={<SimulationExplorer />} />
          <Route path="/console/plugins" element={<PluginManagement />} />
          <Route path="/console/upgrades" element={<UpgradeManagement />} />
          <Route path="/console/cli-tools" element={<CliAssetManager />} />
          <Route path="/console/mcp-servers" element={<McpServerDashboard />} />
          <Route path="/console/audit" element={<AuditReplay />} />
          <Route path="/console/learning" element={<LearningDashboard />} />
          <Route path="*" element={<Navigate to="/console/dashboard" replace />} />
        </Routes>
      </Box>
    </Box>
  );
}
