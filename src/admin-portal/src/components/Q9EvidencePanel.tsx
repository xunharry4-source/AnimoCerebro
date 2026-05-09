import React from "react";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useTranslation } from "react-i18next";
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
  providerName,
  elapsedMs = 0,
}) => {
  const { t } = useTranslation();
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
              label={`${t("nineQuestions.postureEngine")}: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          ) : null}
          {elapsedMs > 0 ? <Chip label={`${t("common.latency")}: ${elapsedMs}ms`} size="small" variant="outlined" /> : null}
        </Box>
      )}

      <Accordion defaultExpanded={false} data-testid="q9-snapshot-accordion">
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ fontWeight: "bold" }}>
            {t("nineQuestions.q1Q8SnapshotAggregation")}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
            <Chip label={`${t("nineQuestions.cognitiveUncertainty")}: ${snapshot?.uncertainty_count ?? 0}`} color="warning" variant="outlined" />
            <Chip label={`${t("nineQuestions.cumulativeRedLines")}: ${snapshot?.absolute_red_line_count ?? 0}`} color="error" />
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
                <ListItemText primary={t("nineQuestions.noQ1Q8SnapshotData")} />
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
                {t("nineQuestions.selfModelBudgetPressure")}
              </Typography>

              <Typography variant="subtitle2" gutterBottom>
                {t("nineQuestions.cognitiveLoadStability")}
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                <Chip
                  label={selfModel?.cognitive_load || "unknown"}
                  color={loadChipColor(selfModel?.cognitive_load || "unknown")}
                  data-testid="q9-cognitive-load-chip"
                />
                {selfModel?.stability_level ? (
                  <Chip label={`${t("nineQuestions.stabilityLevel")}: ${selfModel.stability_level}`} variant="outlined" />
                ) : null}
                {typeof selfModel?.confidence_drift === "number" ? (
                  <Chip label={`confidence_drift=${selfModel.confidence_drift}`} variant="outlined" />
                ) : null}
              </Stack>

              <Typography variant="subtitle2" gutterBottom>
                {t("nineQuestions.recentWeaknesses")}
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
                    {t("nineQuestions.noRecentWeaknesses")}
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
                {t("nineQuestions.reasoningBudgetConsumption")}
              </Typography>
              <Stack spacing={2} sx={{ mt: 2 }}>
                <Box>
                  <Typography variant="caption" display="block">
                    {t("nineQuestions.computeRemainingRate")}: {((budget?.compute_remaining_ratio ?? 0) * 100).toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(budget?.compute_remaining_ratio ?? 0) * 100}
                    color={progressColor((budget?.compute_remaining_ratio ?? 0) * 100)}
                  />
                </Box>
                <Box>
                  <Typography variant="caption" display="block">
                    {t("nineQuestions.tokenRemainingRate")}: {((budget?.token_remaining_ratio ?? 0) * 100).toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(budget?.token_remaining_ratio ?? 0) * 100}
                    color={progressColor((budget?.token_remaining_ratio ?? 0) * 100)}
                  />
                </Box>
                <Box>
                  <Typography variant="caption" display="block">
                    {t("nineQuestions.timeRemainingRate")}: {((budget?.time_remaining_ratio ?? 0) * 100).toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={(budget?.time_remaining_ratio ?? 0) * 100}
                    color={progressColor((budget?.time_remaining_ratio ?? 0) * 100)}
                  />
                </Box>
                <Alert severity={loadChipColor(budget?.budget_pressure || "unknown") === "error" ? "error" : "info"} icon={false}>
                  {t("nineQuestions.budgetPressure")}: {budget?.budget_pressure || "unknown"}
                </Alert>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q9EvidencePanel;
