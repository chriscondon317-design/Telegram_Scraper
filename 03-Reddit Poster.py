import csv
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import praw
from praw.exceptions import APIException

# === Reddit API credentials (create app at https://www.reddit.com/prefs/apps) ===
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
USERNAME = "YOUR_REDDIT_USERNAME"
PASSWORD = "YOUR_REDDIT_PASSWORD"
USER_AGENT = "telegram-image-poster/2.0 by YOUR_REDDIT_USERNAME"

# === Input files (easiest workflow: maintain these two text files) ===
SUBREDDITS_FILE = "subreddits.txt"  # one subreddit per line (without r/)
CAPTIONS_FILE = "captions.txt"  # one caption per line

# Directory that contains images to post
IMAGE_DIR = "downloads"

# File to track already-posted images
POSTED_LOG = "posted_images.txt"

# Optional exact plan CSV: image_filename,subreddit,caption,post_at_utc(YYYY-mm-dd HH:MM)
SCHEDULE_CSV = "schedule.csv"
USE_SCHEDULE_CSV = False

# Timed posting mode (when not using schedule CSV)
POST_EVERY_MINUTES = 30
RANDOM_JITTER_SECONDS: Tuple[int, int] = (0, 300)
START_AT_UTC = ""  # e.g. "2026-05-03 14:00"; leave blank for immediate

# Optional dry run mode: set True to preview without posting
DRY_RUN = True

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass
class PostPlan:
    image_path: Path
    subreddit: str
    caption: str
    post_at: datetime


def read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def load_posted_images(log_path: Path) -> set:
    if not log_path.exists():
        return set()
    return {line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()}


def save_posted_image(log_path: Path, image_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{image_path.name}\n")


def discover_images(image_dir: Path, posted_images: set) -> List[Path]:
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir.resolve()}")

    images = [
        image_path
        for image_path in image_dir.iterdir()
        if image_path.is_file()
        and image_path.suffix.lower() in SUPPORTED_EXTENSIONS
        and image_path.name not in posted_images
    ]
    return sorted(images)


def create_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        username=USERNAME,
        password=PASSWORD,
        user_agent=USER_AGENT,
    )


def submit_image(reddit: praw.Reddit, subreddit: str, image_path: Path, caption: str, dry_run: bool) -> Optional[str]:
    if dry_run:
        print(f"[DRY RUN] r/{subreddit} <- {image_path.name} | {caption}")
        return "dry-run"

    try:
        submission = reddit.subreddit(subreddit).submit_image(title=caption.strip(), image_path=str(image_path))
        print(f"Posted to r/{subreddit}: https://reddit.com{submission.permalink}")
        return submission.id
    except APIException as exc:
        print(f"Reddit API error for {image_path.name} in r/{subreddit}: {exc}")
    except Exception as exc:
        print(f"Unexpected error for {image_path.name} in r/{subreddit}: {exc}")
    return None


def parse_start_time() -> datetime:
    if not START_AT_UTC.strip():
        return datetime.now(timezone.utc)
    return datetime.strptime(START_AT_UTC.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def build_plans_with_interval(images: List[Path], subreddits: List[str], captions: List[str]) -> List[PostPlan]:
    if not subreddits:
        raise ValueError("subreddits.txt is empty. Add at least one subreddit.")
    if not captions:
        raise ValueError("captions.txt is empty. Add at least one caption.")

    cursor = parse_start_time()
    plans: List[PostPlan] = []
    for image_path in images:
        plans.append(
            PostPlan(
                image_path=image_path,
                subreddit=random.choice(subreddits),
                caption=random.choice(captions),
                post_at=cursor,
            )
        )
        cursor += timedelta(minutes=POST_EVERY_MINUTES, seconds=random.randint(*RANDOM_JITTER_SECONDS))
    return plans


def build_plans_from_csv(base_dir: Path) -> List[PostPlan]:
    csv_path = base_dir / SCHEDULE_CSV
    if not csv_path.exists():
        raise FileNotFoundError(f"Schedule CSV not found: {csv_path}")

    plans: List[PostPlan] = []
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        required = {"image_filename", "subreddit", "caption", "post_at_utc"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"CSV must include headers: {sorted(required)}")

        for row in reader:
            image_path = Path(IMAGE_DIR) / row["image_filename"].strip()
            post_at = datetime.strptime(row["post_at_utc"].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            plans.append(
                PostPlan(
                    image_path=image_path,
                    subreddit=row["subreddit"].strip(),
                    caption=row["caption"].strip(),
                    post_at=post_at,
                )
            )
    plans.sort(key=lambda plan: plan.post_at)
    return plans


def run() -> None:
    base_dir = Path(".")
    posted = load_posted_images(base_dir / POSTED_LOG)
    reddit = create_reddit_client()

    if USE_SCHEDULE_CSV:
        plans = [plan for plan in build_plans_from_csv(base_dir) if plan.image_path.name not in posted]
    else:
        images = discover_images(Path(IMAGE_DIR), posted)
        subreddits = read_lines(base_dir / SUBREDDITS_FILE)
        captions = read_lines(base_dir / CAPTIONS_FILE)
        plans = build_plans_with_interval(images, subreddits, captions)

    if not plans:
        print("No scheduled posts to process.")
        return

    for index, plan in enumerate(plans, start=1):
        now = datetime.now(timezone.utc)
        if plan.post_at > now:
            sleep_seconds = int((plan.post_at - now).total_seconds())
            print(f"[{index}/{len(plans)}] Waiting {sleep_seconds}s until {plan.post_at.isoformat()} UTC")
            time.sleep(max(0, sleep_seconds))

        print(f"[{index}/{len(plans)}] Posting {plan.image_path.name} to r/{plan.subreddit}")
        result = submit_image(reddit, plan.subreddit, plan.image_path, plan.caption, DRY_RUN)
        if result is not None:
            save_posted_image(base_dir / POSTED_LOG, plan.image_path)


if __name__ == "__main__":
    run()
