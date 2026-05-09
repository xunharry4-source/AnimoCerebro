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
  Chip,
  CircularProgress,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RefreshIcon from "@mui/icons-material/Refresh";
import { Link as RouterLink } from "react-router-dom";

import {
  fetchNineQuestionDetail,
  fetchNineQuestionModules,
  fetchQ9LlmTaskDetail,
  fetchQ9LlmTasks,
  getQuestionDisplayLabel,
  NineQuestionItem,
  Q9LlmTaskDetail,
  Q9LlmTasksPayload,
  Q9PreprocessedEvidence,
  Q9ActionPostureInferenceView,
} from "../nineQuestionsApi";
import Q9EvidencePanel from "../../../components/Q9EvidencePanel";
import NineQuestionIntroCard from "../../../components/NineQuestionIntroCard";
import Q9DataTabs from "../../../components/Q9DataTabs";
import NineQuestionIncompleteResultAlert from "../../../components/NineQuestionIncompleteResultAlert";
import NineQuestionRerunButton from "../../../components/NineQuestionRerunButton";
import NineQuestionWorkflowNavButton from "../../../components/NineQuestionWorkflowNavButton";
import NineQuestionRecoveryActions from "../../../components/NineQuestionRecoveryActions";
import NineQuestionIntegrationStatusCard from "../../../components/NineQuestionIntegrationStatusCard";
import NineQuestionAnswerTable from "../../../components/NineQuestionAnswerTable";
import { sanitizeQ9Evidence, sanitizeQ9Inference } from "../detailSafeData";

function resolveErrorGuidance(errMsg: string): { title: string; action: string } {
  if (errMsg.includes("No active session") || errMsg.includes("没有活动 session")) {
    return {
      title: "当前还没有可读取的九问快照",
      action: "请先运行一次完整的九问推演流程，完成后再回到这个监控页刷新。",
    };
  }
  if (errMsg.includes("尚无快照记录")) {
    return {
      title: "Q9 尚未产生姿态定调",
      action: "该问题的推断快照为空。可能由于前置认知环（Q1-Q8）存在阻塞。请在 Zentex Brain Runtime 中重新触发推演。",
    };
  }
  if (errMsg.includes("状态机未挂载") || errMsg.includes("503")) {
    return {
      title: "后端推演引擎未就绪",
      action: "NineQuestionState 未挂载。请检查 Zentex Brain Runtime 启动状态，确认服务初始化后再刷新。",
    };
  }
  return {
    title: "加载数据失败",
    action: "请检查网络或确认后台服务状态后刷新重试。",
  };
}

function renderJsonBlock(value: unknown) {
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
        maxHeight: 420,
      }}
    >
      <code>{typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2)}</code>
    </Box>
  );
}

function taskScopeLabel(scope: string) {
  if (scope === "internal") return "内部认知";
  if (scope === "external") return "外部执行";
  return scope || "-";
}

