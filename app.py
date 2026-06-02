import io
from datetime import date, datetime
from flask import Flask, render_template, request, send_file
from scraper import fetch_usage_html, parse_daily_usage, to_csv

app = Flask(__name__)

LATEST = {
    "csv": None,
    "rows": None,
    "filename": None,
}


def _parse_billing_date(value: str):
    """Parse a YYYY-MM-DD string into a date. Returns None if blank or invalid."""
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    rows = None
    filename = None
    mode = "upload"

    if request.method == "POST":
        mode = request.form.get("mode", "upload")
        if mode == "live":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            url = request.form.get("target_url", "").strip()
            open_browser = request.form.get("open_browser") == "on"
            use_edge = request.form.get("use_edge") == "on"
            cookies_json = request.form.get("cookies_json", "").strip()

            if not url:
                error = "Please provide the daily usage URL."
            elif not cookies_json and (not username or not password):
                error = "Provide username/password or paste cookies JSON."
            else:
                billing_start = _parse_billing_date(request.form.get("billing_start", ""))
                try:
                    html = fetch_usage_html(
                        url,
                        username,
                        password,
                        headless=not open_browser,
                        use_edge=use_edge,
                        cookies_json=cookies_json or None,
                    )
                    daily = parse_daily_usage(html, billing_start_date=billing_start)
                    csv_text = to_csv(daily)

                    LATEST["csv"] = csv_text
                    LATEST["rows"] = daily
                    LATEST["filename"] = "starlink_live"

                    rows = daily
                    filename = url
                except Exception as exc:
                    error = f"Failed to scrape live page: {exc}"
        else:
            upload = request.files.get("html_file")
            if not upload or upload.filename == "":
                error = "Please upload a Starlink HTML file."
            else:
                try:
                    html = upload.read().decode("utf-8", errors="ignore")
                    billing_start = _parse_billing_date(request.form.get("billing_start", ""))
                    daily = parse_daily_usage(html, billing_start_date=billing_start)
                    csv_text = to_csv(daily)

                    LATEST["csv"] = csv_text
                    LATEST["rows"] = daily
                    LATEST["filename"] = upload.filename

                    rows = daily
                    filename = upload.filename
                except Exception as exc:
                    error = f"Failed to parse file: {exc}"

    return render_template(
        "index.html",
        error=error,
        rows=rows,
        filename=filename,
        has_csv=LATEST["csv"] is not None,
        mode=mode,
    )


@app.route("/download", methods=["GET"])
def download_csv():
    if not LATEST["csv"]:
        return ("No CSV is ready yet.", 400)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = LATEST["filename"] or "starlink_usage"
    safe_name = name.rsplit(".", 1)[0]
    filename = f"{safe_name}_{timestamp}.csv"

    csv_bytes = LATEST["csv"].encode("utf-8")
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(port=5055, debug=True)
