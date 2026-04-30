import React from 'react';
import { useTranslation } from 'react-i18next';
import { Chip } from '@mui/material';
import { TaskStatus } from './types';

interface StatusChipProps {
  status: TaskStatus;
}

const StatusChip: React.FC<StatusChipProps> = ({ status }) => {
  const { t } = useTranslation();
  const colorMap: Record<TaskStatus, any> = {
    todo: 'default',
    in_progress: 'primary',
    blocked: 'warning',
    waiting_confirmation: 'secondary',
    done: 'success',
    failed: 'error',
    suspended: 'info',
    archived: 'default',
    cancelled: 'default',
  };

  return (
    <Chip
      size="small"
      label={t(`tasks.statuses.${status}`, { defaultValue: status })}
      color={colorMap[status]}
      variant="outlined"
      sx={{ fontWeight: 'bold' }}
    />
  );
};

export default StatusChip;
