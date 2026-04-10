import React from "react";
import { useTranslation } from "react-i18next";
import {
  Alert, Box, Card, CardContent, Chip, Grid, Stack, Typography, Accordion, AccordionSummary, AccordionDetails, List, ListItem, ListItemText, ListItemIcon, ListItemAvatar, Avatar
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HistoryEduIcon from '@mui/icons-material/HistoryEdu';
import GroupAddIcon from '@mui/icons-material/GroupAdd';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import HardwareIcon from '@mui/icons-material/Hardware';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import {
  Q7PreprocessedEvidence, Q7AlternativeStrategyInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q7EvidencePanelProps {
  evidence: Q7PreprocessedEvidence;
  inference: Q7AlternativeStrategyInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

export const Q7EvidencePanel: React.FC<Q7EvidencePanelProps> = ({
  evidence, inference, providerName, elapsedMs = 0,
}) => {
  const { t } = useTranslation();
  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {/* Partition 0: Inference Metadata */}
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && (
            <Chip
              label={`${t("nineQuestions.fallbackPlannerEngine")}: ${providerName}`}
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
        {/* Partition 1: 前置瓶颈与红线约束区 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderLeft: '4px solid', borderLeftColor: 'error.main' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                {t("nineQuestions.bottlenecksConstraints")}
              </Typography>

              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.resourceBottlenecks")}:</Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                    {evidence.resource_bottlenecks && evidence.resource_bottlenecks.length > 0 ? (
                      evidence.resource_bottlenecks.map((res, i) => (
                        <Chip key={`res-${i}`} label={res} size="small" variant="outlined" />
                      ))
                    ) : (
                      <Chip label={t("nineQuestions.noResourceBottlenecks")} size="small" />
                    )}
                  </Stack>

                  <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.limitsAuthBoundaries")}:</Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    {evidence.capability_limits && evidence.capability_limits.map((cap, i) => (
                      <Chip key={`cap-${i}`} label={cap} size="small" color="secondary" variant="outlined" />
                    ))}
                    {evidence.permission_boundaries && evidence.permission_boundaries.map((auth, i) => (
                      <Chip key={`auth-${i}`} label={auth} size="small" color="warning" variant="outlined" />
                    ))}
                  </Stack>
                </Grid>

                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="error.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <ErrorOutlineIcon fontSize="small" /> {t("nineQuestions.absoluteRedLinesQ6")}:
                  </Typography>
                  <Box data-testid="q7-absolute-red-lines">
                    {evidence.absolute_red_lines && evidence.absolute_red_lines.length > 0 ? (
                      <Stack spacing={1}>
                        {evidence.absolute_red_lines.map((redline, i) => (
                          <Alert key={i} severity="error" sx={{ py: 0, '& .MuiAlert-message': { py: 1.5 } }}>
                            {redline}
                          </Alert>
                        ))}
                      </Stack>
                    ) : (
                      <Alert severity="success">{t("nineQuestions.noRetreatRedlines")}</Alert>
                    )}
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Partition 2: 历史失败经验避坑区 */}
        {evidence.historical_failure_patches && evidence.historical_failure_patches.length > 0 && (
          <Grid size={{ xs: 12 }}>
            <Card variant="outlined" sx={{ borderLeft: '4px solid', borderLeftColor: 'info.main' }}>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                  {t("nineQuestions.historicalFailurePatches")}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  {t("nineQuestions.historicalFailurePatchesDesc")}
                </Typography>
                <Stack spacing={1}>
                  {evidence.historical_failure_patches.map((patch, i) => (
                    <Accordion key={i} variant="outlined" defaultExpanded={false} data-testid="q7-historical-patch-accordion">
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <HistoryEduIcon color="action" fontSize="small" />
                          <Typography variant="subtitle2">{t("nineQuestions.historicalPatchLabel")} #00{i + 1}</Typography>
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails>
                        <Typography variant="body2" sx={{ bgcolor: 'action.hover', p: 2, borderRadius: 1 }}>
                          {patch}
                        </Typography>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Partition 3: 大模型终极降级预案区 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ border: '2px solid', borderColor: 'primary.main' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                {t("nineQuestions.alternativeStrategyProfile")}
              </Typography>
              
              {inference ? (
                <Grid container spacing={3} sx={{ mt: 1 }}>
                  
                  {/* 降级策略 (warning Alerts) */}
                  <Grid size={{ xs: 12, md: 6 }} data-testid="q7-degradation-strategies">
                    <Typography variant="subtitle2" gutterBottom color="warning.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <WarningAmberIcon fontSize="small" /> {t("nineQuestions.degradationStrategies")}:
                    </Typography>
                    {inference.degradation_strategies && inference.degradation_strategies.length > 0 ? (
                      <Stack spacing={1}>
                        {inference.degradation_strategies.map((strat, i) => (
                          <Alert key={i} severity="warning" variant="filled" sx={{ py: 0 }}>
                            {strat}
                          </Alert>
                        ))}
                      </Stack>
                    ) : (
                      <Alert severity="info" variant="outlined" sx={{ py: 0 }}>{t("nineQuestions.noDegradationNeeded")}</Alert>
                    )}
                  </Grid>

                  {/* 探索动作 (blue Chips) */}
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="subtitle2" gutterBottom color="info.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <HardwareIcon fontSize="small" /> {t("nineQuestions.exploratoryActions")}:
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      {inference.exploratory_actions && inference.exploratory_actions.length > 0 ? (
                        inference.exploratory_actions.map((act, i) => (
                          <Chip key={i} label={act} color="info" />
                        ))
                      ) : (
                        <Chip label={t("nineQuestions.noExploratoryProbes")} size="small" variant="outlined" />
                      )}
                    </Stack>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    <Grid container spacing={3}>
                      {/* 安全备选动作 (List) */}
                      <Grid size={{ xs: 12, md: 6 }}>
                        <Typography variant="subtitle2" gutterBottom color="success.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <VerifiedUserIcon fontSize="small" /> {t("nineQuestions.fallbackPlans")}:
                        </Typography>
                        <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                          <List dense>
                            {inference.fallback_plans && inference.fallback_plans.length > 0 ? (
                              inference.fallback_plans.map((plan, i) => (
                                <ListItem key={i} divider={i < inference.fallback_plans.length - 1}>
                                  <ListItemIcon sx={{ minWidth: 28 }}><VerifiedUserIcon color="success" fontSize="small" /></ListItemIcon>
                                  <ListItemText primary={plan} primaryTypographyProps={{ variant: "body2" }} />
                                </ListItem>
                              ))
                            ) : (
                              <ListItem><ListItemText primary={t("nineQuestions.noFallbackPlansProvided")} /></ListItem>
                            )}
                          </List>
                        </Box>
                      </Grid>

                      {/* 协作切换 (Cards / Avatars) */}
                      <Grid size={{ xs: 12, md: 6 }}>
                        <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <GroupAddIcon fontSize="small" /> {t("nineQuestions.collaborationSwitches")}:
                        </Typography>
                        <List disablePadding>
                          {inference.collaboration_switches && inference.collaboration_switches.length > 0 ? (
                            inference.collaboration_switches.map((sw, i) => (
                              <ListItem key={i} sx={{ border: '1px solid', borderColor: 'divider', mb: 1, borderRadius: 1, bgcolor: 'background.paper' }}>
                                <ListItemAvatar>
                                  <Avatar sx={{ bgcolor: 'secondary.main' }}>
                                    <GroupAddIcon />
                                  </Avatar>
                                </ListItemAvatar>
                                <ListItemText
                                  primary={sw.target_agent || sw.agent || sw.name || `${t("nineQuestions.emergencyCollabSwitch")} #${i + 1}`}
                                  secondaryTypographyProps={{ component: 'div' as any }}
                                  secondary={
                                    <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                                      {Object.entries(sw).filter(([k]) => k !== 'target_agent' && k !== 'agent' && k !== 'name').map(([k, v]) => (
                                        <Typography key={k} variant="caption" color="text.secondary">
                                          <b>{k}:</b> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                        </Typography>
                                      ))}
                                    </Stack>
                                  }
                                />
                              </ListItem>
                            ))
                          ) : (
                            <Alert severity="info" sx={{ py: 0 }}>{t("nineQuestions.noDegradedCollabNetwork")}</Alert>
                          )}
                        </List>
                      </Grid>
                    </Grid>
                  </Grid>

                </Grid>
              ) : (
                <Alert severity="info" sx={{ mt: 2 }}>{t("nineQuestions.waitingDegradationTree")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q7EvidencePanel;
