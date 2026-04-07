import { Button, Card, CardContent, Stack, Typography } from "@mui/material";

type PluginLifecycleTestPageProps = {
  onBack: () => void;
};

export default function PluginLifecycleTestPage({ onBack }: PluginLifecycleTestPageProps) {
  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        插件生命周期测试
      </Typography>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="subtitle1">验证插件启停、降级、回滚链路是否符合预期。</Typography>
            <Typography variant="body2" color="text.secondary">
              在这里执行插件管理相关测试，例如强制启用/停用后的状态一致性检查。
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
