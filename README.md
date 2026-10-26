# scene-driven-roleplay

**Kei v1.1** 公开架构参考快照（标识：`kei-v1.1-public`）。这是面向本地单用户的 RolePlay 参考实现：第一人称 Role Profile 与 Scene RAG 为生成提供上下文，Generator 写出台词，Selector 在台词完成后独立选择贴图。这个仓库用于分享设计演化和失败经验，不是通用 SOTA 模型、官方《蔚蓝档案》产品、可直接游玩的客户端，也没有严格实验来证明优于其他 RP 系统。

设计从多阶段的 `State Manager → Appraiser → Deliberator → Speech Habit / Character NLG → Corrector` 逐步收敛到：

```text
Role Profile + 当前对话 + Memory/Knowledge + 检索到的 Scene
                         ↓
                    Generator → 台词 + affect
                                        ↓
                               Selector → 贴图或 null
```

三个关键取舍：人格描述是上下文参考，不是逐条执行的行为规则；Scene 提供说话和互动先例，不自动建立当前事实；Generator 定稿台词与 affect，Selector 只选图、不改词，并允许 `null`。这种简化减少了模板化及单轮演完情绪的诱因，也失去了对显式状态转移的细粒度控制。详见 [架构取舍](docs/ARCHITECTURE_DECISIONS.md)、[失败案例](docs/FAILURE_CASES.md) 与 [源文件及排除清单](docs/SOURCE_AUDIT.json)。

公开包包含当前工作树的第一人称凯伊 Profile（仅修正头像路径）、34 张凯伊贴图 PNG、1 张头像、对应贴图 YAML、7 份原作剧情人工整理的 Scene Markdown、代码和详细开发手册。素材来源及作者添加的分段和标注见[场景整理说明](docs/SCENE_SOURCE_NOTES.md)与[第三方声明](THIRD_PARTY_NOTICES.md)。它仍不含转换后的 78 条 evidence、私有 lore、真实聊天与记忆、日志、模型权重、前端和 API Key；合成 Scene 只用于离线协议测试。这里的 `Kei v1.1` 是拟用 Release 名称，尚未发布 GitHub Release。本地未取得可验证的 `kei-v1.1` 冻结包或 Tag；原工作树当前 78 条 evidence 不能认作历史所述冻结版 32 条的子集；本快照是从原 AI4MathAssistant 工作树（当时 HEAD `86c57fdc2cd7fd30f8e0063841664b6457c745da`）整理而来的**独立新仓库**，不声称从冻结 Tag 导出。

## 阅读路径

| 关注点 | 源码入口 |
| --- | --- |
| Profile 数据与提示词 | [`roles/schema.py`](roles/schema.py)、[`roles/prompt_builder.py`](roles/prompt_builder.py) |
| Scene 数据、检索与关系重排 | [`roleplay/evidence/schema.py`](roleplay/evidence/schema.py)、[`roleplay/evidence/retriever.py`](roleplay/evidence/retriever.py)、[`roleplay/evidence/relationship_pre_retrieval.py`](roleplay/evidence/relationship_pre_retrieval.py) |
| Generator 流程 | [`core/roleplay_chatbot.py`](core/roleplay_chatbot.py) |
| 贴图 Selector | [`roleplay/sticker_llm_selector.py`](roleplay/sticker_llm_selector.py)、[`roles/stickers/registry.py`](roles/stickers/registry.py) |
| 会话、记忆与知识 | [`roleplay/session_manager.py`](roleplay/session_manager.py)、[`roleplay/memory/`](roleplay/memory/)、[`knowledge/`](knowledge/) |
| API | [`web/server.py`](web/server.py)、[`web/api.py`](web/api.py) |

含技术正文的公开版开发手册见 [RolePlay Development Manual](docs/ROLEPLAY_DEVELOPMENT_MANUAL.md)。仓库内保留当前工作树 Profile 的 [`tendou_kei.yaml`](roles/profiles/tendou_kei.yaml) 和作者标注的[贴图 YAML](roles/stickers/packs/tendou_kei.yaml)；测试中的合成 Scene 仅用于验证协议，不代表原作角色。

## 离线验证与导出

建议 Python 3.11/3.12。先安装轻量依赖 `python -m pip install -r requirements-offline.txt`（安装本身可能需要网络）；已安装依赖时，下面的检查不调用外部 API、GPU 或联网模型。完整运行时依赖见 `requirements.txt`：

```bash
python -m compileall -q config.py core roleplay roles knowledge memory web tools tests
python -m pytest -q tests
python tools/export_public_kei.py --output /path/outside/worktree/kei-v1.1-public
```

导出目录必须事先不存在；脚本采用明确白名单，不携带 `.git`，并生成 `PUBLIC_MANIFEST.json` 和 `checksums.sha256`。运行 API 可用 `uvicorn web.server:app --host 127.0.0.1 --port 8000`，打开 `/docs` 查看接口；根路径明确提示前端未打包。真实生成需要自行配置 `.env`、模型及可用的 evidence/知识数据；本包的 Scene Markdown 不会自动转换为运行时 JSONL。

本工作受 [ChatHaruhi](https://github.com/LC1332/Chat-Haruhi-Suzumiya) 的场景语料方法启发，也与角色卡、Lorebook、SillyTavern 等生态中的上下文供给方式有相似处；不主张首创 Scene RAG 或贴图选择。第三方与权利边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。作者尚未为自有代码选择 MIT 或 Apache-2.0 等许可证；在许可证及二创素材授权范围确认前，不应假定本仓库授予再分发许可。

## AI-Assisted Development

This project was developed almost entirely through **Vibe Coding**.

As someone without a professional background in software engineering or AI agent development, I relied heavily on AI coding assistants to implement, debug, and maintain the codebase.

My primary contributions were identifying problems, defining requirements, experimenting with different architectures, curating character data, evaluating the actual role-playing experience, and making the final design decisions.

This is a personal hobby project rather than a production-ready framework. While I have tested it through extensive personal use, I cannot guarantee the correctness or quality of every implementation detail.

I am sharing this repository primarily to document the design process, architectural decisions, and lessons learned along the way.

## Acknowledgements

I would like to thank the AI models and assistants that helped bring this project to life.

- **Sol-6 and DeepSeek-flash** — For their assistance throughout the development process.
- **ChatGPT** — For extensive brainstorming, architectural discussions, critical feedback, and helping me explore different approaches to character role-playing.

Special thanks to ChatGPT for the many discussions that helped shape the project's direction, particularly the transition from explicit character behavior planning toward a simpler, scene-driven architecture.

These conversations were an important part of my design process.

The final architectural decisions, project direction, and responsibility for any remaining issues are my own.
