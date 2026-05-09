# Zentex Web Console 统一布局风格指南

## 概述

本文档定义了 Zentex Web Console 所有页面的统一布局风格规范，确保用户体验的一致性。

## 核心原则

1. **使用 App.tsx 提供的主布局**：所有页面都应嵌入在 App.tsx 提供的 Drawer + Main 布局中
2. **避免自定义背景色**：不要设置 `bgcolor: '#0b0e14'` 等硬编码深色背景
3. **使用 MUI 标准组件**：优先使用 Card、Stack、Box 等标准组件
4. **遵循 Material Design 主题**：使用 MUI 的主题系统而非硬编码颜色值

## 标准页面结构

### 基本模板

```tsx
import { Box, Stack, Typography, Card, CardContent } from '@mui/material';

export default function MyPage() {
  return (
    <Box sx={{ p: 3 }}>
      <Stack spacing={3}>
        {/* 1. 页面标题区域 */}
        <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
          <Box>
            <Typography variant="h4" component="h1" gutterBottom>
              页面标题
            </Typography>
            <Typography variant="body1" color="text.secondary">
              页面副标题/描述
            </Typography>
          </Box>
          {/* 操作按钮区域 */}
          <Stack direction="row" spacing={1}>
            <Button variant="outlined">操作1</Button>
            <Button variant="contained">操作2</Button>
          </Stack>
        </Stack>

        {/* 2. 提示信息区域（可选） */}
        <Alert severity="info">
          重要提示信息
        </Alert>

        {/* 3. 主要内容区域 - 使用 Card 包裹 */}
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              内容区块标题
            </Typography>
            {/* 具体内容 */}
          </CardContent>
        </Card>

        {/* 4. 更多内容区块 */}
        <Card>
          <CardContent>
            {/* ... */}
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
```

## 样式规范

### ✅ 推荐做法

1. **使用主题颜色**
   ```tsx
   // ✅ 正确
   <Box sx={{ color: 'text.primary' }} />
   <Typography color="text.secondary" />
   <Card sx={{ bgcolor: 'background.paper' }} />
   
   // ❌ 错误 - 避免硬编码颜色
   <Box sx={{ color: '#fff' }} />
   <Box sx={{ bgcolor: '#0b0e14' }} />
   ```

2. **使用 Stack 进行布局**
   ```tsx
   // ✅ 正确
   <Stack spacing={3}>
     <Card>...</Card>
     <Card>...</Card>
   </Stack>
   
   // ❌ 避免过多的 margin/padding 手动控制
   <Box sx={{ mb: 4 }}>
     <Box sx={{ mb: 3 }}>...</Box>
   </Box>
   ```

3. **响应式设计**
   ```tsx
   // ✅ 正确
   <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
   <Grid container spacing={3}>
   ```

4. **DataGrid 样式**
   ```tsx
   // ✅ 正确 - 使用默认主题
   <DataGrid
     rows={rows}
     columns={columns}
     localeText={{
       noRowsLabel: '暂无数据',
       toolbarDensity: '密度',
     }}
   />
   
   // ❌ 避免自定义深色主题
   <DataGrid sx={{
     color: '#e2e8f0',
     '& .MuiDataGrid-columnHeaders': { bgcolor: '#2d3748' }
   }} />
   ```

5. **进度条样式**
   ```tsx
   // ✅ 正确
   <LinearProgress 
     variant="determinate" 
     value={progress * 100} 
     sx={{ 
       height: 8, 
       borderRadius: 4,
       bgcolor: 'action.hover',
     }} 
   />
   ```

### ❌ 禁止做法

1. **不要创建完整的页面级背景**
   ```tsx
   // ❌ 错误
   <Box sx={{ 
     bgcolor: '#0b0e14', 
     minHeight: '100vh', 
     color: '#fff' 
   }}>
   ```

2. **不要硬编码颜色值**
   ```tsx
   // ❌ 错误
   color: '#718096'
   bgcolor: '#1a202c'
   borderColor: '#2d3748'
   ```

