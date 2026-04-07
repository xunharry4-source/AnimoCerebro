import React from "react";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
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
            <Chip label={`Capability Engine: ${providerName}`} size="small" variant="outlined" color="primary" />
          ) : null}
          {elapsedMs > 0 ? <Chip label={`Latency: ${elapsedMs}ms`} size="small" variant="outlined" /> : null}
        </Box>
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【前置资产与态势依据区】
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Q1 环境态势
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      p: 1.5,
                      bgcolor: "action.hover",
                      borderRadius: 1,
                      overflowX: "auto",
                      whiteSpace: "pre-wrap",
                      fontSize: "0.8rem",
                    }}
                  >
                    <code>{JSON.stringify(q1, null, 2)}</code>
                  </Box>
                </Grid>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Q2 角色与使命边界
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      p: 1.5,
                      bgcolor: "action.hover",
                      borderRadius: 1,
                      overflowX: "auto",
                      whiteSpace: "pre-wrap",
                      fontSize: "0.8rem",
                    }}
                  >
                    <code>{JSON.stringify(q2, null, 2)}</code>
                  </Box>
                </Grid>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Q3 资产盘点与工具域
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                    {(q3.available_cognitive_tools || []).map((tool: string) => (
                      <Chip key={tool} label={tool} size="small" color="info" />
                    ))}
                    {(q3.available_execution_tools || []).map((tool: string) => (
                      <Chip key={tool} label={tool} size="small" color="error" variant="outlined" />
                    ))}
                  </Stack>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                    {(q3.accessible_workspace_zones || []).map((zone: string) => (
                      <Chip key={zone} label={zone} size="small" variant="outlined" />
                    ))}
                  </Stack>
                  <Typography variant="caption" display="block" sx={{ mb: 0.5 }}>
                    已连接 Agent
                  </Typography>
                  <List dense sx={{ py: 0 }}>
                    {connectedAgents.map((agent, index) => (
                      <ListItem key={`${agent.id || agent.agent_id || index}`} disableGutters sx={{ py: 0.25 }}>
                        <ListItemText primary={agent.name || agent.agent_id || agent.id || "Unknown Agent"} secondary={agent.summary || agent.scope || null} />
                      </ListItem>
                    ))}
                    {connectedAgents.length === 0 ? (
                      <ListItem disableGutters sx={{ py: 0.25 }}>
                        <ListItemText primary="无在线 Agent" />
                      </ListItem>
                    ) : null}
                  </List>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderWidth: 2, borderColor: "primary.main" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【物理能力上限与动作空间区】
              </Typography>

              {inference ? (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      能力上限边界
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      {inference.capability_upper_limits.map((item) => (
                        <Chip key={item} label={item} color="secondary" variant="outlined" />
                      ))}
                    </Stack>
                  </Box>

                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      验证的可行动作空间
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q4-actionable-space">
                      {inference.actionable_space.length > 0 ? (
                        inference.actionable_space.map((item) => (
                          <Chip key={item} label={item} color="primary" />
                        ))
                      ) : (
                        <Chip label="【动作空间已被锁死，无可用物理动作】" color="error" />
                      )}
                    </Stack>
                  </Box>
                </Stack>
              ) : (
                <Alert severity="info">等待能力空间推理结果。</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【可执行策略评估区】
              </Typography>
              {inference && inference.executable_strategies.length > 0 ? (
                <Stack spacing={1}>
                  {inference.executable_strategies.map((strategy, index) => (
                    <Accordion key={`${strategy}-${index}`} defaultExpanded={false} data-testid="executable-strategy-accordion">
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Typography variant="subtitle2">预案执行策略 {index + 1}</Typography>
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
                <Alert severity="info">推理结果中未包含有效的可执行组合策略。</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q4EvidencePanel;
