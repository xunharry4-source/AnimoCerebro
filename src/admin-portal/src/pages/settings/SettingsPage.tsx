import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
  type SelectChangeEvent,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import SaveIcon from "@mui/icons-material/Save";
import { useEffect, useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { WorkspaceConfig } from "../../api/workspacesApi";
import {
  fetchSystemIdentity,
  resetSystemIdentity,
  updateSystemIdentity,
} from "../../api/systemIdentityApi";
import { useWorkspaces } from "../../hooks/useWorkspaces";
import { fetchNineQuestionInference } from "../nine-questions/nineQuestionsApi";

type SettingsForm = {
  description: string;
  forbidden_actions: string[];
  task_goals: string[];
};

type IdentityForm = {
  role_name: string;
  mission: string;
  core_values: string;
};

const emptyForm: SettingsForm = {
  description: "",
  forbidden_actions: [],
  task_goals: [],
};

const emptyIdentityForm: IdentityForm = {
  role_name: "",
  mission: "",
  core_values: "",
};

export function formatTaskGoalsForEditor(taskGoals?: string | null): string {
  return formatTaskGoalsForList(taskGoals).join("\n");
}

export function formatTaskGoalsForList(taskGoals?: string | null): string[] {
  if (!taskGoals) {
    return [];
  }

  try {
    const parsed = JSON.parse(taskGoals);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => String(item).trim()).filter(Boolean);
    }
  } catch {
    // Stored values are normally JSON, but older/manual values may be newline text.
  }

  return taskGoals
    .split(/\r?\n/)
    .map((goal) => goal.replace(/^\s*(?:[-*]|\d+[.)])\s*/, "").trim())
    .filter(Boolean);
}

export function serializeTaskGoalsFromEditor(value: string): string | undefined {
  return serializeTaskGoalsFromList(formatTaskGoalsForList(value));
}

export function serializeTaskGoalsFromList(goals: string[]): string | undefined {
  const normalized = goals.map((goal) => goal.trim()).filter(Boolean);
  return normalized.length > 0 ? JSON.stringify(normalized) : undefined;
}

export function formatForbiddenActionsForEditor(forbiddenActions?: string | null): string[] {
  if (!forbiddenActions) {
    return [];
  }

  try {
    const parsed = JSON.parse(forbiddenActions);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => String(item).trim()).filter(Boolean);
    }
  } catch {
    // Stored values are normally newline-delimited plain text.
  }

  return forbiddenActions
    .split(/\r?\n/)
    .map((action) => action.replace(/^\s*(?:[-*]|\d+[.)])\s*/, "").trim())
    .filter(Boolean);
}

export function serializeForbiddenActionsFromEditor(actions: string[]): string | undefined {
  const normalized = actions.map((action) => action.trim()).filter(Boolean);
  return normalized.length > 0 ? normalized.join("\n") : undefined;
}

function formFromWorkspace(workspace: WorkspaceConfig | null): SettingsForm {
  if (!workspace) {
    return emptyForm;
  }

  return {
    description: workspace.description || "",
    forbidden_actions: formatForbiddenActionsForEditor(workspace.forbidden_actions),
    task_goals: formatTaskGoalsForList(workspace.task_goals),
  };
}

