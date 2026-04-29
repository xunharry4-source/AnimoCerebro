/**
 * AI Supervision Dashboard Component
 * 
 * Real-time monitoring dashboard for AI execution supervision.
 * Displays supervision status, active alerts, execution records, and provides
 * intervention capabilities.
 */

import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  AlertTriangle, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Shield, 
  Eye,
  RefreshCw,
  Filter,
  UserCheck
} from 'lucide-react';

interface SupervisionStatus {
  level: string;
  total_executions: number;
  running: number;
  completed: number;
  failed: number;
  interventions_required: number;
  active_alerts: number;
}

interface SupervisionAlert {
  alert_id: string;
  timestamp: string;
  severity: string;
  category: string;
  message: string;
  execution_record_id?: string;
  task_id?: string;
  recommended_action: string;
  acknowledged: boolean;
  resolved: boolean;
}

interface ExecutionRecord {
  record_id: string;
  task_id?: string;
  action_type: string;
  start_time: string;
  end_time?: string;
  status: string;
  verification_results: Record<string, string>;
  intervention_required: boolean;
  human_approved: boolean;
  supervisor_notes: string[];
}

const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string; size?: string }> = ({
  children,
  variant: _variant,
  size: _size,
  className,
  ...props
}) => <button type="button" className={className} {...props}>{children}</button>;

const Card: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ children, className, ...props }) => (
  <div className={className} {...props}>{children}</div>
);
const CardHeader = Card;
const CardContent = Card;
const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ children, className, ...props }) => (
  <h3 className={className} {...props}>{children}</h3>
);
const Badge: React.FC<React.HTMLAttributes<HTMLSpanElement> & { variant?: string }> = ({
  children,
  variant: _variant,
  className,
  ...props
}) => <span className={className} {...props}>{children}</span>;
const Alert: React.FC<React.HTMLAttributes<HTMLDivElement> & { variant?: string }> = ({
  children,
  variant: _variant,
  className,
  ...props
}) => <div className={className} role="status" {...props}>{children}</div>;
const AlertTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ children, className, ...props }) => (
  <h4 className={className} {...props}>{children}</h4>
);
const AlertDescription = Card;
const Tabs: React.FC<React.HTMLAttributes<HTMLDivElement> & { defaultValue?: string }> = ({
  children,
  defaultValue: _defaultValue,
  className,
  ...props
}) => <div className={className} {...props}>{children}</div>;
const TabsList = Card;
const TabsTrigger: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }> = ({
  children,
  value: _value,
  className,
  ...props
}) => <button type="button" className={className} {...props}>{children}</button>;
const TabsContent: React.FC<React.HTMLAttributes<HTMLDivElement> & { value: string }> = ({
  children,
  value: _value,
  className,
  ...props
}) => <div className={className} {...props}>{children}</div>;
const Select: React.FC<React.HTMLAttributes<HTMLDivElement> & { value?: string; onValueChange?: (value: string) => void }> = ({
  children,
  value: _value,
  onValueChange: _onValueChange,
  ...props
}) => <div {...props}>{children}</div>;
const SelectTrigger = Card;
const SelectValue: React.FC<{ placeholder?: string }> = ({ placeholder }) => <span>{placeholder}</span>;
const SelectContent = Card;
const SelectItem: React.FC<React.HTMLAttributes<HTMLDivElement> & { value: string }> = ({
  children,
  value: _value,
  ...props
}) => <div {...props}>{children}</div>;
const Table: React.FC<React.TableHTMLAttributes<HTMLTableElement>> = ({ children, ...props }) => <table {...props}>{children}</table>;
const TableHeader: React.FC<React.HTMLAttributes<HTMLTableSectionElement>> = ({ children, ...props }) => <thead {...props}>{children}</thead>;
const TableBody: React.FC<React.HTMLAttributes<HTMLTableSectionElement>> = ({ children, ...props }) => <tbody {...props}>{children}</tbody>;
const TableRow: React.FC<React.HTMLAttributes<HTMLTableRowElement>> = ({ children, ...props }) => <tr {...props}>{children}</tr>;
const TableHead: React.FC<React.ThHTMLAttributes<HTMLTableCellElement>> = ({ children, ...props }) => <th {...props}>{children}</th>;
const TableCell: React.FC<React.TdHTMLAttributes<HTMLTableCellElement>> = ({ children, ...props }) => <td {...props}>{children}</td>;
const Dialog: React.FC<React.HTMLAttributes<HTMLDivElement> & { open: boolean; onOpenChange?: (open: boolean) => void }> = ({
  children,
  open,
  onOpenChange: _onOpenChange,
  ...props
}) => (open ? <div role="dialog" {...props}>{children}</div> : null);
const DialogContent = Card;
const DialogHeader = Card;
const DialogTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({ children, ...props }) => <h2 {...props}>{children}</h2>;
const Label: React.FC<React.LabelHTMLAttributes<HTMLLabelElement>> = ({ children, ...props }) => <label {...props}>{children}</label>;
const Textarea: React.FC<React.TextareaHTMLAttributes<HTMLTextAreaElement>> = (props) => <textarea {...props} />;

