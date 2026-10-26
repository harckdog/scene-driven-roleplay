"""共享的数学排版指令。"""

MATH_FORMAT_PROMPT = r"""

数学排版规则：
- 正文、标题、列表和代码使用 Markdown。
- 行内数学使用 \( ... \)。
- 行间数学使用 \[ ... \]。
- 所有 LaTeX 命令，包括 \quad、\circ、\mathrm、\hookrightarrow、
  \subset 和 \text，都必须位于数学定界符内部。
- 列表缩进使用 Markdown 缩进；不要在数学定界符外单独使用 \quad 或 \qquad。
- 不要把数学表达式放进 Markdown 代码围栏。
- 保持 LaTeX 语法完整；在需要解释数学内容时，说明重要符号的含义。
"""
