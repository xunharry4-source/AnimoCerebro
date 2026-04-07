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
  Stack,
  Typography,
} from "@mui/material";

import { LLMTracePayloadView } from "../pages/nine-questions/nineQuestionsApi";

function renderCodeBlock(value: unknown) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 2,
        bgcolor: "action.hover",
        borderRadius: 1,
        overflow: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        fontSize: "0.85rem",
      }}
    >
      <code>{typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2)}</code>
    </Box>
  );
}

export default function LLMTracePanel({
  trace,
}: {
  trace: LLMTracePayloadView | null | undefined;
}) {
  return (
    <Card variant="outlined" sx={{ mt: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          大模型交互溯源区
        </Typography>
        {trace ? (
          <>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid size={{ xs: 12, md: 8 }}>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <Chip label={`Provider: ${trace.provider_name || "-"}`} variant="outlined" />
                  <Chip label={`Model: ${trace.model || "-"}`} variant="outlined" />
                  <Chip label={`输入 tokens: ${trace.token_usage?.input_tokens ?? 0}`} color="info" />
                  <Chip label={`输出 tokens: ${trace.token_usage?.output_tokens ?? 0}`} color="success" />
                  <Chip label={`总 tokens: ${trace.token_usage?.total_tokens ?? 0}`} color="warning" />
                  <Chip label={`耗时: ${trace.elapsed_ms ?? 0} ms`} variant="outlined" />
                </Stack>
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                {trace.error_type ? (
                  <Alert severity="error">
                    {trace.error_type}
                    {trace.error_message ? `: ${trace.error_message}` : ""}
                  </Alert>
                ) : (
                  <Alert severity="info">当前展示的是原始 Prompt / Context / Raw Response 溯源数据。</Alert>
                )}
              </Grid>
            </Grid>

            <Stack spacing={1.5}>
              <Accordion defaultExpanded={false} data-testid="llm-trace-prompt-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输入 Prompt</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderCodeBlock(trace.prompt || trace.system_prompt || "No prompt available")}</AccordionDetails>
              </Accordion>

              <Accordion defaultExpanded={false} data-testid="llm-trace-context-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输入 Context</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderCodeBlock(trace.context_data || {})}</AccordionDetails>
              </Accordion>

              <Accordion defaultExpanded={false} data-testid="llm-trace-raw-response-accordion">
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">输出 Raw Response</Typography>
                </AccordionSummary>
                <AccordionDetails>{renderCodeBlock(trace.raw_response || {})}</AccordionDetails>
              </Accordion>
            </Stack>
          </>
        ) : (
          <Alert severity="warning">当前没有可展示的大模型交互溯源数据。</Alert>
        )}
      </CardContent>
    </Card>
  );
}
