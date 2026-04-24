import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

type AuditTraceMode = "nine_questions" | "reflection" | "learning";

const MODE_ROWS: Array<{
  mode: AuditTraceMode;
  title: string;
  sourceLabel: string;
  description: string;
  workflowPath: string;
  tablePath: string;
}> = [
  {
    mode: "nine_questions",
    title: "基于 9 问开始的审计与溯源",
    sourceLabel: "九问工作流",
    description: "从 Q1-Q9 的真实执行链出发，追模块、追插件、追依赖、追恢复动作。",
    workflowPath: "/console/audit/nine_questions/workflow",
    tablePath: "/console/audit/nine_questions/table",
  },
  {
    mode: "reflection",
    title: "基于反思开始的审计与溯源",
    sourceLabel: "反思记录",
    description: "从反思记录出发，回看为什么触发、缺什么、应该回到哪条运行链继续追。",
    workflowPath: "/console/audit/reflection/workflow",
    tablePath: "/console/audit/reflection/table",
  },
  {
    mode: "learning",
    title: "基于学习开始的审计与溯源",
    sourceLabel: "学习循环",
    description: "从学习方向、学习历史和学习 trace 出发，看学习如何反向影响系统行为。",
    workflowPath: "/console/audit/learning/workflow",
    tablePath: "/console/audit/learning/table",
  },
];

export default function AuditTraceCenterPage() {
  return (
    <Box data-testid="audit-trace-center-page" sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Box>
        <Typography variant="h4" gutterBottom>
          审计与溯源中心
        </Typography>
        <Typography variant="body2" color="text.secondary">
          这里只显示 3 个审计起点。先选起点，再进入独立的工作流页或表格页，不再把所有审计内容直接堆在首页。
        </Typography>
      </Box>

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Box>
              <Typography variant="h6">审计起点列表</Typography>
              <Typography variant="body2" color="text.secondary">
                每个起点都提供两种入口：`工作流显示` 和 `表格显示`。
              </Typography>
            </Box>
            <Button component={RouterLink} to="/console/audit/model-provider" variant="outlined">
              查看底层模型调用回放
            </Button>
            <Button component={RouterLink} to="/console/audit/review-ledger" variant="outlined">
              复查台账
            </Button>
          </Stack>

          <Table data-testid="audit-trace-start-table">
            <TableHead>
              <TableRow>
                <TableCell>起点</TableCell>
                <TableCell>说明</TableCell>
                <TableCell>显示方式</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {MODE_ROWS.map((row) => (
                <TableRow key={row.mode} data-testid={`audit-trace-mode-card-${row.mode}`}>
                  <TableCell sx={{ minWidth: 260 }}>
                    <Stack spacing={1}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                        {row.title}
                      </Typography>
                      <Chip size="small" label={`起点：${row.sourceLabel}`} variant="outlined" sx={{ alignSelf: "flex-start" }} />
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{row.description}</Typography>
                  </TableCell>
                  <TableCell sx={{ minWidth: 260 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                      <Button component={RouterLink} to={row.workflowPath} variant="contained">
                        工作流查看
                      </Button>
                      <Button component={RouterLink} to={row.tablePath} variant="outlined">
                        表格查看
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Box>
  );
}
