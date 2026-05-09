import { useEffect, useState } from "react";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { Link as RouterLink } from "react-router-dom";

import {
  fetchQ2AssetStatistics,
  fetchQ2LlmTrace,
  getQuestionDisplayLabel,
} from "../nineQuestionsApi";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionSectionBoundary from "../../../components/NineQuestionSectionBoundary";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};
}

function statNumber(value: unknown): number {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function hasMaterialValue(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.some(hasMaterialValue);
  if (typeof value === "object") {
    return Object.values(asRecord(value)).some(hasMaterialValue);
  }
  return true;
}

function renderCodeBlock(value: unknown) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 2,
        bgcolor: "action.hover",
        borderRadius: 1,
        overflow: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        fontSize: "0.85rem",
      }}
    >
      <code>{typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2)}</code>
    </Box>
  );
}

type AssetStatLink = {
  key: string;
  label: string;
  statKey: string;
  to: string;
  destinationLabel: string;
  testId: string;
};

const ASSET_STAT_LINKS: AssetStatLink[] = [
  {
    key: "internal-plugin",
    label: "内部插件",
    statKey: "internal_plugin_count",
    to: "/console/plugins",
    destinationLabel: "插件页面",
    testId: "q2-stat-internal-plugin-count",
  },
  {
    key: "cli",
    label: "CLI",
    statKey: "cli_count",
    to: "/console/cli-tools",
    destinationLabel: "CLI 页面",
    testId: "q2-stat-cli-count",
  },
  {
    key: "mcp",
    label: "MCP",
    statKey: "mcp_count",
    to: "/console/mcp-servers",
    destinationLabel: "MCP 页面",
    testId: "q2-stat-mcp-count",
  },
  {
    key: "agent",
    label: "Agent",
    statKey: "agent_count",
    to: "/console/agents",
    destinationLabel: "Agent 页面",
    testId: "q2-stat-agent-count",
  },
  {
    key: "external-service",
    label: "外接服务",
    statKey: "external_service_count",
    to: "/console/external-connectors",
    destinationLabel: "外接服务页面",
    testId: "q2-stat-external-service-count",
  },
];

function normalizeTokenUsage(value: unknown): Record<string, number> {
  const tokenUsage = asRecord(value);
  return {
    input_tokens: Number(tokenUsage.input_tokens || 0),
    output_tokens: Number(tokenUsage.output_tokens || 0),
    total_tokens: Number(tokenUsage.total_tokens || 0),
  };
}

function normalizeQ2LlmExchange(value: unknown): Record<string, any> | null {
  const payload = asRecord(value);
  const internal = asRecord(payload.internal_tool_llm);
  const external = asRecord(payload.external_tool_llm);
  const internalInput = asRecord(internal.input_llm);
  const internalOutput = asRecord(internal.output_llm);
  const externalInput = asRecord(external.input_llm);
  const externalOutput = asRecord(external.output_llm);
  if (
    !hasMaterialValue(internalInput) &&
    !hasMaterialValue(internalOutput) &&
    !hasMaterialValue(externalInput) &&
    !hasMaterialValue(externalOutput)
  ) {
    return null;
  }
  return {
    token_usage: normalizeTokenUsage(payload.token_usage),
    internal_tool_llm: {
      provider_name: String(internal.provider_name || ""),
      token_usage: normalizeTokenUsage(internal.token_usage),
      input_llm: internalInput,
      output_llm: internalOutput,
    },
    external_tool_llm: {
      provider_name: String(external.provider_name || ""),
      token_usage: normalizeTokenUsage(external.token_usage),
      input_llm: externalInput,
      output_llm: externalOutput,
    },
  };
}

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次 Q2，再刷新这个页面。",
    };
  }
  if (errMsg.includes("请求超时")) {
    return {
      title: "Q2 接口响应超时",
      action: "请确认后台仍在运行，稍后刷新；若持续出现，请重新执行 Q2。",
    };
  }
  return {
    title: "加载数据失败",
    action: "请检查后台服务状态后刷新重试。",
  };
}

function AssetStatLinkChip({ item, count }: { item: AssetStatLink; count: number }) {
  return (
    <Box
      component={RouterLink}
      to={item.to}
      aria-label={`${item.label}: ${count}，打开${item.destinationLabel}`}
      title={`打开${item.destinationLabel}`}
      sx={{ textDecoration: "none" }}
    >
      <Chip
        clickable
        label={`${item.label}: ${count}`}
        data-testid={item.testId}
        sx={{ cursor: "pointer" }}
      />
    </Box>
  );
}

