import React from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
              label={`${t("nineQuestions.permissionEngine")}: ${providerName}`}
              size="small"
              variant="outlined"
              color="primary"
            />
          ) : null}
          {elapsedMs > 0 ? (
            <Chip label={`${t("common.latency")}: ${elapsedMs}ms`} size="small" variant="outlined" />
          ) : null}
        </Box>
      )}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                {t("nineQuestions.complianceBaseline")}
              </Typography>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    {t("nineQuestions.q4ActionSpace")}
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q5-action-space-zone">
                    {actionableSpace.map((action) => (
                      <Chip key={action} label={action} color="info" variant="outlined" />
                    ))}
                    {actionableSpace.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">
                        {t("nineQuestions.noAuditableActionSpace")}
                      </Typography>
                    ) : null}
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    {t("nineQuestions.contactPolicyTenantBoundaries")}
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
                        <ListItemText primary={t("nineQuestions.noExtraPolicies")} />
                      </ListItem>
                    ) : null}
                  </List>
                  <Typography variant="subtitle2" gutterBottom sx={{ mt: 1.5 }}>
                    {t("nineQuestions.agentTrustStatus")}
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
                        {t("nineQuestions.noExtraAgentTrust")}
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
                {t("nineQuestions.permissionBoundaryZone")}
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
                <Alert severity="info">{t("nineQuestions.waitingComplianceInference")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12 }}>
          <Card variant="outlined" sx={{ borderColor: "error.main" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: "bold" }}>
                {t("nineQuestions.complianceNegativeList")}
              </Typography>
              {inference ? (
                <Stack spacing={2}>
                  <Alert severity="error" data-testid="q5-forbidden-alert">
                    <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                      {t("nineQuestions.explicitlyForbiddenActions")}
                    </Typography>
                    <List dense sx={{ py: 0.5 }}>
                      {forbiddenActions.map((item) => (
                        <ListItem key={item} disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary={item} />
                        </ListItem>
                      ))}
                      {forbiddenActions.length === 0 ? (
                        <ListItem disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary={t("nineQuestions.noNewExplicitBans")} />
                        </ListItem>
                      ) : null}
                    </List>
                  </Alert>

                  <Alert severity="warning" data-testid="q5-risk-alert">
                    <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>
                      {t("nineQuestions.complianceRisks")}
                    </Typography>
                    <List dense sx={{ py: 0.5 }}>
                      {complianceRisks.map((item) => (
                        <ListItem key={item} disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary={item} />
                        </ListItem>
                      ))}
                      {complianceRisks.length === 0 ? (
                        <ListItem disableGutters sx={{ py: 0.25 }}>
                          <ListItemText primary={t("nineQuestions.noNewComplianceRisks")} />
                        </ListItem>
                      ) : null}
                    </List>
                  </Alert>

                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      {t("nineQuestions.allowedDelegationTargets")}
                    </Typography>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" data-testid="q5-allowed-targets-zone">
                      {allowedTargets.map((item) => (
                        <Chip key={item} label={item} color="success" variant="outlined" />
                      ))}
                      {allowedTargets.length === 0 ? (
                        <Typography variant="caption" color="text.secondary">
                          {t("nineQuestions.noWhitelistDelegates")}
                        </Typography>
                      ) : null}
                    </Stack>
                  </Box>
                </Stack>
              ) : (
                <Alert severity="info">{t("nineQuestions.waitingNegativeListData")}</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q5EvidencePanel;
