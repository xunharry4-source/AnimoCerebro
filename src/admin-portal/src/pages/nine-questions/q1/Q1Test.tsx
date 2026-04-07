import { useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { Link as RouterLink } from "react-router-dom";

import {
  NineQuestionSandboxResponse,
  fetchNineQuestionDetail,
  getQuestionDisplayLabel,
  runNineQuestionSandboxTest,
  Q1PreprocessedEvidence,
  WorkspaceDomainInferenceView,
  LLMTracePayloadView,
} from "../nineQuestionsApi";
import Q1EvidencePanel from "../../../components/Q1EvidencePanel";
import MountedPluginsZone from "../../../components/MountedPluginsZone";
import LLMTracePanel from "../../../components/LLMTracePanel";
import Q1UpgradePanel from "../../../components/Q1UpgradePanel";

// ──────────────────────────────────────────────
// 防黑盒红线：沙箱执行绝对禁止写入 NineQuestionState 正式槽位
// 及 BrainTranscriptStore 生产事件流。
// 调用路径：POST /api/web/nine-questions/q1/test（纯内存隔离，不落盘）
// ──────────────────────────────────────────────

/**
 * 将原始错误信息映射为可读的中文指引（问题是什么 + 下一步怎么办）。
 * 绝对禁止暴露内部 Error Enum 或直接白屏崩溃。
 */
function resolveTestErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("Failed to fetch") || errMsg.includes("NetworkError") || errMsg.includes("网络")) {
    return {
      title: "无法连接到后端，请检查服务",
      action:
        "请确认 Zentex Dev Server 正在运行（通常在 localhost:8000），检查网络连接后重试。",
    };
  }
  if (errMsg.includes("500") || errMsg.includes("Internal Server Error")) {
    return {
      title: "沙箱推演引擎内部错误（HTTP 500）",
      action:
        "后端在执行隔离推演时发生了内部错误。请检查后台服务日志，确认 Mock 上下文 JSON 格式是否正确后重试。",
    };
  }
  if (errMsg.includes("400") || errMsg.includes("Bad Request") || errMsg.includes("JSON")) {
    return {
      title: "Mock 上下文格式无效",
      action:
        "注入的 Mock JSON 格式错误或字段缺失。请检查左侧文本框中的 JSON 语法后重新提交。",
    };
  }
  if (errMsg.includes("503") || errMsg.includes("状态机未挂载")) {
    return {
      title: "沙箱推演引擎未就绪（HTTP 503）",
      action:
        "沙箱插件运行时尚未初始化。请检查 Zentex Brain Runtime 的启动状态后再执行测试。",
    };
  }
  if (errMsg.includes("timeout") || errMsg.includes("超时")) {
    return {
      title: "推演请求超时",
      action:
        "沙箱推演耗时过长，请简化 Mock 上下文（减少文件样本数量）后重试，或检查后台是否存在性能瓶颈。",
    };
  }
  return {
    title: "沙箱测试执行失败",
    action:
      "请刷新页面重试，或查看浏览器控制台与后台服务日志获取详细信息。",
  };
}

