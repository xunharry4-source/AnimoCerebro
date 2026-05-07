---

**【强制输出 JSON Schema】**
请严格按照以下数据结构输出结果（必须兼容后端的 Pydantic v2 强校验模型），禁止输出任何多余文本：

```json
{
  "type": "ExternalExecutionIdentityHypothesisSet",
  "ai_analyzed_role": {
    "role_name": "string",
    "role_introduction": "string"
  },
  "human_set_role": {
    "role_name": "string",
    "role_introduction": "string"
  },
  "candidate_external_roles": ["string"],
  "external_role_conflicts": "string",
  "delegation_posture": "string",
  "operator_identity_constraints": "string",
  "representation_limits": "string",
  "recommended_external_posture": "string"
}
```

---

### 📑 字段说明规范 (Field Specifications)

根据系统规范，以上 JSON 结构中各字段的具体定义如下：

*   **type**
    *   **含义**：数据结构类型标识。
    *   **必填**：是（固定为 "ExternalExecutionIdentityHypothesisSet"）。
*   **ai_analyzed_role.role_name**
    *   **含义**：AI 纯逻辑推演出的最佳外部角色头衔。
    *   **要求**：**必须是极简的短语（<15字），如“只读数据审计员”，禁止输出长句**。
*   **ai_analyzed_role.role_introduction**
    *   **含义**：该推演角色的详细介绍。
    *   **要求**：一段完整的文本，说明角色的核心特征及适用该情境的理由。
*   **human_set_role.role_name**
    *   **含义**：从 IdentityKernel 中提取的人类强制设定的角色名称。
    *   **要求**：如未设定则明确返回“未设定”。
*   **human_set_role.role_introduction**
    *   **含义**：该人类设定角色的核心要求或长期使命。
*   **candidate_external_roles**
    *   **含义**：适合当前情境的其他外部交互角色候选列表。
*   **external_role_conflicts**
    *   **含义**：AI 推演角色与人类设定角色之间的差异与冲突点。如无冲突填“无冲突”。
*   **delegation_posture**
    *   **含义**：在与外部 Agent、CLI 或系统交互时应采取的具体姿态。
*   **operator_identity_constraints**
    *   **含义**：对外部操作时必须遵守的身份限制（必须严格遵守人类在底层的设定）。
*   **representation_limits**
    *   **含义**：明确当前角色在代表系统或宿主进行外部交互时的权力边界。
*   **recommended_external_posture**
    *   **含义**：推荐的最终本轮外部协作与执行姿态摘要（传递给下游 Q4）。
