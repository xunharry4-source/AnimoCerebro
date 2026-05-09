import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

type AuditFlowStart = {
  audit_id: string;
  flow_type: string;
  source_module: string;
  parent_audit_id?: string | null;
  status: string;
  started_at: string;
  ended_at?: string | null;
  question_driver_refs: string[];
};

type AuditTraceStartsPage = {
  items: AuditFlowStart[];
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
};

const FLOW_LABELS: Record<string, string> = {
  nine_questions: "9 问审计链",
  reflection: "反思审计链",
  learning: "学习审计链",
  external_connectors: "外部连接器审计链",
};

const TABLE_PATHS: Record<string, string> = {
  nine_questions: "/console/audit/nine_questions/table",
  reflection: "/console/audit/reflection/table",
  learning: "/console/audit/learning/table",
  external_connectors: "/console/external-connectors",
};

function formatFlowTitle(row: AuditFlowStart): string {
  const label = FLOW_LABELS[row.flow_type] || row.flow_type || "审计链";
  const started = row.started_at ? new Date(row.started_at).toLocaleString() : "unknown-time";
  return `${label} · ${started}`;
}

function workflowPath(row: AuditFlowStart): string {
  return `/console/audit/${encodeURIComponent(row.flow_type || "unknown")}/workflow`;
}

async function fetchAuditFlowStarts(page: number, pageSize: number): Promise<AuditTraceStartsPage> {
  const response = await fetch(`/api/web/audit/trace-starts?page=${page + 1}&page_size=${pageSize}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      (typeof data?.detail === "string" && data.detail) ||
      (typeof data?.detail?.message === "string" && data.detail.message) ||
      `获取审计起点失败（HTTP ${response.status}）`;
    throw new Error(detail);
  }
  if (!Array.isArray(data?.items) || typeof data.total_items !== "number") {
    throw new Error("审计起点接口返回格式错误：期望分页对象。");
  }
  return data as AuditTraceStartsPage;
}

export default function AuditTraceCenterPage() {
  const [rows, setRows] = useState<AuditFlowStart[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [totalItems, setTotalItems] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchAuditFlowStarts(page, pageSize);
        if (active) {
          setRows(payload.items);
          setTotalItems(payload.total_items);
        }
      } catch (err: any) {
        if (active) {
          setRows([]);
          setTotalItems(0);
          setError(err?.message || "获取审计起点失败");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [page, pageSize]);

  return (
    <Box data-testid="audit-trace-center-page" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Box>
        <Typography variant="h4" gutterBottom>
          审计与溯源中心
        </Typography>
          <Typography variant="body2" color="text.secondary">
          这里显示真实运行产生的根审计链起点。9 问触发的反思、学习、任务会挂在同一条链下；只有从头启动的行为才会出现在这里。
        </Typography>
      </Box>

      <Card variant="outlined">
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" alignItems={{ xs: "flex-start", md: "center" }} spacing={2} sx={{ mb: 2 }}>
            <Box>
              <Typography variant="h6">审计链起点列表</Typography>
              <Typography variant="body2" color="text.secondary">
                数据来自 audit_flows 中 parent_audit_id 为空的根链记录，页面不再创建固定入口。
              </Typography>
            </Box>
            <Stack direction="row" spacing={1}>
              <Button component={RouterLink} to="/console/audit/model-provider" variant="outlined">
                查看底层模型调用回放
              </Button>
              <Button component={RouterLink} to="/console/audit/review-ledger" variant="outlined">
                复查台账
              </Button>
            </Stack>
          </Stack>

          {loading ? (
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ py: 3 }}>
              <CircularProgress size={22} />
              <Typography variant="body2" color="text.secondary">
                正在读取真实审计链起点...
              </Typography>
            </Stack>
          ) : error ? (
            <Alert severity="error">{error}</Alert>
          ) : rows.length === 0 ? (
            <Alert severity="info">当前没有真实审计链起点。</Alert>
          ) : (
            <>
              <Table data-testid="audit-trace-start-table">
                <TableHead>
                  <TableRow>
                    <TableCell>起点</TableCell>
                    <TableCell>来源</TableCell>
                    <TableCell>状态</TableCell>
                    <TableCell>时间</TableCell>
                    <TableCell>显示方式</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.audit_id} data-testid={`audit-trace-start-${row.audit_id}`}>
                      <TableCell sx={{ minWidth: 300 }}>
                        <Stack spacing={1}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                            {formatFlowTitle(row)}
                          </Typography>
                          <Chip size="small" label={`audit_id: ${row.audit_id}`} variant="outlined" sx={{ alignSelf: "flex-start", fontFamily: "monospace" }} />
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{row.source_module || "-"}</Typography>
                        {row.question_driver_refs?.length ? (
                          <Typography variant="caption" color="text.secondary">
                            {row.question_driver_refs.join(", ")}
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <Chip size="small" label={row.status} color={row.status === "completed" ? "success" : row.status === "failed" ? "error" : "warning"} />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{row.started_at || "-"}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {row.ended_at || "未结束"}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ minWidth: 260 }}>
                        <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                          <Button component={RouterLink} to={workflowPath(row)} variant="contained">
                            工作流查看
                          </Button>
                          {TABLE_PATHS[row.flow_type] ? (
                            <Button component={RouterLink} to={TABLE_PATHS[row.flow_type]} variant="outlined">
                              表格查看
                            </Button>
                          ) : null}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <TablePagination
                component="div"
                count={totalItems}
                page={page}
                onPageChange={(_, nextPage) => setPage(nextPage)}
                rowsPerPage={pageSize}
                rowsPerPageOptions={[25, 50, 100]}
                onRowsPerPageChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setPage(0);
                }}
              />
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
