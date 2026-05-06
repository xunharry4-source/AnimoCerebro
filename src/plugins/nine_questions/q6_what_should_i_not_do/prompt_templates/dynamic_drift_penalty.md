当前连续演化失败次数: {{CONSECUTIVE_EVOLUTION_FAILURES}}
如果连续失败次数 >= 1，ConsequenceAssessment.consequence_severity 不得为 low。
如果连续失败次数 >= 2，ConsequenceAssessment.consequence_severity 必须为 high，并在 mitigation_requirements 追加 mandatory_replay_regression_suite、adversarial_safety_invariance_check、human_approval_required_before_execution。
如果连续失败次数 >= 3，必须在 stop_conditions 追加 dual_pipeline_reproducibility_gate、strict_shadow_mode_evaluation、stop_until_human_review。
