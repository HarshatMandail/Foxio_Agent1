"""
Step Splitter — Converts Agent1Output into structured video generation steps.

Takes the long `context_for_video` narration string from Agent 1 and splits it
into 4–8 beginner-friendly video clips optimized for text-to-video generation.

Strategy:
  1. Split narration into logical action segments (sentence-level).
  2. Group related sentences into clips (target: 1-3 sentences per clip).
  3. Generate visual prompts optimized for Grok Imagine Video.
  4. Map screenshots from Agent 1 as start_image for each clip.
  5. Assign durations based on action complexity.
"""

import re
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import settings

MIN_STEPS = 4
MAX_STEPS = 8
DEFAULT_DURATION = 6
COMPLEX_ACTION_DURATION = 8
SIMPLE_ACTION_DURATION = 5

# Keywords that indicate a complex action (needs more screen time)
COMPLEX_KEYWORDS = {
    "fill", "type", "enter", "select", "choose", "configure",
    "drag", "upload", "search", "scroll", "navigate", "switch",
}

# Keywords that indicate a simple action (quick visual)
SIMPLE_KEYWORDS = {
    "click", "tap", "press", "hover", "see", "notice", "observe",
    "appear", "display", "show", "open", "close",
}

# Sentence boundary pattern
SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+|(?<=\.)\s*(?=[A-Z])')

# Action boundary markers (split narration at these transition words)
ACTION_MARKERS = re.compile(
    r'\b(then|next|after that|now|once|finally|first|second|third|'
    r'step \d|from here|you will|this will|the system)\b',
    re.IGNORECASE,
)


def split_agent1_output_to_steps(
    agent1_output: dict[str, Any],
    user_query: str = "",
) -> list[dict[str, Any]]:
    """
    Convert Agent1Output dict into structured video pipeline steps.

    Args:
        agent1_output: Dict with context_for_video, pages_captured, platform_name, etc.
        user_query: Original user question for context.

    Returns:
        List of step dicts ready for the video pipeline:
        [{"prompt": str, "duration": int, "aspect_ratio": str, "resolution": str, "start_image": str|None}]
    """
    context = agent1_output.get("context_for_video", "")
    platform_name = agent1_output.get("platform_name", "the platform")
    pages_captured = agent1_output.get("pages_captured", [])
    current_page = agent1_output.get("current_page", {})

    if not context.strip():
        logger.warning("[StepSplitter] Empty context_for_video — generating fallback steps.")
        return _generate_fallback_steps(agent1_output, user_query)

    # Step 1: Split narration into sentences
    sentences = _split_into_sentences(context)

    if len(sentences) < 2:
        logger.warning("[StepSplitter] Very short narration — using single-step fallback.")
        return _generate_fallback_steps(agent1_output, user_query)

    # Step 2: Group sentences into logical clips
    groups = _group_sentences_into_clips(sentences)

    # Step 3: Convert groups into video prompts
    steps = _build_video_steps(
        groups=groups,
        platform_name=platform_name,
        current_page=current_page,
        pages_captured=pages_captured,
    )

    # Step 4: Clamp to MIN/MAX steps
    if len(steps) < MIN_STEPS:
        steps = _expand_steps(steps, MIN_STEPS)
    elif len(steps) > MAX_STEPS:
        steps = _compress_steps(steps, MAX_STEPS)

    # Step 5: Map screenshots to steps
    steps = _assign_screenshots(steps, pages_captured)

    logger.info(
        f"[StepSplitter] Generated {len(steps)} steps from "
        f"{len(sentences)} sentences | platform={platform_name}"
    )

    return steps


def _split_into_sentences(text: str) -> list[str]:
    """Split narration text into clean sentences."""
    raw_sentences = SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in raw_sentences if s.strip() and len(s.strip()) > 10]


