import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import praw
from praw.exceptions import APIException


# === Reddit API credentials (create app at https://www.reddit.com/prefs/apps) ===
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
USERNAME = "YOUR_REDDIT_USERNAME"
PASSWORD = "YOUR_REDDIT_PASSWORD"
USER_AGENT = "telegram-image-poster/1.0 by YOUR_REDDIT_USERNAME"


# === Posting configuration ===
SUBREDDITS = [
    "test",
    # "pics",
    # "wallpapers",
]

# Captions to pair with images. The script picks one at random for each post.
CAPTIONS = [
    "Fresh upload from my collection 📸",
    "Hope you enjoy this one!",
    "Another image drop ✨",
]

# Directory that contains images to post
IMAGE_DIR = "downloads"

# File to track already-posted images
POSTED_LOG = "posted_images.txt"

# Post timing controls
POST_INTERVAL_SECONDS = 60 * 30  # 30 minutes
RANDOM_DELAY_RANGE: Tuple[int, int] = (0, 300)  # additional 0-5 minutes

# Optional dry run mode: set True to preview without posting
DRY_RUN = True


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def load_posted_images(log_path: Path) -> set:
    if not log_path.exists():
        return set()
    return {line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()}


def save_posted_image(log_path: Path, image_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{image_path.name}\n")


def discover_images(image_dir: Path, posted_images: set) -> List[Path]:
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir.resolve()}")

    images = [
        p
        for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and p.name not in posted_images
    ]
    images.sort()
    return images


def create_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        username=USERNAME,
        password=PASSWORD,
        user_agent=USER_AGENT,
    )


def submit_image(
    reddit: praw.Reddit,
    subreddit_name: str,
    image_path: Path,
    caption: str,
    dry_run: bool = False,
) -> Optional[str]:
    title = caption.strip()

    if dry_run:
        print(f"[DRY RUN] r/{subreddit_name} <- {image_path.name} | title: {title}")
        return "dry-run"

    try:
        submission = reddit.subreddit(subreddit_name).submit_image(title=title, image_path=str(image_path))
        print(f"Posted to r/{subreddit_name}: https://reddit.com{submission.permalink}")
        return submission.id
    except APIException as exc:
        print(f"Reddit API error while posting {image_path.name} to r/{subreddit_name}: {exc}")
    except Exception as exc:
        print(f"Unexpected error while posting {image_path.name} to r/{subreddit_name}: {exc}")

    return None


def choose_target(subreddits: List[str], captions: List[str]) -> Dict[str, str]:
    return {
        "subreddit": random.choice(subreddits),
        "caption": random.choice(captions),
    }


def run() -> None:
    if not SUBREDDITS:
        raise ValueError("SUBREDDITS list is empty. Add at least one subreddit.")
    if not CAPTIONS:
        raise ValueError("CAPTIONS list is empty. Add at least one caption.")

    image_dir = Path(IMAGE_DIR)
    posted_log = Path(POSTED_LOG)

    posted_images = load_posted_images(posted_log)
    images = discover_images(image_dir, posted_images)

    if not images:
        print("No new images available to post.")
        return

    reddit = create_reddit_client()

    for idx, image_path in enumerate(images, start=1):
        target = choose_target(SUBREDDITS, CAPTIONS)
        subreddit_name = target["subreddit"]
        caption = target["caption"]

        print(f"[{idx}/{len(images)}] Preparing post for {image_path.name}...")
        result = submit_image(reddit, subreddit_name, image_path, caption, dry_run=DRY_RUN)

        if result is not None:
            save_posted_image(posted_log, image_path)

        if idx < len(images):
            delay = POST_INTERVAL_SECONDS + random.randint(*RANDOM_DELAY_RANGE)
            print(f"Sleeping for {delay} seconds before next post...")
            time.sleep(delay)


if __name__ == "__main__":
    run()