const AISupervisionDashboard: React.FC = () => {
  const [status, setStatus] = useState<SupervisionStatus | null>(null);
  const [alerts, setAlerts] = useState<SupervisionAlert[]>([]);
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [interventionDialog, setInterventionDialog] = useState<{
    open: boolean;
    taskId?: string;
    recordId?: string;
  }>({ open: false });
  const [interventionForm, setInterventionForm] = useState({
    action: 'approve',
    reason: '',
    operator_id: 'human-supervisor'
  });

  // Fetch supervision status
  const fetchStatus = async () => {
    try {
      const response = await fetch('/api/supervision/status');
      const data = await response.json();
      setStatus(data);
    } catch (error) {
      console.error('Failed to fetch supervision status:', error);
    }
  };

  // Fetch active alerts
  const fetchAlerts = async () => {
    try {
      const url = selectedSeverity === 'all' 
        ? '/api/supervision/alerts'
        : `/api/supervision/alerts?severity=${selectedSeverity}`;
      
      const response = await fetch(url);
      const data = await response.json();
      setAlerts(data);
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
    }
  };

  // Fetch execution records
  const fetchExecutions = async () => {
    try {
      const response = await fetch('/api/supervision/executions?limit=50');
      const data = await response.json();
      setExecutions(data);
    } catch (error) {
      console.error('Failed to fetch executions:', error);
    }
  };

  // Load all data
  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchAlerts(), fetchExecutions()]);
    setLoading(false);
  };

  // Initial load
  useEffect(() => {
    loadData();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [selectedSeverity]);

  // Acknowledge alert
  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      await fetch(`/api/supervision/alerts/${alertId}/acknowledge`, {
        method: 'POST'
      });
      await fetchAlerts();
    } catch (error) {
      console.error('Failed to acknowledge alert:', error);
    }
  };

  // Submit intervention
  const handleSubmitIntervention = async () => {
    if (!interventionForm.reason.trim()) {
      alert('Please provide a reason for intervention');
      return;
    }

    try {
      await fetch('/api/supervision/intervention', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: interventionDialog.taskId,
          action: interventionForm.action,
          reason: interventionForm.reason,
          operator_id: interventionForm.operator_id
        })
      });
      
      setInterventionDialog({ open: false });
      setInterventionForm({ action: 'approve', reason: '', operator_id: 'human-supervisor' });
      await loadData();
    } catch (error) {
      console.error('Failed to submit intervention:', error);
      alert('Failed to submit intervention');
    }
  };

  // Get severity color
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'medium': return 'bg-yellow-500';
      case 'low': return 'bg-blue-500';
      default: return 'bg-gray-500';
    }
  };

  // Get status icon
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed': return <XCircle className="h-4 w-4 text-red-500" />;
      case 'running': return <Activity className="h-4 w-4 text-blue-500" />;
      default: return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  if (loading && !status) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">AI Supervision Dashboard</h1>
          <p className="text-muted-foreground">
            Monitor and manage AI execution supervision
          </p>
        </div>
        <Button onClick={loadData} variant="outline" size="sm">
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Status Cards */}
      {status && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Supervision Level</CardTitle>
              <Shield className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold capitalize">{status.level}</div>
              <p className="text-xs text-muted-foreground">
                Current oversight intensity
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Executions</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{status.running}</div>
              <p className="text-xs text-muted-foreground">
                Currently running
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Interventions Required</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-orange-500">
                {status.interventions_required}
              </div>
              <p className="text-xs text-muted-foreground">
                Awaiting human approval
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Alerts</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-500">
                {status.active_alerts}
              </div>
              <p className="text-xs text-muted-foreground">
                Require attention
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Content Tabs */}
      <Tabs defaultValue="alerts" className="space-y-4">
        <TabsList>
          <TabsTrigger value="alerts">
            <AlertTriangle className="mr-2 h-4 w-4" />
            Active Alerts ({alerts.length})
          </TabsTrigger>
          <TabsTrigger value="executions">
            <Eye className="mr-2 h-4 w-4" />
            Execution Records
          </TabsTrigger>
        </TabsList>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Active Alerts</h2>
            <div className="flex items-center space-x-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select value={selectedSeverity} onValueChange={setSelectedSeverity}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Filter by severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Severities</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {alerts.length === 0 ? (
            <Alert>
              <CheckCircle className="h-4 w-4" />
              <AlertTitle>All Clear</AlertTitle>
              <AlertDescription>
                No active alerts requiring attention.
              </AlertDescription>
            </Alert>
          ) : (
            <div className="space-y-4">
              {alerts.map((alert) => (
                <Alert key={alert.alert_id} variant={
                  alert.severity === 'critical' ? 'destructive' : 'default'
                }>
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <Badge className={getSeverityColor(alert.severity)}>
                          {alert.severity.toUpperCase()}
                        </Badge>
                        <span className="text-sm text-muted-foreground">
                          {new Date(alert.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <AlertTitle>{alert.message}</AlertTitle>
                      <AlertDescription className="mt-2">
                        <div className="space-y-1">
                          {alert.task_id && (
                            <p><strong>Task:</strong> {alert.task_id}</p>
                          )}
                          {alert.execution_record_id && (
                            <p><strong>Record:</strong> {alert.execution_record_id}</p>
                          )}
                          <p><strong>Recommended Action:</strong> {alert.recommended_action}</p>
                        </div>
                      </AlertDescription>
                    </div>
                    <div className="flex space-x-2 ml-4">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleAcknowledgeAlert(alert.alert_id)}
                      >
                        <UserCheck className="mr-2 h-4 w-4" />
                        Acknowledge
                      </Button>
                      {alert.task_id && (
                        <Button
                          size="sm"
                          onClick={() => setInterventionDialog({
                            open: true,
                            taskId: alert.task_id,
                            recordId: alert.execution_record_id
                          })}
                        >
                          Intervene
                        </Button>
                      )}
                    </div>
                  </div>
                </Alert>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Executions Tab */}
        <TabsContent value="executions">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">Execution Records</h2>
            <Button onClick={fetchExecutions} variant="outline" size="sm">
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </div>

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Task ID</TableHead>
                  <TableHead>Action Type</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Verification</TableHead>
                  <TableHead>Intervention</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {executions.map((record) => (
                  <TableRow key={record.record_id}>
                    <TableCell>
                      <div className="flex items-center">
                        {getStatusIcon(record.status)}
                        <span className="ml-2 capitalize">{record.status}</span>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {record.task_id || 'N/A'}
                    </TableCell>
                    <TableCell>{record.action_type}</TableCell>
                    <TableCell className="text-sm">
                      {new Date(record.start_time).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(record.verification_results).map(([rule, result]) => (
                          <Badge
                            key={rule}
                            variant={result === 'passed' ? 'default' : 'destructive'}
                            className="text-xs"
                          >
                            {rule.split('_').pop()}: {result}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      {record.intervention_required ? (
                        <Badge variant={record.human_approved ? 'default' : 'destructive'}>
                          {record.human_approved ? 'Approved' : 'Required'}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">Not required</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {record.intervention_required && !record.human_approved && (
                        <Button
                          size="sm"
                          onClick={() => setInterventionDialog({
                            open: true,
                            taskId: record.task_id,
                            recordId: record.record_id
                          })}
                        >
                          Review
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>

      {/* Intervention Dialog */}
      <Dialog open={interventionDialog.open} onOpenChange={(open) => 
        setInterventionDialog({ ...interventionDialog, open })
      }>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Human Intervention</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-4">
            <div>
              <Label>Task ID</Label>
              <div className="mt-1 font-mono text-sm bg-muted p-2 rounded">
                {interventionDialog.taskId}
              </div>
            </div>

            <div>
              <Label>Action</Label>
              <Select
                value={interventionForm.action}
                onValueChange={(value) => setInterventionForm({
                  ...interventionForm,
                  action: value
                })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="approve">Approve</SelectItem>
                  <SelectItem value="reject">Reject</SelectItem>
                  <SelectItem value="pause">Pause</SelectItem>
                  <SelectItem value="resume">Resume</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label>Operator ID</Label>
              <input
                type="text"
                value={interventionForm.operator_id}
                onChange={(e) => setInterventionForm({
                  ...interventionForm,
                  operator_id: e.target.value
                })}
                className="mt-1 w-full px-3 py-2 border rounded-md"
              />
            </div>

            <div>
              <Label>Reason for Intervention *</Label>
              <Textarea
                value={interventionForm.reason}
                onChange={(e) => setInterventionForm({
                  ...interventionForm,
                  reason: e.target.value
                })}
                placeholder="Provide detailed reason for this intervention..."
                className="mt-1"
                rows={4}
              />
            </div>

            <div className="flex justify-end space-x-2">
              <Button
                variant="outline"
                onClick={() => setInterventionDialog({ open: false })}
              >
                Cancel
              </Button>
              <Button onClick={handleSubmitIntervention}>
                Submit Intervention
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AISupervisionDashboard;