def _group_sentences_into_clips(sentences: list[str]) -> list[list[str]]:
    """
    Group sentences into logical clip segments.
    Uses action markers and sentence count heuristics.
    Target: 1-3 sentences per group, 4-8 groups total.
    """
    groups: list[list[str]] = []
    current_group: list[str] = []

    target_group_size = max(1, len(sentences) // 6)

    for sentence in sentences:
        has_marker = bool(ACTION_MARKERS.search(sentence))
        group_full = len(current_group) >= target_group_size

        if current_group and (has_marker or group_full):
            groups.append(current_group)
            current_group = [sentence]
        else:
            current_group.append(sentence)

    if current_group:
        groups.append(current_group)

    return groups


def _build_video_steps(
    groups: list[list[str]],
    platform_name: str,
    current_page: dict,
    pages_captured: list[dict],
) -> list[dict[str, Any]]:
    """Convert sentence groups into structured video step dicts."""
    steps = []
    page_title = current_page.get("title", "the current page")

    for i, group in enumerate(groups):
        combined_text = " ".join(group)
        duration = _estimate_duration(combined_text)
        prompt = _build_tutorial_prompt(
            action_text=combined_text,
            step_number=i + 1,
            total_steps=len(groups),
            platform_name=platform_name,
            page_title=page_title,
        )

        steps.append({
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": "16:9",
            "resolution": settings.default_resolution,
            "start_image": None,
        })

    return steps


def _build_tutorial_prompt(
    action_text: str,
    step_number: int,
    total_steps: int,
    platform_name: str,
    page_title: str,
) -> str:
    """
    Build a visual, beginner-friendly prompt optimized for text-to-video AI.
    Describes exactly what the viewer should SEE on screen.
    """
    # Clean up the action text
    action_clean = action_text.strip().rstrip(".")

    # Build context prefix based on step position
    if step_number == 1:
        context = (
            f"Screen recording of the {platform_name} interface showing "
            f"the '{page_title}' page."
        )
    elif step_number == total_steps:
        context = (
            f"Screen recording of {platform_name} showing the final step "
            f"of the workflow."
        )
    else:
        context = f"Screen recording of {platform_name} showing the next action."

    prompt = (
        f"{context} {action_clean}. "
        f"Clean, professional SaaS interface with clear UI elements. "
        f"Smooth cursor movement highlighting the action. "
        f"Beginner-friendly tutorial style."
    )

    return prompt


def _estimate_duration(text: str) -> int:
    """Estimate clip duration based on action complexity."""
    text_lower = text.lower()

    has_complex = any(kw in text_lower for kw in COMPLEX_KEYWORDS)
    has_multiple_actions = text_lower.count("click") + text_lower.count("select") > 1

    if has_complex or has_multiple_actions:
        return COMPLEX_ACTION_DURATION
    elif any(kw in text_lower for kw in SIMPLE_KEYWORDS):
        return SIMPLE_ACTION_DURATION

    # Default based on text length
    word_count = len(text.split())
    if word_count > 30:
        return COMPLEX_ACTION_DURATION
    return DEFAULT_DURATION


def _assign_screenshots(
    steps: list[dict[str, Any]],
    pages_captured: list[dict],
) -> list[dict[str, Any]]:
    """
    Map Agent 1 screenshots to steps as start_image.
    First screenshot → first step, distribute remaining evenly.
    """
    if not pages_captured:
        return steps

    screenshot_paths = [
        p.get("screenshot_path", "")
        for p in pages_captured
        if p.get("screenshot_path")
    ]

    if not screenshot_paths:
        return steps

    # Assign screenshots to steps (distribute evenly)
    for i, step in enumerate(steps):
        if i < len(screenshot_paths):
            path = screenshot_paths[i]
            # Only use if file exists (for image-to-video mode)
            if Path(path).exists():
                step["start_image"] = str(Path(path).resolve())

    return steps


def _expand_steps(steps: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Expand steps to reach minimum count by splitting longest prompts."""
    while len(steps) < target:
        # Find the step with the longest prompt
        longest_idx = max(range(len(steps)), key=lambda i: len(steps[i]["prompt"]))
        longest = steps[longest_idx]

        # Split the prompt roughly in half at a sentence boundary
        prompt = longest["prompt"]
        mid = len(prompt) // 2
        split_point = prompt.find(". ", mid)

        if split_point == -1 or split_point > len(prompt) - 20:
            break

        first_half = prompt[:split_point + 1].strip()
        second_half = prompt[split_point + 2:].strip()

        if not second_half:
            break

        steps[longest_idx] = {**longest, "prompt": first_half, "duration": SIMPLE_ACTION_DURATION}
        steps.insert(longest_idx + 1, {
            **longest,
            "prompt": second_half,
            "duration": SIMPLE_ACTION_DURATION,
            "start_image": None,
        })

    return steps


def _compress_steps(steps: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Compress steps to reach maximum count by merging shortest adjacent pairs."""
    while len(steps) > target:
        # Find shortest adjacent pair
        min_combined_len = float("inf")
        merge_idx = 0

        for i in range(len(steps) - 1):
            combined = len(steps[i]["prompt"]) + len(steps[i + 1]["prompt"])
            if combined < min_combined_len:
                min_combined_len = combined
                merge_idx = i

        merged_prompt = steps[merge_idx]["prompt"] + " " + steps[merge_idx + 1]["prompt"]
        merged_duration = min(
            settings.max_clip_duration,
            steps[merge_idx]["duration"] + steps[merge_idx + 1]["duration"] - 2,
        )

        steps[merge_idx] = {
            **steps[merge_idx],
            "prompt": merged_prompt,
            "duration": merged_duration,
        }
        steps.pop(merge_idx + 1)

    return steps


def _generate_fallback_steps(
    agent1_output: dict[str, Any],
    user_query: str,
) -> list[dict[str, Any]]:
    """Generate minimal fallback steps when context_for_video is empty/short."""
    platform = agent1_output.get("platform_name", "the platform")
    current_page = agent1_output.get("current_page", {})
    page_title = current_page.get("title", "Home")
    workflows = agent1_output.get("relevant_workflows", [])

    steps = [
        {
            "prompt": (
                f"Screen recording of {platform} showing the '{page_title}' page. "
                f"Clean professional SaaS dashboard with navigation menu visible. "
                f"Cursor appears and highlights the main action area."
            ),
            "duration": 6,
            "aspect_ratio": "16:9",
            "resolution": settings.default_resolution,
            "start_image": None,
        },
    ]

    # Add workflow steps if available
    for i, workflow in enumerate(workflows[:3]):
        steps.append({
            "prompt": (
                f"Screen recording of {platform} showing: {workflow}. "
                f"Smooth cursor movement demonstrating the action. "
                f"Beginner-friendly tutorial style with clear UI."
            ),
            "duration": 7,
            "aspect_ratio": "16:9",
            "resolution": settings.default_resolution,
            "start_image": None,
        })

    # Ensure minimum steps
    while len(steps) < MIN_STEPS:
        steps.append({
            "prompt": (
                f"Screen recording of {platform} showing a successful completion "
                f"of the task. Confirmation message or success state visible. "
                f"Clean, modern interface."
            ),
            "duration": 5,
            "aspect_ratio": "16:9",
            "resolution": settings.default_resolution,
            "start_image": None,
        })

    return steps
