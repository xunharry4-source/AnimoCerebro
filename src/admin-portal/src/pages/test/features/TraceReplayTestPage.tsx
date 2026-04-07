import { Button, Card, CardContent, Stack, Typography } from "@mui/material";

type TraceReplayTestPageProps = {
  onBack: () => void;
};

export default function TraceReplayTestPage({ onBack }: TraceReplayTestPageProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        溯源链路测试
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="subtitle1">验证 Trace 聚合、事件回放与上下文摘要是否一致。</Typography>
            <Typography variant="body2" color="text.secondary">
              在这里执行溯源链路相关测试，例如按 trace_id 拉取并检查事件顺序与关键字段。
            </Typography>
            <Stack direction="row">
              <Button variant="outlined" onClick={onBack}>
                返回测试列表
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
