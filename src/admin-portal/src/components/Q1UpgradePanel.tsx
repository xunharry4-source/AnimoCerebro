/**
 * Shows the structured Q1 LLM upgrade planning result so operators can
 * review baseline, candidate, release gate, and validation commands
 * without re-parsing raw context payloads.
 */
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from "@mui/material";

import { Q1LLMUpgradeView } from "../pages/nine-questions/nineQuestionsApi";

interface Q1UpgradePanelProps {
  upgrade?: Q1LLMUpgradeView | null;
}

export default function Q1UpgradePanel({ upgrade }: Q1UpgradePanelProps) {
  if (!upgrade) {
    return null;
  }

  const profile = upgrade.profile;
  const validationCommands = profile?.validation_commands ?? [];

  return (
    <Card variant="outlined" data-testid="q1-upgrade-panel">
      <CardContent>
        <Stack spacing={2}>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: "bold" }}>
              Q1 LLM Upgrade Plan
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Displays the current model optimization plan, candidate version, and release gate for Q1.
            </Typography>
          </Box>

          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip
              label={`状态: ${upgrade.planning_status || "unknown"}`}
              color={upgrade.planning_status === "planned" ? "success" : "default"}
              data-testid="q1-upgrade-status-chip"
            />
            {profile?.baseline_version ? (
              <Chip
                label={`Baseline: ${profile.baseline_version}`}
                variant="outlined"
                data-testid="q1-upgrade-baseline-chip"
              />
            ) : null}
            {upgrade.candidate_version ? (
              <Chip
                label={`Candidate: ${upgrade.candidate_version}`}
                variant="outlined"
                color="warning"
                data-testid="q1-upgrade-candidate-chip"
              />
            ) : null}
            {upgrade.release_gate ? (
              <Chip
                label={`Release Gate: ${upgrade.release_gate}`}
                variant="outlined"
                data-testid="q1-upgrade-release-gate-chip"
              />
            ) : null}
          </Stack>

          {profile ? (
            <>
              <Divider />
              <Stack spacing={1.5}>
                <Typography variant="body2" data-testid="q1-upgrade-objective">
                  <strong>Objective:</strong> {profile.objective_summary}
                </Typography>
                <Typography variant="body2" data-testid="q1-upgrade-target-component">
                  <strong>Target Component:</strong> {profile.target_component}
                </Typography>
                <Typography variant="body2" data-testid="q1-upgrade-target-metric">
                  <strong>Target Metric:</strong> {profile.target_metric}
                </Typography>
                <Typography variant="body2" data-testid="q1-upgrade-dataset">
                  <strong>Recommended Dataset:</strong> {profile.recommended_dataset}
                </Typography>
              </Stack>
            </>
          ) : null}

          {validationCommands.length > 0 ? (
            <>
              <Divider />
              <Box data-testid="q1-upgrade-validation-commands">
                <Typography variant="body2" sx={{ fontWeight: "bold", mb: 1 }}>
                  Validation Commands
                </Typography>
                <Stack spacing={1}>
                  {validationCommands.map((command) => (
                    <Box
                      key={command}
                      component="code"
                      sx={{
                        display: "block",
                        p: 1,
                        borderRadius: 1,
                        bgcolor: "action.hover",
                        fontSize: "0.8rem",
                        overflowX: "auto",
                      }}
                    >
                      {command}
                    </Box>
                  ))}
                </Stack>
              </Box>
            </>
          ) : null}

          {upgrade.error_message ? (
            <Alert severity="warning" data-testid="q1-upgrade-error-alert">
              {upgrade.error_message}
            </Alert>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
