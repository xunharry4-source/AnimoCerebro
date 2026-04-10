import React from "react";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GavelIcon from "@mui/icons-material/Gavel";
import {
  Q2PreprocessedEvidence,
  Q2WhoAmIInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q2EvidencePanelProps {
  evidence: Q2PreprocessedEvidence;
  inference: Q2WhoAmIInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

export const Q2EvidencePanel: React.FC<Q2EvidencePanelProps> = ({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const { t } = useTranslation();
  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {/* Partition 0: Inference Metadata (G31A Transparency) */}
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && (
            <Chip
              label={`${t("nineQuestions.idEngine")}: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          )}
          {elapsedMs > 0 && (
            <Chip
              label={`${t("common.latency")}: ${elapsedMs}ms`}
              size="small"
              variant="outlined"
            />
          )}
        </Box>
      )}

      <Grid container spacing={3}>
        {/* 1. Q1 前置态势聚合区 */}
        <Grid size={{ xs: 12, xl: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                {t("nineQuestions.q1PreAggregation")}
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                <Chip label={`${t("nineQuestions.primaryDomain")}: ${evidence.q1_summary.primary_domain}`} color="primary" />
                {evidence.q1_summary.secondary_domains.map((d, i) => (
                  <Chip key={i} label={`${t("nineQuestions.secondaryDomain")}: ${d}`} variant="outlined" size="small" />
                ))}
              </Stack>
              {evidence.q1_summary.risk_summary && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                  {t("nineQuestions.riskSummary")}: {evidence.q1_summary.risk_summary}
                </Alert>
              )}
              <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.uncertaintyBlindspots")}:</Typography>
              <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                {evidence.q1_summary.uncertainties.map((u, i) => (
                  <Chip key={i} label={u} size="small" variant="outlined" />
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* 2. 身份内核与不可绕过约束区 */}
        <Grid size={{ xs: 12, xl: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                {t("nineQuestions.identityKernel")}
              </Typography>
              <Typography variant="subtitle2" color="error" gutterBottom>{t("nineQuestions.hardConstraints")}:</Typography>
              <List dense sx={{ mb: 2 }}>
                {evidence.identity_kernel.non_bypassable_constraints.map((c, i) => (
                  <ListItem key={i} sx={{ py: 0 }}>
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <GavelIcon fontSize="small" color="error" />
                    </ListItemIcon>
                    <ListItemText primary={c} primaryTypographyProps={{ variant: "body2", fontWeight: "bold" }} />
                  </ListItem>
                ))}
              </List>
              
              <Accordion variant="outlined">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2" color="primary">{t("nineQuestions.metaMotivation")}</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="body2" sx={{ bgcolor: 'action.hover', p: 1, borderRadius: 1 }}>
                    {evidence.identity_kernel.meta_motivation}
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion variant="outlined" sx={{ mt: 1 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2" color="secondary">{t("nineQuestions.valuesProhibition")}</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="body2" sx={{ bgcolor: 'action.selected', p: 1, borderRadius: 1 }}>
                    {evidence.identity_kernel.values_prohibition}
                  </Typography>
                </AccordionDetails>
              </Accordion>
            </CardContent>
          </Card>
        </Grid>

        {/* 3. 人工干预与回执记录 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                {t("nineQuestions.manualIntervention")}
              </Typography>
              {evidence.manual_intervention?.latest_manual_role_modification ? (
                <Box sx={{ p: 1.5, borderLeft: '4px solid', borderColor: 'warning.main', bgcolor: 'warning.light', color: 'warning.contrastText' }}>
                  <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{t("nineQuestions.latestCorrection")}: {evidence.manual_intervention.latest_manual_role_modification}</Typography>
                  <Typography variant="caption" display="block">{t("nineQuestions.appliedAt")}: {evidence.manual_intervention.applied_at || t("common.unknown")}</Typography>
                </Box>
              ) : (
                <Alert severity="info">
                  {t("nineQuestions.noManualIntervention")}
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* 4. 大模型身份最终推断区 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ border: '2px solid', borderColor: 'primary.main' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom color="primary.main" sx={{ fontWeight: 'bold' }}>
                {t("nineQuestions.inferenceZone")}
              </Typography>
              {inference ? (
                <Stack spacing={2}>
                  <Grid container spacing={2}>
                    <Grid size={{ xs: 12, md: 6 }}>
                      <Typography variant="subtitle2" gutterBottom>{t("nineQuestions.roleProfile")}:</Typography>
                      <Box sx={{ bgcolor: 'background.default', p: 2, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                        <Typography variant="body2"><strong>{t("nineQuestions.identityRole")}:</strong> {inference.role_profile.identity_role}</Typography>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="body2"><strong>{t("nineQuestions.activeRole")}:</strong> {inference.role_profile.active_role}</Typography>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="body2"><strong>{t("nineQuestions.taskRole")}:</strong> {inference.role_profile.task_role}</Typography>
                      </Box>
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }}>
                      <Typography variant="subtitle2" gutterBottom>{t("nineQuestions.missionBoundary")}:</Typography>
                      <Box sx={{ bgcolor: 'rgba(25, 118, 210, 0.05)', p: 2, borderRadius: 1, border: '1px solid', borderColor: 'primary.light' }}>
                        <Typography variant="body2" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                          {t("nineQuestions.currentMission")}: {inference.mission_boundary.current_mission}
                        </Typography>
                        <Typography variant="subtitle2" sx={{ mt: 1 }}>{t("nineQuestions.priorityDuties")}:</Typography>
                        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                          {inference.mission_boundary.priority_duties.map((d, i) => (
                            <Chip key={i} label={d} size="small" variant="outlined" color="primary" />
                          ))}
                        </Stack>
                        <Typography variant="subtitle2" sx={{ mt: 1 }}>{t("nineQuestions.continuityBoundaries")}:</Typography>
                        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                          {inference.mission_boundary.continuity_boundaries.map((b, i) => (
                            <Chip key={i} label={b} size="small" variant="outlined" color="secondary" />
                          ))}
                        </Stack>
                      </Box>
                    </Grid>
                  </Grid>
                </Stack>
              ) : (
                <Alert severity="info">{t("nineQuestions.waitingIdentitySync")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q2EvidencePanel;
