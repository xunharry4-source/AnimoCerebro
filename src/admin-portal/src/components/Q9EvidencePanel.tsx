import React from "react";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import AdjustIcon from "@mui/icons-material/Adjust";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";

import {
  Q9ActionPostureInferenceView,
  Q9PreprocessedEvidence,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q9EvidencePanelProps {
  evidence: Q9PreprocessedEvidence;
  inference: Q9ActionPostureInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

function loadChipColor(load: string): "success" | "warning" | "error" | "default" {
  const normalized = load.toLowerCase();
  if (normalized === "high" || normalized === "heavy" || normalized === "critical") {
    return "error";
  }
  if (normalized === "medium" || normalized === "elevated") {
    return "warning";
  }
  if (normalized === "low" || normalized === "stable") {
    return "success";
  }
  return "default";
}

function riskChipColor(risk: string): "success" | "warning" | "error" | "default" {
  const normalized = risk.toLowerCase();
  if (normalized === "zero_tolerance") {
    return "error";
  }
  if (normalized === "fast_fail" || normalized === "guarded") {
    return "warning";
  }
  if (normalized === "balanced" || normalized === "low_risk") {
    return "success";
  }
  return "default";
}

function progressColor(value: number): "primary" | "warning" | "error" {
  if (value < 20) {
    return "error";
  }
  if (value < 40) {
    return "warning";
  }
  return "primary";
}

export const Q9EvidencePanel: React.FC<Q9EvidencePanelProps> = ({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const snapshot = evidence?.cognitive_snapshot;
  const selfModel = evidence?.self_model;
  const budget = evidence?.reasoning_budget;
  const weaknesses = selfModel?.recent_weaknesses ?? [];
  const snapshotEntries = Object.entries(snapshot?.q1_to_q8_snapshot ?? {});

  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {providerName ? (
            <Chip
              label={`Posture Engine: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          ) : null}
          {elapsedMs > 0 ? <Chip label={`Latency: ${elapsedMs}ms`} size="small" variant="outlined" /> : null}
        </Box>
      )}

      <Accordion defaultExpanded={false} data-testid="q9-snapshot-accordion">
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ fontWeight: "bold" }}>
            【Q1-Q8 认知快照聚合区】
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
            <Chip label={`认知不确定性: ${snapshot?.uncertainty_count ?? 0}`} color="warning" variant="outlined" />
            <Chip label={`累计红线数: ${snapshot?.absolute_red_line_count ?? 0}`} color="error" />
          </Stack>
          <List dense sx={{ py: 0 }}>
            {snapshotEntries.map(([key, value]) => (
              <ListItem key={key} disableGutters sx={{ py: 0.5, display: "block" }}>
                <Typography variant="subtitle2">{key}</Typography>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    mt: 0.5,
                    p: 1.5,
                    bgcolor: "action.hover",
                    borderRadius: 1,
                    overflowX: "auto",
                    whiteSpace: "pre-wrap",
                    fontSize: "0.8rem",
                  }}
                >
                  <code>{JSON.stringify(value, null, 2)}</code>
                </Box>
              </ListItem>
            ))}
            {snapshotEntries.length === 0 ? (
              <ListItem disableGutters>
                <ListItemText primary="暂无 Q1-Q8 快照数据" />
              </ListItem>
            ) : null}
          </List>
        </AccordionDetails>
      </Accordion>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【自我模型与预算压力区】
              </Typography>

              <Typography variant="subtitle2" gutterBottom>
                认知负荷与稳定性
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                <Chip
                  label={selfModel?.cognitive_load || "unknown"}
                  color={loadChipColor(selfModel?.cognitive_load || "unknown")}
                  data-testid="q9-cognitive-load-chip"
                />
                {selfModel?.stability_level ? (
                  <Chip label={`稳定性: ${selfModel.stability_level}`} variant="outlined" />
                ) : null}
                {typeof selfModel?.confidence_drift === "number" ? (
                  <Chip label={`confidence_drift=${selfModel.confidence_drift}`} variant="outlined" />
                ) : null}
              </Stack>

              <Typography variant="subtitle2" gutterBottom>
                近期弱点
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q9-weakness-zone">
                {weaknesses.map((weakness, index) => (
                  <Chip
                    key={`${weakness.pattern_id ?? weakness.pattern_type ?? index}`}
                    label={`${weakness.pattern_type} | ${weakness.severity ?? "unknown"} | x${weakness.frequency ?? 1}`}
                    color={loadChipColor(String(weakness.severity || "unknown"))}
                    variant="outlined"
                  />
                ))}
                {weaknesses.length === 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    暂无近期弱点记录
                  </Typography>
                ) : null}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【推理资源预算与消耗态势】
              </Typography>
              <Stack spacing={2} sx={{ mt: 2 }}>
                <Box>
                  <Typography variant="caption" display="block">
                    算力剩余率 (Compute): {((budget?.compute_remaining_ratio ?? 0) * 100).toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(budget?.compute_remaining_ratio ?? 0) * 100}
                    color={progressColor((budget?.compute_remaining_ratio ?? 0) * 100)}
                  />
                </Box>
                <Box>
                  <Typography variant="caption" display="block">
                    Token 剩余率 (Tokens): {((budget?.token_remaining_ratio ?? 0) * 100).toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(budget?.token_remaining_ratio ?? 0) * 100}
                    color={progressColor((budget?.token_remaining_ratio ?? 0) * 100)}
                  />
                </Box>
                <Box>
                  <Typography variant="caption" display="block">
                    推演时间剩余 (Time): {((budget?.time_remaining_ratio ?? 0) * 100).toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(budget?.time_remaining_ratio ?? 0) * 100}
                    color={progressColor((budget?.time_remaining_ratio ?? 0) * 100)}
                  />
                </Box>
                <Alert severity={loadChipColor(budget?.budget_pressure || "unknown") === "error" ? "error" : "info"} icon={false}>
                  预算压力: {budget?.budget_pressure || "unknown"}
                </Alert>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card
            variant="outlined"
            sx={{
              borderWidth: 2,
              borderColor: "warning.main",
              bgcolor: "rgba(237, 108, 2, 0.05)",
            }}
          >
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【终极行动姿态定调区】
              </Typography>
              {inference ? (
                <Stack spacing={2}>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q9-posture-chip-zone">
                    <Chip
                      label={inference.evaluation_style}
                      color={riskChipColor(inference.evaluation_style)}
                      sx={{ fontSize: "0.95rem", fontWeight: "bold" }}
                    />
                    <Chip
                      label={inference.risk_tolerance}
                      color={riskChipColor(inference.risk_tolerance)}
                      sx={{ fontSize: "0.95rem", fontWeight: "bold" }}
                      data-testid="q9-risk-tolerance-chip"
                    />
                  </Stack>

                  <Alert severity="info" data-testid="q9-action-rhythm-alert">
                    行动节奏: {inference.action_rhythm || "-"}
                  </Alert>
                  <Alert
                    severity={/human confirmation|human/i.test(inference.confirmation_strategy || "") ? "warning" : "info"}
                    data-testid="q9-confirmation-strategy-alert"
                  >
                    确认策略: {inference.confirmation_strategy || "-"}
                  </Alert>

                  <List dense sx={{ py: 0 }}>
                    <ListItem disableGutters>
                      <AdjustIcon fontSize="small" color="success" style={{ marginRight: 8 }} />
                      <ListItemText primary={inference.evolution_direction || "Stable"} secondary="演化焦点 (Evolution Direction)" />
                    </ListItem>
                  </List>
                </Stack>
              ) : (
                <Alert severity="info">等待姿态推演数据同步（可能正在执行或鉴权失败）。</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q9EvidencePanel;
