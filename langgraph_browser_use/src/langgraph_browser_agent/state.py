# state.py
from typing import TypedDict, Optional

from .models import Agent1Output, PageCapture


class AgentState(TypedDict):
    url: str
    user_query: str
    page_captures: Optional[list[PageCapture]]
    structured_output: Optional[Agent1Output]
