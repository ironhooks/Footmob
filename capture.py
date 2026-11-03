
import asyncio
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from playwright.async_api import async_playwright

OUTPUT = Path("captures")
OUTPUT.mkdir(exist_ok=True)

TARGET_URL = os.getenv(
    "TARGET_URL",
    "https://www.fotmob.com/"
)

WAIT_SECONDS = min(
    60,
    max(1, int(os.getenv("WAIT_SECONDS", "20")))
)

MAX_RESPONSES = 150
MAX_BODY_SIZE = 5 * 1024 * 1024

results = []
counter = 0
lock = asyncio.Lock()


def safe_url(raw_url):
    try:
        parts = urlsplit(raw_url)

        params = [
            (key, "[REDACTED]" if re.search(
                r"token|key|auth|session|secret|cookie",
                key,
                re.I
            ) else value)
            for key, value in parse_qsl(
                parts.query,
                keep_blank_values=True
            )
        ]

        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(params),
            ""
        ))
    except Exception:
        return "[INVALID URL]"


async def capture_response(response):
    global counter

    try:
        request = response.request
        headers = await response.all_headers()

        content_type = headers.get("content-type", "")
        resource_type = request.resource_type

        if (
            "json" not in content_type.lower()
            and resource_type not in ("xhr", "fetch")
        ):
            return

        if response.status == 204:
            return

        body = await response.body()

        if len(body) > MAX_BODY_SIZE:
            return

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return

        async with lock:
            if counter >= MAX_RESPONSES:
                return

            counter += 1
            number = counter

        filename = f"api_{number:03}.json"

        record = {
            "id": number,
            "url": safe_url(response.url),
            "method": request.method,
            "status": response.status,
            "resource_type": resource_type,
            "content_type": content_type,
            "captured_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "response": data
        }

        (OUTPUT / filename).write_text(
            json.dumps(
                record,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        results.append({
            "id": number,
            "file": filename,
            "url": record["url"],
            "method": record["method"],
            "status": record["status"],
            "resource_type": resource_type
        })

        print(
            f"[CAPTURED] {request.method} "
            f"{response.status} {record['url']}"
        )

    except Exception as error:
        print(f"[RESPONSE ERROR] {error}")


async def main():
    print("Starting Python Playwright Chromium")
    print("Target:", TARGET_URL)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1366,
                "height": 768
            }
        )

        page = await context.new_page()

        page.on(
            "response",
            lambda response: asyncio.create_task(
                capture_response(response)
            )
        )

        try:
            await page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print("Page loaded:", page.url)

            await asyncio.sleep(WAIT_SECONDS)

            # Allow pending response handlers to finish.
            await asyncio.sleep(2)

        except Exception as error:
            print("Navigation error:", error)

            (OUTPUT / "error.txt").write_text(
                str(error),
                encoding="utf-8"
            )

        finally:
            await context.close()
            await browser.close()

    report = {
        "target": safe_url(TARGET_URL),
        "captured_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_captured": counter,
        "responses": sorted(
            results,
            key=lambda item: item["id"]
        )
    }

    (OUTPUT / "network-report.json").write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("=" * 40)
    print("CAPTURE COMPLETED")
    print("Total JSON responses:", counter)
    print("Output:", OUTPUT.resolve())


if __name__ == "__main__":
    asyncio.run(main())