export default function Q1Test() {
  const qId = "q1";
  const [draftJson, setDraftJson] = useState<string>("{}");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<NineQuestionSandboxResponse | null>(null);

  useEffect(() => {
    void loadInitialContext();
  }, []);

  /**
   * 加载生产环境当前 Q1 context_updates 作为沙箱默认注入模板。
   * 此处仅读取数据用于填充 JSON 编辑框，绝不触发任何状态机写入。
   */
  const loadInitialContext = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const question = await fetchNineQuestionDetail(qId);
      setDraftJson(JSON.stringify(question?.context_updates || {}, null, 2));
    } catch (err: any) {
      setLoadError(err?.message || "加载 Q1 沙箱初始上下文失败");
    } finally {
      setLoading(false);
    }
  };

  /**
   * 执行沙箱推演。
   *
   * 防污染红线（Anti-Contamination）：
   * - 调用路径：POST /api/web/nine-questions/q1/test（独立沙箱端点）
   * - 后端在纯内存环境中拉起 Q1 插件，结果仅返回，绝不写入：
   *   a) NineQuestionState 正式槽位
   *   b) BrainTranscriptStore 生产事件流
   */
  const handleRun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const mockContext = JSON.parse(draftJson || "{}");
      const sandboxResult = await runNineQuestionSandboxTest(qId, mockContext);
      setResult(sandboxResult);
    } catch (err: any) {
      setRunError(err?.message || "执行 Q1 沙箱测试失败");
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
        <CircularProgress size={24} />
        <Typography variant="body2" color="text.secondary">
          正在加载 Q1 沙箱初始模板…
        </Typography>
      </Box>
    );
  }

  return (
    <Box data-testid="q1-test-root">
      {/* 页面标题区 */}
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            {getQuestionDisplayLabel(qId)} 独立沙箱测试页
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Anti-Contamination 沙箱：隔离推演，结果绝不写入生产状态机与事件流
            （POST /api/web/nine-questions/q1/test）
          </Typography>
        </Box>
        <Button
          component={RouterLink}
          to="/console/nine-questions/q1"
          variant="outlined"
          data-testid="q1-test-back-to-detail-button"
        >
          返回生产审计页
        </Button>
      </Stack>

      {/* 初始上下文加载错误 · 人话降级熔断区 */}
      {loadError && (() => {
        const g = resolveTestErrorGuidance(loadError);
        return (
          <Alert severity="warning" sx={{ mb: 2 }} data-testid="q1-test-load-error">
            <AlertTitle>{g.title}</AlertTitle>
            <Typography variant="body2" sx={{ mt: 0.5 }}>
              <strong>下一步：</strong> {g.action}
            </Typography>
          </Alert>
        );
      })()}

      <Grid container spacing={3}>
        {/* 左侧：Mock 上下文注入区 */}
        <Grid size={{ xs: 12, md: 5 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
                <Typography variant="h6">Mock Context 注入区</Typography>
                <Tooltip
                  title="在此注入伪造的工作区上下文（如异常目录或极端日志环境），仅用于沙箱推演验证，绝不污染生产数据。"
                  placement="right"
                >
                  <InfoOutlinedIcon fontSize="small" color="info" />
                </Tooltip>
              </Stack>

              <Accordion defaultExpanded={false} data-testid="q1-test-mock-schema-hint">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="caption" color="text.secondary">
                    Mock 上下文字段说明（展开查看）
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      p: 1.5,
                      bgcolor: "action.hover",
                      borderRadius: 1,
                      fontSize: "0.75rem",
                      overflow: "auto",
                    }}
                  >
                    <code>{`{
  "context_snapshot": {
    "workspace_structure_analysis": { ... },
    "workspace_content_samples": [ ... ],
    "environment_event": { "kind": "...", "summary": "..." },
    "physical_host_state": { "memory_pressure": "...", ... }
  }
}`}
                    </code>
                  </Box>
                </AccordionDetails>
              </Accordion>

              <TextField
                fullWidth
                multiline
                minRows={18}
                value={draftJson}
                onChange={(e) => setDraftJson(e.target.value)}
                placeholder='{"context_snapshot": {}}'
                sx={{ mt: 2, fontFamily: "monospace" }}
                inputProps={{ "data-testid": "q1-test-mock-json-input" }}
              />

              <Button
                variant="contained"
                sx={{ mt: 2 }}
                onClick={() => void handleRun()}
                disabled={running}
                data-testid="q1-test-run-button"
              >
                {running ? "推演执行中…" : "执行测试分析"}
              </Button>

              {running && (
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 2 }}>
                  <CircularProgress size={16} />
                  <Typography variant="caption" color="text.secondary">
                    沙箱隔离推演中，请稍候…
                  </Typography>
                </Stack>
              )}

              {/* ——— 推演错误 · 人话降级熔断区 ——— */}
              {runError && (() => {
                const g = resolveTestErrorGuidance(runError);
                return (
                  <Alert
                    severity="error"
                    sx={{ mt: 2 }}
                    data-testid="q1-test-run-error"
                  >
                    <AlertTitle>{g.title}</AlertTitle>
                    <Typography variant="body2" sx={{ mt: 0.5 }}>
                      <strong>下一步：</strong> {g.action}
                    </Typography>
                  </Alert>
                );
              })()}
            </CardContent>
          </Card>
        </Grid>

        {/* 右侧：沙箱结果渲染区（Anti-Contamination 隔离区）*/}
        <Grid size={{ xs: 12, md: 7 }}>
          <Card variant="outlined" sx={{ height: "100%" }} data-testid="q1-test-result-panel">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                推演执行结果 (Sandbox Result)
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
                以下数据由后端在内存环境中生成，绝不写入 NineQuestionState 或 BrainTranscriptStore 生产流。
              </Typography>

              {result ? (
                <>
                  <Alert severity="success" sx={{ mb: 2 }} data-testid="q1-test-success-alert">
                    {result.summary}
                  </Alert>

                  {/* 挂载插件清单快照（沙箱时刻）*/}
                  <MountedPluginsZone plugins={result.mounted_plugins || []} />

                  <Q1UpgradePanel upgrade={result.q1_llm_upgrade} />

                  {/* Q1EvidencePanel：四大高密度分区（内置 Accordion 均默认闭合）*/}
                  {result.preprocessed_evidence ? (
                    <Q1EvidencePanel
                      evidence={result.preprocessed_evidence as Q1PreprocessedEvidence}
                      inference={result.inference_result as WorkspaceDomainInferenceView}
                      providerName={result.provider_name || null}
                      elapsedMs={result.elapsed_ms || 0}
                    />
                  ) : (
                    <Alert severity="warning">
                      沙箱结果未携带结构化证据，请检查 Mock 上下文是否包含有效的 context_snapshot。
                    </Alert>
                  )}

                  {/* LLM 交互溯源（底部 Accordion，默认闭合，防黑盒红线）*/}
                  <LLMTracePanel trace={result.llm_trace_payload as LLMTracePayloadView} />
                </>
              ) : (
                <Box sx={{ py: 6, textAlign: "center" }}>
                  <Typography color="text.secondary" variant="body2">
                    等待执行结果...
                  </Typography>
                  <Typography color="text.secondary" variant="caption" sx={{ mt: 1, display: "block" }}>
                    请在左侧注入 Mock 上下文后点击「执行测试分析」。
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
