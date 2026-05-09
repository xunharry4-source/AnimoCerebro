import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";
import ArticleIcon from "@mui/icons-material/Article";
import { Play } from "lucide-react";
import { extractApiErrorMessage, readResponseBody } from "../../api/httpError";

type AgendaStatus = "open" | "watching" | "blocked" | "review_now" | "overdue" | "expired";

type AgendaItem = {
  item_id: string;
  title: string;
  status: AgendaStatus;
  priority: number;
  next_review_condition: string;
  delay_risk_score: number;
};

type AgendaResponse = {
  state: {
    state_id: string;
    review_now_item_ids: string[];
    overdue_item_ids: string[];
  };
  items: AgendaItem[];
};

type MemoryBackendStatusItem = {
  backend: string;
  package_name?: string | null;
  package_installed: boolean;
  write_enabled: boolean;
  recall_enabled: boolean;
  mode: string;
  detail: string;
};

type EnhancedMemoryOverview = {
  semantic_count: number;
  procedural_count: number;
  episodic_count: number;
  active_count: number;
  deprecated_count: number;
  archived_count: number;
  suspect_count: number;
  projection_failures: string[];
  backends: MemoryBackendStatusItem[];
  health_status?: string;
};

type EnhancedMemoryRecordItem = {
  memory_id: string;
  memory_layer: string;
  source_kind: string;
  title: string;
  summary: string;
  content: string;
  trace_id: string;
  request_id?: string | null;
  source_event_id?: string | null;
  target_id?: string | null;
  version_id?: string | null;
  tags: string[];
  source_refs: string[];
  evidence_refs: string[];
  payload: Record<string, unknown>;
  status: string;
  visibility: string;
  trust_level: string;
  management_note?: string | null;
  correction_note?: string | null;
  supersedes_memory_id?: string | null;
  superseded_by_memory_id?: string | null;
  operator: string;
  last_action: string;
  last_action_reason: string;
  last_verified_at?: string | null;
  updated_at: string;
  created_at: string;
  storage_schema_version?: number;
  record_health_status?: string;
  repair_status?: string;
};

type MemoryBlockDescriptorItem = {
  block_id: string;
  block_kind: string;
  required: boolean;
  derived: boolean;
  codec_chain: string[];
  status: string;
  repairable: boolean;
  compression_strategy?: string;
  encryption_context?: string | null;
  last_verified_at?: string | null;
};

type MemoryRecordManifestItem = {
  memory_id: string;
  manifest_version: number;
  descriptors: MemoryBlockDescriptorItem[];
  updated_at?: string | null;
};

type MemoryRepairTicketItem = {
  memory_id: string;
  record_health_status: string;
  repaired_blocks: string[];
  quarantined_blocks: string[];
  projection_repairs: string[];
  notes: string[];
  updated_at?: string | null;
};

type MemoryRecordDiagnosticsPayload = {
  memory_id: string;
  storage_schema_version: number;
  record_health_status: string;
  repair_status: string;
  header: Record<string, unknown>;
  manifest?: MemoryRecordManifestItem | null;
  verification?: MemoryRepairTicketItem | null;
};

type MemoryRepairSchedulerStatusPayload = {
  enabled: boolean;
  interval_seconds: number;
  last_cycle_at?: string | null;
  last_summary: Record<string, unknown>;
};

type MemoryRepairAllPayload = {
  triggered_by: string;
  scheduler: MemoryRepairSchedulerStatusPayload;
  items: MemoryRepairTicketItem[];
};

type MemoryForceAutoOrganizePayload = {
  status: string;
  mode: string;
  cycle_id: string;
  lease_id: string;
  idempotency_key: string;
  snapshot_version: number;
  queued_cycle?: {
    status?: string;
    trigger_reason?: string;
    input_refs?: string[];
  };
};

type EnhancedMemoryRecordsPayload = {
  layer: string;
  limit: number;
  items: EnhancedMemoryRecordItem[];
};

type EnhancedMemorySearchHit = {
  memory_id: string;
  memory_layer: string;
  source_kind: string;
  title: string;
  summary: string;
  trace_id: string;
  score: number;
  tags: string[];
  source_refs: string[];
};

type EnhancedMemorySearchPayload = {
  query: string;
  limit: number;
  trace_id?: string | null;
  target_id?: string | null;
  items: EnhancedMemorySearchHit[];
};

type EnhancedMemoryAuditEvent = {
  event_id: string;
  memory_id: string;
  action: string;
  reason: string;
  operator: string;
  details: Record<string, unknown>;
  created_at: string;
};

type EnhancedMemoryAuditPayload = {
  memory_id: string;
  limit: number;
  items: EnhancedMemoryAuditEvent[];
};

type ManagementPayload = {
  status?: string;
  visibility?: string;
  trust_level?: string;
  management_note?: string;
  correction_note?: string;
  operator: string;
  reason: string;
  mark_verified?: boolean;
};

const chipColor = (status: AgendaStatus): "default" | "primary" | "warning" | "error" => {
  if (status === "watching") {
    return "primary";
  }
  if (status === "blocked" || status === "review_now") {
    return "warning";
  }
  if (status === "overdue") {
    return "error";
  }
  return "default";
};

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function readJson<T>(input: RequestInfo): Promise<T> {
  const response = await fetch(input, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const data = await readResponseBody(response);
    throw new Error(extractApiErrorMessage(data, `HTTP ${response.status}`));
  }
  return (await response.json()) as T;
}

