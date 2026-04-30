import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
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
  Alert,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tooltip,
  LinearProgress,
  Divider,
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

// --- Types ---

export type AgentTrustLevel = 'unknown' | 'pending' | 'trusted' | 'restricted' | 'revoked';
export type AgentStatus = 'idle' | 'active' | 'busy' | 'offline' | 'handshake_failed' | 'audit_failed' | 'invocation_blocked';

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
    invocation_blocked: '#d32f2f',
  };
  return (
    <Tooltip title={`Status: ${status}`}>
      <CircleIcon sx={{ fontSize: 12, color: colorMap[status] }} />
    </Tooltip>
  );
};

const TASK_COLUMNS = (t: any): GridColDef[] => [
  { field: 'task_id', headerName: t('agents.taskId'), width: 100 },
  { field: 'subtask_id', headerName: t('agents.subtaskId'), width: 100 },
  { field: 'title', headerName: t('agents.taskName'), width: 180 },
  { field: 'task_type', headerName: t('agents.taskType'), width: 130 },
  { 
    field: 'status', 
    headerName: t('agents.taskStatus'), 
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
    headerName: t('agents.taskProgress'), 
    width: 150,
    renderCell: (params) => (
      <Box sx={{ width: '100%', mt: 2 }}>
        <LinearProgress variant="determinate" value={params.value * 100} sx={{ height: 6, borderRadius: 3 }} />
        <Typography variant="caption" sx={{ color: '#718096' }}>{Math.round(params.value * 100)}%</Typography>
      </Box>
    )
  },
  { field: 'originator_id', headerName: t('agents.originator'), width: 130 },
  { field: 'remarks', headerName: t('agents.remarks'), width: 220 },
  { field: 'started_at', headerName: t('agents.startedAt'), width: 180 },
  { field: 'completed_at', headerName: t('agents.completedAt'), width: 180 },
];

