# -*- coding: utf-8 -*-
"""Probe Xiaohongshu follower/following network endpoints.

This script is intentionally diagnostic: it uses the saved Playwright login
state, opens a public profile page, clicks visible "fans/follows" UI affordances,
and records related public web API responses. It does not bypass permissions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
from typing import Any
from urllib.parse import quote

from playwright.async_api import Page, Response, async_playwright

sys.path.insert(0, os.getcwd())

from media_platform.xhs.playwright_sign import sign_with_xhshow
from tools.httpx_util import make_async_client


RELATIONSHIP_HINTS = (
    "follow",
    "fans",
    "fan",
    "relation",
    "user",
    "profile",
    "connections",
    "friend",
)


def _json_preview(value: Any, limit: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text[:limit]


async def _safe_click(page: Page, label: str) -> bool:
    candidates = [
        page.get_by_text(label, exact=True),
        page.locator(f"text={label}"),
        page.locator(f"span:has-text('{label}')"),
        page.locator(f"div:has-text('{label}')"),
    ]
    for locator in candidates:
        try:
            count = await locator.count()
            if count <= 0:
                continue
            await locator.first.click(timeout=3000)
            await page.wait_for_timeout(5000)
            return True
        except Exception:
            continue
    return False


async def _scroll_dialog_or_page(page: Page) -> None:
    for _ in range(3):
        try:
            await page.mouse.wheel(0, 900)
        except Exception:
            pass
        try:
            await page.evaluate(
                """
                () => {
                  const candidates = [...document.querySelectorAll('*')]
                    .filter(el => el.scrollHeight > el.clientHeight + 50)
                    .sort((a, b) => b.scrollHeight - a.scrollHeight);
                  for (const el of candidates.slice(0, 4)) {
                    el.scrollTop += 900;
                  }
                  window.scrollBy(0, 900);
                }
                """
            )
        except Exception:
            pass
        await page.wait_for_timeout(2500)


def _build_query_string(params: dict[str, Any]) -> str:
    parts = []
    for key, value in params.items():
        value_str = str(value) if value is not None else ""
        parts.append(f"{key}={quote(value_str, safe=',')}")
    return "&".join(parts)


async def _probe_candidate_apis(context, user_id: str, output: str) -> None:
    cookies = await context.cookies(["https://www.xiaohongshu.com"])
    cookie_str = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)
    base_headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://www.xiaohongshu.com",
        "pragma": "no-cache",
        "referer": "https://www.xiaohongshu.com/",
        "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
    }
    candidates = [
        "/api/sns/web/v1/user/fans",
        "/api/sns/web/v1/user/follows",
        "/api/sns/web/v1/user/following",
        "/api/sns/web/v1/user/followings",
        "/api/sns/web/v1/user/follower",
        "/api/sns/web/v1/user/followers",
        "/api/sns/web/v2/user/fans",
        "/api/sns/web/v2/user/follows",
        "/api/sns/web/v2/user/following",
        "/api/sns/web/v2/user/followings",
        "/api/sns/web/v2/user/follower",
        "/api/sns/web/v2/user/followers",
        "/api/sns/web/v1/user/relation/fans",
        "/api/sns/web/v1/user/relation/follows",
        "/api/sns/web/v1/relation/fans",
        "/api/sns/web/v1/relation/follows",
    ]
    param_shapes = [
        {"user_id": user_id, "cursor": "", "num": 20},
        {"target_user_id": user_id, "cursor": "", "num": 20},
        {"user_id": user_id, "cursor": "", "page_size": 20},
    ]
    async with make_async_client(proxy=None) as client:
        for uri in candidates:
            for params in param_shapes:
                signs = sign_with_xhshow(
                    uri=uri,
                    data=params,
                    cookie_str=cookie_str,
                    method="GET",
                )
                headers = {**base_headers, **signs}
                url = f"https://edith.xiaohongshu.com{uri}?{_build_query_string(params)}"
                record: dict[str, Any] = {"kind": "candidate_api", "url": url}
                try:
                    response = await client.get(url, headers=headers, timeout=20)
                    record["status"] = response.status_code
                    record["content_type"] = response.headers.get("content-type", "")
                    try:
                        data = response.json()
                        record["json_preview"] = _json_preview(data)
                    except Exception:
                        record["text_preview"] = response.text[:800]
                except Exception as exc:
                    record["error"] = repr(exc)
                print(json.dumps(record, ensure_ascii=False), flush=True)
                with open(output, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                await asyncio.sleep(0.5)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-url", required=True)
    parser.add_argument(
        "--user-data-dir",
        default=os.path.join(os.getcwd(), "browser_data", "xhs_user_data_dir"),
    )
    parser.add_argument("--headless", default="true")
    parser.add_argument(
        "--mobile-web",
        action="store_true",
        help="Use a mobile browser UA/viewport. This probes mobile web, not native app APIs.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join("data", "probe", f"xhs_relationships_{int(time.time())}.jsonl"),
    )
    args = parser.parse_args()

    pathlib.Path(os.path.dirname(args.output)).mkdir(parents=True, exist_ok=True)
    headless = args.headless.lower() in {"1", "true", "t", "yes", "y"}

    seen: set[str] = set()

    async with async_playwright() as p:
        browser_options: dict[str, Any] = {
            "user_data_dir": args.user_data_dir,
            "headless": headless,
            "accept_downloads": True,
            "viewport": {"width": 1440, "height": 1000},
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if args.mobile_web:
            iphone = p.devices["iPhone 13"]
            browser_options.update(
                {
                    "viewport": iphone["viewport"],
                    "user_agent": iphone["user_agent"],
                    "device_scale_factor": iphone["device_scale_factor"],
                    "is_mobile": iphone["is_mobile"],
                    "has_touch": iphone["has_touch"],
                }
            )
        context = await p.chromium.launch_persistent_context(**browser_options)
        stealth_path = os.path.join(os.getcwd(), "libs", "stealth.min.js")
        if os.path.exists(stealth_path):
            await context.add_init_script(path=stealth_path)

        page = await context.new_page()

        async def on_response(response: Response) -> None:
            url = response.url
            url_lower = url.lower()
            if "xiaohongshu.com" not in url_lower and "xhscdn.com" not in url_lower:
                return
            if not any(hint in url_lower for hint in RELATIONSHIP_HINTS):
                return
            if url in seen:
                return
            seen.add(url)
            record: dict[str, Any] = {
                "status": response.status,
                "url": url,
                "content_type": response.headers.get("content-type", ""),
            }
            try:
                data = await response.json()
                record["json_keys"] = list(data.keys()) if isinstance(data, dict) else []
                record["json_preview"] = _json_preview(data)
            except Exception:
                try:
                    text = await response.text()
                    record["text_preview"] = text[:1200]
                except Exception:
                    record["text_preview"] = ""

            print(json.dumps(record, ensure_ascii=False), flush=True)
            with open(args.output, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        page.on("response", lambda response: asyncio.create_task(on_response(response)))

        await page.goto(args.profile_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(7000)
        print("PAGE_TEXT_PREVIEW:", (await page.locator("body").inner_text(timeout=10000))[:1000])

        user_id = args.profile_url.rstrip("/").split("/user/profile/")[-1].split("?")[0]

        for label in ("粉丝", "关注"):
            clicked = await _safe_click(page, label)
            print(f"CLICK_{label}: {clicked}")
            await _scroll_dialog_or_page(page)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1500)

        await _probe_candidate_apis(context, user_id=user_id, output=args.output)

        await context.close()
        print(f"OUTPUT: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    asyncio.run(main())