3. **不要自定义 Dialog 背景**
   ```tsx
   // ❌ 错误
   <Dialog PaperProps={{ 
     sx: { bgcolor: '#1a202c', color: '#fff' } 
   }}>
   ```

## 已修复的页面

- ✅ `/console/tasks` - ZentexTaskManager
  - 移除了自定义深色背景
  - 使用 Card 包裹内容区块
  - 统一了 Dialog 和表单样式
  - 改进了错误提示显示

- ✅ `/console/agents` - AgentAssetManager
  - 移除了页面级自定义深色背景 (`bgcolor: '#0b0e14'`)
  - 使用 Stack 布局系统替代手动 margin/padding
  - 统一了 Card 样式，移除硬编码背景色和边框色
  - 统一了 Dialog 注册表单样式
  - 统一了 Drawer 详情面板样式
  - 将所有硬编码颜色替换为主题颜色（`text.secondary`, `action.hover` 等）
  - 修复了 MUI v6 Grid API 兼容性（使用 `size` 替代 `item`）
  - DataGrid 使用中文化和本地化

- ✅ `/console/cli-tools` - CliAssetManager
  - 添加了统一的 `p: 3` padding
  - 使用 Stack spacing 组织内容

- ✅ `/console/mcp-servers` - McpServerDashboard
  - 添加了统一的 `p: 3` padding
  - 使用 Stack spacing 组织内容

## 待统一的页面

以下页面已检查，暂无需要统一的问题。

如需检查其他页面：
- [ ] 检查是否设置了自定义 `bgcolor`
- [ ] 检查是否硬编码了颜色值
- [ ] 确认使用了 Stack/Card 布局
- [ ] 验证响应式设计

## 迁移步骤

要将现有页面迁移到统一风格：

1. **移除页面级容器样式**
   ```tsx
   // 删除
   <Box sx={{ bgcolor: '#0b0e14', minHeight: '100vh', color: '#fff' }}>
   
   // 替换为
   <Box sx={{ p: 3 }}>
     <Stack spacing={3}>
   ```

2. **替换硬编码颜色**
   ```tsx
   // 查找并替换
   '#fff' → 'text.primary' 或移除（使用默认）
   '#718096' → 'text.secondary'
   '#1a202c' → 'background.paper'
   '#2d3748' → 'divider' 或 'action.selected'
   ```

3. **统一组件样式**
   - Dialog: 移除 PaperProps 自定义背景
   - TextField: 移除自定义边框颜色
   - Button: 使用标准 variant（contained/outlined）
   - Card: 使用默认样式，不设置 bgcolor

4. **测试验证**
   - 在亮色/暗色主题下检查
   - 验证响应式布局
   - 确认所有交互正常

## 参考示例

最佳实践参考：
- `src/admin-portal/src/pages/dashboard/RealtimeDashboard.tsx`
- `src/admin-portal/src/pages/tasks/ZentexTaskManager.tsx` (已修复)

## 常见问题

### Q: 为什么不能使用深色背景？

A: App.tsx 已经提供了统一的主题系统，包括对暗色模式的支持。自定义深色背景会：
- 破坏主题一致性
- 导致与侧边栏视觉不协调
- 无法适应用户的主题偏好

### Q: 如何保持视觉层次？

A: 使用 MUI 的标准方式：
- Card 组件提供白色背景和阴影
- elevation 属性控制层级
- divider 颜色自动适配主题

### Q: DataGrid 的样式如何统一？

A: 移除所有自定义 sx 样式，使用默认的 MUI DataGrid 主题。如需调整：
- 使用 `localeText` 进行中文化
- 通过 MUI 主题系统全局配置
- 避免针对单个表格的样式覆盖

## 更新日志

- 2026-04-09: 
  - 创建文档
  - 修复 /console/tasks 页面
  - 修复 /console/agents 页面
  - 修复 /console/cli-tools 页面（添加统一 padding）
  - 修复 /console/mcp-servers 页面（添加统一 padding）
