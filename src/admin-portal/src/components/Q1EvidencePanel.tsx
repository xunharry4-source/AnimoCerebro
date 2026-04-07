import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { DataGrid, GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { useMemo } from "react";

import { Q1PreprocessedEvidence, WorkspaceDomainInferenceView } from "../pages/nine-questions/nineQuestionsApi";

function getHealthChipColor(
  value?: string | null,
): "default" | "success" | "warning" | "error" {
  const normalized = String(value || "").toLowerCase();
  if (["healthy", "ok", "low", "normal", "online"].includes(normalized)) {
    return "success";
  }
  if (["degraded", "degrade", "medium", "warn", "warning", "unknown"].includes(normalized)) {
    return "warning";
  }
  if (["offline", "high", "critical", "error", "failed"].includes(normalized)) {
    return "error";
  }
  return "default";
}

function renderChipArray(
  entries: Array<{ key: string; label: string; color?: "default" | "primary" | "secondary" | "error" | "info" | "success" | "warning"; variant?: "filled" | "outlined" }>,
  fallback: string,
) {
  if (entries.length === 0) {
    return <Chip label={fallback} variant="outlined" />;
  }

  return (
    <>
      {entries.map((entry) => (
        <Chip
          key={entry.key}
          label={entry.label}
          color={entry.color || "default"}
          variant={entry.variant || "filled"}
        />
      ))}
    </>
  );
}

export function Q1EvidencePanel({
  evidence,
  inference,
  providerName,
  elapsedMs,
}: {
  evidence: Q1PreprocessedEvidence;
  inference: WorkspaceDomainInferenceView | null | undefined;
  providerName: string | null;
  elapsedMs: number;
}) {
  const structureRows = useMemo(
    () => [
      ...evidence.workspace_structure.directory_tree_rows.map((row) => ({
        id: row.row_id,
        category: "目录层级",
        label: row.label,
        detail: row.summary || row.path,
        depth: row.depth,
        severity: row.kind,
      })),
      ...evidence.workspace_structure.candidate_group_details.map((group) => ({
        id: group.group_id,
        category: "候选分组",
        label: group.label,
        detail: group.summary || (typeof group.file_count === "number" ? `file_count=${group.file_count}` : "-"),
        depth: 0,
        severity: "group",
      })),
      ...evidence.workspace_structure.obvious_risk_file_details.map((risk, index) => ({
        id: `risk-${index}-${risk.path}`,
        category: "风险文件",
        label: risk.path,
        detail: [risk.severity, risk.reason].filter(Boolean).join(" | ") || "-",
        depth: 0,
        severity: risk.severity || "risk",
      })),
    ],
    [evidence],
  );

  const structureColumns = useMemo<GridColDef[]>(
    () => [
      { field: "category", headerName: "分区", minWidth: 120, flex: 0.55 },
      {
        field: "label",
        headerName: "对象",
        minWidth: 220,
        flex: 0.95,
        renderCell: (params: GridRenderCellParams<any, string>) => (
          <Box sx={{ pl: `${Number(params.row.depth || 0) * 2}px`, width: "100%" }}>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>
              {params.value}
            </Typography>
          </Box>
        ),
      },
      { field: "detail", headerName: "摘要", minWidth: 260, flex: 1.4 },
    ],
    [],
  );

  const suffixChips = Object.entries(evidence.workspace_structure.suffix_distribution).map(([suffix, count]) => ({
    key: suffix,
    label: `${suffix}: ${count}`,
    color: "primary" as const,
  }));
  const keywordChips = Object.entries(evidence.workspace_structure.high_frequency_filename_keywords).map(
    ([keyword, count]) => ({
      key: keyword,
      label: `${keyword}: ${count}`,
      color: "secondary" as const,
      variant: "outlined" as const,
    }),
  );
  const topDirChips = evidence.workspace_structure.top_level_dirs.map((directory) => ({
    key: directory,
    label: directory,
    color: "info" as const,
    variant: "outlined" as const,
  }));
  const groupChips = evidence.workspace_structure.candidate_groups.map((group) => ({
    key: group,
    label: group,
    color: "success" as const,
    variant: "outlined" as const,
  }));

  return (
    <Grid container spacing={3} sx={{ mt: 0.5 }}>
      <Grid size={{ xs: 12, xl: 5 }}>
        <Card variant="outlined" sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              物理与环境态势区
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              <Chip
                label={`网络健康度: ${evidence.physical_and_environment.network_health || "unknown"}`}
                color={getHealthChipColor(evidence.physical_and_environment.network_health_status)}
              />
              <Chip
                label={`内存压力: ${evidence.physical_and_environment.memory_pressure || "unknown"}`}
                color={getHealthChipColor(evidence.physical_and_environment.memory_pressure_status)}
              />
              <Chip label={`Provider: ${providerName || "-"}`} variant="outlined" />
              <Chip label={`耗时: ${elapsedMs} ms`} variant="outlined" />
            </Stack>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              环境摘要
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              {renderChipArray(
                evidence.physical_and_environment.environment_summary.map((item, index) => ({
                  key: `${index}-${item}`,
                  label: item,
                  variant: "outlined",
                })),
                "无环境摘要",
              )}
            </Stack>
            <Typography variant="subtitle2" gutterBottom>
              EnvironmentEvent
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              {renderChipArray(
                Object.entries(evidence.physical_and_environment.environment_event).map(([key, value]) => ({
                  key,
                  label: `${key}: ${String(value)}`,
                  variant: "outlined",
                })),
                "无 EnvironmentEvent 字段",
              )}
            </Stack>
            <Typography variant="subtitle2" gutterBottom>
              PhysicalHostState
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {renderChipArray(
                Object.entries(evidence.physical_and_environment.physical_host_state).map(([key, value]) => ({
                  key,
                  label: `${key}: ${String(value)}`,
                  variant: "outlined",
                })),
                "无 PhysicalHostState 字段",
              )}
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12, xl: 7 }}>
        <Card variant="outlined" sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              工作区本地统计与结构区
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              <Chip
                label={`文件总数: ${
                  typeof evidence.workspace_structure.file_total_count === "number"
                    ? evidence.workspace_structure.file_total_count
                    : "-"
                }`}
                color="primary"
              />
              {renderChipArray(topDirChips, "无顶层目录")}
              {renderChipArray(groupChips, "无候选分组")}
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {evidence.workspace_structure.directory_hierarchy_summary || "当前没有目录层级摘要。"}
            </Typography>
            <Box sx={{ width: "100%", mb: 2 }}>
              <DataGrid
                autoHeight
                disableRowSelectionOnClick
                disableVirtualization
                hideFooter
                rows={structureRows}
                columns={structureColumns}
                getRowHeight={() => "auto"}
                sx={{
                  backgroundColor: "background.paper",
                  "& .MuiDataGrid-cell": {
                    alignItems: "center",
                    py: 1,
                  },
                }}
              />
            </Box>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              文件后缀分布
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              {renderChipArray(suffixChips, "无后缀统计")}
            </Stack>
            <Typography variant="subtitle2" gutterBottom>
              高频文件名关键词
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {renderChipArray(keywordChips, "无关键词统计")}
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12, xl: 6 }}>
        <Card variant="outlined" sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              内容采样与证据区
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              <Chip label={`采样文件数: ${evidence.workspace_content_sampling.sample_count}`} color="info" />
              <Chip label={`异常片段数: ${evidence.workspace_content_sampling.anomaly_count}`} color="warning" />
            </Stack>
            <Stack spacing={1.5}>
              {evidence.workspace_content_sampling.long_text_evidence.map((block) => (
                <Accordion key={block.evidence_id} data-testid="q1-long-text-accordion" defaultExpanded={false}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Stack spacing={0.5}>
                      <Typography variant="subtitle2">{block.label}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {block.source}
                        {block.path ? ` | ${block.path}` : ""}
                      </Typography>
                    </Stack>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box
                      component="pre"
                      sx={{
                        m: 0,
                        p: 2,
                        bgcolor: "action.hover",
                        borderRadius: 1,
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        fontSize: "0.85rem",
                      }}
                    >
                      {block.text}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              ))}
              {evidence.workspace_content_sampling.long_text_evidence.length === 0 ? (
                <Alert severity="info">当前没有可展开的长文本采样证据。</Alert>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
      </Grid>

      <Grid size={{ xs: 12, xl: 6 }}>
        <Card
          variant="outlined"
          sx={{
            height: "100%",
            borderColor: "warning.main",
            boxShadow: (theme) => `0 0 0 1px ${theme.palette.warning.light} inset`,
          }}
        >
          <CardContent>
            <Typography variant="h6" gutterBottom>
              大模型终极推断区
            </Typography>
            {inference ? (
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" gutterBottom>
                        primary_domain
                      </Typography>
                      <Chip label={inference.primary_domain} color="warning" />
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" gutterBottom>
                        confidence
                      </Typography>
                      <Chip label={`${(inference.confidence * 100).toFixed(1)}%`} color="warning" variant="outlined" />
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" gutterBottom>
                        secondary_domains
                      </Typography>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        {renderChipArray(
                          inference.secondary_domains.map((domain) => ({
                            key: domain,
                            label: domain,
                            color: "info",
                          })),
                          "无次领域",
                        )}
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" gutterBottom>
                        reasoning_summary
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {inference.reasoning_summary}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" gutterBottom>
                        uncertainties
                      </Typography>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        {renderChipArray(
                          inference.uncertainties.map((item) => ({
                            key: item,
                            label: item,
                            color: "warning",
                            variant: "outlined",
                          })),
                          "无不确定性",
                        )}
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle2" gutterBottom>
                        suggested_first_step
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {inference.suggested_first_step}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            ) : (
              <Alert severity="warning">本次返回未携带完整的 WorkspaceDomainInference 六字段。</Alert>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
}

export default Q1EvidencePanel;
