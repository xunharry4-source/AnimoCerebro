from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceVerificationFailureMixin:
    async def _handle_verification_failure(
        self,
        task_id: str,
        verification_result: Any,
        result: Optional[Dict[str, Any]] = None,
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle verification failure based on recommendation.
        
        Args:
            task_id: Task ID
            verification_result: Verification result object
            remarks: Optional remarks
            
        Returns:
            Dict containing handling result
        """
        task = self.get_task(task_id)
        recommendation = verification_result.recommendation
        
        logger.warning(
            f"Verification failed for task {task_id}, "
            f"recommendation: {recommendation}"
        )
        
        if recommendation == "retry":
            # Retry: go back to IN_PROGRESS
            retry_remarks = f"Verification failed, auto-retrying: {verification_result.summary}"
            if remarks:
                retry_remarks += f" | {remarks}"
                
            updated_task = await self.update_task_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                remarks=retry_remarks
            )
            task_outcome = self._record_task_outcome(
                task=updated_task,
                result=result or {},
                verification_result=verification_result,
            )
            maintenance_report = await self._run_automatic_outcome_maintenance_hook(task_id)
            
            logger.info(f"Task {task_id} set to IN_PROGRESS for retry")
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_result": verification_result.model_dump(),
                "task_outcome": task_outcome,
                "automatic_outcome_maintenance": maintenance_report,
                "action_taken": "retry",
                "message": "Task set to IN_PROGRESS for automatic retry"
            }
            
        elif recommendation == "escalate":
            # Escalate: create manual review task or suspend
            escalation_target = task.contract.verification.escalation_target
            
            if escalation_target:
                # Create escalation notification
                self._record_audit(
                    task_id,
                    "TASK_VERIFICATION_ESCALATED",
                    {
                        "escalation_target": escalation_target,
                        "verification_summary": verification_result.summary,
                        "failed_verifiers": [
                            r.verifier_id 
                            for r in verification_result.verifier_results 
                            if not r.passed
                        ]
                    }
                )
                
                # Suspend the task pending manual review
                suspension_reason = f"Verification failed, escalated to {escalation_target}"
                suspended_task = await self.suspend_task(
                    task_id,
                    reason=suspension_reason,
                    recovery_conditions=[f"Manual review by {escalation_target}"]
                )
                task_outcome = self._record_task_outcome(
                    task=suspended_task,
                    result=result or {},
                    verification_result=verification_result,
                )
                maintenance_report = await self._run_automatic_outcome_maintenance_hook(task_id)
                
                logger.info(f"Task {task_id} escalated to {escalation_target}")
                return {
                    "success": True,
                    "task": suspended_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "task_outcome": task_outcome,
                    "automatic_outcome_maintenance": maintenance_report,
                    "action_taken": "escalated",
                    "escalation_target": escalation_target,
                    "message": f"Task escalated to {escalation_target} for manual review"
                }
            else:
                # No escalation target, just fail
                fail_remarks = f"Verification failed: {verification_result.summary}"
                if remarks:
                    fail_remarks += f" | {remarks}"
                    
                updated_task = await self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    remarks=fail_remarks
                )
                task_outcome = self._record_task_outcome(
                    task=updated_task,
                    result=result or {},
                    verification_result=verification_result,
                )
                maintenance_report = await self._run_automatic_outcome_maintenance_hook(task_id)
                
                return {
                    "success": False,
                    "task": updated_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "task_outcome": task_outcome,
                    "automatic_outcome_maintenance": maintenance_report,
                    "action_taken": "failed",
                    "message": "Task failed verification (no escalation target configured)"
                }
                
        else:  # recommendation == "reject"
            # Reject: mark as failed
            fail_remarks = f"Verification rejected: {verification_result.summary}"
            if remarks:
                fail_remarks += f" | {remarks}"
                
            updated_task = await self.update_task_status(
                task_id,
                TaskStatus.FAILED,
                remarks=fail_remarks
            )
            task_outcome = self._record_task_outcome(
                task=updated_task,
                result=result or {},
                verification_result=verification_result,
            )
            maintenance_report = await self._run_automatic_outcome_maintenance_hook(task_id)
            
            logger.info(f"Task {task_id} failed verification and rejected")
            return {
                "success": False,
                "task": updated_task.model_dump(),
                "verification_result": verification_result.model_dump(),
                "task_outcome": task_outcome,
                "automatic_outcome_maintenance": maintenance_report,
                "action_taken": "rejected",
                "message": "Task failed verification and rejected"
            }
    

