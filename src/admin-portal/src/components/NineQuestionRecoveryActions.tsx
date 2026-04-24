import { useState } from "react";
import { Alert, Button, Stack, Typography } from "@mui/material";

import {
  executeNineQuestionRecoveryAction,
  type NineQuestionRecoveryPlan,
} from "../pages/nine-questions/nineQuestionsApi";

type Props = {
  qId: string;
  recoveryPlan: NineQuestionRecoveryPlan | null;
  onCompleted?: () => Promise<void> | void;
};

export default function NineQuestionRecoveryActions({ qId, recoveryPlan, onCompleted }: Props) {
  const [runningActionId, setRunningActionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!recoveryPlan) {
    return null;
  }

  const handleAction = async (action: NonNullable<NineQuestionRecoveryPlan["actions"]>[number]) => {
    setRunningActionId(action.action_id);
    setError(null);
    try {
      await executeNineQuestionRecoveryAction(action);
      if (onCompleted) {
        await onCompleted();
      }
    } catch (err: any) {
      setError(err?.message || `${qId.toUpperCase()} 恢复动作执行失败`);
    } finally {
      setRunningActionId(null);
    }
  };

  return (
    <>
      <Typography variant="body2">
        可重试：{recoveryPlan.retriable ? "是" : "否"} | 可回滚：{recoveryPlan.rollback_available ? "是" : "否"} | 局部重试：{recoveryPlan.partial_retry_available ? "是" : "否"} | 局部替换：{recoveryPlan.partial_replace_available ? "是" : "否"}
      </Typography>
      <Stack spacing={1} sx={{ mt: 1 }}>
        {Array.isArray(recoveryPlan.actions) && recoveryPlan.actions.length > 0 ? recoveryPlan.actions.map((action) => (
          <Stack key={String(action.action_id || action.label)} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography
              variant="body2"
              sx={{ fontFamily: "monospace", flex: 1, minWidth: 320 }}
              data-testid={`${qId}-recovery-action-${String(action.action_id || "unknown")}`}
            >
              {String(action.label || action.action_id)} | {String(action.kind || "")} | {String(action.scope || "")} | {action.executable ? "executable" : "plan_only"} | {String(action.target || "")}
            </Typography>
            {action.executable ? (
              <Button
                size="small"
                variant="outlined"
                disabled={runningActionId === action.action_id}
                onClick={() => void handleAction(action)}
                data-testid={`${qId}-recovery-action-button-${String(action.action_id || "unknown")}`}
              >
                {runningActionId === action.action_id ? "执行中..." : "执行"}
              </Button>
            ) : null}
          </Stack>
        )) : (
          <Typography variant="body2">当前没有恢复动作。</Typography>
        )}
      </Stack>
      {error ? (
        <Alert severity="error" sx={{ mt: 1 }} data-testid={`${qId}-recovery-action-error`}>
          {error}
        </Alert>
      ) : null}
    </>
  );
}
