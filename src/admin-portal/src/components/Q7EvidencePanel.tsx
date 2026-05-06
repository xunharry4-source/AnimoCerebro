import React from "react";
import {
  Alert,
  AlertTitle,
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";
import GavelIcon from "@mui/icons-material/Gavel";
import ReportProblemIcon from "@mui/icons-material/ReportProblem";
import SecurityIcon from "@mui/icons-material/Security";
import SourceIcon from "@mui/icons-material/Source";
import {
  Q7PreprocessedEvidence,
  Q7AlternativeStrategyInferenceView,
} from "../pages/nine-questions/nineQuestionsApi";

interface Q7EvidencePanelProps {
  evidence: Q7PreprocessedEvidence;
  inference: Q7AlternativeStrategyInferenceView | null | undefined;
  providerName?: string | null;
  elapsedMs?: number;
}

function renderList(items: string[] | undefined, emptyText: string, icon: React.ReactNode) {
  const normalized = (items || []).map((item) => String(item || "").trim()).filter(Boolean);
  if (!normalized.length) {
    return <Alert severity="info" variant="outlined">{emptyText}</Alert>;
  }
  return (
    <List dense disablePadding>
      {normalized.map((item, index) => (
        <ListItem key={`${item}-${index}`} divider={index < normalized.length - 1}>
          <ListItemIcon sx={{ minWidth: 32 }}>{icon}</ListItemIcon>
          <ListItemText primary={item} primaryTypographyProps={{ variant: "body2" }} />
        </ListItem>
      ))}
    </List>
  );
}

export const Q7EvidencePanel: React.FC<Q7EvidencePanelProps> = ({
  evidence,
  inference,
  providerName,
  elapsedMs = 0,
}) => {
  const currentHits = inference?.current_red_line_hits || [];
  const rejectedRecords = inference?.rejected_operation_records || [];
  const constraints = inference?.non_bypassable_constraints || evidence.non_bypassable_constraints || [];
  const sources = inference?.ban_source_explanations || evidence.ban_source_explanations || [];

  return (
    <Stack spacing={3} sx={{ mt: 2 }}>
      {(providerName || elapsedMs > 0) ? (
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {providerName ? <Chip label={`LLM: ${providerName}`} size="small" variant="outlined" color="error" /> : null}
          {elapsedMs > 0 ? <Chip label={`latency: ${elapsedMs}ms`} size="small" variant="outlined" /> : null}
        </Box>
      ) : null}

      <Alert
        severity="error"
        icon={<GavelIcon fontSize="inherit" />}
        data-testid="q7-red-line-alert"
        sx={{
          border: "2px solid",
          borderColor: "error.main",
          "& .MuiAlert-message": { width: "100%" },
        }}
      >
        <AlertTitle>Q7 红线与不可绕过约束</AlertTitle>
        <Typography variant="body2" sx={{ mb: 1 }}>
          当前页展示的是 Q8 任务生成前的最后一道认知级防火墙。以下约束不能被动态目标、探索动机或效率诉求覆盖。
        </Typography>
        <Stack spacing={1} data-testid="q7-non-bypassable-constraints">
          {constraints.length > 0 ? (
            constraints.map((constraint, index) => (
              <Alert key={`${constraint}-${index}`} severity="error" variant="filled" icon={<GavelIcon fontSize="inherit" />}>
                {constraint}
              </Alert>
            ))
          ) : (
            <Alert severity="warning">未读取到不可绕过约束，Q8 不应继续生成外部任务。</Alert>
          )}
        </Stack>
      </Alert>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ borderColor: "error.main" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <ReportProblemIcon color="error" /> 当前红线命中
              </Typography>
              {renderList(currentHits, "LLM 明确报告无当前红线命中。", <ReportProblemIcon color="error" fontSize="small" />)}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ borderColor: "warning.main" }}>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <SecurityIcon color="warning" /> 拒绝操作记录
              </Typography>
              {renderList(rejectedRecords, "未发现近期安全闸门或云审计正式拒绝记录。", <SecurityIcon color="warning" fontSize="small" />)}
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>输入证据</Typography>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip color="error" variant="outlined" label={`IdentityKernel ${evidence.identity_kernel_constraints?.length || 0}`} />
                <Chip color="warning" variant="outlined" label={`Q5 ${evidence.authorization_boundary_constraints?.length || 0}`} />
                <Chip color="error" variant="outlined" label={`G12/G30 ${evidence.safety_rejection_history?.length || 0}`} />
                <Chip color="secondary" variant="outlined" label={`G38 ${evidence.procedural_memory_constraints?.length || 0}`} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <SourceIcon color="primary" /> 禁令来源说明
              </Typography>
              {renderList(sources, "暂无禁令来源说明。", <SourceIcon color="primary" fontSize="small" />)}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
};

export default Q7EvidencePanel;
