import { Alert, Button, Typography } from "@mui/material";
import type { ModuleErrorInfo } from "./moduleRequest";

type ModuleStatusBannerProps = {
  loading: boolean;
  error: ModuleErrorInfo | null;
  onRetry: () => void;
};

export default function ModuleStatusBanner({
  loading,
  error,
  onRetry,
}: ModuleStatusBannerProps) {
  if (loading) {
    return <Typography color="text.secondary">加载中...</Typography>;
  }

  if (!error) {
    return null;
  }

  return (
    <Alert
      severity="error"
      action={
        error.retryable ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            重试
          </Button>
        ) : null
      }
    >
      {error.message}
      {error.status ? ` (HTTP ${error.status})` : ""}
      {` [code=${error.code}]`}
    </Alert>
  );
}
