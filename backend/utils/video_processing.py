import subprocess
import os


def extract_frames(video_path: str, output_dir: str, num_frames: int = 5) -> list[str]:
    """Extract key frames from a video using ffmpeg."""
    os.makedirs(output_dir, exist_ok=True)

    # Get video duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip()) if result.stdout.strip() else 10.0

    frame_paths = []
    for i in range(num_frames):
        timestamp = (duration / (num_frames + 1)) * (i + 1)
        output_path = os.path.join(output_dir, f"frame_{i:03d}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
             "-vframes", "1", "-q:v", "2", output_path],
            capture_output=True
        )
        if os.path.exists(output_path):
            frame_paths.append(output_path)

    return frame_paths
