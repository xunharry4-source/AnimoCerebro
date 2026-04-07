import { Button, Card, CardContent, Stack, Typography } from "@mui/material";

type InterventionTestPageProps = {
  onBack: () => void;
};

export default function InterventionTestPage({ onBack }: InterventionTestPageProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        人工干预测试
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="subtitle1">验证人工干预写回、幂等与回放展示是否正确。</Typography>
            <Typography variant="body2" color="text.secondary">
              在这里执行干预流程测试，例如重复 idempotency_key 时的回放去重。
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
