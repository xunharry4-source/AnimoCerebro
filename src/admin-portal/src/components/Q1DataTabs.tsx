import { Card, CardContent, Tab, Tabs, Table, TableBody, TableCell, TableContainer, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import { Q1PreprocessedEvidence, WorkspaceDomainInferenceView } from "../pages/nine-questions/nineQuestionsApi";

interface Q1DataTabsProps {
  evidence: Q1PreprocessedEvidence | null;
  inference: WorkspaceDomainInferenceView | null;
}

/**
 * Q1 实际数据Tab面板组件
 * Tab 1: 目标达成情况
 * Tab 2: 实际获取的数据
 * Tab 3: 最终输出结果
 */
export default function Q1DataTabs({ evidence, inference }: Q1DataTabsProps) {
  const [activeTab, setActiveTab] = useState(0);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom fontWeight="bold">
          📊 Q1 实际数据详情
        </Typography>

        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          aria-label="q1 data tabs"
          sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
        >
          <Tab label="🎯 目标达成" />
          <Tab label="📊 获取数据" />
          <Tab label="✨ 输出结果" />
        </Tabs>

        {/* Tab 1: 目标达成情况 */}
        {activeTab === 0 && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "40%" }}>目标</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "60%" }}>达成状态</TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>环境态势感知</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={evidence ? "success.main" : "error.main"}>
                      {evidence ? "✅ 已获取物理主机、工作区结构、内容采样数据" : "❌ 未获取"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>工作区领域归类</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={inference ? "success.main" : "error.main"}>
                      {inference ? `✅ 已推断主领域: ${inference.primary_domain}` : "❌ 未完成"}
                    </Typography>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {/* Tab 2: 实际获取的数据 */}
        {activeTab === 1 && evidence && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "30%" }}>数据类型</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "70%" }}>具体内容</TableCell>
                </TableRow>
                
                {/* 物理环境数据 */}
                <TableRow hover>
                  <TableCell>物理主机状态</TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                      主机名: {evidence.physical_and_environment.physical_host_state?.hostname || "N/A"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>内存压力</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.physical_and_environment.memory_pressure_status}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>网络健康</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.physical_and_environment.network_health_status}
                    </Typography>
                  </TableCell>
                </TableRow>

                {/* 工作区结构 */}
                <TableRow hover>
                  <TableCell>顶层目录数</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.workspace_structure.top_level_dirs?.length || 0} 个
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>文件总数</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.workspace_structure.file_total_count || "N/A"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>候选组</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.workspace_structure.candidate_groups?.join(", ") || "无"}
                    </Typography>
                  </TableCell>
                </TableRow>

                {/* 内容采样 */}
                <TableRow hover>
                  <TableCell>采样文件数</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.workspace_content_sampling.sample_count} 个
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>异常片段数</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {evidence.workspace_content_sampling.anomaly_count} 个
                    </Typography>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {activeTab === 1 && !evidence && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            ⚠️ 暂无预处理证据数据
          </Typography>
        )}

        {/* Tab 3: 最终输出结果 */}
        {activeTab === 2 && inference && (
          <TableContainer>
            <Table size="small">
              <TableBody>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: "bold", width: "30%" }}>输出字段</TableCell>
                  <TableCell sx={{ fontWeight: "bold", width: "70%" }}>值</TableCell>
                </TableRow>
                
                <TableRow hover>
                  <TableCell>主领域</TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold" color="primary">
                      {inference.primary_domain}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>次领域</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {inference.secondary_domains?.join(", ") || "无"}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>置信度</TableCell>
                  <TableCell>
                    <Typography variant="body2" color={(inference.confidence > 0.7 ? "success.main" : "warning.main")}>
                      {(inference.confidence * 100).toFixed(1)}%
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>推理摘要</TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
                      {inference.reasoning_summary}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>不确定性</TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {inference.uncertainties?.length || 0} 项
                      {inference.uncertainties?.map((u, i) => (
                        <div key={i}>• {u}</div>
                      ))}
                    </Typography>
                  </TableCell>
                </TableRow>
                <TableRow hover>
                  <TableCell>建议第一步</TableCell>
                  <TableCell>
                    <Typography variant="body2" color="info.main">
                      {inference.suggested_first_step}
                    </Typography>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {activeTab === 2 && !inference && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
            ⚠️ 暂无推理结果数据
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
