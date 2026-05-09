import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import {
  type Locale,
  dashboardCopy,
  formatLocalizedToken,
  formatUserFacingError,
} from "../../i18n";

type InterventionAction = "pause" | "resume";

type OverviewPayload = {
  runtime?: {
    runtime_id: string;
    active_session_ids: string[];
    transcript_store_status: string;
    memory_store_status: string;
    degraded_mode: boolean;
    manual_confirmation_required: boolean;
  };
  session?: {
    session_id: string;
    turn_count: number;
    active_goal_titles: string[];
    current_focus_summary: string | null;
    current_reasoning_mode: string | null;
    degraded_flags: string[];
  } | null;
  working_memory?: {
    active_focus_titles?: string[];
    current_focus_summary?: string | null;
  };
  metacognition?: {
    scheduler_status?: string;
    current_reasoning_mode?: string;
  };
  living_self_model?: {
    load_level?: string;
    reasoning_posture?: string;
  };
  temporal_agenda?: {
    review_now_item_titles?: string[];
    overdue_item_titles?: string[];
  };
  active_weight_plugin_id?: string | null;
  weight_fallback_occurred?: boolean;
  weight_profile?: {
    active_weight_plugin_id: string;
    weight_fallback_occurred: boolean;
    fallback_reason?: string | null;
    purpose: string;
    risk_tolerance: number;
    cost_sensitivity: number;
    creativity_bias: number;
    continuity_bias: number;
    rationale_tags: string[];
  };
  recent_events?: TranscriptEvent[];
};

type CognitivePluginRow = {
  tool_id: string;
  plugin_kind: string;
  status: string;
  health_status: string | null;
  usage_count: number;
  failure_count: number;
  rollback_conditions: string[];
  trigger_conditions: string[];
};

type CognitiveConflict = {
  conflict_id: string;
  conflict_type: string;
  severity: "low" | "medium" | "high" | "critical";
  suggested_resolution: string;
  source_plugin_id: string;
  status: "unresolved" | "reconciling" | "resolved";
};

type InteractionMindState = {
  entity_id: string;
  brain_scope: string;
  snapshot_version: number;
  clarification_mode: boolean;
  model?: {
    entity_id: string;
    role_hint: string;
    current_goal_hypothesis: string;
    knowledge_depth: "low" | "medium" | "high";
    tolerance_for_detail: "low" | "medium" | "high";
    current_engagement_state: "low" | "medium" | "high" | "uncertain";
    trust_estimate: number;
    last_updated_at: string;
  };
  knowledge_gap?: {
    entity_id: string;
    known_topics: string[];
    uncertain_topics: string[];
    likely_missing_topics: string[];
    confidence: number;
  };
  communication_fit?: {
    entity_id: string;
    preferred_style: "brief" | "structured" | "evidence_first" | "conclusion_first";
    detail_level: "low" | "medium" | "high";
    clarification_bias: number;
    risk_of_misunderstanding: number;
  };
  misunderstanding_signals?: Array<{
    signal_id: string;
    entity_id: string;
    signal_type: string;
    severity: "low" | "medium" | "high" | "critical";
    observed_at: string;
  }>;
};

type TranscriptEvent = {
  entry_id: string;
  session_id: string;
  turn_id: string;
  entry_type: string;
  timestamp: string;
  source: string;
  trace_id: string;
  payload: unknown;
};

type StreamMessage = {
  type: "transcript_event";
  event: TranscriptEvent;
  overview: OverviewPayload;
};

type SnackbarState = {
  open: boolean;
  severity: "success" | "error";
  message: string;
};

type SectionErrors = {
  plugins?: string;
  conflicts?: string;
  interactionMind?: string;
};

type StreamConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";

async function buildHttpError(response: Response, code: string): Promise<Error> {
  const body = await response.text();
  return new Error(`${code}: HTTP ${response.status}${body ? ` ${body.slice(0, 300)}` : ""}`);
}

