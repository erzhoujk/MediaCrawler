# -*- coding: utf-8 -*-
"""Run a Xiaohongshu creator -> comments -> commenter-posts workflow.

The workflow uses the existing web crawler only:
1. Crawl one or more creator homepages and their post comments.
2. Extract commenter user IDs from those comments.
3. Crawl each commenter's public homepage posts.
4. Build one grouped JSON result.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Iterable


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
XHS_PROFILE_PREFIX = "https://www.xiaohongshu.com/user/profile/"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _split_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        for item in re.split(r"[\n,]+", value):
            item = item.strip()
            if item:
                result.append(item)
    return result


def _parse_user_id(value: str) -> str:
    value = value.strip()
    match = re.search(r"/user/profile/([^/?#]+)", value)
    if match:
        return match.group(1)
    return value


def _homepage(user_id: str) -> str:
    return f"{XHS_PROFILE_PREFIX}{user_id}"


def _read_jsonl_files(base_dir: pathlib.Path, pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(base_dir.rglob(pattern)):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _dedupe(rows: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get(key) or "")
        if not row_key or row_key in seen:
            continue
        seen.add(row_key)
        result.append(row)
    return result


def _compact_post(post: dict[str, Any]) -> dict[str, Any]:
    return {
        "note_id": post.get("note_id"),
        "type": post.get("type"),
        "title": post.get("title"),
        "desc": post.get("desc"),
        "note_url": post.get("note_url"),
        "time": post.get("time"),
        "last_update_time": post.get("last_update_time"),
        "tag_list": post.get("tag_list"),
        "liked_count": post.get("liked_count"),
        "collected_count": post.get("collected_count"),
        "comment_count": post.get("comment_count"),
        "share_count": post.get("share_count"),
    }


def _compact_comment(
    comment: dict[str, Any],
    commenter_posts_by_user: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    commenter_id = str(comment.get("user_id") or "")
    return {
        "comment_id": comment.get("comment_id"),
        "content": comment.get("content"),
        "create_time": comment.get("create_time"),
        "ip_location": comment.get("ip_location"),
        "like_count": comment.get("like_count"),
        "parent_comment_id": comment.get("parent_comment_id"),
        "sub_comment_count": comment.get("sub_comment_count"),
        "commenter": {
            "user_id": commenter_id,
            "nickname": comment.get("nickname"),
            "avatar": comment.get("avatar"),
            "homepage": _homepage(commenter_id) if commenter_id else "",
            "posts": commenter_posts_by_user.get(commenter_id, []),
        },
    }


def _run_crawler(
    *,
    creator_inputs: list[str],
    save_data_path: pathlib.Path,
    login_type: str,
    headless: bool,
    get_comments: bool,
    get_sub_comments: bool,
    max_notes: int,
    max_comments_per_note: int,
    max_concurrency: int,
    cookies: str,
) -> None:
    cmd = [
        sys.executable,
        "main.py",
        "--platform",
        "xhs",
        "--lt",
        login_type,
        "--type",
        "creator",
        "--creator_id",
        ",".join(creator_inputs),
        "--get_comment",
        _bool_text(get_comments),
        "--get_sub_comment",
        _bool_text(get_sub_comments),
        "--crawler_max_notes_count",
        str(max_notes),
        "--max_comments_count_singlenotes",
        str(max_comments_per_note),
        "--max_concurrency_num",
        str(max_concurrency),
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(save_data_path),
        "--headless",
        _bool_text(headless),
    ]
    if cookies:
        cmd.extend(["--cookies", cookies])

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def _chunk(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def build_result(
    *,
    input_creators: list[str],
    seed_posts: list[dict[str, Any]],
    seed_comments: list[dict[str, Any]],
    commenter_posts: list[dict[str, Any]],
    raw_dirs: dict[str, str],
    settings: dict[str, Any],
) -> dict[str, Any]:
    input_user_ids = [_parse_user_id(item) for item in input_creators]

    posts_by_creator: dict[str, list[dict[str, Any]]] = {}
    for post in _dedupe(seed_posts, "note_id"):
        creator_id = str(post.get("user_id") or "")
        posts_by_creator.setdefault(creator_id, []).append(post)

    comments_by_note: dict[str, list[dict[str, Any]]] = {}
    for comment in _dedupe(seed_comments, "comment_id"):
        note_id = str(comment.get("note_id") or "")
        comments_by_note.setdefault(note_id, []).append(comment)

    commenter_posts_by_user: dict[str, list[dict[str, Any]]] = {}
    for post in _dedupe(commenter_posts, "note_id"):
        user_id = str(post.get("user_id") or "")
        commenter_posts_by_user.setdefault(user_id, []).append(_compact_post(post))
    for post in _dedupe(seed_posts, "note_id"):
        user_id = str(post.get("user_id") or "")
        if user_id in input_user_ids:
            commenter_posts_by_user.setdefault(user_id, []).append(_compact_post(post))

    creators: dict[str, dict[str, Any]] = {}
    for creator_id in input_user_ids:
        creator_posts = posts_by_creator.get(creator_id, [])
        nickname = next((post.get("nickname") for post in creator_posts if post.get("nickname")), "")
        creators[creator_id] = {
            "input": next((item for item in input_creators if _parse_user_id(item) == creator_id), creator_id),
            "user_id": creator_id,
            "nickname": nickname,
            "homepage": _homepage(creator_id),
            "posts": [],
        }

        for post in creator_posts:
            note_id = str(post.get("note_id") or "")
            post_item = _compact_post(post)
            post_item["comments"] = [
                _compact_comment(comment, commenter_posts_by_user)
                for comment in comments_by_note.get(note_id, [])
            ]
            creators[creator_id]["posts"].append(post_item)

    all_commenter_ids = {
        str(comment.get("user_id") or "")
        for comment in seed_comments
        if comment.get("user_id")
    }
    all_commenter_ids.discard("")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "settings": settings,
        "raw_dirs": raw_dirs,
        "summary": {
            "input_creator_count": len(input_user_ids),
            "seed_post_count": len(_dedupe(seed_posts, "note_id")),
            "comment_count": len(_dedupe(seed_comments, "comment_id")),
            "unique_commenter_count": len(all_commenter_ids),
            "commenter_post_count": len(_dedupe(commenter_posts, "note_id")),
        },
        "creators": creators,
        "commenter_posts_by_user": {
            user_id: {
                "user_id": user_id,
                "homepage": _homepage(user_id),
                "posts": posts,
            }
            for user_id, posts in sorted(commenter_posts_by_user.items())
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl XHS creators, their post comments, and commenters' public homepage posts."
    )
    parser.add_argument(
        "--creator",
        action="append",
        default=[],
        help="Creator URL or user_id. Can be repeated or comma-separated.",
    )
    parser.add_argument(
        "--creator-file",
        help="Text file containing creator URLs/user IDs, one per line or comma-separated.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output directory. Defaults to data/xhs_creator_commenter_flow/<timestamp>.",
    )
    parser.add_argument(
        "--seed-raw-dir",
        default="",
        help="Read seed creator raw JSONL files from this directory instead of output-dir/seed_creators.",
    )
    parser.add_argument(
        "--commenter-raw-dir",
        default="",
        help="Read commenter raw JSONL files from this directory instead of output-dir/commenters.",
    )
    parser.add_argument("--login-type", default="qrcode", choices=["qrcode", "phone", "cookie"])
    parser.add_argument("--cookies", default="")
    parser.add_argument("--headless", default="true", choices=["true", "false"])
    parser.add_argument("--max-creator-notes", type=int, default=15)
    parser.add_argument("--max-comments-per-note", type=int, default=10)
    parser.add_argument("--max-commenter-notes", type=int, default=3)
    parser.add_argument("--max-commenters", type=int, default=100)
    parser.add_argument("--commenter-chunk-size", type=int, default=20)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--get-sub-comments", action="store_true")
    parser.add_argument(
        "--include-seed-creators-as-commenters",
        action="store_true",
        help="Also crawl seed creators again in the commenter-homepage stage if they commented.",
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Only rebuild result.json from existing raw files under output-dir.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    creator_values = list(args.creator)
    if args.creator_file:
        creator_values.append(pathlib.Path(args.creator_file).read_text(encoding="utf-8"))
    input_creators = _split_values(creator_values)
    if not input_creators:
        raise SystemExit("At least one --creator or --creator-file value is required.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        pathlib.Path(args.output_dir)
        if args.output_dir
        else PROJECT_ROOT / "data" / "xhs_creator_commenter_flow" / timestamp
    )
    output_dir = output_dir.resolve()
    seed_dir = output_dir / "seed_creators"
    commenters_dir = output_dir / "commenters"
    seed_read_dir = pathlib.Path(args.seed_raw_dir).resolve() if args.seed_raw_dir else seed_dir
    commenters_read_dir = (
        pathlib.Path(args.commenter_raw_dir).resolve()
        if args.commenter_raw_dir
        else commenters_dir
    )
    result_path = output_dir / "result.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_user_ids = {_parse_user_id(item) for item in input_creators}
    headless = args.headless.lower() == "true"

    if not args.skip_crawl:
        _run_crawler(
            creator_inputs=input_creators,
            save_data_path=seed_dir,
            login_type=args.login_type,
            headless=headless,
            get_comments=True,
            get_sub_comments=args.get_sub_comments,
            max_notes=args.max_creator_notes,
            max_comments_per_note=args.max_comments_per_note,
            max_concurrency=args.max_concurrency,
            cookies=args.cookies,
        )

    seed_posts = _read_jsonl_files(seed_read_dir, "creator_contents_*.jsonl")
    seed_comments = _read_jsonl_files(seed_read_dir, "creator_comments_*.jsonl")

    commenter_ids = sorted({
        str(comment.get("user_id") or "")
        for comment in seed_comments
        if comment.get("user_id")
    })
    if not args.include_seed_creators_as_commenters:
        commenter_ids = [user_id for user_id in commenter_ids if user_id not in seed_user_ids]
    if args.max_commenters >= 0:
        commenter_ids = commenter_ids[:args.max_commenters]

    if not args.skip_crawl and commenter_ids:
        for index, ids in enumerate(_chunk(commenter_ids, args.commenter_chunk_size), start=1):
            chunk_dir = commenters_dir / f"chunk_{index:03d}"
            _run_crawler(
                creator_inputs=ids,
                save_data_path=chunk_dir,
                login_type=args.login_type,
                headless=headless,
                get_comments=False,
                get_sub_comments=False,
                max_notes=args.max_commenter_notes,
                max_comments_per_note=0,
                max_concurrency=args.max_concurrency,
                cookies=args.cookies,
            )

    commenter_posts = _read_jsonl_files(commenters_read_dir, "creator_contents_*.jsonl")
    settings = {
        "max_creator_notes": args.max_creator_notes,
        "max_comments_per_note": args.max_comments_per_note,
        "max_commenter_notes": args.max_commenter_notes,
        "max_commenters": args.max_commenters,
        "get_sub_comments": args.get_sub_comments,
        "web_only": True,
    }
    result = build_result(
        input_creators=input_creators,
        seed_posts=seed_posts,
        seed_comments=seed_comments,
        commenter_posts=commenter_posts,
        raw_dirs={
            "seed_creators": str(seed_read_dir),
            "commenters": str(commenters_read_dir),
        },
        settings=settings,
    )

    with result_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"RESULT: {result_path}")


if __name__ == "__main__":
    main()
