# scene-driven-roleplay

我最初只是想做一个自己愿意长期使用的凯伊 RolePlay 项目：让她在不同情境下自然交流，而不是每轮都机械地展示口癖、性格标签或预先安排好的情绪。整个项目几乎通过 **Vibe Coding** 完成；我主要负责提出问题、整理场景、观察实际体验，以及反复决定哪些设计应该保留。

我想公开的不是一种号称最好的 RolePlay 算法，而是这段**从 Scene RAG 出发，走入复杂人格规划，最后又回到 Scene 的开发过程**。我在里面踩过的坑，也许能给其他开发者一些参考。

## 我走过的路线

**最初：Scene RAG + 贴图选择。** 我整理原作互动，通过 Embedding 召回类似场景供模型参考。当时台词已能生成，但表情经常选得过于激烈，尤其容易误选愤怒图。我起初让 Codex 通过违禁词等局部规则修补，却不断碰到新的例外。

**然后：尝试更精细的角色规划。** 我开始与 ChatGPT 搜索资料、讨论架构，陆续引入 Appraiser、Deliberator、Trajectory、Speech Habit 等思路。最初认为各模块只需接收与自身职责相关的信息就足够了，但原始互动被层层转写为情绪标签和行为建议后，Generator 常常只能执行一份粗糙的计划。回复虽然遵循建议，却可能情绪极端，或者变得 generic。

**接着：反思 Speech Habit 和旧角色卡。** 我发现口癖并不是某个随时可以触发的特征。它出现的时机、方式和强度需要具体语境，独立召回并注入口癖反而会诱导模型每轮表演。我保留了一份[历史失败角色卡](docs/history/tendou_kei_legacy_schema_v1.yaml)，可以看到当时如何使用第三人称人格分析、行为模式和显式情绪策略；现在运行的则是另一份[第一人称角色卡](roles/profiles/tendou_kei.yaml)。

**最后：让语言回到 Scene，再让选图获得 Scene。** 我取消了负责逐层规划台词的心理流水线，让 Generator 直接参考角色自述、当前对话和场景。这让我的个人使用体验明显更自然、更灵动。但表情问题并未自动消失，直到后来让 Selector 也参考原作场景的反应，并用每气泡临时 affect 与贴图 family 约束选择，最初的选图困扰才得到明显改善。

这个过程让我形成了一项设计偏好：**不要过早把丰富的互动转化为要求模型执行的行为清单；要根据下游任务的需要，决定哪些语境必须保留，哪些信息适合抽象。**

详细开发过程见[开发复盘](docs/FAILURE_CASES.md)，背后的信息压缩与条件分布假设见[架构取舍](docs/ARCHITECTURE_DECISIONS.md)。这里记述的是个人使用和架构迭代，不是对其他系统的性能排名。

## 当前架构与取舍

```text
第一人称 Role Profile + 当前对话 + Memory/Knowledge + 检索到的 Scene
                                  ↓
                       Generator → 每气泡 text + 临时 affect
                                              ↓
当前用户输入 + 已完成台词 + affect + Scene 对话摘录 + 可用贴图标注
                                              ↓
                                   Selector → 贴图或 null
```

这里的 Scene-only 是我对**台词生成路径**的简称：不再由显式心理规划链逐层决定台词。我仍保留身份、事实边界、检索策略、关系重排、输出协议和选图约束。Scene 是表达与互动先例，不自动成为本轮发生的事实。Generator 定稿台词；Selector 只选图、不改词。每气泡 affect 不显示、不写入会话、不回灌，不能成为下一轮的心理状态。

对于带 affect 元数据的贴图包和有效 family，Selector 按主 family 限定候选，无匹配图时允许 `null`；缺少 affect 或旧包没有元数据时存在兼容回退，不能把 family gate 描述为无条件生效。

这个设计减少了台词生成前的心理规划，同时也更依赖场景质量与模型自身的表达能力。检索与上下文截断当然仍会取舍信息；我追求的是减少不必要的中间改写，而非宣称能够无损保存全部内容。数学上的理解与局限集中写在[架构取舍](docs/ARCHITECTURE_DECISIONS.md)。

## 公开快照包含什么

这是我整理的本地单用户 **Kei 架构公开快照**，沿用标识 `kei-v1.1-public`。我主要公开设计、实现和开发记录，不把它包装成官方《蔚蓝档案》产品或开箱即玩的完整客户端。这个公开快照与原始冻结标签尚未逐项核对，版本来源细节集中记录在[发布说明](releases/kei-v1.1-public/README.md)。

