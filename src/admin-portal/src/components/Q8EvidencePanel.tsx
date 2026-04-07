import React from "react";
import {
  Alert, Box, Card, CardContent, Chip, Grid, Stack, Typography, Accordion, AccordionSummary, AccordionDetails, List, ListItem, ListItemText, ListItemIcon, Badge, Stepper, Step, StepLabel
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

export const Q8EvidencePanel: React.FC<Q8EvidencePanelProps> = ({
  evidence, inference, providerName, elapsedMs = 0,
}) => {
  const agContext = evidence.aggregated_context;
  const runState = evidence.runtime_state;

  // Assembly DataGrid rows
  const taskRows: any[] = [];
  if (inference?.task_queue) {
    const q = inference.task_queue;
    (q.next_self_tasks || []).forEach((t, i) => {
      taskRows.push({ id: `next-${i}`, grid_type: 'NEXT', title: t.title || t.name || t.task || 'MNC', reason: '-', ...t });
    });
    (q.blocked_self_tasks || []).forEach((t, i) => {
      taskRows.push({ id: `blocked-${i}`, grid_type: 'BLOCKED', title: t.title || t.name || t.task || 'MNC', reason: t.reason || t.blocker_reason || t.block_reason || 'Unknown Block', ...t });
    });
    (q.proactive_actions || []).forEach((t, i) => {
      taskRows.push({ id: `proactive-${i}`, grid_type: 'PROACTIVE', title: t.title || t.name || t.task || 'MNC', reason: t.intent || t.reason || 'Probing', ...t });
    });
  }

  const columns: GridColDef[] = [
    { 
      field: 'grid_type', 
      headerName: '类型/状态', 
      width: 150, 
      renderCell: (params) => {
        if (params.value === 'NEXT') return <Chip icon={<PlayCircleOutlineIcon/>} label="下步执行" color="success" size="small" />;
        if (params.value === 'BLOCKED') return <Chip icon={<BlockIcon/>} label="受阻队列" color="error" size="small" data-testid="q8-blocked-chip" />;
        if (params.value === 'PROACTIVE') return <Chip label="探索探测" color="info" size="small" />;
        return <Chip label={params.value} />;
      }
    },
    { field: 'title', headerName: '任务目标', flex: 1, minWidth: 200 },
    { field: 'reason', headerName: '阻塞原因/意图 (Blocker Reason)', flex: 1, minWidth: 200, renderCell: (params) => {
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
              label={`Decision Arbitrator: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          )}
          {elapsedMs > 0 && (
            <Chip
              label={`Arbitration Latency: ${elapsedMs}ms`}
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
            【Q1-Q7 前置约束聚合区】已加载 Q1-Q7 前置约束（包含 {agContext?.absolute_red_line_count || 0} 项绝对红线与 {agContext?.capability_ceiling_count || 0} 项能力上限）
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
                【运行时状态与内部待办区 (State Machine & Agenda)】
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">持久化状态机 (Persistent Task State):</Typography>
                  <List dense sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                    {runState?.persistent_task_state && runState.persistent_task_state.length > 0 ? (
                      runState.persistent_task_state.map((task, i) => (
                        <ListItem key={i} divider={i < runState.persistent_task_state.length - 1}>
                          <ListItemIcon sx={{ minWidth: 28 }}>
                            <AssignmentTurnedInIcon color={task.status === 'blocked' ? 'error' : 'disabled'} fontSize="small" />
                          </ListItemIcon>
                          <ListItemText 
                            primary={task.title} 
                            secondary={`Status: ${task.status} | Blocker: ${task.blocker_reason || 'N/A'}`} 
                          />
                        </ListItem>
                      ))
                    ) : (
                      <ListItem><ListItemText primary="无可追踪的持久化历史任务" /></ListItem>
                    )}
                  </List>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">活跃内部认知待办 (Cognitive Agenda):</Typography>
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
                              <Chip size="small" label={`Delay Risk: ${agenda.delay_risk_score || 0}`} color={agenda.status === 'overdue' ? 'error' : 'default'} />
                            </Box>
                            {agenda.next_review_condition && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, pl: 4 }}>
                                触发条件: {agenda.next_review_condition}
                              </Typography>
                            )}
                          </CardContent>
                        </Card>
                      ))
                    ) : (
                      <Alert severity="success" sx={{ py: 0 }}>当前无超期或活跃的认知关注项</Alert>
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
                【终极目标与执行队列区 (LLM Objective & Task Queue)】
              </Typography>
              
              {inference ? (
                <Stack spacing={3} sx={{ mt: 2 }}>
                  {/* Current Primary Objective */}
                  <Box sx={{ textAlign: 'center', py: 2, bgcolor: 'secondary.50', borderRadius: 2 }}>
                    <Typography variant="overline" color="secondary.dark" letterSpacing={1.5} fontWeight="bold">主引擎锁定的当下唯一使命</Typography>
                    <Typography variant="h4" fontWeight="bold" color="text.primary" sx={{ my: 1 }}>
                      {inference.objective_profile?.current_primary_objective || "WAITING_FOR_OBJECTIVE"}
                    </Typography>
                  </Box>

                  {/* Objective Phase Tasks */}
                  <Box>
                    <Typography variant="subtitle2" gutterBottom color="text.secondary">执行阶段拆解序列 (Phase Order):</Typography>
                    {inference.objective_profile?.current_phase_tasks && inference.objective_profile.current_phase_tasks.length > 0 ? (
                      <Stepper activeStep={-1} alternativeLabel>
                        {inference.objective_profile.current_phase_tasks.map((label, index) => (
                          <Step key={index}>
                            <StepLabel>{label}</StepLabel>
                          </Step>
                        ))}
                      </Stepper>
                    ) : (
                      <Typography variant="body2" color="text.disabled">未建立阶段拆解链</Typography>
                    )}
                  </Box>

                  {/* Autonomous Task Queue DataGrid */}
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="subtitle2" gutterBottom color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <WarningAmberIcon fontSize="small" color="error" /> 自主任务执行队列 (Autonomous Task Queue DataGrid):
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
                <Alert severity="info" sx={{ mt: 2 }}>等待自主决策引擎下发最终任务队列与目标锁...</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q8EvidencePanel;
