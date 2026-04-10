import { Button, Card, CardContent, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

type PluginLifecycleTestPageProps = {
  onBack: () => void;
};

export default function PluginLifecycleTestPage({ onBack }: PluginLifecycleTestPageProps) {
  const { t } = useTranslation();
  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        {t("test.pluginLifecycleTitle")}
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="subtitle1">{t("test.pluginLifecycleSubtitle")}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t("test.pluginLifecycleDescription")}
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
