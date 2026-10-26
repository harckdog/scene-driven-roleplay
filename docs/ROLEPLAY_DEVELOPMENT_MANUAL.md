# RolePlay 公开开发手册

此手册是审查后的架构说明，不包含原作台词、私人场景卡或历史测试数据。`Kei v1.1` 是拟用 Release 名称；本地没有可验证的同名冻结 Tag，当前公开源码来自 AI4MathAssistant 工作树的独立拷贝。详细决策见 [架构取舍](ARCHITECTURE_DECISIONS.md)，失败模式见 [合成案例](FAILURE_CASES.md)。

## 当前链路

`core/roleplay_chatbot.py` 是 Scene-only 入口。加载 `roles/profiles/` 下的 Profile 与 `local_data/roleplay_evidence/<role_id>.jsonl`，对用户输入检索 Scene，可选读取会话 Memory 和 Knowledge，然后由 `roles/prompt_builder.py` 构建稳定提示词和本轮检索上下文。Generator 负责文本和每个气泡的表达信息。`roleplay/sticker_llm_selector.py` 只在生成完成后为气泡选现有贴图，不改写台词。`roles/stickers/registry.py` 排除不存在的素材，允许无贴图。

Scene 卡由 `roleplay/evidence/schema.py` 校验，`scene`、`relationship_context` 与原始对话参与检索。`roleplay/evidence/retriever.py` 提供本地嵌入索引；可选的 `interaction_retriever.py` 与 `qwen_reranker.py` 需要本地模型及配套 trace。关系预重排在 `relationship_pre_retrieval.py`，不修改场景原文。检索结果仅是表达参考；当前事实来自对话与已确认记忆。Scene 卡中的地点或关系不能自动升格为当前剧情。

`roleplay/session_manager.py` 管理会话；`roleplay/memory/` 负责记忆，`knowledge/` 负责知识文档与索引。它们在公开包中保留接口代码，但不带真实用户数据。`web/api.py` 暴露本地 API；`web/server.py` 在缺少前端与图片时仍能启动。`app.py` 是历史 Gradio 入口，完整交互体验不在此次公开范围内。

## 数据契约与离线验证

经审查的凯伊 Profile 位于 `roles/profiles/tendou_kei.yaml`；公开包不带完整角色 Scene。离线测试在临时目录创建合成 schema v4 Scene，标明来源 ID、角色台词、关系底线和表达倾向。这些合成来源 ID 不对应外部作品。离线测试只验证解析、检索文本、API 导入与无图片降级，不调用真实模型。真实推理还需自行安装依赖、配置 API、合法数据和可能的本地嵌入或重排权重。

## 演化边界

早期多阶段心理流水线试图把状态、评价、决策、措辞和纠错分开，但增加了模板化与单回合过度解释的风险。现在保留清晰的数据和模块边界，同时把即时台词的判断集中到 Generator。这个取舍适用于当前目标，不是对复杂角色或规划任务的通用结论。导出的快照可用于研究代码和协议，不能据此复现私有 Kei 实测结果。
