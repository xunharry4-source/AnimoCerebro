import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Card,
  CardContent,
  Stack,
  Typography,
} from "@mui/material";

interface NineQuestionRawPayloadCardProps {
  title: string;
  warnings?: string[];
  payloads: Array<{
    label: string;
    value: unknown;
  }>;
}

export default function NineQuestionRawPayloadCard({
  title,
  warnings = [],
  payloads,
}: NineQuestionRawPayloadCardProps) {
  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {title}
        </Typography>
        {warnings.length > 0 ? (
          <Stack spacing={1} sx={{ mb: 2 }}>
            {warnings.map((warning) => (
              <Alert key={warning} severity="warning">
                {warning}
              </Alert>
            ))}
          </Stack>
        ) : (
          <Alert severity="info" sx={{ mb: 2 }}>
            当前展示的是接口返回的原始字段快照，供排查结构问题时参考。
          </Alert>
        )}

        <Stack spacing={1.5}>
          {payloads.map((payload) => (
            <Accordion key={payload.label} disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">{payload.label}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <pre
                  style={{
                    margin: 0,
                    padding: "12px",
                    background: "rgba(0,0,0,0.04)",
                    borderRadius: "8px",
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    fontSize: "0.8rem",
                  }}
                >
                  <code>{JSON.stringify(payload.value ?? null, null, 2)}</code>
                </pre>
              </AccordionDetails>
            </Accordion>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
