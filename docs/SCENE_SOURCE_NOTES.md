# 原作 Scene 卡来源与整理说明

这七份 Markdown 是作者从 *Blue Archive* 凯伊相关剧情人工整理的**公开引用副本**，不是游戏官方发布的数据集。故事、角色和原始台词的权利仍归原权利方；本项目只说明整理方法及自身添加的结构化注释，不主张因整理而取得原文版权。通用来源可参阅 [Blue Archive 官方游戏介绍](https://www.nexon.com/main/en/Blue%20Archive/details)。各卡中的 `source: manual/...txt` 是本地溯源 ID，并非可点击的官方 URL；原始手稿 TXT 未随包提供。

| 文件 | 手工整理与修改 | 注意 |
| --- | --- | --- |
| `tendou_kei_kizuna2.md` | 按羁绊第 2 话切成多个对话段；添加 Scene 摘要、关系语境、`relation_floor`、`affection_expression` 和贴图注释。 | `review_status: draft`；这些数值和标签是作者判断，不是原作元数据。 |
| `tendou_kei_kizuna3.md` | 文件头记录由视频 OCR 整理，选项框由 `choice_roi` 识别；按连续互动分段并初拟关系与表情注释。 | OCR 与初拟标注均为 draft；未附原始逐帧截图。 |
| `tendou_kei_kizuna3_reviewed.md` | 在第 3 话分段上重写 Scene 摘要、关系语境与迁移限制，供人工复核。 | 与上一文件有重叠 Scene ID；这是并列版本，不能两份一起转换。文件仍标 `draft`。 |
| `tendou_kei_kizuna4_reviewed.md` | 第 4 话按互动段切分，补充关系前提、迁移限制和贴图 ID。 | 文件仍标 `draft`；“reviewed”是文件名，不等于全部卡完成审核。 |
| `tendou_kei_kizuna6.md` | 第 6 话按对话变化切分，补充 `relation_floor`、表达方向及可迁移范围。 | 关系数值和 `transfer_limits` 是后加注释。 |
| `tendou_kei_memoryhall.md` | 将回忆大厅相关互动拆成独立 Scene，加入概述、关系位置和部分贴图标注。 | 原文与作者的场景概述分层阅读；各卡仍为 draft。公开副本只清理了行尾空格和多余末尾空行，未改台词。 |
| `tendou_kei_valentine_perfect_plan_sliced_v2.md` | 将情人节“完美计划”剧情按交付巧克力、试吃、误会、安慰等话轮再切分；补充 Scene 摘要、关系与情绪标注。 | 实际文件名是 `valentine`，不是 `valentile`；个别极端羞耻台词依赖原剧情，`transfer_limits` 不表示可以照搬到日常聊天。 |

共同处理规则：保留卡片中的 `source`、说话者与对话顺序；`scene`、`relationship_context`、`transfer_limits`、数值和贴图标注是作者的解释层。它们不会自动成为当前会话事实，也不应被当作官方情绪标签。公开包仍**不含**原项目当前 78 条转换后 evidence JSONL；这些 Markdown 未自动合并或转换，不能由此推断冻结 `kei-v1.1` 的 32 条来源。

第三方图片另行处理：34 张贴图 PNG 与头像由作者从 [kivo.wiki 凯伊角色页](https://kivo.wiki/data/character/518)相关资料取得并提供。该页面提供来源指向，但我们未核验逐张文件的原始 URL 或再分发授权；引用来源不改变游戏图片的权利归属。对应的 YAML 是作者写的语义标注，和 PNG 分别标识。
