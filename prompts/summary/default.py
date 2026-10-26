DEFAULT_SUMMARY_PROMPT="""
维护一份对话状态（conversation state），根据新增消息更新已有状态，而不是重新复述整个对话。删除已经过时的信息，保留仍然有效的信息，不要描述助手的回答过程。
"""