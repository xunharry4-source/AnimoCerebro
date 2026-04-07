import React from "react";
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
  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {/* Partition 0: Inference Metadata */}
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && (
            <Chip
              label={`Fallback Planner Engine: ${providerName}`}
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

      <Grid container spacing={3}>
        {/* Partition 1: 前置瓶颈与红线约束区 */}
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderLeft: '4px solid', borderLeftColor: 'error.main' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                【前置瓶颈与红线约束区 (Bottlenecks & Constraints)】
              </Typography>

              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom color="text.secondary">致命资源瓶颈 (Resource Bottlenecks):</Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                    {evidence.resource_bottlenecks && evidence.resource_bottlenecks.length > 0 ? (
                      evidence.resource_bottlenecks.map((res, i) => (
                        <Chip key={`res-${i}`} label={res} size="small" variant="outlined" />
                      ))
                    ) : (
                      <Chip label="暂无明确资源瓶颈" size="small" />
                    )}
                  </Stack>

                  <Typography variant="subtitle2" gutterBottom color="text.secondary">能力上限与授权边界 (Limits & Auth Boundaries):</Typography>
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
                    <ErrorOutlineIcon fontSize="small" /> 绝对越界红线 (Q6 Absolute Red Lines):
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
                      <Alert severity="success">未接收到任何退回红线指令</Alert>
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
                  【历史失败经验避坑区 (Historical Patches)】
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  基于前车之鉴提取的长效防误闭环指导（已强制折叠以免疫满屏攻击）：
                </Typography>
                <Stack spacing={1}>
                  {evidence.historical_failure_patches.map((patch, i) => (
                    <Accordion key={i} variant="outlined" defaultExpanded={false} data-testid="q7-historical-patch-accordion">
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <HistoryEduIcon color="action" fontSize="small" />
                          <Typography variant="subtitle2">历史补丁 #00{i + 1}</Typography>
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
                【终极降级预案区 (Alternative Strategy Profile)】
              </Typography>
              
              {inference ? (
                <Grid container spacing={3} sx={{ mt: 1 }}>
                  
                  {/* 降级策略 (warning Alerts) */}
                  <Grid size={{ xs: 12, md: 6 }} data-testid="q7-degradation-strategies">
                    <Typography variant="subtitle2" gutterBottom color="warning.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <WarningAmberIcon fontSize="small" /> 核心功能降级策略 (Degradation Strategies):
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
                      <Alert severity="info" variant="outlined" sx={{ py: 0 }}>无需启用降级状态</Alert>
                    )}
                  </Grid>

                  {/* 探索动作 (blue Chips) */}
                  <Grid size={{ xs: 12, md: 6 }}>
                    <Typography variant="subtitle2" gutterBottom color="info.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <HardwareIcon fontSize="small" /> 低风险探索尝试 (Exploratory Actions):
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      {inference.exploratory_actions && inference.exploratory_actions.length > 0 ? (
                        inference.exploratory_actions.map((act, i) => (
                          <Chip key={i} label={act} color="info" />
                        ))
                      ) : (
                        <Chip label="暂无可用探索试探" size="small" variant="outlined" />
                      )}
                    </Stack>
                  </Grid>

                  <Grid size={{ xs: 12 }}>
                    <Grid container spacing={3}>
                      {/* 安全备选动作 (List) */}
                      <Grid size={{ xs: 12, md: 6 }}>
                        <Typography variant="subtitle2" gutterBottom color="success.dark" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <VerifiedUserIcon fontSize="small" /> 绝对安全替代方案 (Fallback Plans):
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
                              <ListItem><ListItemText primary="未提供替代安全方案" /></ListItem>
                            )}
                          </List>
                        </Box>
                      </Grid>

                      {/* 协作切换 (Cards / Avatars) */}
                      <Grid size={{ xs: 12, md: 6 }}>
                        <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <GroupAddIcon fontSize="small" /> 转移求助与协作倒换 (Collaboration Switches):
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
                                  primary={sw.target_agent || sw.agent || sw.name || `紧急协作切换点 #${i + 1}`}
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
                            <Alert severity="info" sx={{ py: 0 }}>无可用的降级协作网络</Alert>
                          )}
                        </List>
                      </Grid>
                    </Grid>
                  </Grid>

                </Grid>
              ) : (
                <Alert severity="info" sx={{ mt: 2 }}>等待降级策略树建立...</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q7EvidencePanel;
