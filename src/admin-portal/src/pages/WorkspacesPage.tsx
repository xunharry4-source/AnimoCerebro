import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  CircularProgress,
  IconButton,
  Chip,
} from "@mui/material";
import { Edit, Delete, Star, StarOutline } from "@mui/icons-material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspaces } from "../hooks/useWorkspaces";
import { WorkspaceConfig } from "../api/workspacesApi";

export default function WorkspacesPage() {
  const { t } = useTranslation();
  const {
    workspaces,
    currentWorkspaceId,
    loading,
    error,
    fetchWorkspaces,
    addWorkspace,
    updateWorkspace,
    deleteWorkspace,
    setDefaultWorkspace,
    selectWorkspace,
  } = useWorkspaces();

  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingWorkspace, setEditingWorkspace] = useState<WorkspaceConfig | null>(null);
  const [formData, setFormData] = useState<Omit<WorkspaceConfig, "id" | "created_at" | "updated_at">>({
    name: "",
    path: "",
    description: "",
    is_default: false,
    role: "",
    role_description: "",
    forbidden_actions: "",
    task_goals: "",
  });
  const [taskGoals, setTaskGoals] = useState<string[]>([]);
  const [newTaskGoal, setNewTaskGoal] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  const handleOpenDialog = (workspace: WorkspaceConfig | null = null) => {
    if (workspace) {
      setEditingWorkspace(workspace);
      setFormData({
        name: workspace.name,
        path: workspace.path,
        description: workspace.description || "",
        is_default: workspace.is_default || false,
        role: workspace.role || "",
        role_description: workspace.role_description || "",
        forbidden_actions: workspace.forbidden_actions || "",
        task_goals: workspace.task_goals || "",
      });
      // Parse task goals from JSON
      try {
        const goals = workspace.task_goals ? JSON.parse(workspace.task_goals) : [];
        setTaskGoals(Array.isArray(goals) ? goals : []);
      } catch {
        setTaskGoals([]);
      }
    } else {
      setEditingWorkspace(null);
      setFormData({
        name: "",
        path: "",
        description: "",
        is_default: false,
        role: "",
        role_description: "",
        forbidden_actions: "",
        task_goals: "",
      });
      setTaskGoals([]);
    }
    setNewTaskGoal("");
    setSubmitError(null);
    setIsDialogOpen(true);
  };

  const handleCloseDialog = () => {
    setIsDialogOpen(false);
    setEditingWorkspace(null);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const submitData = {
        ...formData,
        task_goals: taskGoals.length > 0 ? JSON.stringify(taskGoals) : undefined,
      };
      if (editingWorkspace?.id) {
        await updateWorkspace(editingWorkspace.id, submitData);
      } else {
        await addWorkspace(submitData);
      }
      handleCloseDialog();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddTaskGoal = () => {
    if (newTaskGoal.trim()) {
      setTaskGoals([...taskGoals, newTaskGoal.trim()]);
      setNewTaskGoal("");
    }
  };

  const handleRemoveTaskGoal = (index: number) => {
    setTaskGoals(taskGoals.filter((_, i) => i !== index));
  };

  const handleDelete = async (id: number) => {
    if (window.confirm(t("workspaces.confirmDelete"))) {
      try {
        await deleteWorkspace(id);
      } catch (err) {
        alert(err instanceof Error ? err.message : "Delete failed");
      }
    }
  };

  const handleSetDefault = async (id: number) => {
    try {
      await setDefaultWorkspace(id);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to set default");
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="h5" className="text-xl font-bold">
              {t("workspaces.title")}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {t("workspaces.subtitle")}
            </Typography>
          </Box>
          <Button
            variant="contained"
            onClick={() => handleOpenDialog(null)}
            disabled={loading}
          >
            {t("workspaces.addButton")}
          </Button>
        </Stack>

        {error && <Alert severity="error">{error}</Alert>}

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
            <CircularProgress />
          </Box>
        ) : workspaces.length === 0 ? (
          <Card>
            <CardContent>
              <Typography color="textSecondary">{t("workspaces.noWorkspaces")}</Typography>
            </CardContent>
          </Card>
        ) : (
          <TableContainer component={Card}>
            <Table>
              <TableHead>
                <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                  <TableCell>{t("workspaces.name")}</TableCell>
                  <TableCell>{t("workspaces.path")}</TableCell>
                  <TableCell>{t("workspaces.description")}</TableCell>
                  <TableCell>{t("workspaces.role")}</TableCell>
                  <TableCell align="center">{t("workspaces.makesDefault")}</TableCell>
                  <TableCell align="right">{t("common.actions")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {workspaces.map((workspace) => (
                  <TableRow
                    key={workspace.id}
                    sx={{
                      backgroundColor: workspace.id === currentWorkspaceId ? "#e3f2fd" : "transparent",
                      "&:hover": { backgroundColor: "#fafafa" },
                    }}
                  >
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <span>{workspace.name}</span>
                        {workspace.is_default && (
                          <Chip label={t("workspaces.default")} size="small" />
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {workspace.path}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {workspace.description || "-"}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {workspace.role ? (
                        <Chip label={workspace.role} size="small" color="primary" />
                      ) : (
                        <Typography variant="body2" color="textSecondary">-</Typography>
                      )}
                    </TableCell>
                    <TableCell align="center">
                      <IconButton
                        size="small"
                        onClick={() => handleSetDefault(workspace.id!)}
                        disabled={workspace.is_default}
                      >
                        {workspace.is_default ? <Star /> : <StarOutline />}
                      </IconButton>
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} justifyContent="flex-end">
                        <IconButton
                          size="small"
                          onClick={() => handleOpenDialog(workspace)}
                        >
                          <Edit fontSize="small" />
                        </IconButton>
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleDelete(workspace.id!)}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Stack>

      {/* Add/Edit Dialog */}
      <Dialog open={isDialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingWorkspace ? t("workspaces.editWorkspace") : t("workspaces.addButton")}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Stack spacing={2}>
            {submitError && <Alert severity="error">{submitError}</Alert>}
            <TextField
              label={t("workspaces.name")}
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              fullWidth
              disabled={submitting}
            />
            <TextField
              label={t("workspaces.path")}
              value={formData.path}
              onChange={(e) => setFormData({ ...formData, path: e.target.value })}
              fullWidth
              disabled={submitting}
              placeholder="/home/user/projects/project-name"
            />
            <TextField
              label={t("workspaces.description")}
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              fullWidth
              multiline
              rows={3}
              disabled={submitting}
            />
            <TextField
              label={t("workspaces.role")}
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              fullWidth
              disabled={submitting}
              placeholder="e.g., Backend Developer, DevOps Engineer"
            />
            <TextField
              label={t("workspaces.roleDescription")}
              value={formData.role_description}
              onChange={(e) => setFormData({ ...formData, role_description: e.target.value })}
              fullWidth
              multiline
              rows={4}
              disabled={submitting}
              placeholder="Describe the responsibilities, expertise, and goals for this role in this workspace..."
            />
            <TextField
              label={t("workspaces.forbiddenActions")}
              value={formData.forbidden_actions}
              onChange={(e) => setFormData({ ...formData, forbidden_actions: e.target.value })}
              fullWidth
              multiline
              rows={3}
              disabled={submitting}
              placeholder="What should NOT be done in this workspace? (e.g., Delete production data, Access restricted files)"
            />
            {/* Task Goals Section */}
            <Box sx={{ pt: 2, borderTop: "1px solid #eee" }}>
              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: "bold" }}>
                {t("workspaces.taskGoals")}
              </Typography>
              <Stack spacing={2}>
                {/* Add new goal input */}
                <Stack direction="row" spacing={1}>
                  <TextField
                    size="small"
                    value={newTaskGoal}
                    onChange={(e) => setNewTaskGoal(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === "Enter") {
                        handleAddTaskGoal();
                      }
                    }}
                    disabled={submitting}
                    placeholder="Enter a task goal..."
                    fullWidth
                  />
                  <Button
                    variant="outlined"
                    onClick={handleAddTaskGoal}
                    disabled={!newTaskGoal.trim() || submitting}
                  >
                    {t("common.add")}
                  </Button>
                </Stack>
                {/* Display goals list */}
                {taskGoals.length > 0 && (
                  <Box>
                    <Stack spacing={1}>
                      {taskGoals.map((goal, index) => (
                        <Box
                          key={index}
                          sx={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            p: 1,
                            backgroundColor: "#f5f5f5",
                            borderRadius: 1,
                          }}
                        >
                          <Typography variant="body2">{goal}</Typography>
                          <Button
                            size="small"
                            color="error"
                            onClick={() => handleRemoveTaskGoal(index)}
                            disabled={submitting}
                          >
                            {t("common.remove")}
                          </Button>
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                )}
              </Stack>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog} disabled={submitting}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={submitting || !formData.name || !formData.path}
          >
            {submitting ? <CircularProgress size={24} /> : t("common.submit")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