export default function SettingsPage() {
  const { t } = useTranslation();
  const {
    workspaces,
    loading,
    error,
    fetchWorkspaces,
    updateWorkspace,
    setDefaultWorkspace,
  } = useWorkspaces();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<number | "">("");
  const [form, setForm] = useState<SettingsForm>(emptyForm);
  const [newForbiddenAction, setNewForbiddenAction] = useState("");
  const [newTaskGoal, setNewTaskGoal] = useState("");
  const [identityForm, setIdentityForm] = useState<IdentityForm>(emptyIdentityForm);
  const [identityConfigured, setIdentityConfigured] = useState(false);
  const [identityDirty, setIdentityDirty] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [roleRecommendation, setRoleRecommendation] = useState<{
    active_role: string;
    mission: string;
    inferred_reference_role: string;
    role_alignment_gap: string;
  } | null>(null);
  const [roleRecommendationError, setRoleRecommendationError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void fetchWorkspaces();
    void fetchSystemIdentity()
      .then((identity) => {
        const hasUserConfiguredRole = Boolean(identity.user_configured);
        setIdentityForm({
          role_name: hasUserConfiguredRole ? identity.role_name || "" : "",
          mission: hasUserConfiguredRole ? identity.mission || "" : "",
          core_values: hasUserConfiguredRole
            ? (identity.core_values || []).join("\n")
            : "",
        });
        setIdentityConfigured(hasUserConfiguredRole);
        setIdentityDirty(false);
      })
      .catch((err) => {
        setSubmitError(err instanceof Error ? err.message : t("settings.identityLoadFailed"));
      });
    void fetchNineQuestionInference("q2")
      .then((inference) => {
        const roleProfile = inference?.role_profile;
        if (!roleProfile || typeof roleProfile !== "object") {
          setRoleRecommendation(null);
          return;
        }
        const inferredReferenceRole = String((roleProfile as Record<string, unknown>).inferred_reference_role || "").trim();
        if (!inferredReferenceRole) {
          setRoleRecommendation(null);
          return;
        }
        setRoleRecommendation({
          active_role: String((roleProfile as Record<string, unknown>).active_role || ""),
          mission: String(
            ((inference as Record<string, unknown>).mission_boundary as Record<string, unknown>)
              ?.current_mission || "",
          ),
          inferred_reference_role: inferredReferenceRole,
          role_alignment_gap: String((roleProfile as Record<string, unknown>).role_alignment_gap || ""),
        });
        setRoleRecommendationError(null);
      })
      .catch((err) => {
        setRoleRecommendation(null);
        setRoleRecommendationError(err instanceof Error ? err.message : "无法读取 Q2 系统推断参考角色");
      });
  }, [fetchWorkspaces]);

  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === selectedWorkspaceId) || null,
    [selectedWorkspaceId, workspaces],
  );

  useEffect(() => {
    if (selectedWorkspaceId !== "" || workspaces.length === 0) {
      return;
    }

    const defaultWorkspace = workspaces.find((workspace) => workspace.is_default) || workspaces[0];
    setSelectedWorkspaceId(defaultWorkspace.id || "");
  }, [selectedWorkspaceId, workspaces]);

  useEffect(() => {
    setForm(formFromWorkspace(selectedWorkspace));
    setNewForbiddenAction("");
    setNewTaskGoal("");
    setSubmitError(null);
    setSuccessMessage(null);
  }, [selectedWorkspace]);

  const handleWorkspaceChange = (event: SelectChangeEvent<number | "">) => {
    const value = event.target.value;
    setSelectedWorkspaceId(value === "" ? "" : Number(value));
  };

  const handleAddForbiddenAction = () => {
    const action = newForbiddenAction.trim();
    if (!action) {
      return;
    }
    setForm((current) => ({
      ...current,
      forbidden_actions: [...current.forbidden_actions, action],
    }));
    setNewForbiddenAction("");
  };

  const handleRemoveForbiddenAction = (index: number) => {
    setForm((current) => ({
      ...current,
      forbidden_actions: current.forbidden_actions.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const handleAddTaskGoal = () => {
    const goal = newTaskGoal.trim();
    if (!goal) {
      return;
    }
    setForm((current) => ({
      ...current,
      task_goals: [...current.task_goals, goal],
    }));
    setNewTaskGoal("");
  };

  const handleRemoveTaskGoal = (index: number) => {
    setForm((current) => ({
      ...current,
      task_goals: current.task_goals.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const handleSave = async () => {
    if (!selectedWorkspace?.id && !identityForm.role_name.trim()) {
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    setSuccessMessage(null);
    const identityRole = identityForm.role_name.trim();
    const shouldPersistIdentity = identityDirty && identityRole.length > 0;
    const shouldResetIdentity = !shouldPersistIdentity && identityConfigured;

    try {
      if (shouldPersistIdentity) {
        await updateSystemIdentity({
          role_name: identityRole,
          mission: identityForm.mission.trim(),
          core_values: identityForm.core_values
            .split(/\r?\n/)
            .map((item) => item.trim())
            .filter(Boolean),
        });
        setIdentityConfigured(true);
        setIdentityDirty(false);
      } else if (shouldResetIdentity) {
        await resetSystemIdentity();
        setIdentityConfigured(false);
        setIdentityDirty(false);
      }

      if (selectedWorkspace?.id) {
        const payload: Omit<WorkspaceConfig, "id" | "created_at" | "updated_at"> = {
          name: selectedWorkspace.name,
          path: selectedWorkspace.path,
          is_default: true,
          description: form.description || undefined,
          forbidden_actions: serializeForbiddenActionsFromEditor(form.forbidden_actions),
          task_goals: serializeTaskGoalsFromList(form.task_goals),
        };

        await updateWorkspace(selectedWorkspace.id, payload);
        if (!selectedWorkspace.is_default) {
          await setDefaultWorkspace(selectedWorkspace.id);
        }
        await fetchWorkspaces();
      }
      setSuccessMessage(t("settings.saveSuccess"));
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : t("settings.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700 }}>
              {t("settings.title")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t("settings.subtitle")}
            </Typography>
          </Box>
          <Button
            component={RouterLink}
            to="/console/workspaces"
            variant="outlined"
            sx={{ flexShrink: 0 }}
          >
            {t("settings.manageWorkspaces")}
          </Button>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}
        {submitError ? <Alert severity="error">{submitError}</Alert> : null}
        {successMessage ? <Alert severity="success">{successMessage}</Alert> : null}

        <Card>
          <CardContent>
            <Stack spacing={3}>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    {t("settings.roleSection")}
                  </Typography>
                  {identityForm.role_name.trim() ? <Chip size="small" color="warning" label="User Locked" /> : null}
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  {t("settings.roleSectionHelp")}
                </Typography>
              </Box>
              {roleRecommendation ? (
                <Alert
                  severity={
                    identityForm.role_name.trim() &&
                    roleRecommendation.inferred_reference_role !== identityForm.role_name.trim()
                      ? "warning"
                      : "info"
                  }
                >
                  <Stack spacing={1}>
                    <Typography variant="body2">
                      系统推断参考角色：{roleRecommendation.inferred_reference_role}
                    </Typography>
                    {roleRecommendation.role_alignment_gap ? (
                      <Typography variant="caption">{roleRecommendation.role_alignment_gap}</Typography>
                    ) : null}
                    {roleRecommendation.inferred_reference_role !== identityForm.role_name.trim() ? (
                      <Box>
                        <Button
                          size="small"
                          variant="outlined"
                        onClick={() => {
                          setIdentityForm((current) => ({
                            ...current,
                            role_name: roleRecommendation.inferred_reference_role,
                            mission: roleRecommendation.mission,
                          }));
                          setIdentityDirty(true);
                        }}
                        >
                          采纳系统建议
                        </Button>
                      </Box>
                    ) : null}
                  </Stack>
                </Alert>
              ) : roleRecommendationError ? (
                <Alert severity="info">Q2 系统推断参考角色不可用：{roleRecommendationError}</Alert>
              ) : null}
              <TextField
                label={t("settings.role")}
                value={identityForm.role_name}
                onChange={(event) =>
                  {
                    setIdentityDirty(true);
                    setIdentityForm((current) => ({ ...current, role_name: event.target.value }));
                  }
                }
                fullWidth
                disabled={submitting}
                placeholder={t("settings.rolePlaceholder")}
                helperText={t("settings.roleHelp")}
              />
              <TextField
                label={t("settings.roleDescription")}
                value={identityForm.mission}
                onChange={(event) =>
                  {
                    setIdentityDirty(true);
                    setIdentityForm((current) => ({ ...current, mission: event.target.value }));
                  }
                }
                fullWidth
                multiline
                minRows={2}
                disabled={submitting}
                placeholder={t("settings.roleDescriptionPlaceholder")}
              />
              <TextField
                label={t("settings.coreValues")}
                value={identityForm.core_values}
                onChange={(event) =>
                  {
                    setIdentityDirty(true);
                    setIdentityForm((current) => ({ ...current, core_values: event.target.value }));
                  }
                }
                fullWidth
                multiline
                minRows={3}
                disabled={submitting}
                helperText={t("settings.coreValuesHelp")}
              />
              <Stack direction="row" justifyContent="flex-end">
                <Button
                  variant="contained"
                  startIcon={<SaveIcon />}
                  onClick={() => void handleSave()}
                  disabled={submitting || (!identityForm.role_name.trim() && !selectedWorkspace)}
                >
                  {submitting ? t("settings.saving") : t("settings.save")}
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress />
          </Box>
        ) : workspaces.length === 0 ? (
          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Typography color="text.secondary">{t("settings.noWorkspaces")}</Typography>
                <Button component={RouterLink} to="/console/workspaces" variant="contained">
                  {t("workspaces.addButton")}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent>
              <Stack spacing={3}>
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    {t("settings.defaultWorkspace")}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t("settings.defaultWorkspaceHelp")}
                  </Typography>
                </Box>

                <FormControl fullWidth>
                  <InputLabel id="settings-workspace-select-label">
                    {t("settings.defaultWorkspace")}
                  </InputLabel>
                  <Select
                    labelId="settings-workspace-select-label"
                    label={t("settings.defaultWorkspace")}
                    value={selectedWorkspaceId}
                    onChange={handleWorkspaceChange}
                    disabled={submitting}
                  >
                    {workspaces.map((workspace) => (
                      <MenuItem key={workspace.id} value={workspace.id}>
                        {workspace.name}
                        {workspace.is_default ? ` ${t("workspaces.default")}` : ""}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Divider />

                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    {t("settings.defaultConfigSection")}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t("settings.defaultConfigHelp")}
                  </Typography>
                </Box>

                <TextField
                  label={t("settings.description")}
                  value={form.description}
                  onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                  fullWidth
                  multiline
                  minRows={2}
                  disabled={submitting}
                />
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                    {t("settings.forbiddenActions")}
                  </Typography>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField
                      value={newForbiddenAction}
                      onChange={(event) => setNewForbiddenAction(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          handleAddForbiddenAction();
                        }
                      }}
                      fullWidth
                      size="small"
                      disabled={submitting}
                      placeholder={t("settings.forbiddenActionsPlaceholder")}
                    />
                    <Button
                      variant="outlined"
                      startIcon={<AddIcon />}
                      onClick={handleAddForbiddenAction}
                      disabled={submitting || !newForbiddenAction.trim()}
                      sx={{ flexShrink: 0 }}
                    >
                      {t("settings.addForbiddenAction")}
                    </Button>
                  </Stack>
                  {form.forbidden_actions.length > 0 ? (
                    <Stack spacing={1} sx={{ mt: 1.5 }}>
                      {form.forbidden_actions.map((action, index) => (
                        <Box
                          key={`${action}-${index}`}
                          sx={{
                            alignItems: "center",
                            border: "1px solid",
                            borderColor: "divider",
                            borderRadius: 1,
                            display: "flex",
                            gap: 1,
                            justifyContent: "space-between",
                            px: 1.5,
                            py: 1,
                          }}
                        >
                          <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                            {action}
                          </Typography>
                          <IconButton
                            aria-label={t("settings.removeForbiddenAction")}
                            color="error"
                            disabled={submitting}
                            onClick={() => handleRemoveForbiddenAction(index)}
                            size="small"
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Box>
                      ))}
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                      {t("settings.noForbiddenActions")}
                    </Typography>
                  )}
                </Box>
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                    {t("settings.taskGoals")}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {t("settings.taskGoalsHelp")}
                  </Typography>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                    <TextField
                      value={newTaskGoal}
                      onChange={(event) => setNewTaskGoal(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          handleAddTaskGoal();
                        }
                      }}
                      fullWidth
                      size="small"
                      disabled={submitting}
                      placeholder={t("settings.taskGoalsPlaceholder")}
                    />
                    <Button
                      variant="outlined"
                      startIcon={<AddIcon />}
                      onClick={handleAddTaskGoal}
                      disabled={submitting || !newTaskGoal.trim()}
                      sx={{ flexShrink: 0 }}
                    >
                      {t("settings.addTaskGoal")}
                    </Button>
                  </Stack>
                  {form.task_goals.length > 0 ? (
                    <Stack spacing={1} sx={{ mt: 1.5 }}>
                      {form.task_goals.map((goal, index) => (
                        <Box
                          key={`${goal}-${index}`}
                          sx={{
                            alignItems: "center",
                            border: "1px solid",
                            borderColor: "divider",
                            borderRadius: 1,
                            display: "flex",
                            gap: 1,
                            justifyContent: "space-between",
                            px: 1.5,
                            py: 1,
                          }}
                        >
                          <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                            {goal}
                          </Typography>
                          <IconButton
                            aria-label={t("settings.removeTaskGoal")}
                            color="error"
                            disabled={submitting}
                            onClick={() => handleRemoveTaskGoal(index)}
                            size="small"
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Box>
                      ))}
                    </Stack>
                  ) : (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                      {t("settings.noTaskGoals")}
                    </Typography>
                  )}
                </Box>

                <Stack direction="row" justifyContent="flex-end">
                  <Button
                    variant="contained"
                    startIcon={<SaveIcon />}
                    onClick={() => void handleSave()}
                    disabled={submitting || (!selectedWorkspace && !identityForm.role_name.trim())}
                  >
                    {submitting ? t("settings.saving") : t("settings.save")}
                  </Button>
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        )}
      </Stack>
    </Box>
  );
}
