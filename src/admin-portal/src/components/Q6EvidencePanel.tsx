import React from "react";
import { useTranslation } from "react-i18next";
import {
  Alert, Box, Card, CardContent, Chip, Grid, Stack, Typography, Accordion, AccordionSummary, AccordionDetails, List, ListItem, ListItemText, ListItemIcon
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GavelIcon from '@mui/icons-material/Gavel';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import HistoryEduIcon from '@mui/icons-material/HistoryEdu';
import {
  Q6PreprocessedEvidence, Q6ConsequenceInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q6EvidencePanelProps {
  evidence: Q6PreprocessedEvidence;
  inference: Q6ConsequenceInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

export const Q6EvidencePanel: React.FC<Q6EvidencePanelProps> = ({
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
              label={`${t("nineQuestions.guardrailEngine")}: ${providerName}`}
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

      {/* Partition 1: 前置约束证据区 */}
      <Card variant="outlined" sx={{ borderLeft: '4px solid', borderLeftColor: 'warning.main' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
            {t("nineQuestions.constraintEvidence")}
          </Typography>
          <Grid container spacing={3}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" gutterBottom color="text.secondary">{t("nineQuestions.actionableAuthBoundaries")}:</Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                {evidence.actionable_space && evidence.actionable_space.map((act, i) => (
                  <Chip key={`act-${i}`} label={act} size="small" color="primary" variant="outlined" />
                ))}
                {evidence.authorization_boundaries && evidence.authorization_boundaries.map((auth, i) => (
                  <Chip key={`auth-${i}`} label={auth} size="small" color="secondary" variant="outlined" />
                ))}
              </Stack>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" gutterBottom color="error.main" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <GavelIcon fontSize="small" /> {t("nineQuestions.nonBypassableConstraints")}:
              </Typography>
              <List dense sx={{ bgcolor: 'error.50', borderRadius: 1 }}>
                {evidence.non_bypassable_constraints && evidence.non_bypassable_constraints.length > 0 ? (
                  evidence.non_bypassable_constraints.map((constraint, i) => (
                    <ListItem key={i} disablePadding sx={{ px: 1, py: 0.5 }}>
                      <ListItemIcon sx={{ minWidth: 28 }}><GavelIcon color="error" fontSize="inherit" /></ListItemIcon>
                      <ListItemText primary={constraint} primaryTypographyProps={{ variant: "body2", fontWeight: 'bold', color: 'error.dark' }} />
                    </ListItem>
                  ))
                ) : (
                  <ListItem><ListItemText primary={t("nineQuestions.noSystemRigidConstraints")} /></ListItem>
                )}
              </List>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Partition 2: 记忆与策略区（绝对红线） */}
      {evidence.historical_strategy_patches && evidence.historical_strategy_patches.length > 0 && (
        <Card variant="outlined" sx={{ borderLeft: '4px solid', borderLeftColor: 'info.main' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
              {t("nineQuestions.historicalPatches")}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {t("nineQuestions.historicalPatchesDesc")}
            </Typography>
            <Stack spacing={1}>
              {evidence.historical_strategy_patches.map((patch, i) => (
                <Accordion key={i} variant="outlined" defaultExpanded={false} data-testid="q6-historical-patch-accordion">
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <HistoryEduIcon color="action" fontSize="small" />
                      <Typography variant="subtitle2">{t("nineQuestions.historicalPatchLabel")} #00{i + 1}</Typography>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2" sx={{ bgcolor: 'background.default', p: 2, borderRadius: 1 }}>
                      {patch}
                    </Typography>
                  </AccordionDetails>
                </Accordion>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Partition 3: 代价与后果评估区 */}
      <Card variant="outlined" sx={{ border: '2px solid', borderColor: 'warning.main' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', color: 'warning.main' }}>
            代价与后果画像
          </Typography>
          
          {inference ? (
            <Stack spacing={3} sx={{ mt: 2 }}>
              <Box>
                <Typography variant="subtitle2" gutterBottom color="warning.dark">如果我做了:</Typography>
                <Alert severity={inference.ConsequenceAssessment?.consequence_severity === "high" ? "error" : "warning"} variant="outlined">
                  <Typography variant="body2" fontWeight="bold">{inference.ConsequenceAssessment?.action_under_review || "未识别评估动作"}</Typography>
                  <Typography variant="body2">严重度: {inference.ConsequenceAssessment?.consequence_severity || "unknown"} / 可逆性: {inference.ConsequenceAssessment?.reversibility || "unknown"}</Typography>
                </Alert>
              </Box>

              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="warning.dark">直接后果:</Typography>
                  <List dense sx={{ bgcolor: 'warning.50', borderRadius: 1 }}>
                    {inference.ConsequenceAssessment?.immediate_consequences?.length ? (
                      inference.ConsequenceAssessment.immediate_consequences.map((item, i) => (
                        <ListItem key={i} disablePadding sx={{ px: 1, py: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 28 }}><ReportProblemIcon color="warning" fontSize="inherit" /></ListItemIcon>
                          <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                      ))
                    ) : (
                      <ListItem><ListItemText primary="暂无直接后果" /></ListItem>
                    )}
                  </List>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="warning.dark">传导后果:</Typography>
                  <List dense sx={{ bgcolor: 'background.default', borderRadius: 1 }}>
                    {inference.ConsequenceAssessment?.downstream_consequences?.length ? (
                      inference.ConsequenceAssessment.downstream_consequences.map((item, i) => (
                        <ListItem key={i} disablePadding sx={{ px: 1, py: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 28 }}><ReportProblemIcon color="warning" fontSize="inherit" /></ListItemIcon>
                          <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                      ))
                    ) : (
                      <ListItem><ListItemText primary="暂无传导后果" /></ListItem>
                    )}
                  </List>
                </Grid>
              </Grid>

              <Box>
                <Typography variant="subtitle2" gutterBottom color="error.main">安全与合规影响:</Typography>
                <Stack spacing={1} data-testid="q6-security-compliance-impacts">
                  {inference.CostImpactProfile?.security_compliance_impacts?.length ? (
                    inference.CostImpactProfile.security_compliance_impacts.map((impact, i) => (
                      <Alert key={i} severity="error" sx={{ py: 0, '& .MuiAlert-message': { py: 1 } }}>
                        {impact}
                      </Alert>
                    ))
                  ) : (
                    <Alert severity="info" sx={{ py: 0 }}>暂无安全与合规影响</Alert>
                  )}
                </Stack>
              </Box>

              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">操作成本:</Typography>
                  <List dense sx={{ bgcolor: 'background.default', borderRadius: 1 }}>
                    {inference.CostImpactProfile?.operational_costs?.length ? (
                      inference.CostImpactProfile.operational_costs.map((cost, i) => (
                        <ListItem key={i} disablePadding sx={{ px: 1, py: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 28 }}><ReportProblemIcon color="warning" fontSize="inherit" /></ListItemIcon>
                          <ListItemText primary={cost} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                      ))
                    ) : (
                      <ListItem><ListItemText primary="暂无操作成本" /></ListItem>
                    )}
                  </List>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="warning.dark">缓解要求与停止条件:</Typography>
                  <Stack spacing={1}>
                    {[...(inference.CostImpactProfile?.mitigation_requirements || []), ...(inference.CostImpactProfile?.stop_conditions || [])].length ? (
                      [...(inference.CostImpactProfile?.mitigation_requirements || []), ...(inference.CostImpactProfile?.stop_conditions || [])].map((item, i) => (
                        <Alert key={i} severity="warning" sx={{ py: 0, '& .MuiAlert-message': { py: 1 } }}>
                          {item}
                        </Alert>
                      ))
                    ) : (
                      <Alert severity="info" sx={{ py: 0 }}>暂无缓解要求或停止条件</Alert>
                    )}
                  </Stack>
                </Grid>
              </Grid>

            </Stack>
          ) : (
            <Alert severity="info" sx={{ mt: 2 }}>等待 Q6 代价与后果评估同步。</Alert>
          )}
        </CardContent>
      </Card>
      
    </Stack>
  );
};

export default Q6EvidencePanel;
