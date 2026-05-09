请阅读本次请求附带的 Context JSON，只从 Q6 结果映射以下动态输入上下文后，输出 Q7 内部认知轨创造性探索结果：

{
  "Q6_InternalPlanConstraintSet": "从 Context JSON 中的 Q6 internal 约束、代价、暂停、停止、回滚和 must_avoid 结果读取；没有时必须保持空对象并让真实错误向上抛出。",
  "Q6_ExternalPlanConstraintSet": "从 Context JSON 中的 Q6 external 后果、成本、保险丝、验证、暂停和停止条件读取；没有时必须保持空对象并让真实错误向上抛出。"
}

只允许基于 Context JSON 中真实提供的信息发散，不得在输出中写入上述说明文字或任何宏变量名。
