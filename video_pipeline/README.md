# Video Generation Pipeline — xAI Official SDK

A production-grade video generation pipeline using the **official xAI Python SDK** (`xai-sdk`) with LangGraph orchestration. Generates multi-clip tutorial videos from structured step definitions and concatenates them into a single output using FFmpeg.

## Architecture

```
main.py → LangGraph StateGraph → [enqueue_clips] → [generate_all_clips] → [concatenate_clips] → [finalize]
                                       │                     │                      │                  │
                                  Validate &            xAI SDK              FFmpeg concat         Cleanup
                                  prepare steps      (concurrent clips)      successful clips      temp files
                                                           │
                                                     GrokAdapter
                                                     (gRPC API)
                                                           │
                                                  Download video → Save .mp4
```

## Key Features

- **Official xAI SDK** — gRPC-based client with built-in authentication
- **LangGraph orchestration** — 4-node stateful DAG workflow (enqueue → generate → concatenate → finalize)
- **Concurrent clip generation** — all clips generated in parallel via `asyncio.gather`
- **Exponential backoff retries** — configurable attempts with non-retryable error detection (moderation, invalid_argument, permission_denied)
- **Dry run mode** — log prompts without making API calls (saves credits during development)
- **Redis Queue support** — background processing via RQ workers with per-clip fault isolation
- **FFmpeg concatenation** — clips re-encoded with libx264 and merged into a single final video
- **Pydantic validation** — type-safe settings and step schema validation

## Supported Generation Modes

| Mode | Input | Description |
|------|-------|-------------|
| Text-to-video | `prompt` only | Generate from text description |
| Image-to-video | `prompt` + `start_image` | Use image URL as first frame |

## SDK Constraints

- **Resolutions**: `480p`, `720p`
- **Aspect ratios**: `1:1`, `16:9`, `9:16`
- **Duration**: 1–10 seconds per clip (configurable via `MAX_CLIP_DURATION`)
- **Model**: `grok-imagine-video`

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your XAI_API_KEY

# Run the pipeline
python main.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XAI_API_KEY` | (required) | Your xAI API key from https://console.x.ai |
| `DEFAULT_MODEL` | `grok-imagine-video` | Model to use |
| `DEFAULT_RESOLUTION` | `480p` | Default video resolution |
| `MAX_RETRIES` | `3` | Retry attempts per clip |
| `RETRY_BASE_DELAY` | `2.0` | Base delay (seconds) for exponential backoff |
| `MAX_CLIP_DURATION` | `10` | Max seconds per clip |
| `CLIP_OUTPUT_DIR` | `./clips` | Temporary directory for individual clips |
| `FINAL_OUTPUT_DIR` | `./output` | Directory for final concatenated video |
| `DRY_RUN` | `false` | Log prompts without API calls |
| `SDK_GENERATION_TIMEOUT` | `600` | Max wait time for SDK generation (seconds) |
| `SDK_POLL_INTERVAL` | `1.0` | SDK polling interval (seconds) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for RQ |
| `LOG_LEVEL` | `INFO` | Logging level |

## Pipeline Workflow (LangGraph Nodes)

1. **enqueue_clips** — Validates steps, assigns job ID, creates output directories
2. **generate_all_clips** — Generates all clips concurrently with retry logic per clip
3. **concatenate_clips** — Merges successful clips via FFmpeg concat demuxer (skipped in dry run)
4. **finalize** — Cleans up temporary clip files, returns final metadata

## Step Schema

Each tutorial step accepts:

```python
{
    "prompt": str,           # Required — text description of the video
    "duration": int,         # Optional — seconds (default: 6, max: 10)
    "aspect_ratio": str,     # Optional — "16:9", "9:16", "1:1" (default: "16:9")
    "resolution": str,       # Optional — "480p", "720p" (default: "480p")
    "start_image": str,      # Optional — image URL for image-to-video mode
}
```

## Project Structure

```
video_pipeline/
├── adapters/
│   ├── __init__.py          # Adapter factory (get_adapter)
│   ├── base.py              # Abstract VideoGenerationService interface
│   └── grok_adapter.py      # xAI SDK implementation (gRPC)
├── config/
│   └── settings.py          # Pydantic settings from .env
├── core/
│   └── registry.py          # Model registry (VideoModel dataclass)
├── graph/
│   └── workflow.py          # LangGraph StateGraph pipeline (4 nodes)
├── nodes/
│   ├── video_generator.py   # Clip generation with retry logic
│   └── utils.py             # FFmpeg concat, directory management, cleanup
├── tasks/
│   └── queue_tasks.py       # RQ background task definitions
├── output/                  # Final concatenated videos
├── .env.example             # Environment variable template
├── main.py                  # Entry point with sample tutorial steps
└── requirements.txt         # Python dependencies
```

## Dependencies

- `xai-sdk` — Official xAI Python SDK (gRPC)
- `langgraph` / `langchain-core` — Workflow orchestration
- `pydantic` / `pydantic-settings` — Settings & validation
- `httpx` — Async HTTP for video downloads
- `loguru` — Structured logging
- `rq` / `redis` — Background job queue
- `FFmpeg` — System dependency for video concatenation

## Usage with Redis Queue (Optional)

For background processing, start an RQ worker:

```bash
rq worker video_generation --url redis://localhost:6379/0
```

Then enqueue clips programmatically:

```python
from tasks.queue_tasks import enqueue_clip_generation

job = enqueue_clip_generation(
    step_index=0,
    prompt="Screen recording of a dashboard...",
    duration=6,
)
```
