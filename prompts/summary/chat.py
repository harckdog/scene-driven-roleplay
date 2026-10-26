"""Summary instructions for general chat."""

CHAT_SUMMARY_PROMPT = """
You maintain a compact conversation summary for a mathematical assistant.

Rewrite the existing summary into a single replacement summary using the new
conversation. Do not append to the old summary and do not describe the
summarization process.

Keep only information useful in later turns:
- stable user background, preferences, and goals;
- mathematical topics, definitions, assumptions, and conclusions;
- open questions and agreed next steps.

Discard greetings, repeated wording, and transient details. Keep the result
under 400 words. Return only the replacement summary as plain text.
"""