async function postJson<T>(input: RequestInfo, body: object): Promise<T> {
  const response = await fetch(input, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await readResponseBody(response);
    throw new Error(extractApiErrorMessage(data, `HTTP ${response.status}`));
  }
  return (await response.json()) as T;
}

export default function MemoryReasoning() {
  const { t } = useTranslation();
  const [agenda, setAgenda] = useState<AgendaResponse | null>(null);
  const [overview, setOverview] = useState<EnhancedMemoryOverview | null>(null);
  const [records, setRecords] = useState<EnhancedMemoryRecordItem[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<EnhancedMemoryRecordItem | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<EnhancedMemoryAuditEvent[]>([]);
  const [selectedDiagnostics, setSelectedDiagnostics] = useState<MemoryRecordDiagnosticsPayload | null>(null);
  const [searchHits, setSearchHits] = useState<EnhancedMemorySearchHit[]>([]);
  const [repairSchedulerStatus, setRepairSchedulerStatus] = useState<MemoryRepairSchedulerStatusPayload | null>(null);
  const [recentRepairAll, setRecentRepairAll] = useState<MemoryRepairAllPayload | null>(null);
  const [layer, setLayer] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [trustFilter, setTrustFilter] = useState("all");
  const [healthFilter, setHealthFilter] = useState("all");
  const [repairStatusFilter, setRepairStatusFilter] = useState("all");
  const [schemaFilter, setSchemaFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [managementNote, setManagementNote] = useState("");
  const [correctionNote, setCorrectionNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [repairLoading, setRepairLoading] = useState(false);
  const [autoOrganizeLoading, setAutoOrganizeLoading] = useState(false);
  const [recentAutoOrganize, setRecentAutoOrganize] = useState<MemoryForceAutoOrganizePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiErrors, setApiErrors] = useState<string[]>([]);

  const loadRecords = async (recordIdToReload?: string): Promise<string[]> => {
    const params = new URLSearchParams({
      layer,
      limit: "30",
    });
    if (statusFilter !== "all") {
      params.set("status", statusFilter);
    }
    if (trustFilter !== "all") {
      params.set("trust_level", trustFilter);
    }
    
    const errors: string[] = [];

    const [agendaResult, overviewResult, recordsResult, repairStatusResult] = await Promise.allSettled([
      readJson<AgendaResponse>("/api/web/cognitive-agenda"),
      readJson<EnhancedMemoryOverview>("/api/web/memory/overview"),
      readJson<EnhancedMemoryRecordsPayload>(`/api/web/memory/records?${params.toString()}`),
      readJson<MemoryRepairSchedulerStatusPayload>("/api/web/memory/repair/status"),
    ]);

    const captureError = (label: string, reason: unknown) => {
      const errorMsg = reason instanceof Error ? reason.message : String(reason);
      errors.push(`${label}: ${errorMsg}`);
      console.warn(`Failed to load ${label}:`, reason);
    };

    const agendaPayload = agendaResult.status === "fulfilled" ? agendaResult.value : null;
    if (agendaResult.status === "rejected") {
      captureError("cognitive-agenda", agendaResult.reason);
    }

    const overviewPayload = overviewResult.status === "fulfilled" ? overviewResult.value : null;
    if (overviewResult.status === "rejected") {
      captureError("memory/overview", overviewResult.reason);
    }

    const recordsPayload = recordsResult.status === "fulfilled" ? recordsResult.value : null;
    if (recordsResult.status === "rejected") {
      captureError("memory/records", recordsResult.reason);
    }

    const repairStatusPayload = repairStatusResult.status === "fulfilled" ? repairStatusResult.value : null;
    if (repairStatusResult.status === "rejected") {
      captureError("memory/repair/status", repairStatusResult.reason);
    }
    
    // Track API errors for debugging
    setApiErrors(errors);
    
    if (agendaPayload) {
      setAgenda(agendaPayload);
    }
    if (overviewPayload) {
      setOverview(overviewPayload);
    }
    if (recordsPayload) {
      setRecords(recordsPayload.items);
    }
    if (repairStatusPayload) {
      setRepairSchedulerStatus(repairStatusPayload);
    }
    
    const reloadId = recordIdToReload ?? selectedRecord?.memory_id ?? null;
    if (reloadId) {
      try {
        await loadDetail(reloadId);
      } catch (e) {
        console.warn("Failed to load detail:", e);
      }
    } else {
      setSelectedRecord(null);
      setSelectedAudit([]);
      setSelectedDiagnostics(null);
    }
    return errors;
  };

  const loadPage = async () => {
    setLoading(true);
    setError(null);
    setApiErrors([]);
    try {
      const errors = await loadRecords();
      // Check if ALL API calls failed (not just empty data)
      // Empty data is valid - it means the system is working but has no records yet
      if (errors.length >= 4) {
        setError(t("memory.errors.allApisFailed", { details: errors.join("\n") }));
      }
    } catch (e) {
      console.error("Unexpected error loading page:", e);
      setError(t("memory.errors.pageLoadUnexpected"));
    } finally {
      setLoading(false);
    }
  };

  const filteredRecords = records.filter((record) => {
    if (healthFilter !== "all" && (record.record_health_status ?? "unknown") !== healthFilter) {
      return false;
    }
    if (repairStatusFilter !== "all" && (record.repair_status ?? "unknown") !== repairStatusFilter) {
      return false;
    }
    if (schemaFilter === "modular_only" && (record.storage_schema_version ?? 1) < 2) {
      return false;
    }
    if (schemaFilter === "legacy_only" && (record.storage_schema_version ?? 1) >= 2) {
      return false;
    }
    return true;
  });

  const loadDetail = async (memoryId: string) => {
    try {
      const [detailPayload, auditPayload, diagnosticsPayload] = await Promise.all([
        readJson<EnhancedMemoryRecordItem>(`/api/web/memory/${encodeURIComponent(memoryId)}`),
        readJson<EnhancedMemoryAuditPayload>(`/api/web/memory/${encodeURIComponent(memoryId)}/audit?limit=20`),
        readJson<MemoryRecordDiagnosticsPayload>(`/api/web/memory/${encodeURIComponent(memoryId)}/diagnostics`),
      ]);
      setSelectedRecord(detailPayload);
      setSelectedAudit(auditPayload.items);
      setSelectedDiagnostics(diagnosticsPayload);
      setManagementNote(detailPayload.management_note ?? "");
      setCorrectionNote(detailPayload.correction_note ?? "");
    } catch (e) {
      console.warn("Failed to load memory details:", e);
      // Don't block - details are optional
    }
  };

  useEffect(() => {
    void loadPage();
  }, [layer, statusFilter, trustFilter]);

  const handleSearch = async () => {
    if (!query.trim()) {
      setSearchHits([]);
      return;
    }
    setSearchLoading(true);
    setError(null);
    try {
      const payload = await readJson<EnhancedMemorySearchPayload>(
        `/api/web/memory/search?query=${encodeURIComponent(query.trim())}&limit=10`,
      );
      setSearchHits(payload.items);
    } catch {
      setError(t("memory.errors.searchFailed"));
    } finally {
      setSearchLoading(false);
    }
  };

  const applyManagement = async (payload: ManagementPayload) => {
    if (!selectedRecord) {
      return;
    }
    setActionLoading(true);
    setError(null);
    try {
      const resolvedReason = payload.reason.trim() || "Memory governance updated.";
      await postJson<EnhancedMemoryRecordItem>(
        `/api/web/memory/${encodeURIComponent(selectedRecord.memory_id)}/management`,
        {
          ...payload,
          reason: resolvedReason,
          management_note: payload.management_note ?? managementNote,
          correction_note: payload.correction_note ?? correctionNote,
        },
      );
      setReason("");
      await loadRecords(selectedRecord.memory_id);
    } catch {
      setError(t("memory.errors.managementFailed"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerifyRecord = async () => {
    if (!selectedRecord) {
      return;
    }
    setRepairLoading(true);
    setError(null);
    try {
      await postJson<MemoryRepairTicketItem>(
        `/api/web/memory/${encodeURIComponent(selectedRecord.memory_id)}/verify`,
        {},
      );
      await loadDetail(selectedRecord.memory_id);
      await loadRecords(selectedRecord.memory_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("memory.errors.verifyFailed"));
    } finally {
      setRepairLoading(false);
    }
  };

  const handleRepairRecord = async () => {
    if (!selectedRecord) {
      return;
    }
    setRepairLoading(true);
    setError(null);
    try {
      await postJson<MemoryRepairTicketItem>(
        `/api/web/memory/${encodeURIComponent(selectedRecord.memory_id)}/repair`,
        {},
      );
      await loadDetail(selectedRecord.memory_id);
      await loadRecords(selectedRecord.memory_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("memory.errors.repairFailed"));
    } finally {
      setRepairLoading(false);
    }
  };

  const handleRepairAll = async () => {
    setRepairLoading(true);
    setError(null);
    try {
      const payload = await postJson<MemoryRepairAllPayload>("/api/web/memory/repair/trigger", {});
      setRepairSchedulerStatus(payload.scheduler);
      setRecentRepairAll(payload);
      await loadRecords(selectedRecord?.memory_id ?? undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("memory.errors.repairAllFailed"));
    } finally {
      setRepairLoading(false);
    }
  };

  const handleForceAutoOrganize = async () => {
    setAutoOrganizeLoading(true);
    setError(null);
    try {
      const payload = await postJson<MemoryForceAutoOrganizePayload>(
        "/api/web/memory/consolidation/trigger?force_auto_organize=true",
        {},
      );
      setRecentAutoOrganize(payload);
      await loadRecords(selectedRecord?.memory_id ?? undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("memory.errors.forceAutoOrganizeFailed"));
    } finally {
      setAutoOrganizeLoading(false);
    }
  };

  const applyQuickFilter = (preset: "all" | "repair_queue" | "degraded_only" | "legacy_only") => {
    if (preset === "all") {
      setHealthFilter("all");
      setRepairStatusFilter("all");
      setSchemaFilter("all");
      return;
    }
    if (preset === "repair_queue") {
      setHealthFilter("degraded");
      setRepairStatusFilter("pending_repair");
      setSchemaFilter("modular_only");
      return;
    }
    if (preset === "degraded_only") {
      setHealthFilter("degraded");
      setRepairStatusFilter("all");
      setSchemaFilter("all");
      return;
    }
    setHealthFilter("all");
    setRepairStatusFilter("all");
    setSchemaFilter("legacy_only");
  };

  return (
    <Stack spacing={3} data-testid="memory-reasoning-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4">{t("memory.title")}</Typography>
          <Typography variant="body1" color="text.secondary">
            {t("memory.subtitle")}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button
            component={RouterLink}
            to="/console/module-logs/memory"
            variant="outlined"
            startIcon={<ArticleIcon />}
          >
            {t("moduleLogs.view")}
          </Button>
          <Button variant="contained" onClick={() => void loadPage()}>
            {t("common.refresh")}
          </Button>
        </Stack>
      </Stack>

      {/* API Error Warnings */}
      {apiErrors.length > 0 && apiErrors.length < 3 && (
        <Alert severity="warning">
          <Typography variant="subtitle2" gutterBottom>
            {t("memory.partialApiFailure")}
          </Typography>
          <Stack spacing={0.5}>
            {apiErrors.map((err, idx) => (
              <Typography key={idx} variant="body2" component="div">
                • {err}
              </Typography>
            ))}
          </Stack>
        </Alert>
      )}

      {loading ? (
        <Stack alignItems="center" py={6}>
          <CircularProgress />
        </Stack>
      ) : null}

      {error ? <Alert severity="error">{error}</Alert> : null}

      {!loading && !error ? (
        <>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <Card sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {t("memory.overview.title")}
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip label={t("memory.overview.semantic", { count: overview?.semantic_count ?? 0 })} color="info" variant="outlined" />
                  <Chip label={t("memory.overview.procedural", { count: overview?.procedural_count ?? 0 })} color="success" variant="outlined" />
                  <Chip label={t("memory.overview.episodic", { count: overview?.episodic_count ?? 0 })} color="warning" variant="outlined" />
                  <Chip label={t("memory.overview.active", { count: overview?.active_count ?? 0 })} color="primary" variant="outlined" />
                  <Chip label={t("memory.overview.deprecated", { count: overview?.deprecated_count ?? 0 })} variant="outlined" />
                  <Chip label={t("memory.overview.archived", { count: overview?.archived_count ?? 0 })} variant="outlined" />
                  <Chip label={t("memory.overview.suspect", { count: overview?.suspect_count ?? 0 })} color="error" variant="outlined" />
                  <Chip label={t("memory.overview.health", { status: overview?.health_status ?? "unknown" })} color="secondary" variant="outlined" />
                </Stack>
                {overview?.projection_failures.length ? (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    {t("memory.overview.projectionFailures", { failures: overview.projection_failures.join(" | ") })}
                  </Alert>
                ) : null}
              </CardContent>
            </Card>
            <Card sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {t("memory.bridge.title")}
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1.5 }}>
                  <Chip
                    size="small"
                    label={t("memory.chips.repair", { value: repairSchedulerStatus?.enabled ? t("memory.values.on") : t("memory.values.off") })}
                    color={repairSchedulerStatus?.enabled ? "success" : "default"}
                    variant="outlined"
                  />
                  <Chip
                    size="small"
                    label={t("memory.chips.intervalSeconds", { value: repairSchedulerStatus?.interval_seconds ?? 0 })}
                    variant="outlined"
                  />
                  <Chip
                    size="small"
                    label={t("memory.chips.last", { value: formatDateTime(repairSchedulerStatus?.last_cycle_at) })}
                    variant="outlined"
                  />
                  <Chip
                    size="small"
                    label={t("memory.chips.status", { value: String(repairSchedulerStatus?.last_summary?.status ?? "unknown") })}
                    variant="outlined"
                  />
                  <Chip
                    size="small"
                    label={t("memory.chips.tickets", { value: Number(repairSchedulerStatus?.last_summary?.tickets ?? 0) })}
                    variant="outlined"
                  />
                  <Button size="small" variant="outlined" onClick={() => void handleRepairAll()} disabled={repairLoading}>
                    {repairLoading ? t("common.processing") : t("memory.actions.repairAll")}
                  </Button>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<Play size={16} />}
                    onClick={() => void handleForceAutoOrganize()}
                    disabled={autoOrganizeLoading}
                  >
                    {autoOrganizeLoading ? t("common.processing") : t("memory.actions.forceAutoOrganize")}
                  </Button>
                </Stack>
                {recentAutoOrganize ? (
                  <Alert severity="success" sx={{ mb: 1.5 }}>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip size="small" label={t("memory.chips.cycle", { value: recentAutoOrganize.cycle_id })} variant="outlined" />
                      <Chip size="small" label={t("memory.chips.status", { value: recentAutoOrganize.queued_cycle?.status ?? recentAutoOrganize.status })} color="success" variant="outlined" />
                      <Chip size="small" label={t("memory.chips.refs", { value: recentAutoOrganize.queued_cycle?.input_refs?.length ?? 0 })} variant="outlined" />
                    </Stack>
                  </Alert>
                ) : null}
                {recentRepairAll ? (
                  <Paper variant="outlined" sx={{ p: 1.5, mb: 1.5 }}>
                    <Stack spacing={1.25}>
                      <Typography variant="subtitle2">{t("memory.repair.recentRepairAll")}</Typography>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        <Chip size="small" label={t("memory.chips.triggered", { value: recentRepairAll.triggered_by })} variant="outlined" />
                        <Chip size="small" label={t("memory.chips.tickets", { value: recentRepairAll.items.length })} color="info" variant="outlined" />
                        <Chip
                          size="small"
                          label={t("memory.chips.repaired", { value: recentRepairAll.items.reduce((sum, item) => sum + item.repaired_blocks.length, 0) })}
                          color="success"
                          variant="outlined"
                        />
                        <Chip
                          size="small"
                          label={t("memory.chips.quarantined", { value: recentRepairAll.items.reduce((sum, item) => sum + item.quarantined_blocks.length, 0) })}
                          color="warning"
                          variant="outlined"
                        />
                      </Stack>
                      {recentRepairAll.items.length === 0 ? (
                        <Alert severity="info">{t("memory.repair.noRepairAllItems")}</Alert>
                      ) : (
                        <Stack spacing={1}>
                          {recentRepairAll.items.map((item) => (
                            <Paper key={`repair-ticket-${item.memory_id}`} variant="outlined" sx={{ p: 1 }}>
                              <Stack spacing={0.5}>
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                  <Chip size="small" label={item.memory_id} variant="outlined" />
                                  <Chip
                                    size="small"
                                    label={item.record_health_status}
                                    color={item.record_health_status === "healthy" ? "success" : "warning"}
                                    variant="outlined"
                                  />
                                  <Chip size="small" label={t("memory.chips.repaired", { value: item.repaired_blocks.length })} color="success" variant="outlined" />
                                  <Chip size="small" label={t("memory.chips.quarantined", { value: item.quarantined_blocks.length })} color="warning" variant="outlined" />
                                  <Chip size="small" label={t("memory.chips.projection", { value: item.projection_repairs.length })} color="info" variant="outlined" />
                                </Stack>
                                {(item.repaired_blocks.length || item.quarantined_blocks.length || item.projection_repairs.length) ? (
                                  <Typography variant="caption" color="text.secondary">
                                    {t("memory.repair.ticketSummary", {
                                      repaired: item.repaired_blocks.join(" | ") || "--",
                                      quarantined: item.quarantined_blocks.join(" | ") || "--",
                                      projection: item.projection_repairs.join(" | ") || "--",
                                    })}
                                  </Typography>
                                ) : null}
                                {item.notes.length ? (
                                  <Typography variant="caption" color="text.secondary">
                                    {item.notes.join(" | ")}
                                  </Typography>
                                ) : null}
                              </Stack>
                            </Paper>
                          ))}
                        </Stack>
                      )}
                    </Stack>
                  </Paper>
                ) : null}
                <Stack spacing={1.5}>
                  {overview?.backends.map((backend) => (
                    <Paper key={backend.backend} variant="outlined" sx={{ p: 1.5 }}>
                      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                        <Typography variant="subtitle2">{backend.backend}</Typography>
                        <Chip size="small" label={backend.mode} variant="outlined" />
                        <Chip
                          size="small"
                          label={t("memory.chips.write", { value: backend.write_enabled ? t("memory.values.on") : t("memory.values.off") })}
                          color={backend.write_enabled ? "success" : "default"}
                          variant="outlined"
                        />
                        <Chip
                          size="small"
                          label={t("memory.chips.recall", { value: backend.recall_enabled ? t("memory.values.on") : t("memory.values.off") })}
                          color={backend.recall_enabled ? "info" : "default"}
                          variant="outlined"
                        />
                      </Stack>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        {backend.detail}
                      </Typography>
                    </Paper>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Stack>

          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Typography variant="h6">{t("memory.search.title")}</Typography>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField
                    fullWidth
                    label={t("memory.search.label")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  <Button variant="contained" onClick={() => void handleSearch()} disabled={searchLoading}>
                    {searchLoading ? t("memory.search.searching") : t("memory.search.action")}
                  </Button>
                </Stack>
                {searchHits.length ? (
                  <Stack spacing={1.5}>
                    {searchHits.map((hit) => (
                      <Paper
                        key={`${hit.memory_id}-${hit.memory_layer}`}
                        variant="outlined"
                        sx={{ p: 1.5, cursor: "pointer" }}
                        onClick={() => void loadDetail(hit.memory_id)}
                      >
                        <Stack spacing={1}>
                          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                            <Chip size="small" label={hit.memory_layer} color="info" variant="outlined" />
                            <Chip size="small" label={hit.source_kind} variant="outlined" />
                            <Chip size="small" label={t("memory.chips.score", { value: hit.score.toFixed(2) })} color="success" variant="outlined" />
                          </Stack>
                          <Typography variant="subtitle2">{hit.title}</Typography>
                          <Typography variant="body2">{hit.summary}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {t("memory.detail.trace", { traceId: hit.trace_id })}
                          </Typography>
                          {hit.trace_id ? (
                            <Button
                              size="small"
                              variant="outlined"
                              component={RouterLink}
                              to={`/console/audit/transcript-replay/${encodeURIComponent(hit.trace_id)}`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              {t("memory.actions.viewTrace")}
                            </Button>
                          ) : null}
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="info">{t("memory.search.emptyHint")}</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>

          <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems="stretch">
            <Card sx={{ flex: 1.4 }}>
              <CardContent>
                <Stack spacing={2}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2} justifyContent="space-between">
                    <Typography variant="h6">{t("memory.records.title")}</Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Button size="small" variant="outlined" onClick={() => applyQuickFilter("repair_queue")}>
                        {t("memory.filters.repairQueue")}
                      </Button>
                      <Button size="small" variant="outlined" onClick={() => applyQuickFilter("degraded_only")}>
                        {t("memory.filters.degradedOnly")}
                      </Button>
                      <Button size="small" variant="outlined" onClick={() => applyQuickFilter("legacy_only")}>
                        {t("memory.filters.legacyOnly")}
                      </Button>
                      <Button size="small" variant="text" onClick={() => applyQuickFilter("all")}>
                        {t("memory.filters.clearPreset")}
                      </Button>
                      <Select size="small" value={layer} onChange={(event) => setLayer(String(event.target.value))}>
                        <MenuItem value="all">{t("memory.filters.allLayers")}</MenuItem>
                        <MenuItem value="semantic">Semantic</MenuItem>
                        <MenuItem value="procedural">Procedural</MenuItem>
                        <MenuItem value="episodic">Episodic</MenuItem>
                      </Select>
                      <Select size="small" value={statusFilter} onChange={(event) => setStatusFilter(String(event.target.value))}>
                        <MenuItem value="all">{t("memory.filters.allStatuses")}</MenuItem>
                        <MenuItem value="active">active</MenuItem>
                        <MenuItem value="deprecated">deprecated</MenuItem>
                        <MenuItem value="archived">archived</MenuItem>
                        <MenuItem value="rejected">rejected</MenuItem>
                      </Select>
                      <Select size="small" value={trustFilter} onChange={(event) => setTrustFilter(String(event.target.value))}>
                        <MenuItem value="all">{t("memory.filters.allTrust")}</MenuItem>
                        <MenuItem value="unverified">unverified</MenuItem>
                        <MenuItem value="trusted">trusted</MenuItem>
                        <MenuItem value="suspect">suspect</MenuItem>
                      </Select>
                      <Select size="small" value={healthFilter} onChange={(event) => setHealthFilter(String(event.target.value))}>
                        <MenuItem value="all">{t("memory.filters.allHealth")}</MenuItem>
                        <MenuItem value="healthy">healthy</MenuItem>
                        <MenuItem value="degraded">degraded</MenuItem>
                      </Select>
                      <Select size="small" value={repairStatusFilter} onChange={(event) => setRepairStatusFilter(String(event.target.value))}>
                        <MenuItem value="all">{t("memory.filters.allRepairStatuses")}</MenuItem>
                        <MenuItem value="none">none</MenuItem>
                        <MenuItem value="pending_repair">pending_repair</MenuItem>
                      </Select>
                      <Select size="small" value={schemaFilter} onChange={(event) => setSchemaFilter(String(event.target.value))}>
                        <MenuItem value="all">{t("memory.filters.allSchemas")}</MenuItem>
                        <MenuItem value="modular_only">{t("memory.filters.modularOnly")}</MenuItem>
                        <MenuItem value="legacy_only">{t("memory.filters.legacyOnlyOption")}</MenuItem>
                      </Select>
                    </Stack>
                  </Stack>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    <Chip size="small" label={t("memory.chips.visible", { value: filteredRecords.length })} variant="outlined" />
                    <Chip size="small" label={t("memory.chips.healthFilter", { value: healthFilter })} variant="outlined" />
                    <Chip size="small" label={t("memory.chips.repairFilter", { value: repairStatusFilter })} variant="outlined" />
                    <Chip size="small" label={t("memory.chips.schemaFilter", { value: schemaFilter })} variant="outlined" />
                  </Stack>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{t("memory.records.columns.title")}</TableCell>
                        <TableCell>{t("memory.records.columns.layer")}</TableCell>
                        <TableCell>{t("common.status")}</TableCell>
                        <TableCell>{t("memory.records.columns.trust")}</TableCell>
                        <TableCell>{t("memory.records.columns.storage")}</TableCell>
                        <TableCell>{t("memory.records.columns.trace")}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredRecords.map((record) => (
                        <TableRow
                          key={record.memory_id}
                          hover
                          selected={selectedRecord?.memory_id === record.memory_id}
                          sx={{ cursor: "pointer" }}
                          onClick={() => void loadDetail(record.memory_id)}
                        >
                          <TableCell>{record.title}</TableCell>
                          <TableCell>{record.memory_layer}</TableCell>
                          <TableCell>{record.status}</TableCell>
                          <TableCell>{record.trust_level}</TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                              <Chip
                                size="small"
                                label={t("memory.chips.schema", { value: record.storage_schema_version ?? 1 })}
                                variant="outlined"
                              />
                              <Chip
                                size="small"
                                label={t("memory.chips.health", { value: record.record_health_status ?? "unknown" })}
                                color={(record.record_health_status ?? "unknown") === "healthy" ? "success" : "warning"}
                                variant="outlined"
                              />
                              <Chip
                                size="small"
                                label={t("memory.chips.repair", { value: record.repair_status ?? "unknown" })}
                                variant="outlined"
                              />
                            </Stack>
                          </TableCell>
                          <TableCell>
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                              <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                                {record.trace_id}
                              </Typography>
                              {record.trace_id ? (
                                <Button
                                  size="small"
                                  variant="outlined"
                                  component={RouterLink}
                                  to={`/console/audit/transcript-replay/${encodeURIComponent(record.trace_id)}`}
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  {t("memory.actions.viewTrace")}
                                </Button>
                              ) : null}
                            </Stack>
                          </TableCell>
                        </TableRow>
                      ))}
                      {filteredRecords.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6}>
                            <Alert severity="info">{t("memory.records.noMatches")}</Alert>
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ flex: 1 }}>
              <CardContent>
                {!selectedRecord ? (
                  <Alert severity="info">{t("memory.detail.selectHint")}</Alert>
                ) : (
                  <Stack spacing={2}>
                    <Typography variant="h6">{t("memory.detail.title")}</Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip label={selectedRecord.memory_layer} color="info" variant="outlined" />
                      <Chip label={selectedRecord.status} color="primary" variant="outlined" />
                      <Chip label={selectedRecord.trust_level} color="warning" variant="outlined" />
                      <Chip label={selectedRecord.visibility} variant="outlined" />
                      <Chip
                        label={t("memory.chips.schema", { value: selectedDiagnostics?.storage_schema_version ?? selectedRecord.storage_schema_version ?? 1 })}
                        variant="outlined"
                      />
                      <Chip
                        label={t("memory.chips.health", { value: selectedDiagnostics?.record_health_status ?? selectedRecord.record_health_status ?? "unknown" })}
                        color={
                          (selectedDiagnostics?.record_health_status ?? selectedRecord.record_health_status) === "healthy"
                            ? "success"
                            : "warning"
                        }
                        variant="outlined"
                      />
                      <Chip
                        label={t("memory.chips.repair", { value: selectedDiagnostics?.repair_status ?? selectedRecord.repair_status ?? "unknown" })}
                        variant="outlined"
                      />
                    </Stack>
                    <Typography variant="subtitle1">{selectedRecord.title}</Typography>
                    <Typography variant="body2">{selectedRecord.summary}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t("memory.detail.identity", {
                        traceId: selectedRecord.trace_id,
                        targetId: selectedRecord.target_id ?? "--",
                        versionId: selectedRecord.version_id ?? "--",
                      })}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      {selectedRecord.trace_id ? (
                        <Button
                          size="small"
                          variant="outlined"
                          component={RouterLink}
                          to={`/console/audit/transcript-replay/${encodeURIComponent(selectedRecord.trace_id)}`}
                        >
                          {t("memory.actions.viewTraceReplay")}
                        </Button>
                      ) : null}
                      {selectedRecord.source_event_id ? (
                        <Button
                          size="small"
                          variant="outlined"
                          component={RouterLink}
                          to={`/console/audit/transcript-replay/${encodeURIComponent(selectedRecord.source_event_id)}`}
                        >
                          {t("memory.actions.viewSourceEvent")}
                        </Button>
                      ) : null}
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      {t("memory.detail.sources", { sources: selectedRecord.source_refs.join(" | ") || "--" })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t("memory.detail.evidence", { evidence: selectedRecord.evidence_refs.join(" | ") || "--" })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t("memory.detail.lastAction", {
                        action: selectedRecord.last_action,
                        reason: selectedRecord.last_action_reason,
                      })}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t("memory.detail.timestamps", {
                        updatedAt: formatDateTime(selectedRecord.updated_at),
                        verifiedAt: formatDateTime(selectedRecord.last_verified_at),
                      })}
                    </Typography>
                    {selectedDiagnostics ? (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Stack spacing={1.25}>
                          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                            <Typography variant="subtitle2">{t("memory.diagnostics.title")}</Typography>
                            <Button size="small" variant="outlined" onClick={() => void handleVerifyRecord()} disabled={repairLoading}>
                              {t("memory.actions.verify")}
                            </Button>
                            <Button size="small" variant="contained" onClick={() => void handleRepairRecord()} disabled={repairLoading}>
                              {t("memory.actions.repair")}
                            </Button>
                          </Stack>
                          {selectedDiagnostics.verification?.notes?.length ? (
                            <Alert severity="info">
                              {selectedDiagnostics.verification.notes.join(" | ")}
                            </Alert>
                          ) : null}
                          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                            <Chip
                              size="small"
                              label={t("memory.chips.repaired", { value: selectedDiagnostics.verification?.repaired_blocks.length ?? 0 })}
                              color="success"
                              variant="outlined"
                            />
                            <Chip
                              size="small"
                              label={t("memory.chips.quarantined", { value: selectedDiagnostics.verification?.quarantined_blocks.length ?? 0 })}
                              color="warning"
                              variant="outlined"
                            />
                            <Chip
                              size="small"
                              label={t("memory.chips.projection", { value: selectedDiagnostics.verification?.projection_repairs.length ?? 0 })}
                              color="info"
                              variant="outlined"
                            />
                          </Stack>
                          <Stack spacing={1}>
                            {(selectedDiagnostics.manifest?.descriptors ?? []).map((descriptor) => (
                              <Paper key={descriptor.block_id} variant="outlined" sx={{ p: 1 }}>
                                <Stack spacing={0.5}>
                                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                    <Chip size="small" label={descriptor.block_kind} variant="outlined" />
                                    <Chip
                                      size="small"
                                      label={descriptor.status}
                                      color={descriptor.status === "healthy" ? "success" : "warning"}
                                      variant="outlined"
                                    />
                                    <Chip size="small" label={descriptor.codec_chain.join(" -> ") || "raw"} variant="outlined" />
                                    <Chip size="small" label={t("memory.chips.compress", { value: descriptor.compression_strategy ?? "none" })} variant="outlined" />
                                    <Chip size="small" label={descriptor.encryption_context ? t("memory.values.encrypted") : t("memory.values.plain")} variant="outlined" />
                                  </Stack>
                                  <Typography variant="caption" color="text.secondary">
                                    {t("memory.diagnostics.descriptorSummary", {
                                      required: descriptor.required ? t("common.yes") : t("common.no"),
                                      derived: descriptor.derived ? t("common.yes") : t("common.no"),
                                      repairable: descriptor.repairable ? t("common.yes") : t("common.no"),
                                      verified: formatDateTime(descriptor.last_verified_at),
                                    })}
                                  </Typography>
                                </Stack>
                              </Paper>
                            ))}
                          </Stack>
                        </Stack>
                      </Paper>
                    ) : null}
                    <Divider />
                    <TextField
                      label={t("memory.management.reason")}
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      fullWidth
                    />
                    <TextField
                      label={t("memory.management.note")}
                      value={managementNote}
                      onChange={(event) => setManagementNote(event.target.value)}
                      fullWidth
                      multiline
                      minRows={2}
                    />
                    <TextField
                      label={t("memory.management.correction")}
                      value={correctionNote}
                      onChange={(event) => setCorrectionNote(event.target.value)}
                      fullWidth
                      multiline
                      minRows={2}
                    />
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Button
                        variant="contained"
                        disabled={actionLoading}
                        onClick={() =>
                          void applyManagement({
                            status: "active",
                            trust_level: "trusted",
                            operator: "web_console",
                            reason,
                            management_note: managementNote,
                            correction_note: correctionNote,
                            mark_verified: true,
                          })
                        }
                      >
                        {t("memory.actions.markTrusted")}
                      </Button>
                      <Button
                        variant="outlined"
                        color="warning"
                        disabled={actionLoading}
                        onClick={() =>
                          void applyManagement({
                            trust_level: "suspect",
                            operator: "web_console",
                            reason,
                            management_note: managementNote,
                            correction_note: correctionNote,
                          })
                        }
                      >
                        {t("memory.actions.markSuspect")}
                      </Button>
                      <Button
                        variant="outlined"
                        disabled={actionLoading}
                        onClick={() =>
                          void applyManagement({
                            status: "deprecated",
                            operator: "web_console",
                            reason,
                            management_note: managementNote,
                            correction_note: correctionNote,
                          })
                        }
                      >
                        {t("memory.actions.deprecate")}
                      </Button>
                      <Button
                        variant="outlined"
                        color="error"
                        disabled={actionLoading}
                        onClick={() =>
                          void applyManagement({
                            status: "archived",
                            visibility: "hidden",
                            operator: "web_console",
                            reason,
                            management_note: managementNote,
                            correction_note: correctionNote,
                          })
                        }
                      >
                        {t("memory.actions.archiveHidden")}
                      </Button>
                    </Stack>
                    <Divider />
                    <Typography variant="subtitle2">{t("memory.audit.title")}</Typography>
                    {selectedAudit.length === 0 ? (
                      <Alert severity="info">{t("memory.audit.empty")}</Alert>
                    ) : (
                      <Stack spacing={1}>
                        {selectedAudit.map((event) => (
                          <Paper key={event.event_id} variant="outlined" sx={{ p: 1.5 }}>
                            <Stack spacing={0.5}>
                              <Typography variant="subtitle2">{event.action}</Typography>
                              <Typography variant="body2">{event.reason}</Typography>
                              <Typography variant="caption" color="text.secondary">
                                {event.operator} · {formatDateTime(event.created_at)}
                              </Typography>
                            </Stack>
                          </Paper>
                        ))}
                      </Stack>
                    )}
                  </Stack>
                )}
              </CardContent>
            </Card>
          </Stack>

          <Card>
            <CardContent>
              <Stack spacing={2}>
                <Typography variant="h6">{t("memory.agenda.title")}</Typography>
                {agenda?.items.length ? (
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{t("memory.agenda.columns.title")}</TableCell>
                        <TableCell>{t("common.status")}</TableCell>
                        <TableCell>{t("memory.agenda.columns.priority")}</TableCell>
                        <TableCell>{t("memory.agenda.columns.nextReview")}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {agenda.items.map((item) => (
                        <TableRow key={item.item_id}>
                          <TableCell>{item.title}</TableCell>
                          <TableCell>
                            <Chip size="small" label={item.status} color={chipColor(item.status)} variant="outlined" />
                          </TableCell>
                          <TableCell>{item.priority}</TableCell>
                          <TableCell>{item.next_review_condition}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <Alert severity="info">{t("memory.agenda.empty")}</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </>
      ) : null}
    </Stack>
  );
}
