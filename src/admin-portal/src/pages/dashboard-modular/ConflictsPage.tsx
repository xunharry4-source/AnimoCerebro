import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { fetchJson } from "./api";
import type { CognitiveConflict } from "./types";

type ConflictsPayload = { conflicts: CognitiveConflict[] };

export default function ConflictsPage() {
  const [data, setData] = useState<CognitiveConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchJson<ConflictsPayload>("/api/web/cognitive-conflicts");
        if (active) {
          setData(payload.conflicts || []);
        }
      } catch {
        if (active) {
          setError("冲突模块加载失败");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={2}>
        <Typography variant="h4">冲突模块</Typography>
        {loading ? <Typography color="text.secondary">加载中...</Typography> : null}
        {error ? <Alert severity="error">{error}</Alert> : null}

        {!loading && !error ? (
          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>类型</TableCell>
                      <TableCell>严重级别</TableCell>
                      <TableCell>状态</TableCell>
                      <TableCell>建议</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.length > 0 ? (
                      data.map((item) => (
                        <TableRow key={item.conflict_id}>
                          <TableCell>{item.conflict_type}</TableCell>
                          <TableCell>
                            <Chip label={item.severity} size="small" color={item.severity === "critical" ? "error" : "default"} />
                          </TableCell>
                          <TableCell>{item.status}</TableCell>
                          <TableCell>{item.suggested_resolution}</TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={4}>暂无冲突</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        ) : null}
      </Stack>
    </Box>
  );
}