function LlmExchangeCard({
  title,
  payload,
}: {
  title: string;
  payload: Record<string, any>;
}) {
  const tokenUsage = normalizeTokenUsage(payload.token_usage);
  return (
    <Card variant="outlined" data-testid={`q2-${title}-llm-card`}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
            <Typography variant="h6">{title}</Typography>
            <Chip label={`Provider: ${payload.provider_name || "-"}`} variant="outlined" />
            <Chip label={`输入 tokens: ${tokenUsage.input_tokens}`} color="info" />
            <Chip label={`输出 tokens: ${tokenUsage.output_tokens}`} color="success" />
            <Chip label={`总 tokens: ${tokenUsage.total_tokens}`} color="warning" />
          </Stack>
          <Box>
            <Typography variant="subtitle2" gutterBottom>输入 LLM</Typography>
            {renderCodeBlock(payload.input_llm || {})}
          </Box>
          <Box>
            <Typography variant="subtitle2" gutterBottom>输出 LLM</Typography>
            {renderCodeBlock(payload.output_llm || {})}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function Q2Detail() {
  const qId = "q2";
  const [llmTracePayload, setLlmTracePayload] = useState<Record<string, any> | null>(null);
  const [assetStatistics, setAssetStatistics] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    try {
      const [llmPayload, statisticsPayload] = await Promise.all([
        fetchQ2LlmTrace(),
        fetchQ2AssetStatistics(),
      ]);
      setLlmTracePayload(asRecord(llmPayload));
      setAssetStatistics(asRecord(statisticsPayload));
    } catch (err: any) {
      setError(err?.message || "加载 Q2 数据失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
        <CircularProgress size={24} />
        <Typography variant="body2" color="text.secondary">正在加载 Q2 LLM 与资产统计...</Typography>
      </Box>
    );
  }

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q2-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()}>重新加载</Button>
      </Box>
    );
  }

  const stats = asRecord(assetStatistics);
  const llmExchange = normalizeQ2LlmExchange(llmTracePayload);
  const hasRenderableLlm = Boolean(llmExchange);
  const aggregateTokens = normalizeTokenUsage(llmExchange?.token_usage);

  return (
    <Box data-testid="q2-detail-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">
            Q2 仅显示 LLM 查询结果与资产数量统计。
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button component={RouterLink} to="/console/nine-questions/q2/test" variant="contained" color="warning" data-testid="q2-sandbox-nav-button">进入独立沙箱测试</Button>
        </Stack>
      </Stack>

      <NineQuestionIntroCard questionId="q2" />

      <Card variant="outlined" sx={{ mb: 3 }} data-testid="q2-asset-statistics-card">
        <CardContent>
          <Typography variant="h6" gutterBottom>Q2 资产数量统计</Typography>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {ASSET_STAT_LINKS.map((item) => (
              <AssetStatLinkChip key={item.key} item={item} count={statNumber(stats[item.statKey])} />
            ))}
            <Chip label={`总计: ${statNumber(stats.total_count)}`} color="primary" data-testid="q2-stat-total-count" />
          </Stack>
        </CardContent>
      </Card>

      <NineQuestionSectionBoundary title="Q2 LLM">
        {!hasRenderableLlm ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            当前没有可展示的 Q2 LLM 查询结果。
          </Alert>
        ) : (
          <Stack spacing={2}>
            <Card variant="outlined" data-testid="q2-llm-token-summary">
              <CardContent>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                  <Typography variant="h6">Provider / Token</Typography>
                  <Chip label={`输入 tokens: ${aggregateTokens.input_tokens}`} color="info" />
                  <Chip label={`输出 tokens: ${aggregateTokens.output_tokens}`} color="success" />
                  <Chip label={`总 tokens: ${aggregateTokens.total_tokens}`} color="warning" />
                </Stack>
              </CardContent>
            </Card>
            <LlmExchangeCard title="内部 LLM" payload={asRecord(llmExchange?.internal_tool_llm)} />
            <LlmExchangeCard title="外部 LLM" payload={asRecord(llmExchange?.external_tool_llm)} />
          </Stack>
        )}
      </NineQuestionSectionBoundary>
    </Box>
  );
}
