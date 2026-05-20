"""
RQ (Redis Queue) task definitions for background video clip generation.
Each clip is processed as an independent job for fault isolation.
"""

import asyncio
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job
from loguru import logger

from config.settings import settings
from nodes.video_generator import generate_clip


def get_redis_connection() -> Redis:
    """Create a Redis connection from settings."""
    return Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    """Get the default RQ queue for video generation tasks."""
    return Queue("video_generation", connection=get_redis_connection())


def clip_generation_worker(
    step_index: int,
    prompt: str,
    model_name: str | None = None,
    duration: int = 6,
    aspect_ratio: str = "16:9",
    resolution: str = "480p",
    start_image: str | None = None,
) -> dict[str, Any]:
    """
    RQ worker function — runs generate_clip in an event loop.
    This is the function that RQ workers will execute.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            generate_clip(
                step_index=step_index,
                prompt=prompt,
                model_name=model_name,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                start_image=start_image,
            )
        )
    finally:
        loop.close()


def enqueue_clip_generation(
    step_index: int,
    prompt: str,
    model_name: str | None = None,
    duration: int = 6,
    aspect_ratio: str = "16:9",
    resolution: str = "480p",
    start_image: str | None = None,
    job_timeout: int = 700,
) -> Job:
    """
    Enqueue a clip generation task to RQ.
    Returns the RQ Job object for tracking.
    """
    queue = get_queue()

    job = queue.enqueue(
        clip_generation_worker,
        step_index=step_index,
        prompt=prompt,
        model_name=model_name,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        start_image=start_image,
        job_timeout=job_timeout,
        result_ttl=3600,
    )

    logger.info(
        f"[Step {step_index}] Enqueued clip generation | rq_job_id={job.id}"
    )
    return job
