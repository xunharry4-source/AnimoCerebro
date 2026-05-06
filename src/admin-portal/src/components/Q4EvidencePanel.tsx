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
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";

import {
  Q4PreprocessedEvidence,
  Q4WhatCanIDoInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q4EvidencePanelProps {
  evidence: Q4PreprocessedEvidence;
  inference: Q4WhatCanIDoInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

function assetListSummary(value: unknown): string {
  if (!Array.isArray(value) || value.length === 0) return "";
  return value
    .map((rawItem) => {
      if (typeof rawItem === "string") return rawItem.trim();
      const item = rawItem && typeof rawItem === "object" && !Array.isArray(rawItem) ? (rawItem as Record<string, any>) : {};
      return String(item.asset_name || item.name || item.tool_name || item.command || item.description || item.source || item.id || "").trim();
    })
    .filter(Boolean)
    .slice(0, 3)
    .join(", ");
}

function asTextList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

export const Q4EvidencePanel: React.FC<Q4EvidencePanelProps> = ({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const { t } = useTranslation();
  const q1 = evidence.q1_context || {};
  const q2 = evidence.q2_context || {};
  const q3 = evidence.q3_inventory || {};
  const q2AssetInventory = q2.asset_inventory || {};
  const q2ResourceEvaluation = q2.resource_evaluation || {};
  const q3RoleProfile = q3.role_profile || {};
  const q3MissionBoundary = q3.mission_boundary || {};
  const primaryDomain = q1.scene_model?.primary_domain || q1.scene_model?.domain || q1.scene_model?.primaryDomain || "";
  const secondaryDomains = asTextList(q1.scene_model?.secondary_domains || q1.scene_model?.secondaryDomains);
  const uncertainties = asTextList(q1.uncertainty_profile?.uncertainties || q1.uncertainty_profile?.risk_sources);
  const priorityDuties = asTextList(q3MissionBoundary.priority_duties);
  const availableTools =
    assetListSummary(q2AssetInventory.cognitive_and_functional_tools) ||
    assetListSummary(q2AssetInventory.execution_domains) ||
    assetListSummary(q3.available_execution_tools) ||
    assetListSummary(q3.connected_agents);
  const roleLabel = q3RoleProfile.active_role || q3RoleProfile.identity_role || q3RoleProfile.inferred_reference_role || q3RoleProfile.task_role || "";

  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
          {providerName ? (
            <Chip label={`${t("nineQuestions.capabilityEngine")}: ${providerName}`} size="small" variant="outlined" color="primary" />
          ) : null}
          {elapsedMs > 0 ? <Chip label={`${t("common.latency")}: ${elapsedMs}ms`} size="small" variant="outlined" /> : null}
        </Box>
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                {t("nineQuestions.preAssetSnapshot")}
              </Typography>
               <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom color="primary.main" fontWeight="bold">
                    {t("nineQuestions.q1EnvironmentSnapshot")}
                  </Typography>
                  <Box sx={{ bgcolor: "action.hover", p: 1.5, borderRadius: 1, height: "100%" }}>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.inferredDomain")}:
                    </Typography>
                    <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                      {primaryDomain && (
                        <Chip label={primaryDomain} size="small" color="primary" />
                      )}
                      {secondaryDomains.map((d: string) => (
                        <Chip key={d} label={d} size="small" variant="outlined" />
                      ))}
                      {!primaryDomain && !secondaryDomains.length ? (
                        <Typography variant="caption" color="text.disabled">{t("common.undefined")}</Typography>
                      ) : null}
                    </Stack>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.uncertaintyBlindspots")}:
                    </Typography>
                    <List dense sx={{ py: 0 }}>
                      {uncertainties.map((u: string, i: number) => (
                        <ListItem key={i} disableGutters sx={{ py: 0 }}>
                          <ListItemText 
                            primary={u} 
                            primaryTypographyProps={{ variant: "caption", sx: { fontSize: "0.75rem" } }} 
                          />
                        </ListItem>
                      ))}
                      {!uncertainties.length && (
                        <Typography variant="caption" color="text.disabled">{t("nineQuestions.noKnownBlindspots")}</Typography>
                      )}
                    </List>
                  </Box>
                </Grid>

                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom color="secondary.main" fontWeight="bold">
                    {t("nineQuestions.q2AssetInventorySnapshot")}
                  </Typography>
                  <Box sx={{ bgcolor: "action.hover", p: 1.5, borderRadius: 1, height: "100%" }}>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.availableTools")}:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                      {availableTools || t("common.undefined")}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.resourceStatus")}:
                    </Typography>
                    <Chip
                      label={q2ResourceEvaluation.resource_status || t("common.undefined")}
                      size="small"
                      variant="outlined"
                      color="secondary"
                    />
                  </Box>
                </Grid>

                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom color="info.main" fontWeight="bold">
                    {t("nineQuestions.q3RoleMissionSnapshot")}
                  </Typography>
                  <Box sx={{ bgcolor: "action.hover", p: 1.5, borderRadius: 1, height: "100%" }}>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.currentRoleIdentity")}:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                      {roleLabel || t("common.undefined")}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.coreDuties")}:
                    </Typography>
                    <List dense sx={{ py: 0 }}>
                      {priorityDuties.map((d: string) => (
                        <ListItem key={d} disableGutters sx={{ py: 0 }}>
                          <ListItemText 
                            primary={d} 
                            primaryTypographyProps={{ variant: "caption", sx: { fontWeight: 600 } }}
                          />
                        </ListItem>
                      ))}
                      {!priorityDuties.length && (
                        <Typography variant="caption" color="text.disabled">{t("common.undefined")}</Typography>
                      )}
                    </List>
                    {q3MissionBoundary.current_mission && (
                      <>
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1, mb: 0.5 }}>
                          {t("nineQuestions.currentMission")}:
                        </Typography>
                        <Typography variant="caption" sx={{ fontStyle: "italic" }}>
                          {q3MissionBoundary.current_mission}
                        </Typography>
                      </>
                    )}
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderWidth: 2, borderColor: "primary.main" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                {t("nineQuestions.physicalCapabilityLimits")}
              </Typography>

              {inference ? (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t("nineQuestions.capabilityUpperLimits")}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      {inference.capability_upper_limits.map((item) => (
                        <Chip key={item} label={item} color="secondary" variant="outlined" />
                      ))}
                    </Stack>
                  </Box>

                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t("nineQuestions.validatedActionSpace")}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q4-actionable-space">
                      {inference.actionable_space.length > 0 ? (
                        inference.actionable_space.map((item) => (
                          <Chip key={item} label={item} color="primary" />
                        ))
                      ) : (
                        <Chip label={t("nineQuestions.actionSpaceLocked")} color="error" />
                      )}
                    </Stack>
                  </Box>
                </Stack>
              ) : (
                <Alert severity="info">{t("nineQuestions.waitingCapabilityInference")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                {t("nineQuestions.executableStrategyAssessment")}
              </Typography>
              {inference && inference.executable_strategies.length > 0 ? (
                <Stack spacing={1}>
                  {inference.executable_strategies.map((strategy, index) => (
                    <Accordion key={`${strategy}-${index}`} defaultExpanded={false} data-testid="executable-strategy-accordion">
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Typography variant="subtitle2">{t("nineQuestions.contingencyStrategy")} {index + 1}</Typography>
                      </AccordionSummary>
                      <AccordionDetails>
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                          {strategy}
                        </Typography>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                </Stack>
              ) : (
                <Alert severity="info">{t("nineQuestions.noExecutableStrategies")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q4EvidencePanel;
