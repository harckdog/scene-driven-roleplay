"""Long-term-memory extraction instructions for general chat."""

CHAT_MEMORY_PROMPT = """
Extract only new, stable long-term memories from the conversation summary.

Keep facts that can improve future conversations, such as user background,
preferences, long-running research goals, or persistent mathematical context.
Do not keep greetings, one-time requests, temporary details, or information
already present in Existing Memories.

Return only a valid JSON array of concise strings. Do not use Markdown, code
fences, headings, or explanatory text. Return [] when there is no new stable
memory.
"""
