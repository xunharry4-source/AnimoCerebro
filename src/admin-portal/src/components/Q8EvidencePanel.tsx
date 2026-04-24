import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Alert, Box, Card, CardContent, Chip, Grid, Stack, Typography, Accordion, AccordionSummary, AccordionDetails, List, ListItem, ListItemText, ListItemIcon, Badge, Stepper, Step, StepLabel, Tabs, Tab
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import PendingActionsIcon from '@mui/icons-material/PendingActions';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import BlockIcon from '@mui/icons-material/Block';
import { DataGrid, GridColDef } from '@mui/x-data-grid';

import {
  Q8PreprocessedEvidence, Q8WhatShouldIDoNowInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q8EvidencePanelProps {
  evidence: Q8PreprocessedEvidence;
  inference: Q8WhatShouldIDoNowInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

function normalizeTaskItem(item: any) {
  if (typeof item === "string") {
    return { title: item };
  }
  if (item && typeof item === "object" && !Array.isArray(item)) {
    return item;
  }
  return { title: String(item ?? "") };
}

export const Q8EvidencePanel: React.FC<Q8EvidencePanelProps> = ({
  evidence, inference, providerName, elapsedMs = 0,
}) => {
  const { t } = useTranslation();
  const agContext = evidence.aggregated_context;
  const runState = evidence.runtime_state;

  // Assembly DataGrid rows
  const taskRows: any[] = [];
  if (inference?.task_queue) {
    const q = inference.task_queue;
    (q.next_self_tasks || []).forEach((rawItem, i) => {
      const item = normalizeTaskItem(rawItem);
      taskRows.push({ id: `next-${i}`, grid_type: 'NEXT', title: item.title || item.name || item.task || 'MNC', reason: '-', ...item });
    });
    (q.blocked_self_tasks || []).forEach((rawItem, i) => {
      const item = normalizeTaskItem(rawItem);
      taskRows.push({ id: `blocked-${i}`, grid_type: 'BLOCKED', title: item.title || item.name || item.task || 'MNC', reason: item.reason || item.blocker_reason || item.block_reason || 'Unknown Block', ...item });
    });
    (q.proactive_actions || []).forEach((rawItem, i) => {
      const item = normalizeTaskItem(rawItem);
      taskRows.push({ id: `proactive-${i}`, grid_type: 'PROACTIVE', title: item.title || item.name || item.task || 'MNC', reason: item.intent || item.reason || 'Probing', ...item });
    });
  }

  const columns: GridColDef[] = [
    { 
      field: 'grid_type', 
      headerName: t("nineQuestions.typeStatus"), 
      width: 150, 
      renderCell: (params) => {
        if (params.value === 'NEXT') return <Chip icon={<PlayCircleOutlineIcon/>} label={t("nineQuestions.nextExecution")} color="success" size="small" />;
        if (params.value === 'BLOCKED') return <Chip icon={<BlockIcon/>} label={t("nineQuestions.blockedQueue")} color="error" size="small" data-testid="q8-blocked-chip" />;
        if (params.value === 'PROACTIVE') return <Chip label={t("nineQuestions.exploratoryProbe")} color="info" size="small" />;
        return <Chip label={params.value} />;
      }
    },
    { field: 'title', headerName: t("nineQuestions.taskObjective"), flex: 1, minWidth: 200 },
    { field: 'reason', headerName: t("nineQuestions.blockerReason"), flex: 1, minWidth: 200, renderCell: (params) => {
        if (params.row.grid_type === 'BLOCKED') {
          return <Typography variant="body2" color="error.main" fontWeight="bold">{params.value}</Typography>;
        }
        return <Typography variant="body2">{params.value}</Typography>;
    }}
  ];

  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {/* Partition 0: Inference Metadata */}
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && (
            <Chip
              label={`${t("nineQuestions.decisionArbitrator")}: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          )}
          {elapsedMs > 0 && (
            <Chip
              label={`${t("nineQuestions.arbitrationLatency")}: ${elapsedMs}ms`}
              size="small"
              variant="outlined"
            />
          )}
        </Box>
      )}

      {/* Partition 1: Q1-Q7 全量前置约束聚合区 */}
      <Accordion variant="outlined" defaultExpanded={false} sx={{ border: '2px solid', borderColor: 'primary.main', bgcolor: 'background.paper' }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} data-testid="q8-context-accordion-summary">
          <Typography variant="h6" fontWeight="bold" color="primary.main">
            {t("nineQuestions.q1Q7ConstraintAggregation", { redLineCount: agContext?.absolute_red_line_count || 0, capabilityCeilingCount: agContext?.capability_ceiling_count || 0 })}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ bgcolor: 'grey.900', p: 2, borderRadius: 1, overflowX: 'auto', maxHeight: 400, overflowY: 'auto' }}>
            <pre style={{ margin: 0, color: 'lime' }}>
              <code>{JSON.stringify(agContext?.q1_to_q7_snapshot, null, 2)}</code>
            </pre>
          </Box>
        </AccordionDetails>
      </Accordion>

      <Grid container spacing={3}>
        {/* Partition 2: 运行时状态与内部待办区 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderLeft: '4px solid', borderLeftColor: 'info.main' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                {t("nineQuestions.stateMachineAgenda")}
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.persistentTaskState")}:</Typography>
                  <List dense sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                    {runState?.persistent_task_state && runState.persistent_task_state.length > 0 ? (
                      runState.persistent_task_state.map((task, i) => (
                        <ListItem key={i} divider={i < runState.persistent_task_state.length - 1}>
                          <ListItemIcon sx={{ minWidth: 28 }}>
                            <AssignmentTurnedInIcon color={task.status === 'blocked' ? 'error' : 'disabled'} fontSize="small" />
                          </ListItemIcon>
                          <ListItemText 
                            primary={task.title} 
                            secondary={`${t("common.status")}: ${task.status} | ${t("nineQuestions.blocker")}: ${task.blocker_reason || 'N/A'}`} 
                          />
                        </ListItem>
                      ))
                    ) : (
                      <ListItem><ListItemText primary={t("nineQuestions.noPersistentHistoryTasks")} /></ListItem>
                    )}
                  </List>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.cognitiveAgenda")}:</Typography>
                  <Stack spacing={1}>
                    {runState?.cognitive_agenda && runState.cognitive_agenda.length > 0 ? (
                      runState.cognitive_agenda.map((agenda, i) => (
                        <Card key={i} variant="outlined" sx={{ bgcolor: agenda.status === 'overdue' ? 'error.50' : 'background.paper' }}>
                          <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Badge color="error" variant="dot" invisible={agenda.status !== 'overdue'}>
                                  <PendingActionsIcon color="action" />
                                </Badge>
                                <Typography variant="body2" fontWeight="bold">{agenda.title}</Typography>
                              </Box>
                              <Chip size="small" label={`${t("nineQuestions.delayRisk")}: ${agenda.delay_risk_score || 0}`} color={agenda.status === 'overdue' ? 'error' : 'default'} />
                            </Box>
                            {agenda.next_review_condition && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, pl: 4 }}>
                                {t("nineQuestions.triggerCondition")}: {agenda.next_review_condition}
                              </Typography>
                            )}
                          </CardContent>
                        </Card>
                      ))
                    ) : (
                      <Alert severity="success" sx={{ py: 0 }}>{t("nineQuestions.noOverdueCognitiveItems")}</Alert>
                    )}
                  </Stack>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Partition 3: 大模型终极目标与队列排布区 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ border: '2px solid', borderColor: 'secondary.main' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', color: 'secondary.main' }}>
                {t("nineQuestions.llmObjectiveTaskQueue")}
              </Typography>
              
              {inference ? (
                <Stack spacing={3} sx={{ mt: 2 }}>
                  {/* Current Primary Objective */}
                  <Box sx={{ textAlign: 'center', py: 2, bgcolor: 'secondary.50', borderRadius: 2 }}>
                    <Typography variant="overline" color="secondary.dark" letterSpacing={1.5} fontWeight="bold">{t("nineQuestions.primaryMissionLocked")}</Typography>
                    <Typography variant="h4" fontWeight="bold" color="text.primary" sx={{ my: 1 }}>
                      {inference.objective_profile?.current_primary_objective || "WAITING_FOR_OBJECTIVE"}
                    </Typography>
                  </Box>

                  {/* Objective Phase Tasks */}
                  <Box>
                    <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.phaseOrder")}:</Typography>
                    {inference.objective_profile?.current_phase_tasks && inference.objective_profile.current_phase_tasks.length > 0 ? (
                      <Stepper activeStep={-1} alternativeLabel>
                        {inference.objective_profile.current_phase_tasks.map((label, index) => (
                          <Step key={index}>
                            <StepLabel>{label}</StepLabel>
                          </Step>
                        ))}
                      </Stepper>
                    ) : (
                      <Typography variant="body2" color="text.disabled">{t("nineQuestions.noPhaseChain")}</Typography>
                    )}
                  </Box>

                  {/* Autonomous Task Queue DataGrid */}
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="subtitle2" gutterBottom color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <WarningAmberIcon fontSize="small" color="error" /> {t("nineQuestions.autonomousTaskQueue")}:
                    </Typography>
                    <Box sx={{ height: 350, width: '100%', mt: 1 }} data-testid="q8-datagrid-container">
                      <DataGrid
                        rows={taskRows}
                        columns={columns}
                        rowSelection={false}
                        disableColumnMenu
                        hideFooter
                      />
                    </Box>
                  </Box>

                </Stack>
              ) : (
                <Alert severity="info" sx={{ mt: 2 }}>{t("nineQuestions.waitingAutonomousDecision")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Partition 4: 6类展示 Tab表 - 目标画像与自主任务队列详细展示 */}
        {inference && (
          <Q8DetailedTablesPartition inference={inference} />
        )}
      </Grid>
    </Stack>
  );
};

/**
 * 新增的 Tab 表格部分 - 显示 6 类详细数据
 */
const Q8DetailedTablesPartition: React.FC<{ inference: Q8WhatShouldIDoNowInferenceView }> = ({ inference }) => {
  const { t } = useTranslation();
  const [tabValue, setTabValue] = useState(0);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  // 表格数据准备
  const currentObjectiveRows = inference.objective_profile?.current_primary_objective 
    ? [{ id: 'current-primary', name: t("nineQuestions.currentPrimaryObjective"), value: inference.objective_profile.current_primary_objective }]
    : [];

  const phaseTasksRows = (inference.objective_profile?.current_phase_tasks || []).map((task, idx) => ({
    id: `phase-${idx}`,
    index: idx + 1,
    task: task,
  }));

  const priorityOrderRows = (inference.objective_profile?.priority_order || []).map((priority, idx) => ({
    id: `priority-${idx}`,
    index: idx + 1,
    priority: priority,
  }));

  const nextTasksRows = (inference.task_queue?.next_self_tasks || []).map((rawTask: any, idx: number) => {
    const task = normalizeTaskItem(rawTask);
    return ({
    id: `next-${idx}`,
    index: idx + 1,
    taskId: task.task_id || task.id || '-',
    title: task.title || task.name || task.task || '-',
    });
  });

  const blockedTasksRows = (inference.task_queue?.blocked_self_tasks || []).map((rawTask: any, idx:number) => {
    const task = normalizeTaskItem(rawTask);
    return ({
    id: `blocked-${idx}`,
    index: idx + 1,
    taskId: task.task_id || task.id || '-',
    title: task.title || task.name || task.task || '-',
    reason: task.reason || task.blocker_reason || task.block_reason || '-',
    });
  });

  const proactiveActionRows = (inference.task_queue?.proactive_actions || []).map((rawAction: any, idx: number) => {
    const action = normalizeTaskItem(rawAction);
    return ({
    id: `proactive-${idx}`,
    index: idx + 1,
    taskId: action.task_id || action.id || '-',
    title: action.title || action.name || action.task || '-',
    intent: action.intent || action.reason || '-',
    });
  });

  // 定义表格列
  const objectiveColumns: GridColDef[] = [
    { field: 'name', headerName: t("nineQuestions.keyName"), width: 200 },
    { field: 'value', headerName: t("nineQuestions.value"), flex: 1, minWidth: 300 },
  ];

  const phaseTasksColumns: GridColDef[] = [
    { field: 'index', headerName: t("nineQuestions.order"), width: 80 },
    { field: 'task', headerName: t("nineQuestions.taskContent"), flex: 1, minWidth: 300 },
  ];

  const priorityOrderColumns: GridColDef[] = [
    { field: 'index', headerName: t("nineQuestions.order"), width: 80 },
    { field: 'priority', headerName: t("nineQuestions.priorityItem"), flex: 1, minWidth: 300 },
  ];

  const nextTasksColumns: GridColDef[] = [
    { field: 'index', headerName: t("nineQuestions.order"), width: 80 },
    { field: 'taskId', headerName: 'Task ID', width: 120 },
    { field: 'title', headerName: t("nineQuestions.taskTitle"), flex: 1, minWidth: 250 },
  ];

  const blockedTasksColumns: GridColDef[] = [
    { field: 'index', headerName: t("nineQuestions.order"), width: 80 },
    { field: 'taskId', headerName: 'Task ID', width: 120 },
    { field: 'title', headerName: t("nineQuestions.taskTitle"), flex: 1, minWidth: 200 },
    { field: 'reason', headerName: t("nineQuestions.blockerReason"), flex: 1, minWidth: 200, renderCell: (params) => (
      <Typography variant="body2" color="error.main">{params.value}</Typography>
    ) },
  ];

  const proactiveActionColumns: GridColDef[] = [
    { field: 'index', headerName: t("nineQuestions.order"), width: 80 },
    { field: 'taskId', headerName: 'Task ID', width: 120 },
    { field: 'title', headerName: t("nineQuestions.taskTitle"), flex: 1, minWidth: 200 },
    { field: 'intent', headerName: t("nineQuestions.intent"), flex: 1, minWidth: 200 },
  ];

  return (
    <Grid size={{ xs: 12 }}>
      <Card variant="outlined" sx={{ border: '2px solid', borderColor: 'info.main' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', color: 'info.main', mb: 2 }}>
            {t("nineQuestions.detailedObjectiveAndQueueView", "目标画像与自主任务队列详细展示")}
          </Typography>

          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={tabValue} onChange={handleTabChange} aria-label="Q8 detailed tables">
              <Tab label={t("nineQuestions.currentPrimaryObjective", "当前主目标")} />
              <Tab label={t("nineQuestions.currentPhaseTasksTab", "阶段任务")} />
              <Tab label={t("nineQuestions.priorityOrder", "优先级排序")} />
              <Tab label={t("nineQuestions.nextSelfTasks", "下一步任务")} />
              <Tab label={t("nineQuestions.blockedSelfTasks", "阻塞任务")} />
              <Tab label={t("nineQuestions.proactiveActions", "主动行动")} />
            </Tabs>
          </Box>

          <Box sx={{ mt: 2, height: 400, overflow: 'auto' }}>
            {tabValue === 0 && currentObjectiveRows.length > 0 && (
              <DataGrid rows={currentObjectiveRows} columns={objectiveColumns} hideFooter disableColumnMenu rowSelection={false} />
            )}
            {tabValue === 0 && currentObjectiveRows.length === 0 && (
              <Alert severity="info">{t("nineQuestions.noDataAvailable")}</Alert>
            )}

            {tabValue === 1 && phaseTasksRows.length > 0 && (
              <DataGrid rows={phaseTasksRows} columns={phaseTasksColumns} hideFooter disableColumnMenu rowSelection={false} />
            )}
            {tabValue === 1 && phaseTasksRows.length === 0 && (
              <Alert severity="info">{t("nineQuestions.noDataAvailable")}</Alert>
            )}

            {tabValue === 2 && priorityOrderRows.length > 0 && (
              <DataGrid rows={priorityOrderRows} columns={priorityOrderColumns} hideFooter disableColumnMenu rowSelection={false} />
            )}
            {tabValue === 2 && priorityOrderRows.length === 0 && (
              <Alert severity="info">{t("nineQuestions.noDataAvailable")}</Alert>
            )}

            {tabValue === 3 && nextTasksRows.length > 0 && (
              <DataGrid rows={nextTasksRows} columns={nextTasksColumns} hideFooter disableColumnMenu rowSelection={false} />
            )}
            {tabValue === 3 && nextTasksRows.length === 0 && (
              <Alert severity="info">{t("nineQuestions.noDataAvailable")}</Alert>
            )}

            {tabValue === 4 && blockedTasksRows.length > 0 && (
              <DataGrid rows={blockedTasksRows} columns={blockedTasksColumns} hideFooter disableColumnMenu rowSelection={false} />
            )}
            {tabValue === 4 && blockedTasksRows.length === 0 && (
              <Alert severity="success">{t("nineQuestions.noBlockedTasks", "暂无阻塞任务")}</Alert>
            )}

            {tabValue === 5 && proactiveActionRows.length > 0 && (
              <DataGrid rows={proactiveActionRows} columns={proactiveActionColumns} hideFooter disableColumnMenu rowSelection={false} />
            )}
            {tabValue === 5 && proactiveActionRows.length === 0 && (
              <Alert severity="info">{t("nineQuestions.noDataAvailable")}</Alert>
            )}
          </Box>
        </CardContent>
      </Card>
    </Grid>
  );
};

export default Q8EvidencePanel;
