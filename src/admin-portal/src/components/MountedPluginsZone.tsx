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
  Tooltip,
  Typography,
} from "@mui/material";
import { MountedPluginInfo } from "../pages/nine-questions/nineQuestionsApi";
import SecurityIcon from "@mui/icons-material/Security";
import ExtensionIcon from "@mui/icons-material/Extension";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import WarningIcon from "@mui/icons-material/Warning";
import CancelIcon from "@mui/icons-material/Cancel";

interface MountedPluginsZoneProps {
  plugins: MountedPluginInfo[];
}

export default function MountedPluginsZone({ plugins }: MountedPluginsZoneProps) {
  if (!plugins || plugins.length === 0) {
    return (
      <Alert severity="warning" sx={{ mb: 2 }} data-testid="plugin-mount-empty-warning">
        [告警] 当前算子未挂载任何认证插件！检测到潜在的黑盒推演风险。
      </Alert>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "active":
        return "success";
      case "candidate":
        return "info";
      case "degraded":
        return "warning";
      case "revoked":
        return "error";
      default:
        return "default";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case "active":
        return <CheckCircleIcon fontSize="small" />;
      case "candidate":
        return <ExtensionIcon fontSize="small" />;
      case "degraded":
        return <WarningIcon fontSize="small" />;
      case "revoked":
        return <CancelIcon fontSize="small" />;
      default:
        return null;
    }
  };

  const describeSourceKind = (sourceKind: string) => {
    switch (sourceKind) {
      case "patch":
        return "能力补丁 (Patch)";
      case "functional":
        return "功能插件 (Functional)";
      default:
        return "主算子 (Base)";
    }
  };

  const overviewPlugins = plugins.filter((plugin) => plugin.source_kind !== "functional");
  const functionalPlugins = plugins.filter((plugin) => plugin.source_kind === "functional");
  const pluginDisplayName = (plugin: MountedPluginInfo) => plugin.display_name || plugin.plugin_id;
  const pluginFunctionDescription = (plugin: MountedPluginInfo) =>
    plugin.function_description || plugin.description || plugin.plugin_id;

  return (
    <Card 
      variant="outlined" 
      sx={{ 
        mb: 3, 
        borderLeft: 6, 
        borderColor: "primary.main",
        bgcolor: "rgba(25, 118, 210, 0.02)"
      }}
      data-testid="plugin-mount-zone"
    >
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <SecurityIcon color="primary" />
          <Typography variant="h6" sx={{ fontWeight: "bold", letterSpacing: 1 }}>
            PLUGIN & PATCH MOUNT ZONE (算子插件与能力补丁挂载全景)
          </Typography>
        </Stack>

        {overviewPlugins.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: "bold" }}>
              主算子 / 能力补丁
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: functionalPlugins.length > 0 ? 3 : 0 }}>
              {overviewPlugins.map((plugin) => (
                <Tooltip
                  key={plugin.plugin_id}
                  title={
                    <Box sx={{ p: 1, maxWidth: 300 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: "bold" }}>ID: {plugin.plugin_id}</Typography>
                      <Typography variant="caption" display="block">名称: {pluginDisplayName(plugin)}</Typography>
                      <Typography variant="caption" display="block">Version: {plugin.version || "latest"}</Typography>
                      <Typography variant="caption" display="block">Type: {describeSourceKind(plugin.source_kind)}</Typography>
                      <Typography variant="caption" display="block">Status: {plugin.status.toUpperCase()}</Typography>
                      <Typography variant="body2" sx={{ mt: 1 }}>{pluginFunctionDescription(plugin)}</Typography>
                    </Box>
                  }
                  arrow
                  placement="bottom"
                >
                  <Chip
                    icon={getStatusIcon(plugin.status) || undefined}
                    label={`${pluginDisplayName(plugin)} [${plugin.status.toUpperCase()}]`}
                    color={getStatusColor(plugin.status) as any}
                    variant={plugin.source_kind === "base" ? "filled" : "outlined"}
                    sx={{
                      fontWeight: "bold",
                      borderStyle: plugin.source_kind === "patch" ? "dashed" : "solid",
                      borderWidth: 2
                    }}
                    data-testid={`mounted-plugin-${plugin.plugin_id}`}
                  />
                </Tooltip>
              ))}
            </Box>
          </>
        )}

        {functionalPlugins.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: "bold" }}>
              功能插件列表
            </Typography>
            <TableContainer sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
              <Table size="small" data-testid="functional-plugin-table">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: "bold" }}>功能插件名称</TableCell>
                    <TableCell sx={{ fontWeight: "bold" }}>插件功能</TableCell>
                    <TableCell sx={{ fontWeight: "bold", whiteSpace: "nowrap" }}>版本号</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {functionalPlugins.map((plugin) => (
                    <TableRow key={plugin.plugin_id} hover>
                      <TableCell sx={{ verticalAlign: "top" }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {pluginDisplayName(plugin)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {plugin.plugin_id}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ verticalAlign: "top" }}>
                        <Typography variant="body2">{pluginFunctionDescription(plugin)}</Typography>
                        {plugin.description !== pluginFunctionDescription(plugin) && (
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                            {plugin.description}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap", verticalAlign: "top" }}>
                        {plugin.version || "latest"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </CardContent>
    </Card>
  );
}
