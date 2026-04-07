import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stepper,
  Step,
  StepLabel,
  TextField,
  Drawer,
  Tabs,
  Tab,
  Alert,
  Tooltip,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import {
  Timeline,
  TimelineItem,
  TimelineSeparator,
  TimelineConnector,
  TimelineContent,
  TimelineDot,
} from '@mui/lab';
import {
  Add as AddIcon,
  Lan as LanIcon,
  Circle as CircleIcon,
} from '@mui/icons-material';
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

// --- Types ---

export type AgentTrustLevel = 'unknown' | 'pending' | 'trusted' | 'restricted' | 'revoked';
export type AgentStatus = 'idle' | 'active' | 'busy' | 'offline' | 'handshake_failed' | 'audit_failed';

export interface AgentAsset {
  agent_id: string;
  name: string; // Technical ID
  agent_name: string; // Human Name
  version: string;
  function_description: string;
  endpoint: string;
  role_tag: string;
  trust_level: AgentTrustLevel;
  status: AgentStatus;
  scope: string[];
  capabilities: any[];
  latency_ms: number | null;
  success_rate: number;
  last_ping_at: string | null;
  registered_at: string;
  inbox: Array<{
    task_id: string;
    title: string;
    status: string;
    idempotency_key: string;
    originator_id: string;
    remarks: string | null;
  }>;
  assigned_goal: string | null;
  receipts: Array<{
    task_id: string;
    title: string;
    status: string;
    idempotency_key: string;
    completed_at: string | null;
    remarks: string | null;
  }>;
}

export interface AgentTask {
  id: string; // Required for DataGrid
  task_id: string;
  subtask_id: string | null;
  title: string;
  task_type: string;
  status: string;
  progress: number;
  originator_id: string;
  remarks: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface TranscriptEventPayload {
  entry_id: string;
  session_id: string;
  turn_id: string;
  entry_type: string;
  timestamp: string;
  source: string;
  trace_id: string;
  context_info: any;
  payload: any;
}

// --- Components ---

const TrustLevelChip = ({ level }: { level: AgentTrustLevel }) => {
  const colorMap: Record<AgentTrustLevel, any> = {
    unknown: 'default',
    pending: 'warning',
    trusted: 'success',
    restricted: 'info',
    revoked: 'error',
  };
  return (
    <Chip
      size="small"
      label={level.toUpperCase()}
      color={colorMap[level]}
      variant={level === 'pending' ? 'outlined' : 'filled'}
      sx={{ fontWeight: 'bold' }}
    />
  );
};

const StatusDot = ({ status }: { status: AgentStatus }) => {
  const colorMap: Record<AgentStatus, string> = {
    idle: '#4caf50',
    active: '#2196f3',
    busy: '#ff9800',
    offline: '#9e9e9e',
    handshake_failed: '#f44336',
    audit_failed: '#d32f2f',
  };
  return (
    <Tooltip title={`Status: ${status}`}>
      <CircleIcon sx={{ fontSize: 12, color: colorMap[status] }} />
    </Tooltip>
  );
};

const TASK_COLUMNS: GridColDef[] = [
  { field: 'task_id', headerName: '任务ID', width: 100 },
  { field: 'subtask_id', headerName: '任务子ID', width: 100 },
  { field: 'title', headerName: '任务名称', width: 180 },
  { field: 'task_type', headerName: '任务类型', width: 130 },
  { 
    field: 'status', 
    headerName: '任务状态', 
    width: 120,
    renderCell: (params) => (
      <Chip
        label={String(params.value || "").toUpperCase()}
        size="small"
        variant="outlined"
        color={
          params.value === "in_progress"
            ? "primary"
            : params.value === "blocked"
              ? "warning"
              : params.value === "waiting_confirmation"
                ? "secondary"
                : params.value === "done"
                  ? "success"
                  : params.value === "failed"
                    ? "error"
                    : "default"
        }
      />
    )
  },
  { 
    field: 'progress', 
    headerName: '任务进度', 
    width: 150,
    renderCell: (params) => (
      <Box sx={{ width: '100%', mt: 2 }}>
        <LinearProgress variant="determinate" value={params.value * 100} sx={{ height: 6, borderRadius: 3 }} />
        <Typography variant="caption" sx={{ color: '#718096' }}>{Math.round(params.value * 100)}%</Typography>
      </Box>
    )
  },
  { field: 'originator_id', headerName: '任务发布方', width: 130 },
  { field: 'remarks', headerName: '任务备注', width: 220 },
  { field: 'started_at', headerName: '任务开始时间', width: 180 },
  { field: 'completed_at', headerName: '任务结束时间', width: 180 },
];

export const AgentAssetManager: React.FC = () => {
  const [agents, setAgents] = useState<AgentAsset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setDialogOpen] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [drawerAgent, setDrawerAgent] = useState<AgentAsset | null>(null);
  const [drawerTasks, setDrawerTasks] = useState<AgentTask[]>([]);
  const [drawerAuditEvents, setDrawerAuditEvents] = useState<TranscriptEventPayload[]>([]);
  const [tabValue, setTabValue] = useState(0);
  const [taskTabValue, setTaskTabValue] = useState(0);

