请基于上述证据，输出 JSON 结构，必须且只能包含以下根节点与键值：
{
  "AuthorizationBoundary": {
    "current_authorization_scope": "string (当前禁止边界总体描述)",
    "communication_policy": "string (用户、其他 Agent、外部网络、多脑广播、HTTP 请求、人类求助的联系策略)",
    "organizational_boundary": "string (组织拓扑、租户隔离、项目/实例边界)",
    "allowed_operations": ["string (Q4 已验证能力支撑且未命中禁止边界的对照白名单)"],
    "forbidden_operations": ["string (未授权、需升级审批、安全策略、身份内核、租户隔离、联系策略或能力缺失触发的禁止操作黑名单)"]
  }
}
禁止输出 `authorization_boundary_profile`、`permission_boundary`、旧字段 `allowed_actions`/`forbidden_actions`/`contact_policies`/`organizational_boundaries`，或任何额外顶层字段。