function Q9LlmTaskTable({
  payload,
  activeScope,
  onScopeChange,
  selectedTaskKey,
  onSelect,
  detail,
  detailLoading,
  detailError,
}: {
  payload: Q9LlmTasksPayload | null;
  activeScope: "internal" | "external";
  onScopeChange: (scope: "internal" | "external") => void;
  selectedTaskKey: string | null;
  onSelect: (taskKey: string) => void;
  detail: Q9LlmTaskDetail | null;
  detailLoading: boolean;
  detailError: string | null;
}) {
  const tasks = payload?.tasks ?? [];
  const scopedTasks = tasks.filter((task) => task.task_scope === activeScope);
  const internalCount = tasks.filter((task) => task.task_scope === "internal").length;
  const externalCount = tasks.filter((task) => task.task_scope === "external").length;
  const scopedDetail = detail?.task_scope === activeScope ? detail : null;
  const tokenUsage = scopedDetail?.token_usage && typeof scopedDetail.token_usage === "object" ? scopedDetail.token_usage as Record<string, any> : {};
  return (
    <Card variant="outlined" data-testid="q9-llm-task-table-card">
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Box>
            <Typography variant="h6" gutterBottom>Q9 任务级 LLM 拆解</Typography>
            <Typography variant="body2" color="text.secondary">
              来源表：{payload?.source_table || "nine_question_q9_llm_tasks"}
            </Typography>
          </Box>
          <Chip label={`任务数: ${payload?.task_count ?? 0}`} color="primary" variant="outlined" />
        </Stack>

        <Tabs
          value={activeScope}
          onChange={(_, nextScope) => onScopeChange(nextScope)}
          sx={{ mb: 1.5, borderBottom: 1, borderColor: "divider" }}
        >
          <Tab value="internal" label={`内部 (${internalCount})`} data-testid="q9-llm-task-tab-internal" />
          <Tab value="external" label={`外部 (${externalCount})`} data-testid="q9-llm-task-tab-external" />
        </Tabs>

        {scopedTasks.length ? (
          <TableContainer sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: "26%" }}>任务名称</TableCell>
                  <TableCell sx={{ width: "34%" }}>任务说明</TableCell>
                  <TableCell>类型</TableCell>
                  <TableCell>Provider</TableCell>
                  <TableCell align="right">耗时</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {scopedTasks.map((task) => (
                  <TableRow
                    key={task.task_key}
                    hover
                    selected={task.task_key === selectedTaskKey}
                    data-testid={`q9-llm-task-row-${task.task_key}`}
                  >
                    <TableCell>
                      <Button
                        variant="text"
                        onClick={() => onSelect(task.task_key)}
                        sx={{ p: 0, minWidth: 0, textAlign: "left", justifyContent: "flex-start", textTransform: "none" }}
                        data-testid={`q9-llm-task-name-${task.task_key}`}
                      >
                        <Typography variant="body2" fontWeight="bold" sx={{ wordBreak: "break-word" }}>
                          {task.task_name || task.plan_objective || task.task_key}
                        </Typography>
                      </Button>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary" sx={{ wordBreak: "break-word" }}>
                        {task.task_description || task.plan_objective || "-"}
                      </Typography>
                    </TableCell>
                    <TableCell><Chip size="small" label={taskScopeLabel(task.task_scope)} /></TableCell>
                    <TableCell>{task.provider_name || "-"}</TableCell>
                    <TableCell align="right">{task.elapsed_ms ?? 0} ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Alert severity="warning">当前没有 {taskScopeLabel(activeScope)} Q9 任务级 LLM 记录。</Alert>
        )}

        {detailLoading ? (
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mt: 2 }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">正在加载任务详情...</Typography>
          </Stack>
        ) : null}
        {detailError ? <Alert severity="warning" sx={{ mt: 2 }}>{detailError}</Alert> : null}

        {scopedDetail && !detailLoading ? (
          <Box sx={{ mt: 2 }}>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1.5 }}>
              <Chip label={taskScopeLabel(scopedDetail.task_scope)} color={scopedDetail.task_scope === "external" ? "warning" : "info"} />
              <Chip label={`index: ${scopedDetail.task_index}`} variant="outlined" />
              <Chip label={`request: ${scopedDetail.request_id || "-"}`} variant="outlined" sx={{ fontFamily: "monospace" }} />
              <Chip label={`trace: ${scopedDetail.trace_id || "-"}`} variant="outlined" sx={{ fontFamily: "monospace" }} />
            </Stack>
            <Typography variant="subtitle1" fontWeight="bold">{scopedDetail.task_name}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{scopedDetail.task_description}</Typography>
            <Accordion defaultExpanded={false}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">Q8 原始任务</Typography>
              </AccordionSummary>
              <AccordionDetails>{renderJsonBlock(scopedDetail.q8_task || {})}</AccordionDetails>
            </Accordion>
            <Box sx={{ mt: 2, border: 1, borderColor: "divider", borderRadius: 1 }}>
              <Box sx={{ px: 2, py: 1.5 }}>
                <Typography variant="subtitle2" gutterBottom>任务 LLM 情况</Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip size="small" label={`Provider: ${scopedDetail.provider_name || "-"}`} variant="outlined" />
                  <Chip size="small" label={`Model: ${scopedDetail.model || "-"}`} variant="outlined" />
                  <Chip size="small" label={`输入 tokens: ${Number(tokenUsage.input_tokens || 0)}`} color="info" />
                  <Chip size="small" label={`输出 tokens: ${Number(tokenUsage.output_tokens || 0)}`} color="success" />
                  <Chip size="small" label={`总 tokens: ${Number(tokenUsage.total_tokens || 0)}`} color="warning" />
                  <Chip size="small" label={`耗时: ${scopedDetail.elapsed_ms || 0} ms`} variant="outlined" />
                </Stack>
              </Box>
              <Accordion defaultExpanded={false}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输入 System Prompt</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderJsonBlock(scopedDetail.llm_input?.system_prompt || "")}</AccordionDetails>
              </Accordion>
              <Accordion defaultExpanded={false}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输入 Prompt</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderJsonBlock(scopedDetail.llm_input?.prompt || "")}</AccordionDetails>
              </Accordion>
              <Accordion defaultExpanded={false}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输入 Context</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderJsonBlock(scopedDetail.llm_input?.context || {})}</AccordionDetails>
              </Accordion>
              <Accordion defaultExpanded={false}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输出 Raw Response</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderJsonBlock(scopedDetail.llm_output || {})}</AccordionDetails>
              </Accordion>
            </Box>
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function Q9Detail() {
  const qId = "q9";
  const [question, setQuestion] = useState<NineQuestionItem | null>(null);
  const [modulesPayload, setModulesPayload] = useState<Record<string, any> | null>(null);
  const [llmTasksPayload, setLlmTasksPayload] = useState<Q9LlmTasksPayload | null>(null);
  const [activeTaskScope, setActiveTaskScope] = useState<"internal" | "external">("internal");
  const [selectedTaskKey, setSelectedTaskKey] = useState<string | null>(null);
  const [selectedTaskDetail, setSelectedTaskDetail] = useState<Q9LlmTaskDetail | null>(null);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [taskDetailError, setTaskDetailError] = useState<string | null>(null);
  const [sectionErrors, setSectionErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTaskDetail = async (taskKey: string) => {
    setSelectedTaskKey(taskKey);
    setTaskDetailLoading(true);
    setTaskDetailError(null);
    try {
      const payload = await fetchQ9LlmTaskDetail(taskKey);
      setSelectedTaskDetail(payload.task);
    } catch (err: any) {
      setSelectedTaskDetail(null);
      setTaskDetailError(err?.message || "加载 Q9 任务 LLM 详情失败");
    } finally {
      setTaskDetailLoading(false);
    }
  };

  const selectFirstTaskForScope = (payload: Q9LlmTasksPayload | null, scope: "internal" | "external") => {
    const taskKey = payload?.tasks?.find((task) => task.task_scope === scope)?.task_key || null;
    if (taskKey) {
      void loadTaskDetail(taskKey);
      return;
    }
    setSelectedTaskKey(null);
    setSelectedTaskDetail(null);
    setTaskDetailError(null);
  };

  const handleTaskScopeChange = (scope: "internal" | "external") => {
    setActiveTaskScope(scope);
    selectFirstTaskForScope(llmTasksPayload, scope);
  };

  const loadDetail = async () => {
    setLoading(true);
    setError(null);
    setSectionErrors({});
    try {
      const results = await Promise.allSettled([
        fetchNineQuestionDetail(qId),
        fetchNineQuestionModules(qId),
        fetchQ9LlmTasks(),
      ]);
      const [detailResult, modulesResult, llmTasksResult] = results;
      const nextErrors: Record<string, string> = {};

      if (detailResult.status === "fulfilled") setQuestion(detailResult.value);
      else throw detailResult.reason;

      if (modulesResult.status === "fulfilled") setModulesPayload(modulesResult.value);
      else nextErrors.modules = modulesResult.reason?.message || "加载 Q9 modules 失败";

      if (llmTasksResult.status === "fulfilled") {
        setLlmTasksPayload(llmTasksResult.value);
        const nextScope = llmTasksResult.value.tasks?.some((task) => task.task_scope === "internal") ? "internal" : "external";
        setActiveTaskScope(nextScope);
        selectFirstTaskForScope(llmTasksResult.value, nextScope);
      } else {
        nextErrors.llmTasks = llmTasksResult.reason?.message || "加载 Q9 任务级 LLM 失败";
      }

      setSectionErrors(nextErrors);
    } catch (err: any) {
      setError(err?.message || "加载 Q9 详情失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDetail();
  }, []);

  if (loading) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, p: 3 }}>
      <CircularProgress size={24} />
      <Typography variant="body2" color="text.secondary">正在加载 Q9 姿态审计数据...</Typography>
    </Box>
  );

  if (error) {
    const guidance = resolveErrorGuidance(error);
    return (
      <Box sx={{ p: 3 }} data-testid="q9-error-boundary">
        <Alert severity="error" sx={{ mb: 2 }}>
          <AlertTitle>{guidance.title}</AlertTitle>
          <Typography variant="body2"><strong>建议操作：</strong> {guidance.action}</Typography>
        </Alert>
        <Button variant="outlined" startIcon={<RefreshIcon />} onClick={() => void loadDetail()} data-testid="q9-retry-button">重新加载</Button>
      </Box>
    );
  }

  if (!question) return <Alert severity="warning">未能找到 Q9 记录。</Alert>;

  const sanitizedEvidence = sanitizeQ9Evidence(question.preprocessed_evidence);
  const sanitizedInference = sanitizeQ9Inference(question.inference_result);
  const evidence = sanitizedEvidence.value as Q9PreprocessedEvidence;
  const inference = sanitizedInference.value as Q9ActionPostureInferenceView | null;
  const q9RunPayload = evidence
    ? {
        self_model: {
          current_cognitive_load: evidence.self_model?.cognitive_load,
          current_state: {
            stability_level: evidence.self_model?.stability_level,
          },
          recent_weaknesses: evidence.self_model?.recent_weaknesses ?? [],
        },
        reasoning_budget: {
          compute_remaining_ratio: evidence.reasoning_budget?.compute_remaining_ratio,
          token_remaining_ratio: evidence.reasoning_budget?.token_remaining_ratio,
          time_remaining_ratio: evidence.reasoning_budget?.time_remaining_ratio,
          budget_pressure: evidence.reasoning_budget?.budget_pressure,
        },
      }
    : undefined;
  const hasStructuredSnapshot = Boolean(question.preprocessed_evidence);
  const executionDiagnosis = question.context_updates?.q9_execution_diagnosis || null;
  const recoveryPlan = executionDiagnosis?.recovery_plan || null;
  const detailWarnings = [...sanitizedEvidence.warnings, ...sanitizedInference.warnings];

  return (
    <Box data-testid="q9-detail-root" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0 }}>
        <Box>
          <Typography variant="h4" fontWeight="bold" gutterBottom>{getQuestionDisplayLabel(qId)} 正式审计页</Typography>
          <Typography variant="body2" color="text.secondary">Self-Model Pressure & Action Posture Audit (Independent API GET /nine-questions/q9)</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <NineQuestionRerunButton qId={qId} onCompleted={loadDetail} runPayload={q9RunPayload} />
          <NineQuestionWorkflowNavButton qId={qId} />
          <Button
            component={RouterLink}
            to={`/console/nine-questions/${qId}/test`}
            variant="contained"
            color="warning"
            data-testid="q9-sandbox-nav-button"
          >
            进入独立沙箱测试
          </Button>
        </Stack>
      </Stack>

      {executionDiagnosis ? (
        <Alert severity={executionDiagnosis.authenticity_status === "completed" ? "success" : "warning"}>
          <AlertTitle>
            {executionDiagnosis.authenticity_status === "completed" ? "Q9 真实性状态：已验证完成" : "Q9 真实性状态：降级/部分失败"}
          </AlertTitle>
          <Typography variant="body2">{String(executionDiagnosis.diagnosis_message || "当前没有诊断说明。")}</Typography>
        </Alert>
      ) : null}
      {recoveryPlan ? (
        <Alert severity="info" data-testid="q9-recovery-plan">
          <AlertTitle>Q9 失败恢复计划</AlertTitle>
          <NineQuestionRecoveryActions qId={qId} recoveryPlan={recoveryPlan} onCompleted={loadDetail} />
        </Alert>
      ) : null}
      {detailWarnings.length > 0 ? (
        <Alert severity="warning">
          <AlertTitle>Q9 数据已按降级结构清洗</AlertTitle>
          <Typography variant="body2">{detailWarnings.join(" ")}</Typography>
        </Alert>
      ) : null}

      <NineQuestionAnswerTable questionId={qId} inference={inference} result={question.result} />

      {sectionErrors.llmTasks ? <Alert severity="warning">{sectionErrors.llmTasks}</Alert> : null}
      <Q9LlmTaskTable
        payload={llmTasksPayload}
        activeScope={activeTaskScope}
        onScopeChange={handleTaskScopeChange}
        selectedTaskKey={selectedTaskKey}
        onSelect={(taskKey) => void loadTaskDetail(taskKey)}
        detail={selectedTaskDetail}
        detailLoading={taskDetailLoading}
        detailError={taskDetailError}
      />

      {hasStructuredSnapshot ? (
        <>
          <NineQuestionIntroCard questionId="q9" />
          <Q9DataTabs
            evidence={evidence as any}
            inference={inference as any}
          />
        </>
      ) : (
        <NineQuestionIncompleteResultAlert
          questionId={qId}
          result={question.result}
          contextUpdates={question.context_updates}
        />
      )}
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1} sx={{ mb: 2 }} useFlexGap flexWrap="wrap">
            <Chip label={question.cache_status} color="primary" data-testid="q9-cache-status-chip" />
            <Chip label={question.provider_name} variant="outlined" />
            <Chip label={question.tool_id} variant="outlined" sx={{ fontFamily: "monospace" }} />
            {question.trace_id && <Chip label={`trace: ${question.trace_id}`} variant="outlined" sx={{ fontFamily: "monospace" }} data-testid="q9-trace-chip" />}
          </Stack>

          <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: "bold", mt: 2 }}>
            结构化行动姿态证据 (Self-Model & Posture)
          </Typography>

          {hasStructuredSnapshot ? (
            <Q9EvidencePanel
              evidence={evidence}
              inference={inference}
              providerName={question.provider_name || null}
              elapsedMs={0}
            />
          ) : <Alert severity="warning">暂无结构化行动姿态证据。</Alert>}
        </CardContent>
      </Card>

      {sectionErrors.modules ? <Alert severity="warning">{sectionErrors.modules}</Alert> : null}
      <NineQuestionIntegrationStatusCard qId={qId} modulesPayload={modulesPayload} />
    </Box>
  );
}
