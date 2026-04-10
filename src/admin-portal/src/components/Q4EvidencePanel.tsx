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
  const connectedAgents = Array.isArray(q3.connected_agents)
    ? q3.connected_agents.filter((agent) => String(agent.status || "").toLowerCase() !== "offline")
    : [];

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
                      {q1.scene_model?.primary_domain && (
                        <Chip label={q1.scene_model.primary_domain} size="small" color="primary" />
                      )}
                      {(q1.scene_model?.secondary_domains || []).map((d: string) => (
                        <Chip key={d} label={d} size="small" variant="outlined" />
                      ))}
                    </Stack>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.uncertaintyBlindspots")}:
                    </Typography>
                    <List dense sx={{ py: 0 }}>
                      {(q1.uncertainty_profile?.uncertainties || []).map((u: string, i: number) => (
                        <ListItem key={i} disableGutters sx={{ py: 0 }}>
                          <ListItemText 
                            primary={u} 
                            primaryTypographyProps={{ variant: "caption", sx: { fontSize: "0.75rem" } }} 
                          />
                        </ListItem>
                      ))}
                      {!(q1.uncertainty_profile?.uncertainties?.length) && (
                        <Typography variant="caption" color="text.disabled">{t("nineQuestions.noKnownBlindspots")}</Typography>
                      )}
                    </List>
                  </Box>
                </Grid>

                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom color="secondary.main" fontWeight="bold">
                    {t("nineQuestions.q2RoleMissionSnapshot")}
                  </Typography>
                  <Box sx={{ bgcolor: "action.hover", p: 1.5, borderRadius: 1, height: "100%" }}>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.currentRoleIdentity")}:
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                      {q2.role_profile?.active_role || q2.role_profile?.identity_role || t("common.undefined")}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.coreDuties")}:
                    </Typography>
                    <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                      {(q2.mission_boundary?.priority_duties || []).map((d: string) => (
                        <Chip key={d} label={d} size="small" variant="outlined" color="secondary" />
                      ))}
                    </Stack>
                    {q2.mission_boundary?.current_mission && (
                      <>
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1, mb: 0.5 }}>
                          {t("nineQuestions.currentMission")}:
                        </Typography>
                        <Typography variant="caption" sx={{ fontStyle: "italic" }}>
                          {q2.mission_boundary.current_mission}
                        </Typography>
                      </>
                    )}
                  </Box>
                </Grid>

                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom color="info.main" fontWeight="bold">
                    {t("nineQuestions.q3InventorySnapshot")}
                  </Typography>
                  <Box sx={{ bgcolor: "action.hover", p: 1.5, borderRadius: 1, height: "100%" }}>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.auditedToolDomains")}:
                    </Typography>
                    <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                      {(q3.available_cognitive_tools || []).map((tool: string) => (
                        <Chip key={tool} label={tool} size="small" color="info" />
                      ))}
                      {(q3.available_execution_tools || []).map((tool: string) => (
                        <Chip key={tool} label={tool} size="small" color="error" variant="outlined" />
                      ))}
                    </Stack>
                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                      {t("nineQuestions.connectedAgents")}:
                    </Typography>
                    <List dense sx={{ py: 0 }}>
                      {connectedAgents.map((agent, index) => (
                        <ListItem key={`${agent.id || agent.agent_id || index}`} disableGutters sx={{ py: 0 }}>
                          <ListItemText 
                            primary={agent.name || agent.agent_id || agent.id || "Unknown"} 
                            primaryTypographyProps={{ variant: "caption", sx: { fontWeight: 600 } }}
                          />
                        </ListItem>
                      ))}
                      {connectedAgents.length === 0 && (
                        <Typography variant="caption" color="text.disabled">{t("nineQuestions.noOnlineAgents")}</Typography>
                      )}
                    </List>
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