function buildStreamUrl(lastEntryId: string | null): string {
  const search = lastEntryId ? `?last_entry_id=${encodeURIComponent(lastEntryId)}` : "";
  if (typeof window === "undefined") {
    return `ws://localhost/api/web/events/stream${search}`;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/web/events/stream${search}`;
}

function getLoadChipColor(loadLevel?: string): "default" | "success" | "warning" | "error" {
  switch ((loadLevel || "").toLowerCase()) {
    case "low":
      return "success";
    case "medium":
      return "warning";
    case "high":
      return "error";
    default:
      return "default";
  }
}

function getPluginStatusColor(
  status: CognitivePluginRow["status"],
): "default" | "success" | "warning" | "error" | "info" {
  switch (status) {
    case "active":
      return "success";
    case "degraded":
      return "warning";
    case "revoked":
      return "error";
    case "sandbox_verified":
      return "info";
    default:
      return "default";
  }
}

export default function RealtimeDashboard() {
  const { t, i18n } = useTranslation();
  const [locale, setLocale] = useState<Locale>(i18n.language as Locale || "zh-CN");
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [pluginRows, setPluginRows] = useState<CognitivePluginRow[]>([]);
  const [conflicts, setConflicts] = useState<CognitiveConflict[]>([]);
  const [interactionMind, setInteractionMind] = useState<InteractionMindState | null>(null);
  const [eventStream, setEventStream] = useState<TranscriptEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sectionErrors, setSectionErrors] = useState<SectionErrors>({});
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pendingAction, setPendingAction] = useState<InterventionAction>("pause");
  const [snackbarState, setSnackbarState] = useState<SnackbarState>({
    open: false,
    severity: "success",
    message: "",
  });
  const [streamConnectionState, setStreamConnectionState] =
    useState<StreamConnectionState>("connecting");
  const [eventTypeFilter, setEventTypeFilter] = useState<string>("default");
  const [refreshing, setRefreshing] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const lastEntryIdRef = useRef<string | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const text = dashboardCopy[locale];
  const inlineSeparator = locale === "zh-CN" ? "，" : ", ";

  const loadOverview = async (): Promise<OverviewPayload> => {
    const response = await fetch("/api/web/overview", {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw await buildHttpError(response, "overview_failed");
    }
    const payload = (await response.json()) as OverviewPayload;
    setOverview(payload);
    return payload;
  };

  const loadPlugins = async (): Promise<void> => {
    const response = await fetch("/api/web/plugins/cognitive", {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw await buildHttpError(response, "plugins_failed");
    }
    const payload = (await response.json()) as Array<CognitivePluginRow & {
      lifecycle_status?: string;
      operational_status?: string;
    }>;
    if (!Array.isArray(payload)) {
      throw new Error("plugins_failed: response is not an array");
    }
    setPluginRows(
      payload.map((row) => ({
        ...row,
        status: row.status || row.lifecycle_status || row.operational_status || "unknown",
        health_status: row.health_status || "unknown",
        usage_count: Number(row.usage_count || 0),
        failure_count: Number(row.failure_count || 0),
        rollback_conditions: Array.isArray(row.rollback_conditions) ? row.rollback_conditions : [],
        trigger_conditions: Array.isArray(row.trigger_conditions) ? row.trigger_conditions : [],
      })),
    );
  };

  const loadConflicts = async (): Promise<void> => {
    const response = await fetch("/api/web/cognitive-conflicts", {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw await buildHttpError(response, "conflicts_failed");
    }
    const payload = (await response.json()) as { conflicts: CognitiveConflict[] };
    if (!Array.isArray(payload.conflicts)) {
      throw new Error("conflicts_failed: response.conflicts is not an array");
    }
    setConflicts(payload.conflicts);
  };

  const loadInteractionMind = async (entityId: string): Promise<void> => {
    const response = await fetch(`/api/web/interaction-mind/${encodeURIComponent(entityId)}`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw await buildHttpError(response, "interaction_mind_failed");
    }
    const payload = (await response.json()) as { state: InteractionMindState };
    // 如果 state 是空对象或没有 entity_id，视为无效数据
    const stateData = payload.state && payload.state.entity_id ? payload.state : null;
    setInteractionMind(stateData);
  };

  const refreshDashboard = async (): Promise<void> => {
    setRefreshing(true);
    try {
      const overviewPayload = await loadOverview();
      const recentEvents = overviewPayload.recent_events || [];
      setEventStream(recentEvents.slice(0, 50));
      lastEntryIdRef.current = recentEvents[0]?.entry_id || null;
      const interactionEntityId = overviewPayload.session?.session_id || "web-console";
      const settled = await Promise.allSettled([
        loadPlugins(),
        loadConflicts(),
        loadInteractionMind(interactionEntityId),
      ]);
      const nextSectionErrors: SectionErrors = {};
      if (settled[0].status === "rejected") {
        nextSectionErrors.plugins = settled[0].reason instanceof Error ? settled[0].reason.message : String(settled[0].reason);
      }
      if (settled[1].status === "rejected") {
        nextSectionErrors.conflicts = settled[1].reason instanceof Error ? settled[1].reason.message : String(settled[1].reason);
      }
      if (settled[2].status === "rejected") {
        nextSectionErrors.interactionMind = settled[2].reason instanceof Error ? settled[2].reason.message : String(settled[2].reason);
      }
      setSectionErrors(nextSectionErrors);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : formatUserFacingError(locale));
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void refreshDashboard();
  }, []);

  useEffect(() => {
    let isUnmounted = false;

    const scheduleReconnect = () => {
      if (isUnmounted) return;
      // Don't schedule when page is hidden — handleVisibilityChange will reconnect on reveal
      if (document.visibilityState === "hidden") return;
      // Clear any existing pending timer to avoid duplicate reconnects
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      const attempts = reconnectAttemptsRef.current;
      // Exponential backoff: 3s, 6s, 12s, 24s, capped at 60s
      const delay = Math.min(3000 * Math.pow(2, attempts), 60000);
      reconnectAttemptsRef.current = attempts + 1;
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        connectStream(true);
      }, delay);
    };

    const connectStream = (isReconnectAttempt: boolean) => {
      if (isUnmounted) return;

      // Skip if an active or connecting socket already exists
      const existing = wsRef.current;
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }

      // Skip if the page is hidden — reconnect when it becomes visible
      if (document.visibilityState === "hidden") return;

      setStreamConnectionState(isReconnectAttempt ? "reconnecting" : "connecting");
      const streamUrl = buildStreamUrl(lastEntryIdRef.current);
      const socket = new WebSocket(streamUrl);
      wsRef.current = socket;

      // Track when this socket opened to determine if connection was stable
      let openedAt = 0;

      socket.onopen = () => {
        openedAt = Date.now();
        setStreamConnectionState("connected");
        setStreamError(null);
      };

      socket.onmessage = (message) => {
        try {
          const parsed = JSON.parse(message.data) as StreamMessage;
          if (parsed.type !== "transcript_event") {
            return;
          }
          lastEntryIdRef.current = parsed.event.entry_id;
          setOverview(parsed.overview);
          setEventStream((previous) => [parsed.event, ...previous].slice(0, 50));
          setStreamError(null);
        } catch {
          setStreamError(text.streamParseError);
        }
      };

      socket.onerror = () => {
        setStreamError(text.streamConnectionError);
      };

      socket.onclose = () => {
        wsRef.current = null;
        if (isUnmounted) return;
        // Only reset backoff if connection was stable for > 5s; otherwise keep counting
        if (openedAt > 0 && Date.now() - openedAt > 5000) {
          reconnectAttemptsRef.current = 0;
        }
        setStreamConnectionState("reconnecting");
        setStreamError(text.streamReconnect);
        scheduleReconnect();
      };
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        // Page became visible — reconnect immediately, reset backoff
        if (reconnectTimerRef.current !== null) {
          window.clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
        reconnectAttemptsRef.current = 0;
        connectStream(true);
      } else {
        // Page hidden — close the connection to avoid idle load
        if (reconnectTimerRef.current !== null) {
          window.clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
        wsRef.current?.close(1000, "page hidden");
        wsRef.current = null;
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    connectStream(false);

    return () => {
      isUnmounted = true;
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  const degradedMessage = useMemo(() => {
    if (overview === null) {
      return null;
    }
    if (overview.runtime?.degraded_mode) {
      return text.runtimeDegraded;
    }
    if ((overview.session?.degraded_flags || []).length > 0) {
      return `${text.sessionDegradedPrefix}${(overview.session?.degraded_flags || [])
        .map((flag) => formatLocalizedToken(flag, locale))
        .join(inlineSeparator)}`;
    }
    return null;
  }, [overview, text, inlineSeparator, locale]);

  const activeFocusTitles = overview?.working_memory?.active_focus_titles || [];
  const overdueItemTitles = overview?.temporal_agenda?.overdue_item_titles || [];
  const reviewNowItemTitles = overview?.temporal_agenda?.review_now_item_titles || [];
  const weightProfile = overview?.weight_profile;
  const criticalConflicts = conflicts.filter((conflict) => conflict.severity === "critical");
  const severeMisunderstandingSignals = (interactionMind?.misunderstanding_signals || []).filter(
    (signal) => signal.severity === "high" || signal.severity === "critical",
  );
  const availableEventTypes = Array.from(new Set(eventStream.map((event) => event.entry_type)));
  const filteredEventStream = eventStream.filter((event) => {
    if (eventTypeFilter === "default") {
      return event.entry_type !== "plugin_audit_event";
    }
    if (eventTypeFilter === "all") {
      return true;
    }
    return event.entry_type === eventTypeFilter;
  });

  const openInterventionDialog = (action: InterventionAction) => {
    setPendingAction(action);
    setReason("");
    setDialogOpen(true);
  };

  const closeInterventionDialog = () => {
    setDialogOpen(false);
  };

  const submitIntervention = async () => {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setSnackbarState({
        open: true,
        severity: "error",
        message: text.interventionReasonRequired,
      });
      return;
    }

    try {
      const response = await fetch("/api/web/interventions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          action: pendingAction,
          reason: trimmedReason,
        }),
      });

      if (!response.ok) {
        throw new Error("intervention_failed");
      }

      await refreshDashboard();
      setSnackbarState({
        open: true,
        severity: "success",
        message: pendingAction === "pause" ? text.pauseSubmitted : text.resumeSubmitted,
      });
      setDialogOpen(false);
    } catch {
      setSnackbarState({
        open: true,
        severity: "error",
        message: text.interventionSubmitFailed,
      });
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h4" component="h1" gutterBottom>
              {t("dashboard.title")}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {t("dashboard.subtitle")}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <FormControl sx={{ minWidth: 140 }}>
              <InputLabel id="dashboard-language-label">{t("common.language")}</InputLabel>
              <Select
                labelId="dashboard-language-label"
                value={locale}
                label={t("common.language")}
                onChange={(event) => {
                  const newLang = event.target.value as Locale;
                  setLocale(newLang);
                  i18n.changeLanguage(newLang);
                }}
              >
                <MenuItem value="zh-CN">中文</MenuItem>
                <MenuItem value="en-US">English</MenuItem>
              </Select>
            </FormControl>
            <Button variant="outlined" onClick={() => void refreshDashboard()} disabled={refreshing}>
              {refreshing ? t("common.refreshing") : t("common.refresh")}
            </Button>
            <Button color="warning" variant="contained" onClick={() => openInterventionDialog("pause")}>
              {t("dashboard.pause")}
            </Button>
            <Button color="success" variant="contained" onClick={() => openInterventionDialog("resume")}>
              {t("dashboard.resume")}
            </Button>
          </Stack>
        </Stack>

        {degradedMessage ? (
          <Alert severity="warning" data-testid="llm-degraded-alert">
            {degradedMessage}
          </Alert>
        ) : null}

        {overview?.weight_fallback_occurred ? (
          <Alert severity="warning" data-testid="weight-fallback-alert">
            {t("dashboard.weightFallbackWarning")}
          </Alert>
        ) : null}

        {criticalConflicts.length > 0 ? (
          <Alert severity="error" data-testid="critical-conflict-alert">
            {t("dashboard.criticalConflictWarning")}
          </Alert>
        ) : null}

        {severeMisunderstandingSignals.length > 0 ? (
          <Alert severity="warning" data-testid="interaction-mind-alert">
            {t("dashboard.interactionMindWarning")}
          </Alert>
        ) : null}

        {loadError ? (
          <Alert severity="error" data-testid="overview-load-error">
            {t("dashboard.backendDisconnected")} {loadError}
          </Alert>
        ) : null}

        {Object.keys(sectionErrors).length > 0 ? (
          <Alert severity="error" data-testid="dashboard-section-load-error">
            {t("dashboard.sectionLoadFailed")}{" "}
            {Object.entries(sectionErrors)
              .map(([section, message]) => `${t(`dashboard.sections.${section}`)}: ${message}`)
              .join(inlineSeparator)}
          </Alert>
        ) : null}

        {streamError ? (
          <Alert severity="error" data-testid="stream-error-alert">
            {streamError}
          </Alert>
        ) : null}

        <Alert
          severity={
            streamConnectionState === "connected"
              ? "success"
              : streamConnectionState === "reconnecting"
                ? "warning"
                : "info"
          }
        >
          {t("dashboard.streamStatus")}
          {streamConnectionState === "connected"
            ? t("dashboard.streamConnected")
            : streamConnectionState === "reconnecting"
              ? t("dashboard.streamReconnecting")
              : streamConnectionState === "connecting"
                ? t("dashboard.streamConnecting")
                : t("dashboard.streamDisconnected")}
        </Alert>

        {overview === null && refreshing ? (
          <Stack alignItems="center" justifyContent="center" sx={{ py: 8 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t("dashboard.loading")}
            </Typography>
          </Stack>
        ) : null}

        <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
          <Card sx={{ flex: 1 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t("dashboard.workingMemory")}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {t("dashboard.focusSummary")}
              </Typography>
              <Typography variant="body1" data-testid="focus-summary">
                {overview?.working_memory?.current_focus_summary
                  ? formatLocalizedToken(overview.working_memory.current_focus_summary, locale)
                  : t("dashboard.focusFallback")}
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
                {activeFocusTitles.length > 0 ? (
                  activeFocusTitles.map((title) => (
                    <Chip key={title} label={formatLocalizedToken(title, locale)} color="primary" />
                  ))
                ) : (
                  <Chip label={t("dashboard.noActiveTasks")} variant="outlined" />
                )}
              </Stack>
            </CardContent>
          </Card>

          <Card sx={{ flex: 1 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {t("dashboard.metacognition")}
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                <Chip
                  label={`${t("dashboard.loadLevel")}: ${formatLocalizedToken(overview?.living_self_model?.load_level, locale)}`}
                  color={getLoadChipColor(overview?.living_self_model?.load_level)}
                />
                <Chip
                  label={`${t("dashboard.reasoningPosture")}: ${formatLocalizedToken(overview?.living_self_model?.reasoning_posture, locale)}`}
                  variant="outlined"
                />
                <Chip
                  label={`${t("dashboard.schedulerStatus")}: ${formatLocalizedToken(overview?.metacognition?.scheduler_status, locale)}`}
                  color="info"
                  variant="outlined"
                />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.reasoningMode")}: {formatLocalizedToken(overview?.session?.current_reasoning_mode, locale)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.runtime")}: {overview?.runtime?.runtime_id || "--"}
              </Typography>
            </CardContent>
          </Card>
        </Stack>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("dashboard.weightCard")}
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
              <Chip
                label={`${t("dashboard.activeWeightPlugin")}: ${overview?.active_weight_plugin_id || "--"}`}
                color={overview?.weight_fallback_occurred ? "warning" : "primary"}
                variant="outlined"
              />
            </Stack>
            <Stack spacing={1}>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.weightPurpose")}: {weightProfile?.purpose || "--"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.riskTolerance")}: {weightProfile?.risk_tolerance ?? "--"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.costSensitivity")}: {weightProfile?.cost_sensitivity ?? "--"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.creativityBias")}: {weightProfile?.creativity_bias ?? "--"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.continuityBias")}: {weightProfile?.continuity_bias ?? "--"}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.rationaleTags")}:{" "}
                {weightProfile?.rationale_tags && weightProfile.rationale_tags.length > 0
                  ? weightProfile.rationale_tags.join(inlineSeparator)
                  : t("dashboard.noRationaleTags")}
              </Typography>
            </Stack>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("dashboard.interactionMindCard")}
            </Typography>
            {interactionMind === null ? (
              <Typography variant="body2" color="text.secondary">
                {t("dashboard.noInteractionMind")}
              </Typography>
            ) : (
              <Stack spacing={1.5}>
                <Typography variant="body2">
                  {t("dashboard.interactionRole")}: {interactionMind.model ? interactionMind.model.role_hint : "--"}
                </Typography>
                <Typography variant="body2">
                  {t("dashboard.interactionGoal")}: {interactionMind.model ? interactionMind.model.current_goal_hypothesis : "--"}
                </Typography>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Typography variant="body2">{t("dashboard.communicationStyle")}:</Typography>
                  <Chip
                    size="small"
                    color={interactionMind.clarification_mode ? "warning" : "info"}
                    label={formatLocalizedToken(interactionMind.communication_fit ? interactionMind.communication_fit.preferred_style : "unknown", locale)}
                  />
                </Stack>
                <Typography variant="body2">
                  {t("dashboard.knowledgeDepth")}: {formatLocalizedToken(interactionMind.model ? interactionMind.model.knowledge_depth : "unknown", locale)}
                </Typography>
                <Typography variant="body2">
                  {t("dashboard.misunderstandingRisk")}: {Math.round((interactionMind.communication_fit ? interactionMind.communication_fit.risk_of_misunderstanding : 0) * 100)}%
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {(interactionMind.misunderstanding_signals || []).map((signal) => (
                    <Chip
                      key={signal.signal_id}
                      size="small"
                      variant="outlined"
                      color={signal.severity === "high" || signal.severity === "critical" ? "warning" : "default"}
                      label={formatLocalizedToken(signal.signal_type, locale)}
                    />
                  ))}
                </Stack>
              </Stack>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("dashboard.reviewSection")}
            </Typography>
            <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" color="text.secondary">
                  {t("dashboard.reviewNow")}
                </Typography>
                <List dense>
                  {reviewNowItemTitles.length > 0 ? (
                    reviewNowItemTitles.map((title) => (
                      <ListItem key={title} sx={{ px: 0 }}>
                        <ListItemText primary={formatLocalizedToken(title, locale)} />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem sx={{ px: 0 }}>
                      <ListItemText primary={t("dashboard.noReviewNow")} />
                    </ListItem>
                  )}
                </List>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" color="text.secondary">
                  {t("dashboard.overdue")}
                </Typography>
                <List dense>
                  {overdueItemTitles.length > 0 ? (
                    overdueItemTitles.map((title) => (
                      <ListItem key={title} sx={{ px: 0 }}>
                        <ListItemText primary={formatLocalizedToken(title, locale)} />
                      </ListItem>
                    ))
                  ) : (
                    <ListItem sx={{ px: 0 }}>
                      <ListItemText primary={t("dashboard.noOverdue")} />
                    </ListItem>
                  )}
                </List>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("dashboard.conflictCard")}
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>{t("dashboard.conflictType")}</TableCell>
                    <TableCell>{t("dashboard.severity")}</TableCell>
                    <TableCell>{t("dashboard.status")}</TableCell>
                    <TableCell>{t("dashboard.conflictResolution")}</TableCell>
                    <TableCell>{t("dashboard.sourcePlugin")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {conflicts.length > 0 ? (
                    conflicts.map((conflict) => (
                      <TableRow key={conflict.conflict_id}>
                        <TableCell>{formatLocalizedToken(conflict.conflict_type, locale)}</TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={formatLocalizedToken(conflict.severity, locale)}
                            color={conflict.severity === "critical" ? "error" : conflict.severity === "high" ? "warning" : "default"}
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>{formatLocalizedToken(conflict.status, locale)}</TableCell>
                        <TableCell>{formatLocalizedToken(conflict.suggested_resolution, locale)}</TableCell>
                        <TableCell>{conflict.source_plugin_id}</TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography variant="body2" color="text.secondary">
                          {t("dashboard.noConflicts")}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {t("dashboard.pluginState")}
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Tool ID</TableCell>
                    <TableCell>{t("dashboard.status")}</TableCell>
                    <TableCell>{t("dashboard.health")}</TableCell>
                    <TableCell align="right">{t("dashboard.usageCount")}</TableCell>
                    <TableCell align="right">{t("dashboard.failureCount")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {pluginRows.map((row) => (
                    <TableRow key={row.tool_id}>
                      <TableCell>{row.tool_id}</TableCell>
                      <TableCell>
                        <Chip
                          label={formatLocalizedToken(row.status, locale)}
                          color={getPluginStatusColor(row.status)}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>{formatLocalizedToken(row.health_status || "unknown", locale)}</TableCell>
                      <TableCell align="right">{row.usage_count}</TableCell>
                      <TableCell align="right">{row.failure_count}</TableCell>
                    </TableRow>
                  ))}
                  {pluginRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                          {t("dashboard.noPlugins")}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Stack
              direction={{ xs: "column", md: "row" }}
              justifyContent="space-between"
              spacing={2}
              sx={{ mb: 2 }}
            >
              <Typography variant="h6">{t("dashboard.eventStream")}</Typography>
              <FormControl sx={{ minWidth: { xs: "100%", md: 240 } }}>
                <InputLabel id="event-type-filter-label">{t("dashboard.eventFilter")}</InputLabel>
                <Select
                  labelId="event-type-filter-label"
                  value={eventTypeFilter}
                  label={t("dashboard.eventFilter")}
                  onChange={(event) => setEventTypeFilter(event.target.value)}
                >
                  <MenuItem value="default">{t("dashboard.defaultEvents")}</MenuItem>
                  <MenuItem value="all">{t("dashboard.allEvents")}</MenuItem>
                  {availableEventTypes.map((eventType) => (
                    <MenuItem key={eventType} value={eventType}>
                      {formatLocalizedToken(eventType, locale)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
            <List dense>
              {filteredEventStream.length > 0 ? (
                filteredEventStream.map((event) => (
                  <ListItem key={event.entry_id} divider>
                    <ListItemText
                      primary={`${formatLocalizedToken(event.entry_type, locale)} · ${event.source}`}
                      secondary={`${event.timestamp} · turn=${event.turn_id}`}
                    />
                  </ListItem>
                ))
              ) : (
                <ListItem>
                  <ListItemText primary={t("dashboard.noEvents")} />
                </ListItem>
              )}
            </List>
          </CardContent>
        </Card>
      </Stack>

      <Dialog open={dialogOpen} onClose={closeInterventionDialog} fullWidth maxWidth="sm">
        <DialogTitle>{pendingAction === "pause" ? t("dashboard.pauseDialog") : t("dashboard.resumeDialog")}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={3}
            margin="dense"
            label={t("dashboard.interventionReason")}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={closeInterventionDialog}>{t("common.cancel")}</Button>
          <Button onClick={submitIntervention} variant="contained">
            {t("common.submit")}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbarState.open}
        autoHideDuration={3000}
        onClose={() => setSnackbarState((previous) => ({ ...previous, open: false }))}
      >
        <Alert severity={snackbarState.severity} sx={{ width: "100%" }}>
          {snackbarState.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
