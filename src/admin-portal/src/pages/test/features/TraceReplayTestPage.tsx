import { Button, Card, CardContent, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

type TraceReplayTestPageProps = {
  onBack: () => void;
};

export default function TraceReplayTestPage({ onBack }: TraceReplayTestPageProps) {
  const { t } = useTranslation();
  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        {t("test.traceReplayTitle")}
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="subtitle1">{t("test.traceReplaySubtitle")}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t("test.traceReplayDescription")}
            </Typography>
            <Stack direction="row">
              <Button variant="outlined" onClick={onBack}>
                {t("test.backToTestList")}
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
