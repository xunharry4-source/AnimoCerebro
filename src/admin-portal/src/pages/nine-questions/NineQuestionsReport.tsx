import { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import { useNavigate } from "react-router-dom";

import {
  ReportPayload,
  fetchNineQuestionsReport,
  getQuestionDisplayLabel,
  runAllNineQuestions,
} from "./nineQuestionsApi";

export default function NineQuestionsReport() {
  const navigate = useNavigate();
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningAll, setRunningAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void loadReport();
  }, []);

  useEffect(() => {
    if (report?.status !== "initializing") {
      return;
    }
    const timer = window.setTimeout(() => {
      void loadReport();
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [report?.status]);

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchNineQuestionsReport();
      setReport(data.report);
      setNotice(data.notice);
    } catch (err: any) {
      setError(err?.message || "获取九问报告失败");
    } finally {
      setLoading(false);
    }
  };

  const handleForceRunAll = async () => {
    setRunningAll(true);
    setError(null);
    try {
      await runAllNineQuestions(true);
      await loadReport();
      setNotice("已强制执行一轮正式九问流程，列表已刷新。");
    } catch (err: any) {
      setError(err?.message || "强制执行九问失败");
    } finally {
      setRunningAll(false);
    }
  };

  const columns: GridColDef[] = [
    { field: "question_label", headerName: "问题标识", flex: 1.1, minWidth: 190 },
    { field: "title", headerName: "问题名称", flex: 0.8, minWidth: 120 },
    { field: "cache_status", headerName: "主脑缓存状态", flex: 0.75, minWidth: 120 },
    { field: "timestamp", headerName: "最后更新时间", flex: 1, minWidth: 180 },
    { field: "provider_name", headerName: "Provider", flex: 1, minWidth: 170 },
    { field: "summary", headerName: "摘要", flex: 1.4, minWidth: 240 },
  ];

  if (loading) {
    return <CircularProgress />;
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  const rows =
    report?.questions.map((question) => ({
      id: question.question_id,
      ...question,
      question_label: getQuestionDisplayLabel(question.question_id),
      cache_status: question.cache_status || "未知",
      provider_name: question.provider_name || "-",
    })) || [];

  if (report?.status === "initializing") {
    return (
      <Box sx={{ py: 8, display: "grid", placeItems: "center" }}>
        <Stack spacing={2} alignItems="center">
          <CircularProgress />
          <Typography variant="h6">大脑冷启动中：正在执行全量九问推演...</Typography>
          <Typography variant="body2" color="text.secondary">
            {report.status_message || "正在构建初始认知快照，请稍候。"}
          </Typography>
        </Stack>
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            9问测试页
          </Typography>
          <Typography variant="body2" color="text.secondary">
            九问总览列表，支持从真实主脑缓存钻取到详情与独立沙箱测试。
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Session: {report?.session_id || "-"} | Snapshot: v{report?.snapshot_version ?? 0} / rev{" "}
            {report?.revision ?? 0}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={() => void loadReport()} disabled={runningAll}>
            刷新列表
          </Button>
          <Button variant="outlined" onClick={() => void handleForceRunAll()} disabled={runningAll}>
            {runningAll ? "正在执行 9 问..." : "强制运行一次 9 问"}
          </Button>
        </Stack>
      </Stack>

      {notice ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          {notice}
        </Alert>
      ) : null}

      <Box sx={{ width: "100%" }}>
        <DataGrid
          autoHeight
          disableRowSelectionOnClick
          disableVirtualization
          rows={rows}
          columns={columns}
          pageSizeOptions={[9]}
          initialState={{
            pagination: {
              paginationModel: {
                pageSize: 9,
                page: 0,
              },
            },
          }}
          onRowClick={(params) => navigate(`/console/nine-questions/${params.row.question_id}`)}
          sx={{
            backgroundColor: "background.paper",
            "& .MuiDataGrid-row": { cursor: "pointer" },
          }}
        />
      </Box>
    </Box>
  );
}
