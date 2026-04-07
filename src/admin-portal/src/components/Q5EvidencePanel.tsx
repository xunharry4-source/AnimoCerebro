import React from "react";
import {
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
  Q5PreprocessedEvidence,
  Q5WhatAmIAllowedToDoInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q5EvidencePanelProps {
  evidence: Q5PreprocessedEvidence;
  inference: Q5WhatAmIAllowedToDoInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

function trustChipColor(status: string): "success" | "warning" | "error" | "default" {
  const normalized = status.toLowerCase();
  if (normalized === "trusted" || normalized === "active") {
    return "success";
  }
  if (normalized === "revoked" || normalized === "blocked") {
    return "error";
  }
  if (normalized === "pending" || normalized === "read_only" || normalized === "limited") {
    return "warning";
  }
  return "default";
}

function executionTierColor(tier: string): "success" | "warning" | "error" | "default" {
  const normalized = tier.toLowerCase();
  if (normalized === "full_access" || normalized === "standard") {
    return "success";
  }
  if (normalized === "read_only" || normalized === "limited") {
    return "warning";
  }
  if (normalized === "deny_all" || normalized === "revoked") {
    return "error";
  }
  return "default";
}

export const Q5EvidencePanel: React.FC<Q5EvidencePanelProps> = ({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const actionableSpace = evidence.actionable_space ?? [];
  const contactPolicy = evidence.contact_policy ?? [];
  const tenantBoundaries = evidence.tenant_boundaries ?? [];
  const trustEntries = Object.entries(evidence.agent_trust_status || {});
  const forbiddenActions = inference?.explicitly_forbidden_actions ?? [];
  const complianceRisks = inference?.compliance_risks ?? [];
  const allowedTargets = inference?.allowed_delegation_targets ?? [];

  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {(providerName || elapsedMs > 0) && (
        <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
          {providerName ? (
            <Chip
              label={`Permission Engine: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          ) : null}
          {elapsedMs > 0 ? (
            <Chip label={`Latency: ${elapsedMs}ms`} size="small" variant="outlined" />
          ) : null}
        </Box>
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【合规基线与前置动作空间区】
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Q4 动作空间
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q5-action-space-zone">
                    {actionableSpace.map((action) => (
                      <Chip key={action} label={action} color="info" variant="outlined" />
                    ))}
                    {actionableSpace.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        当前无可审计动作空间
                      </Typography>
                    ) : null}
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    联系策略与租户边界
                  </Typography>
                  <List dense sx={{ py: 0 }} data-testid="q5-policy-list">
                    {contactPolicy.map((item) => (
                      <ListItem key={item} disableGutters sx={{ py: 0.25 }}>
                        <ListItemText primary={item} />
                      </ListItem>
                    ))}
                    {tenantBoundaries.map((item) => (
                      <ListItem key={item} disableGutters sx={{ py: 0.25 }}>
                        <ListItemText primary={item} />
                      </ListItem>
                    ))}
                    {contactPolicy.length === 0 && tenantBoundaries.length === 0 ? (
                      <ListItem disableGutters>
                        <ListItemText primary="未返回额外策略说明" />
                      </ListItem>
                    ) : null}
                  </List>
                  <Typography variant="subtitle2" gutterBottom sx={{ mt: 1.5 }}>
                    Agent 授信状态
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q5-agent-trust-zone">
                    {trustEntries.map(([agentId, status]) => (
                      <Chip
                        key={agentId}
                        label={`${agentId}: ${status}`}
                        color={trustChipColor(status)}
                        variant={status.toLowerCase() === "trusted" ? "filled" : "outlined"}
                      />
                    ))}
                    {trustEntries.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        当前无额外 Agent 授信记录
                      </Typography>
                    ) : null}
                  </Stack>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderColor: "warning.main", borderWidth: 2 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【许可边界区】
              </Typography>
              {inference ? (
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q5-permission-boundary-zone">
                  <Chip
                    label={`execution_tier=${inference.execution_tier}`}
                    color={executionTierColor(inference.execution_tier)}
                    sx={{ fontWeight: "bold" }}
                  />
                  <Chip
                    label={`interaction_scope=${inference.interaction_scope}`}
                    color="info"
                    variant="outlined"
                  />
                  <Chip
                    label={`requires_human_confirmation=${String(inference.requires_human_confirmation)}`}
                    color={inference.requires_human_confirmation ? "error" : "success"}
                    variant={inference.requires_human_confirmation ? "filled" : "outlined"}
                  />
                  <Chip
                    label={`requires_cloud_audit=${String(inference.requires_cloud_audit)}`}
                    color={inference.requires_cloud_audit ? "warning" : "default"}
                    variant="outlined"
                  />
                </Stack>
              ) : (
                <Alert severity="info">等待合规边界推演结果。</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderColor: "error.main" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                【合规负面清单与风险池区】
              </Typography>
              {inference ? (
                <Stack spacing={2}>
                  <Alert severity="error" data-testid="q5-forbidden-alert">
                    <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                      明确禁止动作
                    </Typography>
                    <List dense sx={{ py: 0.5 }}>
                      {forbiddenActions.map((item) => (
                        <ListItem key={item} disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary={item} />
                        </ListItem>
                      ))}
                      {forbiddenActions.length === 0 ? (
                        <ListItem disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary="当前无新增显式禁令" />
                        </ListItem>
                      ) : null}
                    </List>
                  </Alert>

                  <Alert severity="warning" data-testid="q5-risk-alert">
                    <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                      合规风险
                    </Typography>
                    <List dense sx={{ py: 0.5 }}>
                      {complianceRisks.map((item) => (
                        <ListItem key={item} disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary={item} />
                        </ListItem>
                      ))}
                      {complianceRisks.length === 0 ? (
                        <ListItem disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary="当前无新增合规风险" />
                        </ListItem>
                      ) : null}
                    </List>
                  </Alert>

                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      允许委托的白名单目标
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q5-allowed-targets-zone">
                      {allowedTargets.map((item) => (
                        <Chip key={item} label={item} color="success" variant="outlined" />
                      ))}
                      {allowedTargets.length === 0 ? (
                        <Typography variant="caption" color="text.secondary">
                          当前无白名单委托对象
                        </Typography>
                      ) : null}
                    </Stack>
                  </Box>
                </Stack>
              ) : (
                <Alert severity="info">等待负面清单与风险池数据。</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q5EvidencePanel;
