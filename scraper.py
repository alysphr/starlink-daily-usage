import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class DailyUsage:
    day_index: int
    date: str
    day_of_week: str
    month: str
    usage_gb: float
    pct_change_prev_day: str


_BAR_RECT_REGEX = re.compile(
    r"<rect(?=[^>]*class=\"[^\"]*MuiBarElement-series-y_0[^\"]*\")[^>]*>",
    re.IGNORECASE,
)
_TICK_LABEL_REGEX = re.compile(
    r"MuiChartsAxis-tickLabel[^>]*>.*?<tspan[^>]*>([^<]*)</tspan>",
    re.IGNORECASE | re.DOTALL,
)


def _extract_bars(html: str) -> List[dict]:
    bars = []
    for match in _BAR_RECT_REGEX.finditer(html):
        tag = match.group(0)
        x = _attr_as_float(tag, "x")
        y = _attr_as_float(tag, "y")
        height = _attr_as_float(tag, "height")
        if x is None or y is None or height is None:
            continue
        bars.append({"x": x, "y": y, "height": height})
    return bars


def _attr_as_float(tag: str, name: str):
    attr_match = re.search(rf"\s{name}=\"([0-9.]+)\"", tag)
    if not attr_match:
        return None
    return float(attr_match.group(1))


def _extract_axis_max_gb(html: str) -> float:
    labels = _TICK_LABEL_REGEX.findall(html)
    values = []
    for label in labels:
        label = label.strip()
        if "GB" not in label:
            continue
        number_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", label)
        if number_match:
            values.append(float(number_match.group(1)))
    return max(values) if values else 20.0


def parse_daily_usage(
    html: str,
    reference_date: Optional[date] = None,
) -> List["DailyUsage"]:
    bars = _extract_bars(html)
    if not bars:
        raise ValueError("No daily usage bars found in HTML.")

    bars.sort(key=lambda item: item["x"])

    min_y = min(bar["y"] for bar in bars)
    max_bottom = max(bar["y"] + bar["height"] for bar in bars)
    chart_height = max_bottom - min_y
    if chart_height <= 0:
        raise ValueError("Chart height could not be determined.")

    max_gb = _extract_axis_max_gb(html)

    # Use today as the billing-month anchor when no reference date is given.
    # Day 1 = the 1st of that month; Day N = the Nth of that month.
    if reference_date is None:
        reference_date = date.today()
    month_start = date(reference_date.year, reference_date.month, 1)

    usages: List[float] = []
    for bar in bars:
        usages.append(round((bar["height"] / chart_height) * max_gb, 2))

    daily = []
    for index, usage in enumerate(usages, start=1):
        day_date = month_start + timedelta(days=index - 1)
        if index == 1 or usages[index - 2] == 0:
            pct = "NaN"
        else:
            prev = usages[index - 2]
            pct = f"{((usage - prev) / prev * 100):.4f}"

        daily.append(
            DailyUsage(
                day_index=index,
                date=day_date.strftime("%Y-%m-%d"),
                day_of_week=day_date.strftime("%A"),
                month=day_date.strftime("%B"),
                usage_gb=usage,
                pct_change_prev_day=pct,
            )
        )

    return daily


def fetch_usage_html(
    url: str,
    username: str,
    password: str,
    headless: bool,
    use_edge: bool,
    cookies_json: Optional[str] = None,
) -> str:
    with sync_playwright() as playwright:
        launch_kwargs = {"headless": headless}
        if use_edge:
            launch_kwargs["channel"] = "msedge"

        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context()
        if cookies_json:
            cookies = _parse_cookie_json(cookies_json)
            context.add_cookies(cookies)

        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded")

        if not cookies_json:
            try:
                email_selector = (
                    "input[type='email'], input[name='email'], input[autocomplete='username']"
                )
                page.wait_for_selector(email_selector, timeout=8000)
                page.fill(email_selector, username)

                password_selector = (
                    "input[type='password'], input[autocomplete='current-password']"
                )
                page.fill(password_selector, password)

                submit_selector = (
                    "button[type='submit'], button:has-text('Sign in'), "
                    "button:has-text('Sign In'), button:has-text('Log in'), "
                    "button:has-text('Log In')"
                )
                page.click(submit_selector)

                page.wait_for_load_state("networkidle", timeout=20000)
            except PlaywrightTimeoutError:
                pass

        page.goto(url, wait_until="networkidle")

        try:
            page.wait_for_selector(
                "svg .MuiBarElement-series-y_0",
                state="attached",
                timeout=40000,
            )
        except PlaywrightTimeoutError as exc:
            raise PlaywrightTimeoutError(
                "Chart bars not found. Try enabling 'Open browser window' "
                "and complete the login manually, then submit again."
            ) from exc

        html = page.content()
        browser.close()
        return html


def _parse_cookie_json(cookie_text: str) -> List[dict]:
    try:
        payload = json.loads(cookie_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Cookie JSON is not valid JSON.") from exc

    cookies = payload.get("cookies") if isinstance(payload, dict) else payload
    if not isinstance(cookies, list):
        raise ValueError("Cookie JSON must be a list or contain a 'cookies' list.")

    normalized = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue

        item = {
            "name": cookie.get("name"),
            "value": cookie.get("value"),
            "domain": cookie.get("domain"),
            "path": cookie.get("path", "/"),
            "secure": bool(cookie.get("secure", False)),
            "httpOnly": bool(cookie.get("httpOnly", False)),
        }

        if cookie.get("url") and not item["domain"]:
            item["url"] = cookie.get("url")

        expires = cookie.get("expires")
        if expires is None:
            expires = cookie.get("expirationDate")
        if isinstance(expires, (int, float)):
            item["expires"] = float(expires)

        same_site = cookie.get("sameSite")
        if isinstance(same_site, str):
            same_site = same_site.strip().lower()
            if same_site in {"lax", "strict", "none"}:
                item["sameSite"] = same_site.capitalize()

        if not item["name"] or item["value"] is None:
            continue

        normalized.append(item)

    if not normalized:
        raise ValueError("No usable cookies were found in the JSON.")

    return normalized


def to_csv(daily: List[DailyUsage]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["day_index", "date", "day_of_week", "month", "usage_gb", "pct_change_prev_day"])
    for entry in daily:
        writer.writerow([
            entry.day_index,
            entry.date,
            entry.day_of_week,
            entry.month,
            f"{entry.usage_gb:.2f}",
            entry.pct_change_prev_day,
        ])
    return buffer.getvalue()