公开树包含现行第一人称凯伊 Profile（公开整理时仅修正头像路径）、34 张凯伊贴图 PNG、1 张头像、对应贴图 YAML、7 份原作剧情人工整理的 Scene Markdown、代码和详细开发手册。素材来源及我补充的分段、标注见[场景整理说明](docs/SCENE_SOURCE_NOTES.md)与[第三方声明](THIRD_PARTY_NOTICES.md)。合成 Scene 只用于离线协议测试，不代表原作角色或历史失败记录。

公开树不含转换后的 evidence、私有 lore、真实聊天与记忆、日志、模型权重、前端和 API Key。历史上不同版本曾记录过 32 条与 78 条 evidence；目前没有将两份清单核对为同一冻结版本。详细来源与排除内容见[发布说明](releases/kei-v1.1-public/README.md)和[源文件及排除清单](docs/SOURCE_AUDIT.json)。

## 阅读路径

| 关注点 | 源码入口 |
| --- | --- |
| Profile 数据与提示词 | [`roles/schema.py`](roles/schema.py)、[`roles/prompt_builder.py`](roles/prompt_builder.py) |
| Scene 数据、检索与关系重排 | [`roleplay/evidence/schema.py`](roleplay/evidence/schema.py)、[`roleplay/evidence/retriever.py`](roleplay/evidence/retriever.py)、[`roleplay/evidence/relationship_pre_retrieval.py`](roleplay/evidence/relationship_pre_retrieval.py) |
| Generator 流程 | [`core/roleplay_chatbot.py`](core/roleplay_chatbot.py) |
| 贴图 Selector | [`roleplay/sticker_llm_selector.py`](roleplay/sticker_llm_selector.py)、[`roles/stickers/registry.py`](roles/stickers/registry.py) |
| 会话、记忆与知识 | [`roleplay/session_manager.py`](roleplay/session_manager.py)、[`roleplay/memory/`](roleplay/memory/)、[`knowledge/`](knowledge/) |
| API | [`web/server.py`](web/server.py)、[`web/api.py`](web/api.py) |

完整技术实现和更详细的架构演化见 [RolePlay Development Manual](docs/ROLEPLAY_DEVELOPMENT_MANUAL.md)。当前使用的 [`tendou_kei.yaml`](roles/profiles/tendou_kei.yaml) 与[贴图 YAML](roles/stickers/packs/tendou_kei.yaml) 保持不变；[旧版角色卡](docs/history/tendou_kei_legacy_schema_v1.yaml) 单独作为历史案例保存，不在默认角色扫描路径中，也不应作为当前 Profile 使用。测试中的合成 Scene 只用于验证协议。


## 环境、离线验证与导出

建议 Python 3.11/3.12。先安装轻量依赖 `python -m pip install -r requirements-offline.txt`（安装本身可能需要网络）；已安装依赖时，下面的检查不调用外部 API、GPU 或联网模型。完整运行时依赖见 `requirements.txt`：

```bash
python -m compileall -q config.py core roleplay roles knowledge memory web tools tests
python -m pytest -q tests
python tools/export_public_kei.py --output /path/outside/worktree/kei-v1.1-public
```

以上是供本地复查的命令。导出目录必须事先不存在；脚本采用明确白名单，不携带 `.git`，并生成 `PUBLIC_MANIFEST.json` 和 `checksums.sha256`。目前导出白名单遗漏 `LICENSE`，也尚未包含本轮新增的历史角色卡。若另行制作包含本次文档的导出包，需要先补齐并验证导出清单。

运行 API 可用 `uvicorn web.server:app --host 127.0.0.1 --port 8000`，打开 `/docs` 查看接口；根路径明确提示前端未打包。真实生成需要自行配置 `.env`、模型及可用的 evidence/知识数据；本包的 Scene Markdown 不会自动转换为运行时 JSONL。

## License & Credits

仓库原有代码采用 [MIT License](LICENSE)。该许可证与第三方角色、游戏图像、剧情文本、商标及衍生标注的权利边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；来源记录不等于第三方素材的再分发许可。

本工作受 [ChatHaruhi](https://github.com/LC1332/Chat-Haruhi-Suzumiya) 的场景语料方法启发，也与角色卡、Lorebook、SillyTavern 等生态中的上下文供给方式有相似处；不主张首创 Scene RAG 或贴图选择。第三方与权利边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

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