  // Registration Form State
  const [regData, setRegData] = useState({
    name: '', // Technical ID
    agent_name: '', // Human Name
    version: '1.0.0',
    function_description: '',
    endpoint: '',
    auth_token: '',
    role_tag: 'worker',
    scope: 'general',
  });

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const res = await fetch("/api/web/agents");
      if (!res.ok) {
        throw new Error(`获取 Agent 列表失败（HTTP ${res.status}）`);
      }
      const data = await res.json();
      setAgents(data);
      setError(null);
    } catch (err) {
        console.error('Failed to fetch agents', err);
        setError(err instanceof Error ? err.message : "获取 Agent 列表失败");
    }
  };

  const fetchTasks = async (agentId: string) => {
    try {
      const res = await fetch(`/api/web/agents/${agentId}/tasks`);
      const data = await res.json();
      setDrawerTasks(data.map((t: any) => ({ ...t, id: t.task_id })));
    } catch (err) {
        console.error('Failed to fetch tasks', err);
    }
  };

  const fetchAudit = async (agentId: string) => {
    try {
      const res = await fetch(`/api/web/agents/${agentId}/audit`);
      const data = await res.json();
      setDrawerAuditEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Failed to fetch agent audit events", err);
      setDrawerAuditEvents([]);
    }
  };

  useEffect(() => {
    if (drawerAgent) {
        fetchTasks(drawerAgent.agent_id);
        fetchAudit(drawerAgent.agent_id);
    }
  }, [drawerAgent]);

  const handleRegister = async () => {
    try {
      const res = await fetch("/api/web/agents/register", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...regData,
          scope: [regData.scope],
        }),
      });
      if (res.ok) {
        fetchAgents();
        setDialogOpen(false);
        setActiveStep(0);
        setRegData({ name: '', agent_name: '', version: '1.0.0', function_description: '', endpoint: '', auth_token: '', role_tag: 'worker', scope: 'general' });
      } else if (res.status === 422) {
          alert('Validation Failed: Both name, version, and description are required.');
      }
    } catch (err) {
      console.error('Registration failed', err);
    }
  };

  return (
    <Box sx={{ p: 4, bgcolor: '#0b0e14', minHeight: '100vh', color: '#fff' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 4, alignItems: 'center' }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 2 }}>
          <LanIcon color="primary" fontSize="large" />
          Agent 资产管理中心
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setDialogOpen(true)}
          sx={{
            borderRadius: 2,
            background: 'linear-gradient(45deg, #2196F3 30%, #21CBF3 90%)',
            boxShadow: '0 3px 5px 2px rgba(33, 203, 243, .3)',
          }}
        >
          Add Agent Asset
        </Button>
      </Box>

      {error ? (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      ) : null}

      {/* Asset Grid */}
      <Grid container spacing={3}>
        {agents.map((agent) => (
          <Grid item xs={12} sm={6} md={4} key={agent.agent_id}>
            <Card
              sx={{
                bgcolor: '#1c222d', color: '#fff', border: '1px solid #2d3748',
                transition: 'transform 0.2s', '&:hover': { transform: 'translateY(-4px)', borderColor: '#4a5568' },
                cursor: 'pointer',
              }}
              onClick={() => setDrawerAgent(agent)}
            >
              <CardHeader
                avatar={<StatusDot status={agent.status} />}
                action={<Typography variant="caption" color="#718096">v{agent.version}</Typography>}
                title={<Typography variant="subtitle1" fontWeight="bold">{agent.agent_name}</Typography>}
                subheader={<Typography variant="caption" sx={{ color: '#718096' }}>ID: {agent.agent_id}</Typography>}
              />
              <CardContent sx={{ pt: 0 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                  <TrustLevelChip level={agent.trust_level} />
                  <Typography variant="caption" sx={{ color: '#a0aec0' }}>{agent.role_tag}</Typography>
                </Box>
                <Typography variant="body2" sx={{ mb: 1, color: '#e2e8f0', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {agent.function_description}
                </Typography>
                <Typography variant="body2" sx={{ color: '#90caf9', fontSize: '0.78rem', mb: 1 }}>
                  Assigned Goal: {agent.assigned_goal || "暂无"}
                </Typography>
                <Typography variant="caption" display="block" sx={{ color: '#a0aec0' }}>
                  Inbox: {agent.inbox.length} | Receipts: {agent.receipts.length}
                </Typography>
                <Divider sx={{ my: 2, bgcolor: '#2d3748' }} />
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                   <Box><Typography variant="caption" display="block" color="#718096">Status</Typography><Typography variant="body2">{agent.status}</Typography></Box>
                   <Box><Typography variant="caption" display="block" color="#718096">对接时间</Typography><Typography variant="body2" sx={{ fontSize: '0.7rem' }}>{new Date(agent.registered_at).toLocaleDateString()}</Typography></Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Registration Dialog */}
      <Dialog open={isDialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth
        PaperProps={{ sx: { bgcolor: '#1a202c', color: '#fff', borderRadius: 4 } }}
      >
        <DialogTitle sx={{ fontWeight: 'bold' }}>Agent 引导式注册 (V2 Secured)</DialogTitle>
        <DialogContent sx={{ mt: 2 }}>
          <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 4, '& .MuiStepLabel-label': { color: '#718096' }, '& .MuiStepIcon-root': { color: '#2d3748' } }}>
            {['Asset Profile', 'Security & Scoping', 'Handshake'].map((label) => (
              <Step key={label}><StepLabel>{label}</StepLabel></Step>
            ))}
          </Stepper>

          {activeStep === 0 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <TextField label="Technical Name (ID)" fullWidth variant="outlined" value={regData.name} onChange={(e) => setRegData({ ...regData, name: e.target.value })}
                InputLabelProps={{ style: { color: '#718096' } }} inputProps={{ style: { color: '#fff' } }} sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              />
              <TextField label="Human-Readable Name" fullWidth variant="outlined" value={regData.agent_name} onChange={(e) => setRegData({ ...regData, agent_name: e.target.value })}
                 required InputLabelProps={{ style: { color: '#718096' } }} inputProps={{ style: { color: '#fff' } }} sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              />
              <TextField label="Version (e.g., 1.0.2)" fullWidth variant="outlined" value={regData.version} onChange={(e) => setRegData({ ...regData, version: e.target.value })}
                 required InputLabelProps={{ style: { color: '#718096' } }} inputProps={{ style: { color: '#fff' } }} sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              />
              <TextField label="Function Description" fullWidth multiline rows={2} variant="outlined" value={regData.function_description} onChange={(e) => setRegData({ ...regData, function_description: e.target.value })}
                 required InputLabelProps={{ style: { color: '#718096' } }} inputProps={{ style: { color: '#fff' } }} sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              />
            </Box>
          )}

          {activeStep === 1 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <TextField label="Endpoint URL" fullWidth variant="outlined" value={regData.endpoint} onChange={(e) => setRegData({ ...regData, endpoint: e.target.value })}
                InputLabelProps={{ style: { color: '#718096' } }} inputProps={{ style: { color: '#fff' } }} sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              />
              <TextField label="Auth Token (Encrypted)" fullWidth variant="outlined" type="password" value={regData.auth_token} onChange={(e) => setRegData({ ...regData, auth_token: e.target.value })}
                InputLabelProps={{ style: { color: '#718096' } }} inputProps={{ style: { color: '#fff' } }} sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#2d3748' } } }}
              />
            </Box>
          )}

          {activeStep === 2 && (
            <Box>
                <Alert severity="warning" sx={{ mb: 2 }}>Agent will be created in PENDING state until Cloud Audit completes.</Alert>
                <Typography variant="body2" color="#718096">Initiating handshake will perform connectivity and capability probes.</Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 3 }}>
          <Button onClick={() => setDialogOpen(false)} sx={{ color: '#718096' }}>Cancel</Button>
          {activeStep > 0 && <Button onClick={() => setActiveStep(activeStep - 1)}>Back</Button>}
          <Button onClick={activeStep === 2 ? handleRegister : () => setActiveStep(activeStep + 1)} variant="contained" 
            disabled={activeStep === 0 && (!regData.agent_name || !regData.version || !regData.function_description)}>
            {activeStep === 2 ? 'Finalize Registration' : 'Continue'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Detail Drawer - High Density Monitoring */}
      <Drawer anchor="right" open={Boolean(drawerAgent)} onClose={() => setDrawerAgent(null)}
        PaperProps={{ sx: { width: '80vw', maxWidth: 1000, bgcolor: '#0b0e14', color: '#fff', borderLeft: '1px solid #2d3748' } }}
      >
        {drawerAgent && (
          <Box sx={{ p: 4, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 4 }}>
               <Box>
                  <Typography variant="h4" fontWeight="bold">{drawerAgent.agent_name}</Typography>
                  <Typography variant="body2" color="#718096">Version {drawerAgent.version} | 对接时间: {new Date(drawerAgent.registered_at).toLocaleString()}</Typography>
               </Box>
               <Box sx={{ textAlign: 'right' }}>
                  <TrustLevelChip level={drawerAgent.trust_level} />
                  <Typography variant="caption" display="block" color="#718096" mt={1}>Endpoint: {drawerAgent.endpoint}</Typography>
               </Box>
            </Box>

            <Typography variant="subtitle1" sx={{ mb: 3, p: 2, bgcolor: '#1a202c', borderRadius: 2, borderLeft: '4px solid #2196f3' }}>
               {drawerAgent.function_description}
            </Typography>
            <Alert severity="info" sx={{ mb: 2 }}>
              Assigned Goal: {drawerAgent.assigned_goal || "暂无"} | Inbox: {drawerAgent.inbox.length} | Receipts: {drawerAgent.receipts.length}
            </Alert>
            <List dense sx={{ mb: 2, bgcolor: '#111827', borderRadius: 2 }}>
              {drawerTasks.map((task) => (
                <ListItem key={`snapshot-${task.task_id}`}>
                  <ListItemText
                    primary={task.title}
                    secondary={`${task.status} | ${task.task_id}`}
                    primaryTypographyProps={{ color: '#fff' }}
                    secondaryTypographyProps={{ color: '#a0aec0' }}
                  />
                </ListItem>
              ))}
            </List>

            <Tabs value={tabValue} onChange={(_, v) => setTabValue(v)} sx={{ borderBottom: 1, borderColor: '#2d3748', mb: 2 }}>
               <Tab label="任务流水线 (Unified Pipeline)" sx={{ color: '#718096', '&.Mui-selected': { color: '#2196f3' } }} />
               <Tab label="审计与握手详情" sx={{ color: '#718096', '&.Mui-selected': { color: '#2196f3' } }} />
               <Tab label="历史记录" sx={{ color: '#718096', '&.Mui-selected': { color: '#2196f3' } }} />
            </Tabs>

            {tabValue === 0 && (
              <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
                  <Tabs value={taskTabValue} onChange={(_, v) => setTaskTabValue(v)} variant="scrollable" scrollButtons="auto" 
                    sx={{ minHeight: 40, mb: 1, '& .MuiTab-root': { fontSize: '0.8rem', minHeight: 40 } }}>
                     <Tab label="当前待处理" />
                     <Tab label="正在进行中" />
                     <Tab label="已处理回执" />
                  </Tabs>
                  
                  <Box sx={{ height: 400, width: '100%', bgcolor: '#1c222d', borderRadius: 2, overflow: 'hidden' }}>
                      <DataGrid
                        rows={drawerTasks.filter(t => {
                            if (taskTabValue === 0) return ["todo", "blocked", "waiting_confirmation"].includes(t.status);
                            if (taskTabValue === 1) return t.status === "in_progress";
                            return ["done", "failed"].includes(t.status);
                        })}
                        columns={TASK_COLUMNS}
                        disableVirtualization
                        pageSizeOptions={[5, 10]}
                        initialState={{ pagination: { paginationModel: { pageSize: 5 } } }}
                        sx={{
                            color: '#e2e8f0', borderColor: '#2d3748',
                            '& .MuiDataGrid-cell': { borderColor: '#2d3748' },
                            '& .MuiDataGrid-columnHeaders': { bgcolor: '#2d3748', color: '#fff', borderBottom: '1px solid #4a5568' },
                            '& .MuiDataGrid-footerContainer': { bgcolor: '#1c222d', borderTop: '1px solid #2d3748' },
                            '& .MuiCheckbox-root': { color: '#4a5568' },
                        }}
                      />
                  </Box>
              </Box>
            )}

            {tabValue === 1 && (
                <Grid container spacing={4}>
                    <Grid item xs={6}>
                       <Typography variant="overline" color="#718096">Capability Probes</Typography>
                       <List dense sx={{ bgcolor: '#1a202c', borderRadius: 2 }}>
                          {drawerAgent.capabilities.map((cap, i) => (
                              <ListItem key={i}><ListItemText primary={cap.capability} secondary={`version: ${cap.version}`} primaryTypographyProps={{ color: '#fff' }} /></ListItem>
                          ))}
                       </List>
                    </Grid>
                    <Grid item xs={6}>
                       <Typography variant="overline" color="#718096">Trust Verification</Typography>
                       <Box sx={{ p: 2, border: '1px solid #2d3748', borderRadius: 2 }}>
                          <Typography variant="body2" gutterBottom>Cloud Audit Score: 0.98</Typography>
                          <LinearProgress variant="determinate" value={98} color="success" />
                          <Typography variant="caption" display="block" sx={{ mt: 1, color: '#718096' }}>All security policies satisfied.</Typography>
                       </Box>
                       <Typography variant="overline" color="#718096" sx={{ mt: 3, display: 'block' }}>Inbox Snapshot</Typography>
                       <List dense sx={{ bgcolor: '#1a202c', borderRadius: 2 }}>
                          {drawerAgent.inbox.length ? drawerAgent.inbox.map((item) => (
                            <ListItem key={item.task_id}>
                              <ListItemText
                                primary={item.title}
                                secondary={`${item.status} | ${item.idempotency_key} | ${item.remarks || "-"}`}
                                primaryTypographyProps={{ color: '#fff' }}
                              />
                            </ListItem>
                          )) : (
                            <ListItem>
                              <ListItemText primary="暂无待处理 inbox 项" primaryTypographyProps={{ color: '#a0aec0' }} />
                            </ListItem>
                          )}
                       </List>
                    </Grid>
                </Grid>
            )}

            {tabValue === 2 && (
                <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
                    <Typography variant="overline" color="#718096">Task Receipts</Typography>
                    <List dense sx={{ mb: 3, bgcolor: '#1a202c', borderRadius: 2 }}>
                      {drawerAgent.receipts.length ? drawerAgent.receipts.map((receipt) => (
                        <ListItem key={receipt.task_id}>
                          <ListItemText
                            primary={receipt.title}
                            secondary={`${receipt.status} | ${receipt.idempotency_key}`}
                            primaryTypographyProps={{ color: '#fff' }}
                          />
                        </ListItem>
                      )) : (
                        <ListItem>
                          <ListItemText primary="暂无回执" primaryTypographyProps={{ color: '#a0aec0' }} />
                        </ListItem>
                      )}
                    </List>
                    <Timeline position="right">
                      {drawerAuditEvents.length === 0 ? (
                        <TimelineItem>
                          <TimelineSeparator>
                            <TimelineDot color="grey" />
                          </TimelineSeparator>
                          <TimelineContent>
                            <Typography variant="subtitle2">暂无审计流水</Typography>
                            <Typography variant="body2" color="#a0aec0">
                              后端未写入该 Agent 的审计事件，或当前没有匹配记录。
                            </Typography>
                          </TimelineContent>
                        </TimelineItem>
                      ) : (
                        drawerAuditEvents.map((event, index) => {
                          const entryType = String(event.entry_type || "");
                          const dotColor =
                            entryType.includes("failed") ? "error" : entryType.includes("completed") ? "success" : "info";
                          const summary =
                            (event.payload && (event.payload.summary || event.payload.message)) ||
                            (event.payload && event.payload.details && (event.payload.details.action || event.payload.details.new_status)) ||
                            entryType;

                          return (
                            <TimelineItem key={event.entry_id}>
                              <TimelineSeparator>
                                <TimelineDot color={dotColor as any} />
                                {index < drawerAuditEvents.length - 1 ? <TimelineConnector /> : null}
                              </TimelineSeparator>
                              <TimelineContent>
                                <Typography variant="subtitle2">{entryType}</Typography>
                                <Typography variant="caption" color="#718096">
                                  {new Date(event.timestamp).toLocaleString()} | trace:{" "}
                                  <span style={{ fontFamily: "monospace" }}>{event.trace_id.slice(0, 10)}</span>
                                </Typography>
                                <Typography variant="body2" color="#a0aec0" sx={{ mt: 0.5 }}>
                                  {String(summary)}
                                </Typography>

                                <Accordion
                                  sx={{
                                    mt: 1,
                                    bgcolor: "#1a202c",
                                    color: "#fff",
                                    border: "1px solid #2d3748",
                                  }}
                                >
                                  <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: "#718096" }} />}>
                                    <Typography variant="body2" sx={{ color: "#e2e8f0" }}>
                                      Payload（默认折叠）
                                    </Typography>
                                  </AccordionSummary>
                                  <AccordionDetails>
                                    <Box
                                      component="pre"
                                      sx={{
                                        m: 0,
                                        p: 2,
                                        bgcolor: "#0b0e14",
                                        borderRadius: 1,
                                        overflow: "auto",
                                        maxHeight: 260,
                                        fontSize: "0.75rem",
                                      }}
                                    >
                                      <code>{JSON.stringify(event.payload ?? {}, null, 2)}</code>
                                    </Box>
                                  </AccordionDetails>
                                </Accordion>
                              </TimelineContent>
                            </TimelineItem>
                          );
                        })
                      )}
                    </Timeline>
                </Box>
            )}
          </Box>
        )}
      </Drawer>
    </Box>
  );
};

export default AgentAssetManager;
