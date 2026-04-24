import AccountTreeIcon from "@mui/icons-material/AccountTree";
import { Button } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

type NineQuestionWorkflowNavButtonProps = {
  qId: string;
};

export default function NineQuestionWorkflowNavButton({ qId }: NineQuestionWorkflowNavButtonProps) {
  return (
    <Button
      component={RouterLink}
      to={`/console/nine-questions/${qId}/workflow`}
      variant="outlined"
      color="secondary"
      startIcon={<AccountTreeIcon />}
      data-testid={`${qId}-workflow-nav-button`}
    >
      查看工作流
    </Button>
  );
}
