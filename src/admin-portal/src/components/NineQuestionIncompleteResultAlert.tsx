import { Alert, Box, Stack, Typography } from "@mui/material";

interface NineQuestionIncompleteResultAlertProps {
  questionId: string;
  result?: unknown;
  contextUpdates?: unknown;
}

export default function NineQuestionIncompleteResultAlert({
  questionId,
  result,
  contextUpdates,
}: NineQuestionIncompleteResultAlertProps) {
  const safeResult = result ?? null;
  const safeContextUpdates = contextUpdates ?? null;

  return (
    <Box sx={{ mt: 2 }}>
      <Alert severity="warning" sx={{ mb: 2 }}>
        {questionId.toUpperCase()} 返回了不完整结果：当前只有原始快照，缺少可渲染的结构化推理结果。
      </Alert>
      <Stack spacing={2}>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: "bold" }}>
            后端 `result`
          </Typography>
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2,
              bgcolor: "action.hover",
              borderRadius: 1,
              overflow: "auto",
              fontSize: "0.85rem",
            }}
          >
            <Typography component="code" sx={{ whiteSpace: "pre-wrap" }}>
              {JSON.stringify(safeResult, null, 2)}
            </Typography>
          </Box>
        </Box>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: "bold" }}>
            后端 `context_updates`
          </Typography>
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 2,
              bgcolor: "action.hover",
              borderRadius: 1,
              overflow: "auto",
              fontSize: "0.85rem",
            }}
          >
            <Typography component="code" sx={{ whiteSpace: "pre-wrap" }}>
              {JSON.stringify(safeContextUpdates, null, 2)}
            </Typography>
          </Box>
        </Box>
      </Stack>
    </Box>
  );
}
