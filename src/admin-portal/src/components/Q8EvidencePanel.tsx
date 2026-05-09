import React from "react";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import AssignmentTurnedInIcon from "@mui/icons-material/AssignmentTurnedIn";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HubIcon from "@mui/icons-material/Hub";

import {
  Q8PreprocessedEvidence,
  Q8WhatShouldIDoNowInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q8EvidencePanelProps {
  evidence: Q8PreprocessedEvidence;
  inference: Q8WhatShouldIDoNowInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

type TaskScope = "internal" | "external";
type Translate = (key: string, fallback: string) => string;

interface Q8CreatedTaskRow {
  id: string;
  title: string;
  description: string;
  taskType: string;
  queueName: string;
  creationReason: string;
  createdAt: string;
  scope: TaskScope;
}

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string") return value.trim() || fallback;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const joined = value.map((item) => text(item, "")).filter(Boolean).join("；");
    return joined || fallback;
  }
  if (isRecord(value)) {
    const preferred = value.summary || value.description || value.reason || value.title || value.name;
    if (preferred) return text(preferred, fallback);
    return Object.entries(value)
      .map(([key, entryValue]) => `${key}: ${text(entryValue, "")}`)
      .filter((item) => !item.endsWith(": "))
      .join("；") || fallback;
  }
  return String(value);
}

function firstText(fallback: string, ...values: unknown[]): string {
  for (const value of values) {
    const resolved = text(value, "");
    if (resolved) return resolved;
  }
  return fallback;
}

function normalizeTaskItem(item: unknown): Record<string, any> {
  if (typeof item === "string") return { title: item };
  if (isRecord(item)) return item;
  return { title: text(item, "") };
}

function buildIntentRows(
  inference: Q8WhatShouldIDoNowInferenceView | null | undefined,
  t: Translate,
  scope: TaskScope,
): Q8CreatedTaskRow[] {
  const rawRows =
    scope === "internal"
      ? inference?.q8_internal_cognitive_tasks || []
      : inference?.q8_external_execution_tasks || [];
  const rows: Q8CreatedTaskRow[] = [];
  rawRows.forEach((rawTask: unknown, index: number) => {
    const task = normalizeTaskItem(rawTask);
    const metadata = isRecord(task.metadata) ? task.metadata : {};
    const taskRawPayload = isRecord(metadata.raw_payload) ? metadata.raw_payload : {};
    const title = text(
      task.intent_name || task.title || task.name || task.task_id || task.id,
      t("nineQuestions.untitledQ8Task", "未命名 Q8 任务"),
    );
    rows.push({
      id: `${scope}-${index}-${text(task.task_id || task.id || title, String(index))}`,
      title,
      description: firstText(
        t("nineQuestions.noTaskDescription", "暂无任务说明"),
        task.intent_description ||
          task.task_description ||
          task.description ||
          metadata.intent_description ||
          metadata.task_description ||
          metadata.description ||
          taskRawPayload.intent_description ||
          taskRawPayload.task_description ||
          taskRawPayload.description,
      ),
      taskType: firstText(
        scope === "internal"
          ? t("nineQuestions.internalTasks", "内部任务")
          : t("nineQuestions.externalTasks", "外部任务"),
        task.required_capability ||
          task.target_engine_or_organ ||
          task.target_execution_domain ||
          task.task_type ||
          task.type,
      ),
      queueName:
        scope === "internal"
          ? t("nineQuestions.internalTasks", "内部任务")
          : t("nineQuestions.externalTasks", "外部任务"),
      creationReason: firstText(
        t("nineQuestions.noCreationReason", "暂无创建原因"),
        task.creation_rationale ||
          task.reason ||
          task.creation_reason ||
          metadata.creation_rationale ||
          metadata.creation_reason ||
          taskRawPayload.creation_rationale ||
          taskRawPayload.creation_reason ||
          taskRawPayload.reason,
      ),
      createdAt: firstText(
        "-",
        task.created_at ||
          task.createdAt ||
          task.creation_time ||
          task.creationTime ||
          metadata.created_at ||
          metadata.createdAt ||
          taskRawPayload.created_at ||
          taskRawPayload.createdAt,
      ),
      scope,
    });
  });
  return rows;
}

