import { useState } from "react";
import { Alert, Button } from "@mui/material";
import AutorenewIcon from "@mui/icons-material/Autorenew";

import { runSingleNineQuestion } from "../pages/nine-questions/nineQuestionsApi";

type NineQuestionRerunButtonProps = {
  qId: string;
  onCompleted?: () => Promise<void> | void;
  runPayload?: Record<string, unknown>;
};

export default function NineQuestionRerunButton({ qId, onCompleted, runPayload }: NineQuestionRerunButtonProps) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      if (runPayload) {
        await runSingleNineQuestion(qId, true, runPayload);
      } else {
        await runSingleNineQuestion(qId, true);
      }
      if (onCompleted) {
        await onCompleted();
      }
    } catch (err: any) {
      setError(err?.message || `${qId.toUpperCase()} 单独重启失败`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <Button
        variant="outlined"
        color="primary"
        startIcon={<AutorenewIcon />}
        onClick={() => void handleRun()}
        disabled={running}
        data-testid={`${qId}-rerun-button`}
      >
        {running ? "重启中..." : "单独重启"}
      </Button>
      {error ? (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      ) : null}
    </>
  );
}
