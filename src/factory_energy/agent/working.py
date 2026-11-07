"""Take the model's own working out of a final answer.

Some models write a draft or a remark such as "Now I have all the information I need" before
the answer, then a line such as "Let me provide the answer:" or an "Answer:" heading. The chat
shows the plan and the tool calls separately, so the answer keeps only what follows that line.
"""

from __future__ import annotations

import re

# A line of its own that introduces the answer: everything before it is working.
LEAD_IN = re.compile(
    r"^[ \t]*(?:\*\*|#+[ \t]*)?"
    r"(?:(?:final[ \t]+)?answer"
    r"|let me (?:now )?(?:provide|give|write)(?: you)? (?:the|my) (?:final )?answer)"
    r"[ \t]*[:.]?[ \t]*(?:\*\*)?[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
# An opening remark about having gathered enough, before the answer itself.
REMARK = re.compile(
    r"\A\s*(?:now,? )?i (?:now )?have (?:all )?(?:the )?(?:information|data) (?:that )?"
    r"(?:i need|i needed|needed)\b[^.\n]*?[.:!]\s*",
    re.IGNORECASE,
)


def strip_working(text: str) -> str:
    """The answer without a leading draft or remark; unchanged if there is none."""
    leads = list(LEAD_IN.finditer(text))
    if leads and text[leads[-1].end():].strip():
        text = text[leads[-1].end():]
    return REMARK.sub("", text, count=1).strip()
