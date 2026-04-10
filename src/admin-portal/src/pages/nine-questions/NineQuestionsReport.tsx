import { useTranslation } from "react-i18next";
import { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import { useNavigate } from "react-router-dom";

import {
  ReportPayload,
  fetchNineQuestionsStatus,
  getQuestionDisplayLabel,
  runAllNineQuestions,
} from "./nineQuestionsApi";

export default function NineQuestionsReport() {
  const { t } = useTranslation();
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
      const data = await fetchNineQuestionsStatus();
      setReport(data.report);
      setNotice(data.notice);
    } catch (err: any) {
      setError(err?.message || t("nineQuestions.fetchError"));
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
      setNotice(t("nineQuestions.forceRunSuccess"));
    } catch (err: any) {
      setError(err?.message || t("nineQuestions.forceRunError"));
    } finally {
      setRunningAll(false);
    }
  };

  const columns: GridColDef[] = [
    { field: "question_label", headerName: t("nineQuestions.label"), flex: 1.1, minWidth: 190 },
    { field: "title", headerName: t("nineQuestions.name"), flex: 0.8, minWidth: 120 },
    { field: "cache_status", headerName: t("nineQuestions.cacheStatus"), flex: 0.75, minWidth: 120 },
    { field: "timestamp", headerName: t("nineQuestions.lastUpdate"), flex: 1, minWidth: 180 },
    { field: "provider_name", headerName: t("nineQuestions.provider"), flex: 1, minWidth: 170 },
    { field: "summary", headerName: t("nineQuestions.summary"), flex: 1.4, minWidth: 240 },
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
          <Typography variant="h6">{t("nineQuestions.initializingTitle")}</Typography>
          <Typography variant="body2" color="text.secondary">
            {report.status_message || t("nineQuestions.initializingMessage")}
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
            {t("app.nav.nineQuestions.title")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t("nineQuestions.subtitle")}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Session: {report?.session_id || "-"} | Snapshot: v{report?.snapshot_version ?? 0} / rev{" "}
            {report?.revision ?? 0}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={() => void loadReport()} disabled={runningAll}>
            {t("common.refreshList")}
          </Button>
          <Button variant="outlined" onClick={() => void handleForceRunAll()} disabled={runningAll}>
            {runningAll ? t("nineQuestions.running") : t("nineQuestions.forceRun")}
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
