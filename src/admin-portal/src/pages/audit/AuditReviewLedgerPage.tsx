import { Alert, Box, Card, CardContent, Chip, Stack, Typography } from "@mui/material";

const FILE_GROUPS = [
  {
    title: "上游更新复查重点",
    items: [
      "src/zentex/nine_questions/query.py",
      "src/plugins/nine_questions/q2_asset_inventory/q2_asset_inventory_plugin.py",
      "src/plugins/nine_questions/q6_what_should_i_not_do/q6_what_should_i_not_do_plugin.py",
      "src/plugins/nine_questions/q8_what_should_i_do_now/q8_what_should_i_do_now_plugin.py",
      "src/plugins/nine_questions/q9_how_should_i_act/q9_how_should_i_act_plugin.py",
    ],
  },
  {
    title: "前端审计页面",
    items: [
      "src/admin-portal/src/pages/audit/AuditTraceCenterPage.tsx",
      "src/admin-portal/src/pages/audit/AuditTraceModePage.tsx",
      "src/admin-portal/src/pages/audit/auditApi.ts",
      "src/admin-portal/src/pages/nine-questions/NineQuestionWorkflowGraphPage.tsx",
      "src/admin-portal/src/App.tsx",
    ],
  },
  {
    title: "后端审计数据库与接口",
    items: [
      "src/zentex/web_console/storage/audit_trace.py",
      "src/zentex/web_console/services/audit.py",
      "src/zentex/web_console/routers/audit.py",
      "src/zentex/web_console/routers/audit_commons.py",
      "src/zentex/web_console/contracts/audit.py",
      "src/zentex/web_console/app.py",
    ],
  },
  {
    title: "验证文件",
    items: [
      "tests/unit/common/test_audit_trace_store.py",
      "src/admin-portal/src/pages/audit/AuditTraceCenterPage.test.tsx",
      "src/admin-portal/src/pages/audit/AuditTraceModePage.test.tsx",
      "src/admin-portal/src/pages/nine-questions/NineQuestionWorkflowGraphPage.test.tsx",
    ],
  },
];

export default function AuditReviewLedgerPage() {
  return (
    <Stack spacing={3} data-testid="audit-review-ledger-page">
      <Box>
        <Typography variant="h4" gutterBottom>
          审计模块复查台账
        </Typography>
        <Typography variant="body2" color="text.secondary">
          这个页面只用于复查审计模块改动范围，完整说明文档在 `docs/AUDIT_MODULE_REVIEW_LEDGER.md`。
        </Typography>
      </Box>

      <Alert severity="info">
        审计模块当前的复查重点是五件事：数据库持久化、多泳道工作流页、所有模块族都进入统一 graph family、驱动层节点可见、以及执行层节点没有被后续修改删掉。
      </Alert>

      <Alert severity="warning">
        2026-04-20 已吸收上游 `8145d0b`。这次更新没有直接覆盖审计页面，但改动触达了 `query.py` 和 `Q2/Q6/Q8/Q9`，后续任何人修改这些文件时，都必须同步复查审计状态解释是否还正确。
      </Alert>

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        <Chip label="审计数据已落库" color="success" />
        <Chip label="首页只显示起点" variant="outlined" />
        <Chip label="工作流页数据库驱动" variant="outlined" />
        <Chip label="全模块族 graph family" variant="outlined" />
        <Chip label="驱动层节点已接入" variant="outlined" />
        <Chip label="执行层节点已接入" variant="outlined" />
        <Chip label="已复查上游 8145d0b" color="warning" variant="outlined" />
        <Chip label="Q2/Q6/Q8/Q9 需持续复查" color="warning" variant="outlined" />
      </Stack>

      {FILE_GROUPS.map((group) => (
        <Card key={group.title} variant="outlined">
          <CardContent>
            <Stack spacing={1}>
              <Typography variant="h6">{group.title}</Typography>
              {group.items.map((item) => (
                <Box
                  key={item}
                  sx={{
                    px: 1.25,
                    py: 1,
                    borderRadius: 2,
                    bgcolor: "rgba(15,23,42,0.04)",
                    fontFamily: "monospace",
                    fontSize: 13,
                    wordBreak: "break-all",
                  }}
                >
                  {item}
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      ))}
    </Stack>
  );
}
