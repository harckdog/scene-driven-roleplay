"""Gradio application entry point."""

from functools import lru_cache

import gradio as gr

from config import DEFAULT_ROLE_ID, MODES, PAPER, ROLEPLAY
from core.chatbot import chat
from roleplay.session_manager import clear as clear_roleplay_session
from roleplay.session_manager import get_history as get_roleplay_history
from roles.registry import get_role, list_roles
from roles.stickers.renderer import render_history
from roles.stickers.registry import StickerRegistry


LATEX_DELIMITERS = [
    {"left": "$$", "right": "$$", "display": True},
    {"left": "\\[", "right": "\\]", "display": True},
    {"left": "\\(", "right": "\\)", "display": False},
    {"left": "$", "right": "$", "display": False},
]


@lru_cache(maxsize=1)
def _sticker_registry() -> StickerRegistry:
    """Reuse the immutable local sticker registry across transcript renders."""
    return StickerRegistry.from_directory()


def _render_roleplay_history(role_id: str | None) -> list[dict]:
    """Render one role's isolated structured history through component content."""
    if not role_id:
        return []
    profile = get_role(role_id)
    return render_history(
        get_roleplay_history(role_id),
        pack_id=profile.sticker_pack,
        registry=_sticker_registry(),
    )


def _role_selector_update(
    selected_mode: str,
    role_id: str | None,
) -> tuple[gr.Dropdown, gr.Group, gr.Group, list[dict]]:
    """Switch between the existing chat UI and the dedicated Roleplay UI."""
    is_roleplay = selected_mode == ROLEPLAY
    return (
        gr.Dropdown(visible=is_roleplay),
        gr.Group(visible=not is_roleplay),
        gr.Group(visible=is_roleplay),
        _render_roleplay_history(role_id) if is_roleplay else [],
    )


def _on_role_change(role_id: str) -> list[dict]:
    """Load the selected role's own transcript."""
    return _render_roleplay_history(role_id)


def _send_roleplay(
    message: str,
    role_id: str,
) -> tuple[list[dict], str]:
    """Persist one structured RP turn and return its component-rendered history."""
    from core.roleplay_chatbot import chat_structured

    chat_structured(message, role_id)
    return _render_roleplay_history(role_id), ""


def _clear_roleplay(role_id: str) -> list[dict]:
    """Clear only the current role's persisted RP conversation."""
    clear_roleplay_session(role_id)
    return []


def create_demo() -> gr.Blocks:
    """Create the web interface with mode and role selection."""
    with gr.Blocks(title="AI4MathAssistant") as demo:
        gr.Markdown("# AI4MathAssistant")
        gr.Markdown("面向数学研究、论文阅读、习题讲解与角色扮演的个人助手。")
        with gr.Row():
            mode = gr.Dropdown(
                choices=[(config["display_name"], name) for name, config in MODES.items()],
                value=PAPER,
                label="模式",
            )
            role_selector = gr.Dropdown(
                choices=[(profile.display_name, profile.id) for profile in list_roles()],
                value=DEFAULT_ROLE_ID,
                label="角色",
                visible=False,
            )
        with gr.Group(visible=True) as standard_chat_group:
            chatbot = gr.Chatbot(
                render_markdown=True,
                latex_delimiters=LATEX_DELIMITERS,
                placeholder="输入数学问题，或选择角色后开始对话。",
            )
            gr.ChatInterface(
                fn=chat,
                chatbot=chatbot,
                additional_inputs=[mode, role_selector],
            )

        with gr.Group(visible=False) as roleplay_group:
            roleplay_chatbot = gr.Chatbot(
                render_markdown=True,
                latex_delimiters=LATEX_DELIMITERS,
                placeholder="选择一个角色后开始对话。",
            )
            with gr.Row():
                roleplay_input = gr.Textbox(
                    label="角色扮演消息",
                    placeholder="输入文字；也可以只发送一个表情。",
                    scale=4,
                )
            with gr.Row():
                roleplay_send = gr.Button("发送", variant="primary")
                roleplay_clear = gr.Button("清空当前角色对话")

            roleplay_send.click(
                fn=_send_roleplay,
                inputs=[roleplay_input, role_selector],
                outputs=[roleplay_chatbot, roleplay_input],
            )
            roleplay_input.submit(
                fn=_send_roleplay,
                inputs=[roleplay_input, role_selector],
                outputs=[roleplay_chatbot, roleplay_input],
            )
            roleplay_clear.click(
                fn=_clear_roleplay,
                inputs=role_selector,
                outputs=roleplay_chatbot,
            )

        mode.change(
            fn=_role_selector_update,
            inputs=[mode, role_selector],
            outputs=[role_selector, standard_chat_group, roleplay_group, roleplay_chatbot],
        )
        role_selector.change(
            fn=_on_role_change,
            inputs=role_selector,
            outputs=roleplay_chatbot,
        )
    return demo


if __name__ == "__main__":
    create_demo().launch()
