from __future__ import annotations

from zentex.tasks.management.service_context import *


class TaskServiceCompletionVerificationMixin:
    async def complete_task_with_verification(
        self, 
        task_id: str, 
        result: Dict[str, Any],
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Complete a task with verification workflow.
        
        This method implements the full verification flow:
        1. Check if verification is enabled for the task
        2. Transition to WAITING_CONFIRMATION state
        3. Execute verification engine
        4. Based on results: accept/retry/escalate/reject
        
        Args:
            task_id: Task ID
            result: Worker's submission result (output, metadata, etc.)
            remarks: Optional remarks
            
        Returns:
            Dict containing completion status and verification result
        """
        task = self.get_task(task_id)
        if not task:
            return {
                "success": False,
                "error": f"Task {task_id} not found",
                "error_code": "TASK_NOT_FOUND"
            }
        if task.status == TaskStatus.DONE:
            existing_outcome = self.get_task_outcome(task_id)
            if existing_outcome is not None and existing_outcome.get("overall_passed") is True:
                return {
                    "success": True,
                    "task": task.model_dump(),
                    "task_outcome": existing_outcome,
                    "message": "Task already completed and verified successfully",
                    "idempotent": True,
                }

        async def _complete_without_verification(message: str) -> Dict[str, Any]:
            current = self.get_task(task_id)
            if current and current.status in {TaskStatus.TODO, TaskStatus.QUEUED}:
                await self.update_task_status(
                    task_id,
                    TaskStatus.IN_PROGRESS,
                    "Auto-claimed before completion",
                )
            updated_task = await self.update_task_status(task_id, TaskStatus.DONE, remarks)
            return {
                "success": True,
                "task": updated_task.model_dump(),
                "verification_skipped": True,
                "message": message,
            }
        
        # Check if verification is available and enabled
        if not VERIFICATION_AVAILABLE or not self._verification_engine:
            logger.warning(f"Verification engine not available, completing task {task_id} without verification")
            return await _complete_without_verification(
                "Task completed without verification (engine not available)"
            )
        
        # Check if verification is enabled for this task
        if not task.contract.verification.enabled:
            logger.debug(f"Verification disabled for task {task_id}, completing directly")
            return await _complete_without_verification(
                "Task completed (verification disabled for this task)"
            )
        
        try:
            if task.status in {TaskStatus.TODO, TaskStatus.QUEUED}:
                await self.update_task_status(
                    task_id,
                    TaskStatus.IN_PROGRESS,
                    "Auto-claimed before verification",
                )
                task = self.get_task(task_id) or task

            # Step 1: Transition to WAITING_CONFIRMATION
            logger.info(f"Task {task_id} entering verification phase")
            await self.update_task_status(
                task_id, 
                TaskStatus.WAITING_CONFIRMATION, 
                remarks="Waiting for verification"
            )
            
            # Step 2: Execute verification
            verification_result = await self._verification_engine.execute_verification(
                task=task,
                result=result
            )
            
            # Step 3: Record verification result in transcript
            self._record_audit(
                task_id,
                "TASK_VERIFICATION_COMPLETED",
                {
                    "overall_passed": verification_result.overall_passed,
                    "strategy": verification_result.strategy,
                    "confidence_score": verification_result.confidence_score,
                    "summary": verification_result.summary,
                    "recommendation": verification_result.recommendation,
                    "verifier_count": len(verification_result.verifier_results),
                    "execution_time_ms": verification_result.total_execution_time_ms
                }
            )
            
            # Step 4: Handle based on recommendation
            if verification_result.overall_passed:
                # Verification passed - complete the task
                final_remarks = f"Verified: {verification_result.summary}"
                if remarks:
                    final_remarks += f" | {remarks}"
                    
                updated_task = await self.update_task_status(
                    task_id,
                    TaskStatus.DONE,
                    remarks=final_remarks,
                    skip_verification_bridge=True,
                )
                task_outcome = self._record_task_outcome(
                    task=updated_task,
                    result=result,
                    verification_result=verification_result,
                )
                maintenance_report = await self._run_automatic_outcome_maintenance_hook(task_id)
                
                logger.info(f"Task {task_id} verified and completed successfully")
                return {
                    "success": True,
                    "task": updated_task.model_dump(),
                    "verification_result": verification_result.model_dump(),
                    "task_outcome": task_outcome,
                    "automatic_outcome_maintenance": maintenance_report,
                    "message": "Task completed and verified successfully"
                }
            
            else:
                # Verification failed - handle based on recommendation
                return await self._handle_verification_failure(
                    task_id, 
                    verification_result,
                    result,
                    remarks
                )
                
        except Exception as e:
            logger.error(f"Verification failed for task {task_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # On error, mark task as failed
            try:
                updated_task = await self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    remarks=f"Verification error: {str(e)}"
                )
                return {
                    "success": False,
                    "task": updated_task.model_dump(),
                    "error": str(e),
                    "error_code": "VERIFICATION_ERROR"
                }
            except Exception as inner_e:
                logger.error(f"Failed to update task status after verification error: {inner_e}")
                return {
                    "success": False,
                    "error": f"Verification error: {str(e)}, Status update error: {str(inner_e)}",
                    "error_code": "VERIFICATION_AND_STATUS_ERROR"
                }
    

