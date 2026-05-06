import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link as RouterLink } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ArticleIcon from "@mui/icons-material/Article";
import { Locale, formatLocalizedToken, formatUserFacingError, simulationCopy } from "../../i18n";

/** 单个预演分支在前端中的展示结构。 */
type ScenarioBranch = {
  branch_id: string;
  branch_label: string;
  target_domain: string;
  predicted_impacts: string[];
  risk_score: number;
  failure_cascade: boolean;
  veto_reason?: string | null;
  simulated_by: string[];
};

/** 后端返回的完整多分支预演结果。 */
type SimulationBundle = {
  goal_id: string;
  status: string;
  branches: ScenarioBranch[];
  outcome_comparison: {
    summary: string;
    risk_ranking: Array<{ branch_id: string; risk_score: number; rank: number }>;
    recommended_branch_id: string;
  } | null;
};

export default function SimulationExplorer() {
  const { t } = useTranslation();
  const locale: Locale = "zh-CN";
  const copy = simulationCopy[locale];
  const [goalId, setGoalId] = useState("");
  const [bundle, setBundle] = useState<SimulationBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 为什么这里优先用 branch_label：用户需要看到“哪个方案更推荐”，而不是内部 branch_id。
  const recommendedBranchLabel = bundle?.outcome_comparison
    ? bundle.branches.find(
      (branch) => branch.branch_id === bundle.outcome_comparison?.recommended_branch_id,
    )?.branch_label ?? formatLocalizedToken(bundle.outcome_comparison.recommended_branch_id, locale)
    : "--";

  const loadBundle = async (): Promise<void> => {
    const normalizedGoalId = goalId.trim();
    if (!normalizedGoalId) {
      setBundle(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/web/simulations/${encodeURIComponent(normalizedGoalId)}`);
      if (!response.ok) {
        throw new Error("simulation_fetch_failed");
      }
      const payload = (await response.json()) as { bundle: SimulationBundle };
      setBundle(payload.bundle);
    } catch {
      setError(formatUserFacingError(locale));
    } finally {
      setLoading(false);
    }
  };

  const failureCascadeBranches = bundle?.branches.filter((branch) => branch.failure_cascade) || [];

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} alignItems="center">
        <TextField
          label={copy.goalIdLabel}
          value={goalId}
          onChange={(event) => setGoalId(event.target.value)}
          size="small"
        />
        <Button variant="contained" onClick={() => void loadBundle()} disabled={!goalId.trim()}>
          {copy.refresh}
        </Button>
        <Button
          component={RouterLink}
          to="/console/module-logs/simulation"
          variant="outlined"
          startIcon={<ArticleIcon />}
        >
          {t("moduleLogs.view")}
        </Button>
      </Stack>

      {loading ? (
        <Stack alignItems="center" py={6}>
          <CircularProgress />
        </Stack>
      ) : null}

      {error ? <Alert severity="error">{error}</Alert> : null}

      {failureCascadeBranches.length > 0 ? (
        <Alert severity="error">
          {copy.disasterWarning}
        </Alert>
      ) : null}

      {bundle?.outcome_comparison ? (
        <Card>
          <CardContent>
            <Typography variant="h6">{copy.branchComparison}</Typography>
            <Typography variant="body2" color="text.secondary">
              {bundle.outcome_comparison.summary}
            </Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>
              {copy.recommendedBranch}：{recommendedBranchLabel}
            </Typography>
          </CardContent>
        </Card>
      ) : null}

      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        {bundle?.branches.map((branch) => (
          <Card key={branch.branch_id} sx={{ width: 320 }} data-testid="simulation-branch-card">
            <CardContent>
              <Typography variant="h6">{branch.branch_label}</Typography>
              <Typography variant="body2" color="text.secondary">
                {copy.targetDomain}：{formatLocalizedToken(branch.target_domain, locale)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {copy.riskScore}：{branch.risk_score.toFixed(2)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {copy.simulationSource}：{branch.simulated_by.map((item) => formatLocalizedToken(item, locale)).join("、")}
              </Typography>
              <Stack spacing={1} sx={{ mt: 2 }}>
                {branch.predicted_impacts.map((impact) => (
                  <Typography key={impact} variant="body2">
                    {impact}
                  </Typography>
                ))}
              </Stack>
              {branch.failure_cascade ? (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {copy.disasterCascade}
                </Alert>
              ) : null}
              {branch.veto_reason ? (
                <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                  {formatLocalizedToken(branch.veto_reason, locale)}
                </Typography>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Stack>
  );
}
