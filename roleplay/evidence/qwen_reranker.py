"""Local instruction-aware scoring with Qwen3-Reranker-0.6B."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Sequence

LOGGER = logging.getLogger(__name__)

SCENE_RANKING_INSTRUCTION = (
    "给定当前角色扮演对话和一个历史 Scene，判断该 Scene 是否适合作为生成角色下一句回复的上下文示例。"
    "核心不是判断两个场景讨论的话题是否相似，而是判断其中的互动结构和角色反应是否可以迁移到当前对话。"
    "\n\n"
    "优先考虑："
    "\n1. 用户当前这一轮在做什么：例如邀请、请求、调侃、关心、示弱、抱怨、表达亲近、寻求安慰或普通闲聊；"
    "\n2. Scene 中对方采取的 conversational move 是否与当前用户的 move 相似；"
    "\n3. Scene 中角色的回应方式、主动性、接受或拒绝方式，以及互动如何继续，是否适合成为当前回复的行为先例；"
    "\n4. 双方关系阶段和距离感是否兼容；"
    "\n5. 场景的情绪强度和 conversational stakes 是否接近。"
    "\n\n"
    "应降低以下 Scene 的排名："
    "\n- 只有主题或关键词相似，但互动目的不同；"
    "\n- 对话双方的主动/被动关系相反；"
    "\n- 角色反应依赖明显不同的关系阶段或特殊剧情条件；"
    "\n- 情绪强度明显不匹配；"
    "\n- 将其中的角色反应迁移到当前对话会造成不自然的关系升级、降级或行为跳变。"
    "\n\n"
    "不要生成角色回复，也不要评价 Scene 本身写得好不好。"
    "只判断它作为当前下一轮回复的参考示例有多有用。"
)

_PREFIX = (
    '<|im_start|>system\nJudge whether the Document meets the requirements based on '
    'the Query and the Instruct provided. Note that the answer can only be "yes" '
    'or "no".<|im_end|>\n<|im_start|>user\n'
)
_SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'


class QwenSceneReranker:
    """Score every candidate independently; model loading is lazy and local-only."""

    def __init__(self, model_path: str | Path, *, batch_size: int = 4, max_length: int = 2048) -> None:
        if batch_size < 1 or max_length < 128:
            raise ValueError("invalid reranker batch size or sequence length")
        self.model_path = Path(model_path)
        self.batch_size = batch_size
        self.max_length = max_length

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        import torch

        tokenizer, model = _load_model(str(self.model_path.resolve()))
        prefix_tokens = tokenizer.encode(_PREFIX, add_special_tokens=False)
        suffix_tokens = tokenizer.encode(_SUFFIX, add_special_tokens=False)
        body_limit = self.max_length - len(prefix_tokens) - len(suffix_tokens)
        if body_limit < 64:
            raise ValueError("reranker max_length leaves too little room for the query and scene")
        yes_id = tokenizer.convert_tokens_to_ids("yes")
        no_id = tokenizer.convert_tokens_to_ids("no")
        scores: list[float] = []
        for start in range(0, len(documents), self.batch_size):
            batch = documents[start:start + self.batch_size]
            pairs = [
                f"<Instruct>: {SCENE_RANKING_INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"
                for document in batch
            ]
            encoded = tokenizer(
                pairs, padding=False, truncation="longest_first",
                max_length=body_limit, return_attention_mask=False,
            )
            encoded["input_ids"] = [
                prefix_tokens + token_ids + suffix_tokens
                for token_ids in encoded["input_ids"]
            ]
            inputs = tokenizer.pad(encoded, padding=True, return_tensors="pt")
            inputs = {key: value.to(model.device) for key, value in inputs.items()}
            with torch.inference_mode():
                logits = model(**inputs, use_cache=False).logits[:, -1, :]
                binary_logits = torch.stack((logits[:, no_id], logits[:, yes_id]), dim=1)
                scores.extend(torch.softmax(binary_logits.float(), dim=1)[:, 1].cpu().tolist())
        return scores


@lru_cache(maxsize=2)
def _load_model(model_path: str):
    """Keep weights in memory across turns without attempting network downloads."""
    path = Path(model_path)
    if not path.is_dir():
        raise FileNotFoundError(f"Qwen scene reranker weights are missing: {path}")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path, padding_side="left", local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True).eval()
    device = "cuda" if torch.cuda.is_available() else (
        "mps" if torch.backends.mps.is_available() else "cpu"
    )
    if device == "cpu":
        LOGGER.warning("Qwen scene reranker is using CPU; GPU acceleration is unavailable")
    else:
        LOGGER.info("Qwen scene reranker is using %s", device)
    model.to(device)
    return tokenizer, model