function formatDate(value: string): string {
  if (!value || value === "-") return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

const Q8TaskGroup: React.FC<{
  title: string;
  icon: React.ReactNode;
  rows: Q8CreatedTaskRow[];
  emptyText: string;
}> = ({ title, icon, rows, emptyText }) => {
  const { t } = useTranslation();
  return (
    <Card variant="outlined" data-testid={`q8-task-group-${title}`}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          {icon}
          <Typography variant="h6" fontWeight="bold">{title}</Typography>
          <Chip size="small" label={rows.length} variant="outlined" />
        </Stack>
        {rows.length === 0 ? (
          <Alert severity="info">{emptyText}</Alert>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t("nineQuestions.createdTask", "创建任务")}</TableCell>
                  <TableCell>{t("nineQuestions.taskDescription", "任务说明")}</TableCell>
                  <TableCell>{t("nineQuestions.taskType", "任务类型")}</TableCell>
                  <TableCell>{t("nineQuestions.creationReason", "创建原因")}</TableCell>
                  <TableCell>{t("nineQuestions.createdAt", "创建时间")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id} hover data-testid={`q8-created-task-${row.scope}`}>
                    <TableCell sx={{ minWidth: 180 }}>
                      <Typography variant="body2" fontWeight="bold">{row.title}</Typography>
                      <Typography variant="caption" color="text.secondary">{row.queueName}</Typography>
                    </TableCell>
                    <TableCell sx={{ minWidth: 240 }}>{row.description}</TableCell>
                    <TableCell sx={{ minWidth: 140 }}>
                      <Chip
                        size="small"
                        label={row.taskType}
                        color={row.scope === "external" ? "secondary" : "primary"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell sx={{ minWidth: 220 }}>{row.creationReason}</TableCell>
                    <TableCell sx={{ minWidth: 170 }}>{formatDate(row.createdAt)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
};

export const Q8EvidencePanel: React.FC<Q8EvidencePanelProps> = ({
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const { t } = useTranslation();
  const tr: Translate = (key, fallback) => t(key, { defaultValue: fallback });
  const internalRows = buildIntentRows(inference, tr, "internal");
  const externalRows = buildIntentRows(inference, tr, "external");
  const hasDirectIntentRows = internalRows.length + externalRows.length > 0;

  return (
    <Stack spacing={3} sx={{ mt: 2 }} data-testid="q8-created-task-list">
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName ? (
            <Chip
              label={`${t("nineQuestions.decisionArbitrator")}: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          ) : null}
          {elapsedMs > 0 ? (
            <Chip
              label={`${t("nineQuestions.arbitrationLatency")}: ${elapsedMs}ms`}
              size="small"
              variant="outlined"
            />
          ) : null}
        </Box>
      )}

      <Card variant="outlined" sx={{ borderLeft: "4px solid", borderLeftColor: "primary.main" }}>
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="h6" fontWeight="bold">
              {t("nineQuestions.q8CreatedTaskList", "Q8 创建任务清单")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t(
                "nineQuestions.q8CreatedTaskListHelp",
                "这里只展示 Q8 生成的抽象任务意图与创建原因；内部意图与外部意图分组展示。",
              )}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={`${t("nineQuestions.internalTasks", "内部任务")}: ${internalRows.length}`} color="primary" variant="outlined" />
              <Chip label={`${t("nineQuestions.externalTasks", "外部任务")}: ${externalRows.length}`} color="secondary" variant="outlined" />
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      {!inference ? (
        <Alert severity="info">{t("nineQuestions.waitingAutonomousDecision", "等待自主决策")}</Alert>
      ) : null}
      {inference && !hasDirectIntentRows ? (
        <Alert severity="warning" icon={<ErrorOutlineIcon />}>
          {t("nineQuestions.noQ8CreatedTasks", "Q8 推理结果中没有可展示的创建任务。")}
        </Alert>
      ) : null}

      {inference && hasDirectIntentRows ? (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12 }}>
            <Q8TaskGroup
              title={t("nineQuestions.internalTasks", "内部任务")}
              icon={<AssignmentTurnedInIcon color="primary" />}
              rows={internalRows}
              emptyText={t("nineQuestions.noInternalQ8Tasks", "本次 Q8 没有创建内部任务。")}
            />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Q8TaskGroup
              title={t("nineQuestions.externalTasks", "外部任务")}
              icon={<HubIcon color="secondary" />}
              rows={externalRows}
              emptyText={t("nineQuestions.noExternalQ8Tasks", "本次 Q8 没有创建外部任务。")}
            />
          </Grid>
        </Grid>
      ) : null}

      <Divider />
    </Stack>
  );
};

export default Q8EvidencePanel;
