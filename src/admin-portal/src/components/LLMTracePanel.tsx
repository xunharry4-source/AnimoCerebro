import { useState } from "react";
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
  Tab,
  Tabs,
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

function invocationTabLabel(invocation: LLMTracePayloadView | undefined, index: number) {
  const phase = String(invocation?.invocation_phase || invocation?.source_module || "").toLowerCase();
  if (phase.includes("internal")) return `内部${index + 1}`;
  if (phase.includes("external")) return `外部${index + 1}`;
  return `执行${index + 1}`;
}

export default function LLMTracePanel({
  trace,
}: {
  trace: LLMTracePayloadView | null | undefined;
}) {
  const invocations = trace?.invocations?.length ? trace.invocations : trace ? [trace] : [];
  const [activeInvocationIndex, setActiveInvocationIndex] = useState(0);
  const activeInvocation = invocations[Math.min(activeInvocationIndex, Math.max(invocations.length - 1, 0))];

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
                  <Chip label={`LLM 调用次数: ${invocations.length}`} variant="outlined" />
                </Stack>
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                {trace.error_type ? (
                  <Alert severity="error">
                    {trace.error_type}
                    {trace.error_message ? `: ${trace.error_message}` : ""}
                  </Alert>
                ) : (
                  <Alert severity="info">当前展示的是原始 System Prompt / Prompt / Context / Raw Response 溯源数据。</Alert>
                )}
              </Grid>
            </Grid>

            {invocations.length > 1 ? (
              <Tabs
                value={Math.min(activeInvocationIndex, invocations.length - 1)}
                onChange={(_, nextIndex) => setActiveInvocationIndex(nextIndex)}
                sx={{ mb: 1.5, borderBottom: 1, borderColor: "divider" }}
                variant="scrollable"
                scrollButtons="auto"
              >
                {invocations.map((invocation, index) => (
                  <Tab key={`llm-trace-tab-${index}`} label={invocationTabLabel(invocation, index)} data-testid={`llm-trace-tab-${index + 1}`} />
                ))}
              </Tabs>
            ) : null}

            {activeInvocation ? (
              <Box sx={{ border: 1, borderColor: "divider", borderRadius: 1 }}>
                <Box sx={{ px: 2, py: 1.5 }}>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                    <Typography variant="subtitle2">执行{Math.min(activeInvocationIndex, invocations.length - 1) + 1}</Typography>
                    <Chip
                      size="small"
                      label={activeInvocation.invocation_phase || activeInvocation.source_module || activeInvocation.decision_id || activeInvocation.request_id || `执行${Math.min(activeInvocationIndex, invocations.length - 1) + 1}`}
                      variant="outlined"
                    />
                    <Chip size="small" label={`Provider: ${activeInvocation.provider_name || "-"}`} variant="outlined" />
                    <Chip size="small" label={`Model: ${activeInvocation.model || "-"}`} variant="outlined" />
                    <Chip size="small" label={`总 tokens: ${activeInvocation.token_usage?.total_tokens ?? 0}`} color="warning" />
                  </Stack>
                </Box>

                <Accordion defaultExpanded={false} data-testid={`llm-trace-system-prompt-accordion-${Math.min(activeInvocationIndex, invocations.length - 1) + 1}`}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle2">输入 System Prompt</Typography>
                  </AccordionSummary>
                  <AccordionDetails>{renderCodeBlock(activeInvocation.system_prompt || "No system prompt available")}</AccordionDetails>
                </Accordion>

                <Accordion defaultExpanded={false} data-testid={`llm-trace-prompt-accordion-${Math.min(activeInvocationIndex, invocations.length - 1) + 1}`}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle2">输入 Prompt</Typography>
                  </AccordionSummary>
                  <AccordionDetails>{renderCodeBlock(activeInvocation.prompt || "No prompt available")}</AccordionDetails>
                </Accordion>

                <Accordion defaultExpanded={false} data-testid={`llm-trace-context-accordion-${Math.min(activeInvocationIndex, invocations.length - 1) + 1}`}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle2">输入 Context</Typography>
                  </AccordionSummary>
                  <AccordionDetails>{renderCodeBlock(activeInvocation.context_data || {})}</AccordionDetails>
                </Accordion>

                <Accordion defaultExpanded={false} data-testid={`llm-trace-raw-response-accordion-${Math.min(activeInvocationIndex, invocations.length - 1) + 1}`}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="subtitle2">输出 Raw Response</Typography>
                  </AccordionSummary>
                  <AccordionDetails>{renderCodeBlock(activeInvocation.raw_response || {})}</AccordionDetails>
                </Accordion>

                {"result" in activeInvocation ? (
                  <Accordion defaultExpanded={false} data-testid={`llm-trace-result-accordion-${Math.min(activeInvocationIndex, invocations.length - 1) + 1}`}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="subtitle2">输出 Result</Typography>
                    </AccordionSummary>
                    <AccordionDetails>{renderCodeBlock((activeInvocation as Record<string, unknown>).result || {})}</AccordionDetails>
                  </Accordion>
                ) : null}
              </Box>
            ) : null}
          </>
        ) : (
          <Alert severity="warning">当前没有可展示的大模型交互溯源数据。</Alert>
        )}
      </CardContent>
    </Card>
  );
}
