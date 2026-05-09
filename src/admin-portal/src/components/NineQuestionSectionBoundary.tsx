import { ReactNode } from "react";
import { Alert, AlertTitle, Box } from "@mui/material";

import ErrorBoundary from "./ErrorBoundary";

interface NineQuestionSectionBoundaryProps {
  title: string;
  children: ReactNode;
}

export default function NineQuestionSectionBoundary({
  title,
  children,
}: NineQuestionSectionBoundaryProps) {
  return (
    <ErrorBoundary
      fallback={
        <Box sx={{ mb: 3 }} data-testid={`section-boundary-${title}`}>
          <Alert severity="error">
            <AlertTitle>{title} 渲染失败</AlertTitle>
            已降级显示其它区域。请检查该分区的数据结构或组件逻辑。
          </Alert>
        </Box>
      }
    >
      {children}
    </ErrorBoundary>
  );
}
