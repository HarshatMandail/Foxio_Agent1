# models.py
from pydantic import BaseModel, Field
from typing import List


class UIElement(BaseModel):
    element_type: str
    visible_text: str
    purpose: str
    suggested_action: str


class VideoClip(BaseModel):
    """A recorded video clip for a single atomic browser step."""
    step: int
    video_path: str
    narration: str = ""
    action: str = ""
    duration_hint: str = "3-8s"


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
    video_clips: List[dict] = Field(
        default_factory=list,
        description="List of recorded video clips per step. Each entry: {step, video_path, narration, action}",
    )
