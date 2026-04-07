import React from "react";
import {
  Alert, Box, Card, CardContent, Chip, Grid, Stack, Typography, Accordion, AccordionSummary, AccordionDetails, List, ListItem, ListItemText, ListItemIcon
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GavelIcon from '@mui/icons-material/Gavel';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import HistoryEduIcon from '@mui/icons-material/HistoryEdu';
import {
  Q6PreprocessedEvidence, Q6ForbiddenZoneInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q6EvidencePanelProps {
  evidence: Q6PreprocessedEvidence;
  inference: Q6ForbiddenZoneInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

export const Q6EvidencePanel: React.FC<Q6EvidencePanelProps> = ({
  evidence, inference, providerName, elapsedMs = 0,
}) => {
  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {/* Partition 0: Inference Metadata */}
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && (
            <Chip
              label={`Guardrail Engine: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          )}
          {elapsedMs > 0 && (
            <Chip
              label={`Latency: ${elapsedMs}ms`}
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
            【前置约束证据区 (Constraint Evidence)】
          </Typography>
          <Grid container spacing={3}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="subtitle2" gutterBottom color="text.secondary">可行动作与授权边界 (Actionable & Auth Boundaries):</Typography>
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
                <GavelIcon fontSize="small" /> 不可绕过约束 (Non-Bypassable Constraints):
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
                  <ListItem><ListItemText primary="未发现系统级刚性约束" /></ListItem>
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
              【长效记忆与补丁区 (Historical Patches)】
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              系统捕获到以下历史失败或红线纠正的降级补丁，严禁重复试错：
            </Typography>
            <Stack spacing={1}>
              {evidence.historical_strategy_patches.map((patch, i) => (
                <Accordion key={i} variant="outlined" defaultExpanded={false} data-testid="q6-historical-patch-accordion">
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <HistoryEduIcon color="action" fontSize="small" />
                      <Typography variant="subtitle2">历史补丁 #00{i + 1}</Typography>
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

      {/* Partition 3: 终极禁区判定区 */}
      <Card variant="outlined" sx={{ border: '2px solid', borderColor: 'error.main' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold', color: 'error.main' }}>
            【终极禁区判定区 (Forbidden Zone Profile)】
          </Typography>
          
          {inference ? (
            <Stack spacing={3} sx={{ mt: 2 }}>
              
              {/* 绝对红线 (Alert Error) */}
              <Box>
                <Typography variant="subtitle2" gutterBottom color="error.dark">绝对红线判决 (Absolute Red Lines):</Typography>
                {inference.absolute_red_lines && inference.absolute_red_lines.length > 0 ? (
                  <Stack spacing={1} data-testid="q6-absolute-red-lines">
                    {inference.absolute_red_lines.map((redline, i) => (
                      <Alert key={i} severity="error" variant="filled" sx={{ fontWeight: 'bold', py: 0 }}>
                        {redline}
                      </Alert>
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="success" sx={{ py: 0 }}>未触发绝对红线否决</Alert>
                )}
              </Box>

              {/* 被否决策略 (Red Chips) */}
              <Box>
                <Typography variant="subtitle2" gutterBottom color="error.main">已拦截的高危策略 (Prohibited Strategies):</Typography>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q6-prohibited-strategies">
                  {inference.prohibited_strategies && inference.prohibited_strategies.length > 0 ? (
                    inference.prohibited_strategies.map((strat, i) => (
                      <Chip key={i} label={strat} color="error" />
                    ))
                  ) : (
                    <Chip label="暂无否决" size="small" variant="outlined" />
                  )}
                </Stack>
              </Box>

              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  {/* 性能交换禁令 (List) */}
                  <Typography variant="subtitle2" gutterBottom color="warning.dark">性能交换禁令 (Tradeoff Bans):</Typography>
                  <List dense sx={{ bgcolor: 'warning.50', borderRadius: 1 }}>
                    {inference.performance_tradeoff_bans && inference.performance_tradeoff_bans.length > 0 ? (
                      inference.performance_tradeoff_bans.map((ban, i) => (
                        <ListItem key={i} disablePadding sx={{ px: 1, py: 0.5 }}>
                          <ListItemIcon sx={{ minWidth: 28 }}><ReportProblemIcon color="warning" fontSize="inherit" /></ListItemIcon>
                          <ListItemText primary={ban} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                      ))
                    ) : (
                      <ListItem><ListItemText primary="无可观风险交换约束" /></ListItem>
                    )}
                  </List>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  {/* 污染风险点 (Warning Alerts) */}
                  <Typography variant="subtitle2" gutterBottom color="warning.dark">污染评估 (Contamination Risks):</Typography>
                  <Stack spacing={1}>
                    {inference.contamination_risks && inference.contamination_risks.length > 0 ? (
                      inference.contamination_risks.map((risk, i) => (
                        <Alert key={i} severity="warning" sx={{ py: 0, '& .MuiAlert-message': { py: 1 } }}>
                          {risk}
                        </Alert>
                      ))
                    ) : (
                      <Alert severity="success" sx={{ py: 0 }}>沙箱上下文纯净度验证通过</Alert>
                    )}
                  </Stack>
                </Grid>
              </Grid>

            </Stack>
          ) : (
            <Alert severity="info" sx={{ mt: 2 }}>等待红线推断数据同步...</Alert>
          )}
        </CardContent>
      </Card>
      
    </Stack>
  );
};

export default Q6EvidencePanel;
