# models.py
from pydantic import BaseModel, Field
from typing import List, Optional


class UIElement(BaseModel):
    element_type: str
    visible_text: str
    purpose: str
    suggested_action: str


class PageCapture(BaseModel):
    """Single page capture during platform crawl."""
    url: str
    title: str
    screenshot_path: str
    dom_summary: dict
    navigation_links: List[str] = []
    buttons: List[dict] = []
    forms_count: int = 0


class PageContext(BaseModel):
    url: str
    title: str
    description: str
    key_elements: List[UIElement]
    main_actions: List[str]


class Agent1Output(BaseModel):
    platform_name: str
    pages_captured: List[PageCapture] = []
    current_page: PageContext
    overall_user_journey: str
    relevant_workflows: List[str]
    context_for_video: str = Field(
        ...,
        description="Rich, visual-friendly summary of the full platform optimized for generating a demo video",
    )
