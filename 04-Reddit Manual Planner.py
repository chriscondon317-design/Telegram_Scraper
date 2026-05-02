import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote_plus

import streamlit as st

st.set_page_config(page_title="Reddit Manual Planner", layout="wide")

TITLES_FILE = Path("title_variants.txt")
SUBREDDITS_FILE = Path("subreddits.txt")


@dataclass
class PlanRow:
    subreddit: str
    title: str
    open_url: str


def parse_title_variants(path: Path) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    current_group = None

    if not path.exists():
        return groups

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1].strip()
            groups.setdefault(current_group, [])
            continue
        if current_group is None:
            continue
        groups[current_group].append(line)
    return groups


def read_subreddits(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [ln.strip().replace("r/", "") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def compose_url(subreddit: str, title: str) -> str:
    # Reddit supports pre-filling title via query param.
    # Browsers do NOT allow pre-filling an image file for security reasons.
    return f"https://www.reddit.com/r/{subreddit}/submit?title={quote_plus(title)}&type=IMAGE"


def build_plan(subreddits: List[str], selected_groups: List[str], variants: Dict[str, List[str]]) -> List[PlanRow]:
    rows: List[PlanRow] = []
    for subreddit in subreddits:
        for group in selected_groups:
            choices = variants.get(group, [])
            if not choices:
                continue
            title = random.choice(choices)
            rows.append(PlanRow(subreddit=subreddit, title=title, open_url=compose_url(subreddit, title)))
    return rows


st.title("Reddit Manual Posting Planner")
st.caption("Upload image, pick title groups, pick subreddits, generate tappable checklist.")

uploaded = st.file_uploader("1) Upload image", type=["png", "jpg", "jpeg"])
variants = parse_title_variants(TITLES_FILE)
subreddit_options = read_subreddits(SUBREDDITS_FILE)

if not variants:
    st.warning("No title variants found. Create title_variants.txt (example in README).")
if not subreddit_options:
    st.warning("No subreddits found. Create subreddits.txt with one subreddit per line.")

selected_groups = st.multiselect("2) Pick title groups", options=sorted(variants.keys()))
selected_subreddits = st.multiselect("3) Pick subreddits", options=subreddit_options)

col1, col2 = st.columns([1, 1])
with col1:
    generate = st.button("Generate Plan", type="primary")
with col2:
    reshuffle = st.button("Reshuffle Titles")

if reshuffle:
    st.session_state.pop("plan_rows", None)

if generate:
    st.session_state["plan_rows"] = build_plan(selected_subreddits, selected_groups, variants)

rows: List[PlanRow] = st.session_state.get("plan_rows", [])

if rows:
    st.subheader(f"Plan ({len(rows)} rows)")
    if uploaded is not None:
        st.image(uploaded, width=220, caption="Use this image when the Reddit submit page opens")

    for i, row in enumerate(rows, start=1):
        with st.container(border=True):
            st.markdown(f"**#{i} r/{row.subreddit}**")
            st.write(row.title)
            st.code(row.title, language="text")
            st.link_button("Open Reddit compose", row.open_url, use_container_width=True)

st.info(
    "Reddit can prefill the title in the compose URL, but cannot prefill local image files automatically. "
    "After opening, attach the uploaded image manually and submit."
)
