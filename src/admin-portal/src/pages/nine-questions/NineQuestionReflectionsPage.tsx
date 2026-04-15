import { useEffect, useState } from "react";
import { Alert, Box, CircularProgress, Stack, Typography, Chip, Button } from "@mui/material";
import { useLocation, useSearchParams } from "react-router-dom";

import {
  fetchNineQuestionReflectionDetail,
  fetchNineQuestionReflections,
  NineQuestionReflectionRecord,
  NineQuestionReflectionResult,
} from "./nineQuestionsApi";

export default function NineQuestionReflectionsPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const qId = (searchParams.get("q") || "").trim().toLowerCase();

  const forcedResults = Array.isArray((location.state as any)?.forcedResults)
    ? ((location.state as any).forcedResults as NineQuestionReflectionResult[])
    : [];
  const forcedAt = String((location.state as any)?.forcedAt || "");
  const sourceQuestionId = String((location.state as any)?.sourceQuestionId || "");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [records, setRecords] = useState<NineQuestionReflectionRecord[]>([]);
  const [detail, setDetail] = useState<NineQuestionReflectionRecord | null>(null);

  useEffect(() => {
    void loadReflections();
  }, [qId]);

  const loadReflections = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await fetchNineQuestionReflections(qId || undefined);
      setRecords(items);
      if (items.length > 0) {
        const first = await fetchNineQuestionReflectionDetail(items[0].reflection_id);
        setDetail(first);
      } else {
        setDetail(null);
      }
    } catch (err: any) {
      setError(err?.message || "获取反思结果失败");
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (reflectionId: string) => {
    try {
      const item = await fetchNineQuestionReflectionDetail(reflectionId);
      setDetail(item);
    } catch (err: any) {
      setError(err?.message || "获取反思详情失败");
    }
  };

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            九问反思结果
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {qId ? `当前筛选: ${qId.toUpperCase()}` : "当前筛选: 全部问题"}
          </Typography>
        </Box>
        <Button variant="contained" onClick={() => void loadReflections()}>
          刷新
        </Button>
      </Stack>

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}

      {forcedResults.length > 0 ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          已完成本次强制反思（来源 {sourceQuestionId.toUpperCase() || "Q?"}，触发时间 {forcedAt || "-"}）。
          共返回 {forcedResults.length} 条结果。
        </Alert>
      ) : null}

      {forcedResults.length > 0 ? (
        <Box sx={{ mb: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            本次强制反思结果
          </Typography>
          <Stack spacing={1}>
            {forcedResults.map((item) => (
              <Alert key={`${item.question_id}-${item.created_at}`} severity={item.analysis.effective ? "success" : "warning"}>
                {item.question_id.toUpperCase()} | score: {item.analysis.effectiveness_score.toFixed(3)} | need_upgrade: {String(item.analysis.need_upgrade)}
                {item.analysis.missing_data.length > 0 ? ` | 缺失: ${item.analysis.missing_data.join("；")}` : ""}
                {item.reflection_error ? ` | fallback: ${item.reflection_error}` : ""}
              </Alert>
            ))}
          </Stack>
        </Box>
      ) : null}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Box sx={{ flex: 1, minWidth: 260 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            反思记录
          </Typography>
          <Stack spacing={1}>
            {records.map((item) => {
              const itemQId = String(item.context?.question_id || "").toLowerCase();
              const score = Number(item.context?.analysis?.effectiveness_score || 0);
              const effective = Boolean(item.context?.analysis?.effective);
              return (
                <Box
                  key={item.reflection_id}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 2,
                    p: 1.5,
                    cursor: "pointer",
                  }}
                  onClick={() => void loadDetail(item.reflection_id)}
                >
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                    <Typography variant="subtitle2">{itemQId.toUpperCase() || "Q?"}</Typography>
                    <Chip
                      size="small"
                      color={effective ? "success" : "warning"}
                      label={effective ? "有效" : "待优化"}
                    />
                  </Stack>
                  <Typography variant="caption" color="text.secondary">
                    score: {Number.isFinite(score) ? score.toFixed(3) : "0.000"}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 0.5 }}>
                    {item.summary}
                  </Typography>
                </Box>
              );
            })}
            {records.length === 0 ? (
              <Alert severity="info">暂无反思记录，请先在九问页执行“强制反思”。</Alert>
            ) : null}
          </Stack>
        </Box>

        <Box sx={{ flex: 1.2, minWidth: 300 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            反思详情
          </Typography>
          {detail ? (
            <Stack spacing={1.2}>
              <Typography variant="subtitle1">{detail.subject}</Typography>
              <Typography variant="body2" color="text.secondary">
                {detail.created_at}
              </Typography>
              <Typography variant="body2">{detail.summary}</Typography>
              <Alert severity="info">
                need_upgrade: {String(Boolean(detail.context?.analysis?.need_upgrade))}
                {" | "}
                effectiveness_score: {String(detail.context?.analysis?.effectiveness_score ?? "-")}
              </Alert>
              <Typography variant="subtitle2">缺失数据</Typography>
              <Typography variant="body2">
                {Array.isArray(detail.context?.analysis?.missing_data)
                  ? detail.context.analysis.missing_data.join("；") || "无"
                  : "无"}
              </Typography>
              <Typography variant="subtitle2">无用数据</Typography>
              <Typography variant="body2">
                {Array.isArray(detail.context?.analysis?.useless_data)
                  ? detail.context.analysis.useless_data.join("；") || "无"
                  : "无"}
              </Typography>
              <Typography variant="subtitle2">为达成本问目标仍缺</Typography>
              <Typography variant="body2">{String(detail.context?.analysis?.missing_for_goal || "无")}</Typography>
            </Stack>
          ) : (
            <Alert severity="info">请选择一条反思记录查看详情。</Alert>
          )}
        </Box>
      </Stack>
    </Box>
  );
}
