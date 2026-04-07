import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Checkbox,
  Divider,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import AddIcon from "@mui/icons-material/Add";

type CliToolItem = {
  command_name: string;
  description: string;
  mapped_domain: "cognitive" | "execution";
  plugin_id: string;
  feature_code: string;
  execution_domain?: string | null;
  read_only: boolean;
  side_effect_free: boolean;
  mutates_state: boolean;
  requires_cloud_audit: boolean;
  status: "active" | "degraded" | "revoked";
};

export default function CliAssetManager() {
  const [rows, setRows] = useState<CliToolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openRegister, setOpenRegister] = useState(false);
  const [selectedTool, setSelectedTool] = useState<CliToolItem | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    tool_name: "",
    command_executable: "",
    description: "",
    read_only_flag: true,
    project_path: "",
    project_name: "",
    project_description: "",
    help_doc_url: "",
  });
  const [testData, setTestData] = useState({
    arguments: "",
    stdin_input: "",
    working_directory: "",
  });

  useEffect(() => {
    void loadTools();
  }, []);

  const loadTools = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/web/cli-tools");
      if (!response.ok) {
        throw new Error(`获取 CLI 工具失败 (HTTP ${response.status})`);
      }
      const payload = (await response.json()) as CliToolItem[];
      setRows(payload);
    } catch (err: any) {
      setError(err?.message || "获取 CLI 工具失败");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    try {
      const response = await fetch("/api/web/cli-tools/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      if (!response.ok) {
        const detail = await response.json();
        throw new Error(detail?.detail || "注册失败");
      }
      setOpenRegister(false);
      setFormData({
        tool_name: "",
        command_executable: "",
        description: "",
        read_only_flag: true,
        project_path: "",
        project_name: "",
        project_description: "",
        help_doc_url: "",
      });
      void loadTools();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleTestCall = async () => {
    if (!selectedTool) return;
    setTestResult(null);
    try {
      const response = await fetch(`/api/web/cli-tools/${selectedTool.command_name}/test-call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          arguments: testData.arguments
            .split(" ")
            .map((item) => item.trim())
            .filter(Boolean),
          stdin_input: testData.stdin_input || null,
          working_directory: testData.working_directory || null,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || "测试调用失败");
      }
      setTestResult(JSON.stringify(payload, null, 2));
    } catch (err: any) {
      setTestResult(err?.message || "测试调用失败");
    }
  };

  const columns: GridColDef[] = [
    { field: "command_name", headerName: "工具名称", flex: 1, minWidth: 150 },
    {
      field: "mapped_domain",
      headerName: "域权限",
      flex: 1,
      minWidth: 150,
      renderCell: (params) => (
        <Chip
          label={params.value === "cognitive" ? "认知辅助" : "物理执行"}
          color={params.value === "cognitive" ? "primary" : "error"}
          size="small"
        />
      ),
    },
    {
      field: "status",
      headerName: "运行状态",
      flex: 1,
      minWidth: 120,
      renderCell: (params) => (
        <Chip
          label={params.value}
          color={params.value === "active" ? "success" : "warning"}
          size="small"
          variant="outlined"
        />
      ),
    },
    { field: "feature_code", headerName: "特征码", flex: 1.5, minWidth: 250 },
    {
      field: "actions",
      headerName: "操作",
      minWidth: 120,
      sortable: false,
      renderCell: (params) => (
        <Button size="small" onClick={() => setSelectedTool(params.row as CliToolItem)}>
          测试调用
        </Button>
      ),
    },
  ];

  if (loading) return <CircularProgress sx={{ m: 4 }} />;

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            CLI 工具集资产管理
          </Typography>
          <Typography variant="body2" color="text.secondary">
            基于“认知与执行彻底分离”原则管理的外部命令行工具资产。
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpenRegister(true)}>
          注册新工具
        </Button>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <DataGrid
        autoHeight
        rows={rows.map((r, i) => ({ id: r.plugin_id || i, ...r }))}
        columns={columns}
        sx={{ bgcolor: "background.paper" }}
      />

      <Dialog open={openRegister} onClose={() => setOpenRegister(false)} fullWidth maxWidth="sm">
        <DialogTitle>注册新 CLI 工具</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <TextField
              label="工具名称 (tool_name)"
              fullWidth
              value={formData.tool_name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, tool_name: e.target.value })}
            />
            <TextField
              label="执行命令 (command_executable)"
              fullWidth
              placeholder="如 git, curl, /usr/bin/python3"
              value={formData.command_executable}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, command_executable: e.target.value })}
            />
            <TextField
              label="功能说明 (description)"
              fullWidth
              multiline
              rows={2}
              value={formData.description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, description: e.target.value })}
            />
            <TextField
              label="项目路径 (project_path)"
              fullWidth
              value={formData.project_path}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, project_path: e.target.value })}
            />
            <TextField
              label="项目名称 (project_name)"
              fullWidth
              value={formData.project_name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, project_name: e.target.value })}
            />
            <TextField
              label="项目说明 (project_description)"
              fullWidth
              multiline
              rows={2}
              value={formData.project_description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFormData({ ...formData, project_description: e.target.value })
              }
            />
            <TextField
              label="帮助文档地址 (help_doc_url)"
              fullWidth
              value={formData.help_doc_url}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, help_doc_url: e.target.value })}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={formData.read_only_flag}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData({ ...formData, read_only_flag: e.target.checked })}
                />
              }
              label="只读命令 (read_only_flag)"
            />
            <Alert severity="info" variant="outlined">
              {formData.read_only_flag 
                ? "【认知辅助】仅限只读操作，系统将禁止任何状态修改。" 
                : "【物理执行】具备副作用的操作，将受 SafetyGate 审查与 CloudAudit 审计。"}
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenRegister(false)}>取消</Button>
          <Button variant="contained" onClick={handleRegister} disabled={!formData.tool_name || !formData.command_executable}>
            确认注册
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(selectedTool)} onClose={() => setSelectedTool(null)} fullWidth maxWidth="md">
        <DialogTitle>测试 CLI 工具调用</DialogTitle>
        <DialogContent dividers>
          {selectedTool ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="subtitle1">{selectedTool.command_name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {selectedTool.description}
              </Typography>
              <Divider />
              <TextField
                label="参数 (空格分隔)"
                fullWidth
                value={testData.arguments}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestData({ ...testData, arguments: e.target.value })}
              />
              <TextField
                label="stdin 输入"
                fullWidth
                multiline
                rows={3}
                value={testData.stdin_input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTestData({ ...testData, stdin_input: e.target.value })}
              />
              <TextField
                label="工作目录"
                fullWidth
                value={testData.working_directory}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setTestData({ ...testData, working_directory: e.target.value })
                }
              />
              {testResult ? (
                <Alert severity="info">
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{testResult}</pre>
                </Alert>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedTool(null)}>关闭</Button>
          <Button variant="contained" onClick={() => void handleTestCall()} disabled={!selectedTool}>
            执行测试
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