export const AgentAssetManager: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentAsset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setDialogOpen] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  // Search and filter state
  const [searchName, setSearchName] = useState('');
  const [filterStatus, setFilterStatus] = useState<AgentStatus | 'all'>('all');
  const [filterRole, setFilterRole] = useState<string>('all');

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

  // Get unique role tags for filter dropdown
  const uniqueRoles = useMemo(() => {
    const roles = new Set(agents.map(agent => agent.role_tag));
    return Array.from(roles).sort();
  }, [agents]);

  // Filter agents based on search criteria
  const filteredAgents = useMemo(() => {
    return agents.filter(agent => {
      // Name search (matches agent_name or agent_id)
      const matchesName = !searchName.trim() || 
        agent.agent_name.toLowerCase().includes(searchName.trim().toLowerCase()) ||
        agent.agent_id.toLowerCase().includes(searchName.trim().toLowerCase());
      
      // Status filter
      const matchesStatus = filterStatus === 'all' || agent.status === filterStatus;
      
      // Role tag filter
      const matchesRole = filterRole === 'all' || agent.role_tag === filterRole;
      
      return matchesName && matchesStatus && matchesRole;
    });
  }, [agents, searchName, filterStatus, filterRole]);

  const fetchAgents = async () => {
    try {
      const res = await fetch("/api/web/agents");
      if (!res.ok) {
        throw new Error(t('agents.fetchFailed', { status: res.status }));
      }
      const data = await res.json();
      setAgents(data);
      setError(null);
    } catch (err) {
        console.error('Failed to fetch agents', err);
        setError(err instanceof Error ? err.message : t('agents.fetchFailedGeneric'));
    }
  };

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
          alert(t('agents.validationError'));
      }
    } catch (err) {
      console.error('Registration failed', err);
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        {/* Header Section */}
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <LanIcon color="primary" fontSize="large" />
              {t('agents.title')}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {t('agents.subtitle')}
            </Typography>
          </Box>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setDialogOpen(true)}
          >
            {t('agents.register')}
          </Button>
        </Stack>

        <Alert severity="info" variant="outlined">
          {t('agents.pageFunctionHelp')}
        </Alert>

        {/* Error Alert */}
        {error && (
          <Alert severity="error" data-testid="agent-list-error">
            {error}
          </Alert>
        )}

        {/* Search and Filter Section */}
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 2 }}>
          <TextField
            label={t('agents.searchLabel')}
            value={searchName}
            onChange={(e) => setSearchName(e.target.value)}
            fullWidth
            variant="outlined"
            size="small"
            placeholder={t('agents.searchPlaceholder')}
          />
          <FormControl sx={{ minWidth: { xs: "100%", md: 200 } }} size="small">
            <InputLabel id="agent-status-filter-label">{t('agents.statusFilter')}</InputLabel>
            <Select
              labelId="agent-status-filter-label"
              value={filterStatus}
              label={t('agents.statusFilter')}
              onChange={(e) => setFilterStatus(e.target.value as AgentStatus | 'all')}
            >
              <MenuItem value="all">{t('agents.allStatuses')}</MenuItem>
              <MenuItem value="idle">{t('agents.status.idle')}</MenuItem>
              <MenuItem value="active">{t('agents.status.active')}</MenuItem>
              <MenuItem value="busy">{t('agents.status.busy')}</MenuItem>
              <MenuItem value="offline">{t('agents.status.offline')}</MenuItem>
              <MenuItem value="handshake_failed">{t('agents.status.handshakeFailed')}</MenuItem>
              <MenuItem value="audit_failed">{t('agents.status.auditFailed')}</MenuItem>
              <MenuItem value="invocation_blocked">{t('agents.status.invocationBlocked')}</MenuItem>
            </Select>
          </FormControl>
          <FormControl sx={{ minWidth: { xs: "100%", md: 200 } }} size="small">
            <InputLabel id="agent-role-filter-label">{t('agents.roleFilter')}</InputLabel>
            <Select
              labelId="agent-role-filter-label"
              value={filterRole}
              label={t('agents.roleFilter')}
              onChange={(e) => setFilterRole(e.target.value)}
            >
              <MenuItem value="all">{t('agents.allRoles')}</MenuItem>
              {uniqueRoles.map(role => (
                <MenuItem key={role} value={role}>{role}</MenuItem>
              ))}
            </Select>
          </FormControl>
          {(searchName || filterStatus !== 'all' || filterRole !== 'all') && (
            <Button
              variant="outlined"
              onClick={() => {
                setSearchName('');
                setFilterStatus('all');
                setFilterRole('all');
              }}
              sx={{ minWidth: { xs: "100%", md: 120 } }}
            >
              {t('agents.clearFilter')}
            </Button>
          )}
        </Stack>

        {/* Filter Results Summary */}
        {(searchName || filterStatus !== 'all' || filterRole !== 'all') && (
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('agents.foundCount', { count: filteredAgents.length, total: agents.length })}
          </Alert>
        )}

        {/* Asset Grid */}
        <Grid container spacing={3}>
          {filteredAgents.length === 0 ? (
            <Grid size={12}>
              <Box sx={{ textAlign: 'center', py: 8 }}>
                <Typography variant="h6" color="text.secondary">
                  {agents.length === 0 ? t('agents.noAgents') : t('agents.noMatchedAgents')}
                </Typography>
                {(searchName || filterStatus !== 'all' || filterRole !== 'all') && (
                  <Button
                    variant="outlined"
                    onClick={() => {
                      setSearchName('');
                      setFilterStatus('all');
                      setFilterRole('all');
                    }}
                    sx={{ mt: 2 }}
                  >
                    {t('agents.clearFilterConditions')}
                  </Button>
                )}
              </Box>
            </Grid>
          ) : (
            filteredAgents.map((agent) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={agent.agent_id}>
              <Card
                sx={{
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  '&:hover': { 
                    transform: 'translateY(-4px)',
                    boxShadow: 6
                  },
                  cursor: 'pointer',
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column'
                }}
                onClick={() => navigate(`/console/agents/${agent.agent_id}`)}
              >
                <CardHeader
                  avatar={<StatusDot status={agent.status} />}
                  action={<Typography variant="caption" color="text.secondary">v{agent.version}</Typography>}
                  title={<Typography variant="subtitle1" fontWeight="bold">{agent.agent_name}</Typography>}
                  subheader={<Typography variant="caption" color="text.secondary">ID: {agent.agent_id}</Typography>}
                />
                <CardContent sx={{ pt: 0, flexGrow: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                    <TrustLevelChip level={agent.trust_level} />
                    <Typography variant="caption" color="text.secondary">{agent.role_tag}</Typography>
                  </Box>
                  <Typography variant="body2" sx={{ mb: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {agent.function_description}
                  </Typography>
                  <Typography variant="body2" color="primary" sx={{ fontSize: '0.8rem', mb: 1 }}>
                    {t('agents.assignedGoal')}: {agent.assigned_goal || t('agents.none')}
                  </Typography>
                  <Typography variant="caption" display="block" color="text.secondary">
                    {t('agents.inbox')}: {agent.inbox.length} | {t('agents.receipts')}: {agent.receipts.length}
                  </Typography>
                  <Divider sx={{ my: 2 }} />
                  <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                     <Box>
                       <Typography variant="caption" display="block" color="text.secondary">{t('common.status')}</Typography>
                       <Typography variant="body2">{t(`agents.status.${agent.status === 'handshake_failed' ? 'handshakeFailed' : agent.status === 'audit_failed' ? 'auditFailed' : agent.status === 'invocation_blocked' ? 'invocationBlocked' : agent.status}`)}</Typography>
                     </Box>
                     <Box>
                       <Typography variant="caption" display="block" color="text.secondary">{t('agents.registeredAt')}</Typography>
                       <Typography variant="body2" sx={{ fontSize: '0.75rem' }}>
                         {new Date(agent.registered_at).toLocaleDateString()}
                       </Typography>
                     </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))
          )}
        </Grid>
      </Stack>

      {/* Registration Dialog */}
      <Dialog 
        open={isDialogOpen} 
        onClose={() => setDialogOpen(false)} 
        maxWidth="sm" 
        fullWidth
      >
        <DialogTitle sx={{ fontWeight: 'bold' }}>{t('agents.dialogTitle')}</DialogTitle>
        <DialogContent>
          <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 4 }}>
            {[t('agents.stepProfile'), t('agents.stepSecurity'), t('agents.stepHandshake')].map((label) => (
              <Step key={label}><StepLabel>{label}</StepLabel></Step>
            ))}
          </Stepper>

          {activeStep === 0 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 2 }}>
              <Alert severity="info" variant="outlined">
                {t('agents.stepProfileHelp')}
              </Alert>
              <TextField 
                label={t('agents.techName')} 
                fullWidth 
                variant="outlined" 
                helperText={t('agents.techNameHelp')}
                value={regData.name} 
                onChange={(e) => setRegData({ ...regData, name: e.target.value })}
              />
              <TextField 
                label={t('agents.humanName')} 
                fullWidth 
                variant="outlined" 
                helperText={t('agents.humanNameHelp')}
                value={regData.agent_name} 
                onChange={(e) => setRegData({ ...regData, agent_name: e.target.value })}
                required
              />
              <TextField 
                label={t('agents.version')} 
                fullWidth 
                variant="outlined" 
                helperText={t('agents.versionHelp')}
                value={regData.version} 
                onChange={(e) => setRegData({ ...regData, version: e.target.value })}
                required
              />
              <TextField 
                label={t('agents.funcDesc')} 
                fullWidth 
                multiline 
                rows={2} 
                variant="outlined" 
                helperText={t('agents.funcDescHelp')}
                value={regData.function_description} 
                onChange={(e) => setRegData({ ...regData, function_description: e.target.value })}
                required
              />
            </Box>
          )}

          {activeStep === 1 && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 2 }}>
              <Alert severity="info" variant="outlined">
                {t('agents.stepSecurityHelp')}
              </Alert>
              <TextField 
                label={t('agents.endpoint')} 
                fullWidth 
                variant="outlined" 
                helperText={t('agents.endpointHelp')}
                value={regData.endpoint} 
                onChange={(e) => setRegData({ ...regData, endpoint: e.target.value })}
              />
              <TextField 
                label={t('agents.authToken')} 
                fullWidth 
                variant="outlined" 
                type="password" 
                helperText={t('agents.authTokenHelp')}
                value={regData.auth_token} 
                onChange={(e) => setRegData({ ...regData, auth_token: e.target.value })}
              />
              <TextField
                label={t('agents.roleTag')}
                fullWidth
                variant="outlined"
                helperText={t('agents.roleTagHelp')}
                value={regData.role_tag}
                onChange={(e) => setRegData({ ...regData, role_tag: e.target.value })}
              />
              <TextField
                label={t('agents.scope')}
                fullWidth
                variant="outlined"
                helperText={t('agents.scopeHelp')}
                value={regData.scope}
                onChange={(e) => setRegData({ ...regData, scope: e.target.value })}
              />
            </Box>
          )}

          {activeStep === 2 && (
            <Box sx={{ mt: 2 }}>
                <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
                  {t('agents.stepHandshakeHelp')}
                </Alert>
                <Alert severity="warning" sx={{ mb: 2 }}>
                  {t('agents.auditWarning')}
                </Alert>
                <Typography variant="body2" color="text.secondary">
                  {t('agents.handshakeInfo')}
                </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
          {activeStep > 0 && <Button onClick={() => setActiveStep(activeStep - 1)}>{t('common.back')}</Button>}
          <Button 
            onClick={activeStep === 2 ? handleRegister : () => setActiveStep(activeStep + 1)} 
            variant="contained"
            disabled={activeStep === 0 && (!regData.agent_name || !regData.version || !regData.function_description)}
          >
            {activeStep === 2 ? t('agents.finalize') : t('common.continue')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AgentAssetManager;
