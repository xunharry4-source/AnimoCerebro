import React from "react";
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
  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {/* Partition 0: Inference Metadata (G31A Transparency) */}
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
          {providerName && (
            <Chip
              label={`ID Engine: ${providerName}`}
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
        {/* 1. Q1 前置态势聚合区 */}
        <Grid size={{ xs: 12, xl: 6 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                【Q1 前置态势聚合区】
              </Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                <Chip label={`主领域: ${evidence.q1_summary.primary_domain}`} color="primary" />
                {evidence.q1_summary.secondary_domains.map((d, i) => (
                  <Chip key={i} label={`次领域: ${d}`} variant="outlined" size="small" />
                ))}
              </Stack>
              {evidence.q1_summary.risk_summary && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                  风险摘要: {evidence.q1_summary.risk_summary}
                </Alert>
              )}
              <Typography variant="subtitle2" gutterBottom color="text.secondary">不确定性盲区:</Typography>
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
                【身份内核与不可绕过约束】
              </Typography>
              <Typography variant="subtitle2" color="error" gutterBottom>不可绕过约束 (Hard Constraints):</Typography>
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
                  <Typography variant="subtitle2" color="primary">元动机 (Meta Motivation)</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="body2" sx={{ bgcolor: 'action.hover', p: 1, borderRadius: 1 }}>
                    {evidence.identity_kernel.meta_motivation}
                  </Typography>
                </AccordionDetails>
              </Accordion>

              <Accordion variant="outlined" sx={{ mt: 1 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2" color="secondary">核心价值禁令 (Prohibitions)</Typography>
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
                【人工干预与角色回执记录】
              </Typography>
              {evidence.manual_intervention?.latest_manual_role_modification ? (
                <Box sx={{ p: 1.5, borderLeft: '4px solid', borderColor: 'warning.main', bgcolor: 'warning.light', color: 'warning.contrastText' }}>
                  <Typography variant="body2" sx={{ fontWeight: 'bold' }}>最新修正: {evidence.manual_intervention.latest_manual_role_modification}</Typography>
                  <Typography variant="caption" display="block">应用时间: {evidence.manual_intervention.applied_at || "未知"}</Typography>
                </Box>
              ) : (
                <Alert severity="info">
                  暂无人工角色干预记录。主体身份完全由自动化推导与内核约束驱动。
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
                【大模型身份内核推论区 (Inference)】
              </Typography>
              {inference ? (
                <Stack spacing={2}>
                  <Grid container spacing={2}>
                    <Grid size={{ xs: 12, md: 6 }}>
                      <Typography variant="subtitle2" gutterBottom>角色配置文件 (Role Profile):</Typography>
                      <Box sx={{ bgcolor: 'background.default', p: 2, borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                        <Typography variant="body2"><strong>身份角色:</strong> {inference.role_profile.identity_role}</Typography>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="body2"><strong>当前主角色:</strong> {inference.role_profile.active_role}</Typography>
                        <Divider sx={{ my: 1 }} />
                        <Typography variant="body2"><strong>具体任务角色:</strong> {inference.role_profile.task_role}</Typography>
                      </Box>
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }}>
                      <Typography variant="subtitle2" gutterBottom>使命与连续性边界 (Mission):</Typography>
                      <Box sx={{ bgcolor: 'rgba(25, 118, 210, 0.05)', p: 2, borderRadius: 1, border: '1px solid', borderColor: 'primary.light' }}>
                        <Typography variant="body2" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                          当前使命: {inference.mission_boundary.current_mission}
                        </Typography>
                        <Typography variant="subtitle2" sx={{ mt: 1 }}>核心职责:</Typography>
                        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                          {inference.mission_boundary.priority_duties.map((d, i) => (
                            <Chip key={i} label={d} size="small" variant="outlined" color="primary" />
                          ))}
                        </Stack>
                        <Typography variant="subtitle2" sx={{ mt: 1 }}>连续性边界:</Typography>
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
                <Alert severity="info">等待身份推理数据同步...</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q2EvidencePanel;
