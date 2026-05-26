"""Test single clip with real Grok API to verify base64 approach works."""
import asyncio
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from adapters import get_adapter
from config.settings import settings
from nodes.video_processor import ENHANCEMENT_PROMPT


async def main():
    clips_dir = settings.clip_output_dir
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_path = clips_dir / "split_000.mp4"

    if not clip_path.exists():
        raw = Path(r"D:\Video_Agent\Agent_1(browser_use+Playwright)\output\raw_long_video.mp4")
        if not raw.exists():
            print("ERROR: No raw video found. Run full pipeline first.")
            return
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw), "-t", "8", "-c", "copy", str(clip_path)],
            capture_output=True, check=True,
        )

    print(f"Clip: {clip_path.name} ({clip_path.stat().st_size // 1024}KB)")
    print(f"API Key: {settings.xai_api_key[:10]}...")
    print(f"Dry Run: {settings.dry_run}")

    adapter = get_adapter()
    output_path = clips_dir / "test_enhanced.mp4"

    print("Calling Grok Imagine Video API...")
    print("(This takes 60-120 seconds, please wait...)")

    try:
        result = await adapter.generate_video(
            input_video_path=str(clip_path),
            prompt=ENHANCEMENT_PROMPT,
            duration=8,
            output_path=output_path,
        )
        print(f"\nSUCCESS!")
        print(f"  Status: {result['status']}")
        print(f"  Mode: {result['mode']}")
        if output_path.exists():
            print(f"  Output: {output_path}")
            print(f"  Size: {output_path.stat().st_size // 1024}KB")
    except Exception as e:
        print(f"\nFAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
