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
import type { CognitivePluginRow } from "./types";

export default function PluginsStatusPage() {
  const [data, setData] = useState<CognitivePluginRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchJson<CognitivePluginRow[]>("/api/web/plugins/cognitive");
        if (active) {
          setData(payload);
        }
      } catch {
        if (active) {
          setError("插件状态加载失败");
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
        <Typography variant="h4">插件状态模块</Typography>
        {loading ? <Typography color="text.secondary">加载中...</Typography> : null}
        {error ? <Alert severity="error">{error}</Alert> : null}

        {!loading && !error ? (
          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Tool ID</TableCell>
                      <TableCell>状态</TableCell>
                      <TableCell>健康度</TableCell>
                      <TableCell align="right">使用数</TableCell>
                      <TableCell align="right">失败数</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.length > 0 ? (
                      data.map((item) => (
                        <TableRow key={item.tool_id}>
                          <TableCell>{item.tool_id}</TableCell>
                          <TableCell>
                            <Chip size="small" label={item.status} />
                          </TableCell>
                          <TableCell>{item.health_status || "unknown"}</TableCell>
                          <TableCell align="right">{item.usage_count}</TableCell>
                          <TableCell align="right">{item.failure_count}</TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={5}>暂无插件数据</TableCell>
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
