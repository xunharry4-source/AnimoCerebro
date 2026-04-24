import {
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Typography,
} from "@mui/material";

type RecordLike = Record<string, any>;

function asRecord(value: unknown): RecordLike {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as RecordLike) : {};
}

function statusColor(status: string): "success" | "warning" | "error" | "default" {
  const normalized = status.toLowerCase();
  if (["completed", "success", "ok", "ready"].includes(normalized)) return "success";
  if (["failed", "error", "missing"].includes(normalized)) return "error";
  if (["degraded", "partial", "partial_failed", "running"].includes(normalized)) return "warning";
  return "default";
}

function humanizeModuleId(moduleId: string): string {
  return moduleId.replaceAll("_", " ");
}

export default function NineQuestionIntegrationStatusCard({
  qId,
  modulesPayload,
}: {
  qId: string;
  modulesPayload: Record<string, any> | null;
}) {
  const modules = asRecord(modulesPayload?.modules);
  const integrationEntries = Object.entries(modules)
    .filter(([moduleId]) =>
      moduleId.endsWith("_audit_integration") ||
      moduleId.endsWith("_memory_integration") ||
      moduleId.endsWith("_reflection_integration") ||
      moduleId.endsWith("_learning_integration"),
    )
    .sort(([left], [right]) => left.localeCompare(right));

  if (integrationEntries.length === 0) {
    return null;
  }

  return (
    <Card variant="outlined" data-testid={`${qId}-integration-audit`}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          下游集成状态
        </Typography>
        <Typography variant="body2" sx={{ mb: 2 }}>
          集成模块数：{integrationEntries.length}
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableBody>
              {integrationEntries.map(([moduleId, payload]) => {
                const record = asRecord(payload);
                const data = asRecord(record.data);
                const status = String(record.status || "unknown");
                return (
                  <TableRow key={moduleId} hover data-testid={`${qId}-integration-row-${moduleId}`}>
                    <TableCell sx={{ width: "35%", fontFamily: "monospace" }}>{humanizeModuleId(moduleId)}</TableCell>
                    <TableCell sx={{ width: "20%" }}>
                      <Chip size="small" label={status} color={statusColor(status)} />
                    </TableCell>
                    <TableCell sx={{ width: "20%", fontFamily: "monospace" }}>{String(data.module_kind || record.output_kind || "")}</TableCell>
                    <TableCell>{String(data.summary || record.error_message || record.error_code || "")}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}
