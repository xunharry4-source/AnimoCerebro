/**
 * 系统健康监控页面
 * 
 * 功能：
 * - 显示Token使用统计（总请求数、输入/输出Token）
 * - 显示各LLM Provider的详细统计和健康状态
 * - 显示各功能模块的健康状态（Memory、Task、Plugin、Runtime等）
 * - 自动刷新（每30秒）
 * 
 * 访问路径：/console/health
 */
import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  Typography,
  Chip,
  Divider,
} from "@mui/material";
import { useEffect, useState } from "react";
import { Locale, healthDashboardCopy } from "../../i18n";

export interface ModuleHealthStatus {
  module_id: string;
  module_name: string;
  health_status: string;
  status_message?: string | null;
  last_check_at?: string | null;
  metrics: Record<string, unknown>;
}

export interface LLMProviderStats {
  provider_name: string;
  api_base?: string | null;
  health_status: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  error_count: number;
}

export interface TokenUsageStats {
  total_request_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  providers: LLMProviderStats[];
}

export interface SystemHealthPayload {
  overall_health: string;
  token_usage: TokenUsageStats;
  modules: ModuleHealthStatus[];
  timestamp: string;
}

async function fetchSystemHealth(): Promise<SystemHealthPayload> {
  const response = await fetch("/api/web/health/system", {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`获取系统健康状态失败: ${response.status}`);
  }
  return (await response.json()) as SystemHealthPayload;
}

function getHealthColor(status: string): "success" | "warning" | "error" | "default" {
  switch (status.toLowerCase()) {
    case "healthy":
      return "success";
    case "degraded":
      return "warning";
    case "unhealthy":
      return "error";
    default:
      return "default";
  }
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(2)}M`;
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(2)}K`;
  }
  return num.toString();
}

export default function HealthDashboard() {
  const locale: Locale = "zh-CN";
  const copy = healthDashboardCopy[locale];
  const [health, setHealth] = useState<SystemHealthPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHealth = async () => {
    try {
      setLoading(true);
      const data = await fetchSystemHealth();
      setHealth(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.fetchError);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadHealth();
    // 每30秒自动刷新
    const interval = setInterval(() => {
      void loadHealth();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading && !health) {
    return (
      <Stack spacing={2} alignItems="center" justifyContent="center" sx={{ minHeight: 400 }}>
        <CircularProgress />
        <Typography variant="body2">{copy.loading}</Typography>
      </Stack>
    );
  }

  if (error && !health) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {error}
      </Alert>
    );
  }

  if (!health) {
    return (
      <Alert severity="warning">{copy.noData}</Alert>
    );
  }

  return (
    <Stack spacing={3}>
      {/* 页面标题 */}
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4" component="h1">
          {copy.title}
        </Typography>
        <Chip
          label={`${copy.overallStatus}: ${health.overall_health}`}
          color={getHealthColor(health.overall_health)}
          variant="filled"
          sx={{ fontWeight: "bold" }}
        />
      </Stack>

      {/* Token使用统计卡片 */}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {copy.tokenUsageStats}
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ textAlign: "center", p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                <Typography variant="h4" color="primary">
                  {formatNumber(health.token_usage.total_request_count)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {copy.totalRequests}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ textAlign: "center", p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                <Typography variant="h4" color="info.main">
                  {formatNumber(health.token_usage.total_input_tokens)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {copy.inputTokens}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ textAlign: "center", p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                <Typography variant="h4" color="success.main">
                  {formatNumber(health.token_usage.total_output_tokens)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {copy.outputTokens}
                </Typography>
              </Box>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ textAlign: "center", p: 2, bgcolor: "background.paper", borderRadius: 1 }}>
                <Typography variant="h4" color="warning.main">
                  {formatNumber(health.token_usage.total_tokens)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {copy.totalTokens}
                </Typography>
              </Box>
            </Grid>
          </Grid>

          {/* Provider详细统计 */}
          {health.token_usage.providers.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="subtitle1" gutterBottom>
                {copy.llmProviderDetails}
              </Typography>
              <Stack spacing={1}>
                {health.token_usage.providers.map((provider, index) => (
                  <Card key={index} variant="outlined" sx={{ p: 2 }}>
                    <Stack spacing={1}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="subtitle2">{provider.provider_name}</Typography>
                        <Chip
                          label={provider.health_status}
                          size="small"
                          color={getHealthColor(provider.health_status)}
                        />
                      </Stack>
                      {provider.api_base && (
                        <Typography variant="caption" color="text.secondary">
                          {provider.api_base}
                        </Typography>
                      )}
                      <Grid container spacing={1}>
                        <Grid size={{ xs: 3 }}>
                          <Typography variant="caption" color="text.secondary">
                            {copy.requests}: {formatNumber(provider.request_count)}
                          </Typography>
                        </Grid>
                        <Grid size={{ xs: 3 }}>
                          <Typography variant="caption" color="text.secondary">
                            {copy.input}: {formatNumber(provider.input_tokens)}
                          </Typography>
                        </Grid>
                        <Grid size={{ xs: 3 }}>
                          <Typography variant="caption" color="text.secondary">
                            {copy.output}: {formatNumber(provider.output_tokens)}
                          </Typography>
                        </Grid>
                        <Grid size={{ xs: 3 }}>
                          <Typography variant="caption" color="text.secondary">
                            {copy.total}: {formatNumber(provider.total_tokens)}
                          </Typography>
                        </Grid>
                      </Grid>
                      {provider.error_count > 0 && (
                        <Typography variant="caption" color="error">
                          {copy.errorCount}: {provider.error_count}
                        </Typography>
                      )}
                    </Stack>
                  </Card>
                ))}
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* 功能模块健康状态 */}
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            {copy.moduleHealth}
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Stack spacing={2}>
            {health.modules.map((module) => (
              <Card key={module.module_id} variant="outlined">
                <CardContent>
                  <Stack spacing={1}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                      <Typography variant="subtitle1" fontWeight="bold">
                        {module.module_name}
                      </Typography>
                      <Chip
                        label={module.health_status}
                        color={getHealthColor(module.health_status)}
                        size="small"
                      />
                    </Stack>
                    {module.status_message && (
                      <Typography variant="body2" color="text.secondary">
                        {module.status_message}
                      </Typography>
                    )}
                    {module.last_check_at && (
                      <Typography variant="caption" color="text.secondary">
                        {copy.lastCheck}: {new Date(module.last_check_at).toLocaleString(locale === "zh-CN" ? "zh-CN" : "en-US")}
                      </Typography>
                    )}
                    {/* 显示模块指标 */}
                    {Object.keys(module.metrics).length > 0 && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          {copy.metrics}:
                        </Typography>
                        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
                          {Object.entries(module.metrics).map(([key, value]) => (
                            <Chip
                              key={key}
                              label={`${key}: ${typeof value === "boolean" ? (value ? "是" : "否") : value}`}
                              size="small"
                              variant="outlined"
                              sx={{ mt: 0.5 }}
                            />
                          ))}
                        </Stack>
                      </Box>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* 时间戳 */}
      <Typography variant="caption" color="text.secondary" align="right">
        {copy.updateTime}: {new Date(health.timestamp).toLocaleString(locale === "zh-CN" ? "zh-CN" : "en-US")}
      </Typography>
    </Stack>
  );
}
