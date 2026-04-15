import { Box, Button, Card, CardContent, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

const MODULE_LINKS = [
  { path: "/console/dashboard/runtime", title: "运行时总览", desc: "独立接口: /api/web/overview" },
  { path: "/console/dashboard/plugins", title: "插件状态", desc: "独立接口: /api/web/plugins/cognitive" },
  { path: "/console/dashboard/conflicts", title: "冲突面板", desc: "独立接口: /api/web/cognitive-conflicts" },
  { path: "/console/dashboard/events", title: "事件流", desc: "独立接口: /api/web/overview (recent_events)" },
  { path: "/console/dashboard/interaction", title: "交互心智", desc: "独立接口: /api/web/interaction-mind/:id" },
];

export default function ModularDashboardHome() {
  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h4">模块化控制台</Typography>
        <Typography color="text.secondary">
          每个模块独立页面、独立接口、独立失败，不会因为单个模块异常导致整页崩溃。
        </Typography>

        <Stack spacing={1.5}>
          {MODULE_LINKS.map((item) => (
            <Card key={item.path} variant="outlined">
              <CardContent>
                <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                  <Box>
                    <Typography variant="h6">{item.title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {item.desc}
                    </Typography>
                  </Box>
                  <Button component={RouterLink} to={item.path} variant="contained">
                    进入模块
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      </Stack>
    </Box>
  );
}
