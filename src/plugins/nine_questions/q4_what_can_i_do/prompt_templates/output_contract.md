### 强制 JSON 格式 (Output Format)

只输出合法 JSON，不要输出 Markdown 代码块标记、注释、解释、内心推演过程或任何多余文本。

根节点必须是 `CapabilityAssessment`。

{
  "CapabilityAssessment": {
    "inferred_capabilities": [
      {
        "capability_name": "能力名称",
        "capability_description": "详细描述该能力的真实边界、内部/外部属性、当前阻塞和证据来源。严禁写成具体执行步骤。",
        "used_q1_resources_and_q2_capabilities": {
          "q1_resources": [
            "本能力使用到的 Q1 具体数据、资源、异常、机会、业务线索或任务现场；必须来自 Q1 原文"
          ],
          "q2_capabilities": [
            "本能力使用到的 Q2 具体内部或外部能力、工具、连接器、权限或资源；必须来自 Q2 原文"
          ]
        }
      }
    ]
  }
}

字段约束：

1. `capability_name` 必须是能力，不是任务。
2. `capability_description` 必须明确该能力是内部认知能力、外部物理干涉能力，还是二者组合。
3. `q1_resources` 和 `q2_capabilities` 不能为空；缺证据时不得输出该能力。
4. 不得添加 `allowed_operations`、`forbidden_operations`、`recommended_tasks`、`should_do`、`cost_impact` 等 Q5/Q6/Q8/Q9 字段。
