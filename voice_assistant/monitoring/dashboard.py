import argparse
import statistics
import webbrowser
from datetime import datetime

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from voice_assistant.config import ROOT_DIR
from voice_assistant.monitoring.metrics import load_records

METRICS = [
    ("stt", "STT"),
    ("llm_first_token", "LLM first token"),
    ("llm_total", "LLM total"),
    ("tts", "TTS"),
    ("first_audio", "First audio"),
    ("total", "Total"),
]

STAGE_KEYS = ["stt", "llm_first_token", "llm_total", "tts"]
DEFAULT_OUT = ROOT_DIR / "data" / "dashboard.html"


def split_records(records):
    real = []
    fallback = 0
    cancelled = 0

    for record in records:
        if record.get("status") == "cancelled":
            cancelled += 1
        elif record.get("fallback"):
            fallback += 1
        elif record.get("status") == "done":
            real.append(record)

    return real, fallback, cancelled


def values_of(records, key):
    return [record.get("timings", {}).get(key) for record in records]


def clean(values):
    return [value for value in values if value is not None]


def summary_rows(records):
    names, counts, means, medians, mins, maxs = [], [], [], [], [], []

    for key, label in METRICS:
        data = clean(values_of(records, key))
        names.append(label)
        counts.append(len(data))
        if data:
            means.append(f"{statistics.mean(data):.2f}")
            medians.append(f"{statistics.median(data):.2f}")
            mins.append(f"{min(data):.2f}")
            maxs.append(f"{max(data):.2f}")
        else:
            means.append("-")
            medians.append("-")
            mins.append("-")
            maxs.append("-")

    return [names, counts, means, medians, mins, maxs]


def build_figure(records):
    turns = list(range(1, len(records) + 1))

    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[[{}, {}], [{}, {"type": "table"}]],
        subplot_titles=(
            "First audio vs Total (per turn)",
            "Stage timings (per turn)",
            "Distribution",
            "Summary (seconds)",
        ),
        vertical_spacing=0.2,
        horizontal_spacing=0.1,
    )

    for key, label in (("first_audio", "First audio"), ("total", "Total")):
        fig.add_trace(
            go.Scatter(
                x=turns,
                y=values_of(records, key),
                mode="lines+markers",
                name=label,
                connectgaps=False,
            ),
            row=1,
            col=1,
        )

    labels = dict(METRICS)
    for key in STAGE_KEYS:
        fig.add_trace(
            go.Bar(x=turns, y=values_of(records, key), name=labels[key]),
            row=1,
            col=2,
        )

    for key, label in METRICS:
        data = clean(values_of(records, key))
        if data:
            fig.add_trace(
                go.Box(y=data, name=label, showlegend=False, boxmean=True),
                row=2,
                col=1,
            )

    rows = summary_rows(records)
    fig.add_trace(
        go.Table(
            header=dict(
                values=["Metric", "Count", "Mean", "Median", "Min", "Max"],
                fill_color="#2a3f5f",
                font=dict(color="white"),
                align="left",
            ),
            cells=dict(values=rows, align="left"),
        ),
        row=2,
        col=2,
    )

    fig.update_xaxes(title_text="Turn #", row=1, col=1)
    fig.update_xaxes(title_text="Turn #", row=1, col=2)
    fig.update_yaxes(title_text="seconds", row=1, col=1)
    fig.update_yaxes(title_text="seconds", row=1, col=2)
    fig.update_yaxes(title_text="seconds", row=2, col=1)
    fig.update_layout(
        height=860,
        barmode="group",
        template="plotly_white",
        margin=dict(t=90, b=40, l=60, r=30),
        legend=dict(orientation="h", y=1.1),
    )
    return fig


def render_html(records, refresh_seconds=None):
    real, fallback, cancelled = split_records(records)
    refresh_tag = (
        f'<meta http-equiv="refresh" content="{refresh_seconds}">' if refresh_seconds else ""
    )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if real:
        body = build_figure(real).to_html(full_html=False, include_plotlyjs=True)
    else:
        body = (
            "<p style='font-size:18px'>Real turn data innum illa. "
            "Oru turn pannitu (example: <code>ws_client --text \"Hello\"</code>) "
            "page-a refresh pannu.</p>"
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Voice Assistant Dashboard</title>
{refresh_tag}
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #222; }}
.cards span {{ display: inline-block; margin-right: 12px; padding: 8px 14px;
  background: #eef2f7; border-radius: 6px; }}
.note {{ color: #666; font-size: 13px; margin-top: 8px; }}
</style>
</head>
<body>
<h2>Voice Assistant - Latency Dashboard</h2>
<div class="cards">
  <span>Real turns: <b>{len(real)}</b></span>
  <span>Fallback (empty transcript): <b>{fallback}</b></span>
  <span>Cancelled (interrupt): <b>{cancelled}</b></span>
</div>
<div class="note">Generated: {generated} | Fallback and cancelled turns charts/stats la serkkala.
REST <code>/voice</code> turns la "First audio" illa (gap-a theriyum).</div>
{body}
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Voice Assistant dashboard (static HTML)")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="output html path")
    parser.add_argument("--limit", type=int, default=100, help="last N records")
    parser.add_argument("--open", action="store_true", help="browser la open pannu")
    args = parser.parse_args()

    records = load_records(limit=args.limit)
    html = render_html(records)

    from pathlib import Path

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    real, fallback, cancelled = split_records(records)
    print(f"Records: {len(records)} | real={len(real)} | fallback={fallback} | cancelled={cancelled}")
    print(f"Saved: {out_path}")

    if args.open:
        webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()