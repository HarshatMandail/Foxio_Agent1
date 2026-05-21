# Video Generation Pipeline (Agent 2) — Foxio

Production-grade tutorial video generation pipeline for **Foxio** — a Chrome extension that helps new users navigate complex CLM (Contract Lifecycle Management) platforms.

Takes structured output from **Agent 1** (browser analysis) and generates beginner-friendly tutorial videos using **xAI Grok Imagine Video** with LangGraph orchestration.

## How It Works

```
Agent 1 Output                    Agent 2 (this pipeline)
─────────────────    ─────────────────────────────────────────────────────────────
                     ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
context_for_video ──►│ Step        │───►│ Generate     │───►│ Concatenate │───►│ Finalize │──► tutorial_video.mp4
platform_name        │ Splitter    │    │ All Clips    │    │ (FFmpeg)    │    │ + Save   │
pages_captured       │ (4-8 steps) │    │ (xAI SDK)    │    │             │    │ Metadata │
screenshots          └─────────────┘    └──────────────┘    └─────────────┘    └──────────┘
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Set your XAI_API_KEY in .env

# Run with sample Agent1Output (dry run by default)
python main.py

# Run with raw steps (legacy mode)
python main.py --raw-steps
```

## Integration with Agent 1

### From Agent 1 code (recommended):

```python
from generate_tutorial import generate_tutorial_video

# Agent 1 output (from run_agent1())
agent1_output = {
    "platform_name": "Salesforce",
    "context_for_video": "You are currently on the Contracts page...",
    "pages_captured": [...],
    "current_page": {...},
    "overall_user_journey": "...",
    "relevant_workflows": [...],
}

result = await generate_tutorial_video(
    agent1_output=agent1_output,
    user_query="How do I create a new contract?",
    dry_run=False,  # Set False to generate real video
)

print(result["final_video_path"])  # → generated_videos/tutorial_abc123.mp4
print(result["metadata_path"])     # → generated_videos/abc123_metadata.json
```

### From the unified pipeline (langgraph_browser_use):

```python
from langgraph_browser_agent import run_full_pipeline

result = await run_full_pipeline(
    url="https://myorg.salesforce.com",
    user_query="How do I create a new contract?",
    dry_run=True,
)
```

## Step Splitter — The Conversion Layer

The key innovation: Agent 1 produces a single long narration string (`context_for_video`). The **Step Splitter** (`nodes/step_splitter.py`) automatically converts this into 4–8 structured video clips:

1. Splits narration into sentences
2. Groups related sentences by action boundaries
3. Generates visual prompts optimized for text-to-video AI
4. Maps Agent 1 screenshots as `start_image` (image-to-video mode)
5. Estimates duration per clip based on action complexity

**No LLM call needed** — pure heuristic splitting (fast, free, deterministic).

## Output Structure

```
langgraph_browser_use/generated_videos/
├── tutorial_abc123.mp4          # Final concatenated video
├── abc123_metadata.json         # Full metadata (prompts, costs, timestamps)
└── clips/                       # Temporary (auto-deleted after concat)
    ├── clip_000.mp4
    ├── clip_001.mp4
    └── ...
```

### Metadata JSON contains:
- `job_id`, `timestamp` — tracking
- `user_query` — what the user asked
- `video_title` — auto-generated title
- `steps` — full prompt text for each clip
- `clip_results` — status, duration, cost per clip
- `final_video_path` — where the video lives

## Architecture

```
video_pipeline/
├── generate_tutorial.py      # ★ Main entry point (Agent1Output → video)
├── main.py                   # CLI runner (sample data + raw steps mode)
├── adapters/
│   ├── base.py               # Abstract VideoGenerationService
│   └── grok_adapter.py       # xAI SDK implementation (gRPC)
├── config/
│   └── settings.py           # Pydantic settings (env-based)
├── core/
│   └── registry.py           # Model registry (VideoModel)
├── graph/
│   └── workflow.py           # LangGraph StateGraph (4-node DAG)
├── nodes/
│   ├── step_splitter.py      # ★ Agent1Output → structured steps converter
│   ├── video_generator.py    # Clip generation with retry logic
│   └── utils.py              # FFmpeg concat, directory management
├── tasks/
│   └── queue_tasks.py        # Redis Queue background processing
├── output/                   # Final videos land here
├── .env                      # Configuration
└── requirements.txt          # Dependencies
```

## LangGraph Pipeline Nodes

| Node | Purpose |
|------|---------|
| `enqueue_clips` | Validate steps, assign job ID, create directories |
| `generate_all_clips` | Generate all clips concurrently via asyncio.gather |
| `concatenate_clips` | Merge clips with FFmpeg (libx264, re-encoded) |
| `finalize` | Cleanup temp files, return metadata |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XAI_API_KEY` | (required) | xAI API key from https://console.x.ai |
| `DEFAULT_MODEL` | `grok-imagine-video` | Video generation model |
| `DEFAULT_RESOLUTION` | `480p` | Video resolution (`480p` or `720p`) |
| `MAX_RETRIES` | `3` | Retry attempts per clip |
| `RETRY_BASE_DELAY` | `2.0` | Exponential backoff base (seconds) |
| `MAX_CLIP_DURATION` | `10` | Max seconds per clip |
| `DRY_RUN` | `true` | Skip API calls (saves credits) |
| `MIN_TUTORIAL_STEPS` | `4` | Minimum clips per tutorial |
| `MAX_TUTORIAL_STEPS` | `8` | Maximum clips per tutorial |
| `DEFAULT_CLIP_DURATION` | `6` | Default clip length (seconds) |
| `TUTORIAL_ASPECT_RATIO` | `16:9` | Default aspect ratio |
| `PROMPT_STYLE` | `beginner_friendly` | Prompt generation style |
| `CLIP_OUTPUT_DIR` | `generated_videos/clips` | Temp clip directory |
| `FINAL_OUTPUT_DIR` | `generated_videos/` | Final video output |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for background queue |
| `LOG_LEVEL` | `INFO` | Logging level |

## Video Generation Modes

| Mode | Input | When Used |
|------|-------|-----------|
| Text-to-video | `prompt` only | Default — generates from text description |
| Image-to-video | `prompt` + `start_image` | When Agent 1 screenshots are available |

## Supported Constraints (xAI Grok Imagine)

- **Resolutions**: `480p`, `720p`
- **Aspect ratios**: `1:1`, `16:9`, `9:16`
- **Duration**: 1–10 seconds per clip
- **Model**: `grok-imagine-video`

## Redis Queue (Optional)

For background processing in production:

```bash
# Start worker
rq worker video_generation --url redis://localhost:6379/0
```

## Dependencies

- `xai-sdk` — Official xAI Python SDK (gRPC)
- `langgraph` / `langchain-core` — Workflow orchestration
- `pydantic` / `pydantic-settings` — Settings & validation
- `httpx` — Async HTTP for video downloads
- `loguru` — Structured logging
- `rq` / `redis` — Background job queue
- **FFmpeg** — System dependency for video concatenation
