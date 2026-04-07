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
    throw new Error(`HTTP ${response.status}`);
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
    throw new Error(`HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export default function MemoryReasoning() {
  const [agenda, setAgenda] = useState<AgendaResponse | null>(null);
  const [overview, setOverview] = useState<EnhancedMemoryOverview | null>(null);
  const [records, setRecords] = useState<EnhancedMemoryRecordItem[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<EnhancedMemoryRecordItem | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<EnhancedMemoryAuditEvent[]>([]);
  const [searchHits, setSearchHits] = useState<EnhancedMemorySearchHit[]>([]);
  const [layer, setLayer] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [trustFilter, setTrustFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [managementNote, setManagementNote] = useState("");
  const [correctionNote, setCorrectionNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRecords = async (recordIdToReload?: string) => {
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
    const [agendaPayload, overviewPayload, recordsPayload] = await Promise.all([
      readJson<AgendaResponse>("/api/web/cognitive-agenda"),
      readJson<EnhancedMemoryOverview>("/api/web/memory/enhanced/overview"),
      readJson<EnhancedMemoryRecordsPayload>(`/api/web/memory/enhanced/records?${params.toString()}`),
    ]);
    setAgenda(agendaPayload);
    setOverview(overviewPayload);
    setRecords(recordsPayload.items);
    const reloadId = recordIdToReload ?? selectedRecord?.memory_id ?? recordsPayload.items[0]?.memory_id ?? null;
    if (reloadId) {
      await loadDetail(reloadId);
    } else {
      setSelectedRecord(null);
      setSelectedAudit([]);
    }
  };

  const loadPage = async () => {
    setLoading(true);
    setError(null);
    try {
      await loadRecords();
    } catch {
      setError("无法连接到 Zentex 后端，请检查服务状态");
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (memoryId: string) => {
    const [detailPayload, auditPayload] = await Promise.all([
      readJson<EnhancedMemoryRecordItem>(`/api/web/memory/enhanced/${encodeURIComponent(memoryId)}`),
      readJson<EnhancedMemoryAuditPayload>(`/api/web/memory/enhanced/${encodeURIComponent(memoryId)}/audit?limit=20`),
    ]);
    setSelectedRecord(detailPayload);
    setSelectedAudit(auditPayload.items);
    setManagementNote(detailPayload.management_note ?? "");
    setCorrectionNote(detailPayload.correction_note ?? "");
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
        `/api/web/memory/enhanced/search?query=${encodeURIComponent(query.trim())}&limit=10`,
      );
      setSearchHits(payload.items);
    } catch {
      setError("增强记忆查询失败，请检查后端状态");
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
        `/api/web/memory/enhanced/${encodeURIComponent(selectedRecord.memory_id)}/management`,
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
      setError("记忆管理操作失败，请检查后端状态");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <Stack spacing={3} data-testid="memory-reasoning-root">
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4">记忆治理台</Typography>
          <Typography variant="body1" color="text.secondary">
            管理增强记忆的状态、可信度、纠正说明、来源链和审计记录。
          </Typography>
        </Box>
        <Button variant="contained" onClick={() => void loadPage()}>
          刷新
        </Button>
      </Stack>

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
                  记忆概览
                </Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip label={`Semantic: ${overview?.semantic_count ?? 0}`} color="info" variant="outlined" />
                  <Chip label={`Procedural: ${overview?.procedural_count ?? 0}`} color="success" variant="outlined" />
                  <Chip label={`Episodic: ${overview?.episodic_count ?? 0}`} color="warning" variant="outlined" />
                  <Chip label={`Active: ${overview?.active_count ?? 0}`} color="primary" variant="outlined" />
                  <Chip label={`Deprecated: ${overview?.deprecated_count ?? 0}`} variant="outlined" />
                  <Chip label={`Archived: ${overview?.archived_count ?? 0}`} variant="outlined" />
                  <Chip label={`Suspect: ${overview?.suspect_count ?? 0}`} color="error" variant="outlined" />
                </Stack>
                {overview?.projection_failures.length ? (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    投影失败：{overview.projection_failures.join(" | ")}
                  </Alert>
                ) : null}
              </CardContent>
            </Card>
            <Card sx={{ flex: 1 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  外部记忆桥状态
                </Typography>
                <Stack spacing={1.5}>
                  {overview?.backends.map((backend) => (
                    <Paper key={backend.backend} variant="outlined" sx={{ p: 1.5 }}>
                      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                        <Typography variant="subtitle2">{backend.backend}</Typography>
                        <Chip size="small" label={backend.mode} variant="outlined" />
                        <Chip
                          size="small"
                          label={`write:${backend.write_enabled ? "on" : "off"}`}
                          color={backend.write_enabled ? "success" : "default"}
                          variant="outlined"
                        />
                        <Chip
                          size="small"
                          label={`recall:${backend.recall_enabled ? "on" : "off"}`}
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
                <Typography variant="h6">增强记忆查询</Typography>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                  <TextField
                    fullWidth
                    label="搜索经验、失败教训、版本链"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  <Button variant="contained" onClick={() => void handleSearch()} disabled={searchLoading}>
                    {searchLoading ? "查询中…" : "查询"}
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
                            <Chip size="small" label={`score ${hit.score.toFixed(2)}`} color="success" variant="outlined" />
                          </Stack>
                          <Typography variant="subtitle2">{hit.title}</Typography>
                          <Typography variant="body2">{hit.summary}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            trace: {hit.trace_id}
                          </Typography>
                        </Stack>
                      </Paper>
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="info">输入关键词后可检索 semantic / procedural / episodic 记忆。</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>

          <Stack direction={{ xs: "column", lg: "row" }} spacing={2} alignItems="stretch">
            <Card sx={{ flex: 1.4 }}>
              <CardContent>
                <Stack spacing={2}>
                  <Stack direction={{ xs: "column", md: "row" }} spacing={2} justifyContent="space-between">
                    <Typography variant="h6">记忆记录</Typography>
                    <Stack direction="row" spacing={1}>
                      <Select size="small" value={layer} onChange={(event) => setLayer(String(event.target.value))}>
                        <MenuItem value="all">全部层</MenuItem>
                        <MenuItem value="semantic">Semantic</MenuItem>
                        <MenuItem value="procedural">Procedural</MenuItem>
                        <MenuItem value="episodic">Episodic</MenuItem>
                      </Select>
                      <Select size="small" value={statusFilter} onChange={(event) => setStatusFilter(String(event.target.value))}>
                        <MenuItem value="all">全部状态</MenuItem>
                        <MenuItem value="active">active</MenuItem>
                        <MenuItem value="deprecated">deprecated</MenuItem>
                        <MenuItem value="archived">archived</MenuItem>
                        <MenuItem value="rejected">rejected</MenuItem>
                      </Select>
                      <Select size="small" value={trustFilter} onChange={(event) => setTrustFilter(String(event.target.value))}>
                        <MenuItem value="all">全部可信度</MenuItem>
                        <MenuItem value="unverified">unverified</MenuItem>
                        <MenuItem value="trusted">trusted</MenuItem>
                        <MenuItem value="suspect">suspect</MenuItem>
                      </Select>
                    </Stack>
                  </Stack>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Title</TableCell>
                        <TableCell>Layer</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Trust</TableCell>
                        <TableCell>Trace</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {records.map((record) => (
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
                          <TableCell>{record.trace_id}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ flex: 1 }}>
              <CardContent>
                {!selectedRecord ? (
                  <Alert severity="info">选择一条记忆后可查看来源链、审计和治理动作。</Alert>
                ) : (
                  <Stack spacing={2}>
                    <Typography variant="h6">记忆详情</Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip label={selectedRecord.memory_layer} color="info" variant="outlined" />
                      <Chip label={selectedRecord.status} color="primary" variant="outlined" />
                      <Chip label={selectedRecord.trust_level} color="warning" variant="outlined" />
                      <Chip label={selectedRecord.visibility} variant="outlined" />
                    </Stack>
                    <Typography variant="subtitle1">{selectedRecord.title}</Typography>
                    <Typography variant="body2">{selectedRecord.summary}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      trace: {selectedRecord.trace_id} | target: {selectedRecord.target_id ?? "--"} | version: {selectedRecord.version_id ?? "--"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      来源: {selectedRecord.source_refs.join(" | ") || "--"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      证据: {selectedRecord.evidence_refs.join(" | ") || "--"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      最近动作: {selectedRecord.last_action} | {selectedRecord.last_action_reason}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      更新时间: {formatDateTime(selectedRecord.updated_at)} | 最近验证: {formatDateTime(selectedRecord.last_verified_at)}
                    </Typography>
                    <Divider />
                    <TextField
                      label="治理原因"
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      fullWidth
                    />
                    <TextField
                      label="治理备注"
                      value={managementNote}
                      onChange={(event) => setManagementNote(event.target.value)}
                      fullWidth
                      multiline
                      minRows={2}
                    />
                    <TextField
                      label="纠正说明"
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
                        标记可信
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
                        标记可疑
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
                        废弃
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
                        归档隐藏
                      </Button>
                    </Stack>
                    <Divider />
                    <Typography variant="subtitle2">审计记录</Typography>
                    {selectedAudit.length === 0 ? (
                      <Alert severity="info">当前记忆还没有额外治理审计。</Alert>
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
                <Typography variant="h6">当前认知待办</Typography>
                {agenda?.items.length ? (
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>标题</TableCell>
                        <TableCell>状态</TableCell>
                        <TableCell>优先级</TableCell>
                        <TableCell>下次复查条件</TableCell>
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
                  <Alert severity="info">当前没有待办 agenda 项。</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </>
      ) : null}
    </Stack>
  );
}
