请阅读本次请求附带的 Context JSON，将其中的常规目标池与认知状态映射为以下动态输入上下文后，输出 Q7 内部认知轨创造性探索结果：

{
  "Q4_InternalObjectiveCandidates": "从 Context JSON 中的 q4_internal_objective_candidates、q4_internal_llm_output 或 Q4 internal 相关字段读取；没有时使用空对象。",
  "LivingSelfModel_Snapshot": "从 Context JSON 中的 living_self_model、identity_kernel_snapshot、memory/self/reflection 相关字段读取；没有时使用空对象。",
  "Reflection_CapabilityGapSignal_Internal": "从 Context JSON 中的 reflection capability gap、internal functional plugin capability gap 或 Q4 internal capability gap 相关字段读取；没有时使用空对象。"
}

只允许基于 Context JSON 中真实提供的信息发散，不得在输出中写入上述说明文字或任何宏变量名。
