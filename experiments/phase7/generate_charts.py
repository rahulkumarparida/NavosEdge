"""
Generate reproducible SVG charts from experiments/phase7/results/phase7_experiment_results.json.
Zero external plotting dependencies; uses only measured experiment outputs.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List

RESULTS_FILE = Path(__file__).resolve().parent / "results" / "phase7_experiment_results.json"
CHARTS_DIR = Path(__file__).resolve().parent / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def svg_header(width: int, height: int, title: str, subtitle: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" style="font-family:Segoe UI,Arial,sans-serif;background:#ffffff;">\n'
        f'<rect width="{width}" height="{height}" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>\n'
        f'<text x="24" y="30" font-size="16" font-weight="700" fill="#0f172a">{html.escape(title)}</text>\n'
        f'<text x="24" y="50" font-size="11" fill="#475569">{html.escape(subtitle)}</text>\n'
    )


def build_confusion_matrix_svg(gasnet: Dict[str, Any]) -> None:
    labels = gasnet["labels"]
    cm = gasnet["confusion_matrix"]
    n = len(labels)
    cell = 64
    left, top = 135, 95
    width = left + n * cell + 40
    height = top + n * cell + 70
    max_val = max(max(row) for row in cm) or 1

    out = [
        svg_header(
            width,
            height,
            "GasNet Confusion Matrix (Time-Ordered 20% Holdout)",
            f"Source: {gasnet['provenance']} (n={gasnet['n_samples']}, Acc={gasnet['accuracy']:.3f}, Macro-F1={gasnet['macro_f1']:.3f}) | Units: count",
        )
    ]
    for j, lbl in enumerate(labels):
        x = left + j * cell + cell / 2
        out.append(f'<text x="{x}" y="{top - 10}" font-size="10" text-anchor="middle" fill="#334155">{html.escape(lbl)}</text>')
    for i, row_lbl in enumerate(labels):
        y = top + i * cell
        out.append(f'<text x="{left - 10}" y="{y + cell/2 + 4}" font-size="10" text-anchor="end" fill="#334155">{html.escape(row_lbl)}</text>')
        for j, val in enumerate(cm[i]):
            x = left + j * cell
            intensity = val / max_val
            # Blue shade
            r = int(241 - intensity * 204)
            g = int(245 - intensity * 146)
            b = int(249 - intensity * 14)
            text_color = "#ffffff" if intensity > 0.55 else "#0f172a"
            out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="rgb({r},{g},{b})" stroke="#cbd5e1"/>')
            out.append(f'<text x="{x + cell/2}" y="{y + cell/2 + 5}" font-size="12" font-weight="600" text-anchor="middle" fill="{text_color}">{val}</text>')
    out.append(f'<text x="{width/2}" y="{height - 20}" font-size="11" text-anchor="middle" fill="#64748b">Rows: Ground Truth | Cols: Predicted | Limitation: Synthetic dataset</text>')
    out.append("</svg>")
    (CHARTS_DIR / "gasnet_confusion_matrix.svg").write_text("\n".join(out), encoding="utf-8")


def build_source_f1_svg(sc: Dict[str, Any]) -> None:
    per_class = sc["per_class"]
    items = list(per_class.items())
    width, height = 760, 420
    left, top, bar_h, gap = 250, 85, 28, 10
    max_w = 430

    out = [
        svg_header(
            width,
            height,
            "SourceClassifier Per-Class F1-Score (Controlled Scenarios)",
            f"Source: {sc['provenance']} (seed=42, n={sc['n_samples']}, Macro-F1={sc['macro_f1']:.3f}, Abstain={sc['abstention_rate']:.1%}) | Units: F1 [0-1]",
        )
    ]
    for idx, (lbl, metrics) in enumerate(items):
        y = top + idx * (bar_h + gap)
        f1 = metrics["f1"]
        bw = f1 * max_w
        out.append(f'<text x="{left - 10}" y="{y + 18}" font-size="11" text-anchor="end" fill="#1e293b">{html.escape(lbl)}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{max_w}" height="{bar_h}" fill="#f1f5f9" rx="4"/>')
        out.append(f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{bar_h}" fill="#2563eb" rx="4"/>')
        out.append(f'<text x="{left + bw + 8}" y="{y + 18}" font-size="11" font-weight="600" fill="#0f172a">{f1:.3f} (n={metrics["support"]})</text>')
    out.append(f'<text x="{width/2}" y="{height - 16}" font-size="11" text-anchor="middle" fill="#64748b">Limitation: Evaluated on ScenarioGenerator synthetic profiles, not field-labeled air.</text>')
    out.append("</svg>")
    (CHARTS_DIR / "source_classifier_per_class_f1.svg").write_text("\n".join(out), encoding="utf-8")


def build_anomaly_timeline_svg(anom: Dict[str, Any]) -> None:
    syn = anom["synthetic_controlled"]
    tl = syn["timeline"]
    width, height = 820, 380
    left, right, top, bottom = 65, 30, 85, 55
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_pm = max(r["pm2_5"] for r in tl) or 1.0
    n = len(tl)

    out = [
        svg_header(
            width,
            height,
            "Anomaly Detection Controlled Sequence Timeline",
            f"Source: {syn['provenance']} (n={len(tl)} steps, Precision={syn['precision']:.3f}, Recall={syn['recall']:.3f}, FPR={syn['false_positive_rate']:.3f}) | Units: PM2.5 ug/m3",
        )
    ]
    # Shaded GT anomaly regions
    for r in tl:
        if r["gt_anomaly"] == 1:
            x = left + (r["step"] / max(1, n - 1)) * plot_w
            w = plot_w / max(1, n - 1)
            out.append(f'<rect x="{x:.1f}" y="{top}" width="{w:.1f}" height="{plot_h}" fill="#fee2e2"/>')

    pts = []
    for r in tl:
        x = left + (r["step"] / max(1, n - 1)) * plot_w
        y = top + plot_h - (r["pm2_5"] / max_pm) * plot_h
        pts.append(f"{x:.1f},{y:.1f}")
    out.append(f'<polyline fill="none" stroke="#1d4ed8" stroke-width="2" points="{" ".join(pts)}"/>')

    for r in tl:
        if r["pred_anomaly"] == 1:
            x = left + (r["step"] / max(1, n - 1)) * plot_w
            y = top + plot_h - (r["pm2_5"] / max_pm) * plot_h
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#dc2626"/>')

    out.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#475569"/>')
    out.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#475569"/>')
    out.append(f'<text x="{left - 8}" y="{top + 10}" font-size="10" text-anchor="end" fill="#475569">{max_pm:.0f}</text>')
    out.append(f'<text x="{left - 8}" y="{top + plot_h}" font-size="10" text-anchor="end" fill="#475569">0</text>')
    out.append(f'<text x="{width/2}" y="{height - 16}" font-size="11" text-anchor="middle" fill="#64748b">Pink shade: GT anomaly window | Red dots: Flagged anomaly | Blue line: PM2.5 (ug/m3)</text>')
    out.append("</svg>")
    (CHARTS_DIR / "anomaly_timeline.svg").write_text("\n".join(out), encoding="utf-8")


def build_forecast_svg(fc: Dict[str, Any]) -> None:
    series = fc["sample_series_1h"]
    width, height = 820, 380
    left, right, top, bottom = 65, 30, 85, 55
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_v = max(max(r["actual_1h"], r["ar_pred_1h"]) for r in series) or 1.0
    n = len(series)
    h1 = fc["horizons"]["1h"]

    out = [
        svg_header(
            width,
            height,
            "AR(p) 1-Hour PM2.5 Forecast vs Actual (Bhubaneswar Reference)",
            f"Source: {fc['provenance']} ({fc['dataset']}, n_eval={h1['n']}, AR MAE={h1['ar_mae']}, Pers MAE={h1['persistence_mae']}) | Units: ug/m3",
        )
    ]
    pts_act, pts_ar = [], []
    for i, r in enumerate(series):
        x = left + (i / max(1, n - 1)) * plot_w
        y_a = top + plot_h - (r["actual_1h"] / max_v) * plot_h
        y_p = top + plot_h - (r["ar_pred_1h"] / max_v) * plot_h
        pts_act.append(f"{x:.1f},{y_a:.1f}")
        pts_ar.append(f"{x:.1f},{y_p:.1f}")

    out.append(f'<polyline fill="none" stroke="#0f172a" stroke-width="2" points="{" ".join(pts_act)}"/>')
    out.append(f'<polyline fill="none" stroke="#059669" stroke-width="2" stroke-dasharray="5,3" points="{" ".join(pts_ar)}"/>')
    out.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#475569"/>')
    out.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#475569"/>')
    out.append(f'<text x="{left - 8}" y="{top + 10}" font-size="10" text-anchor="end" fill="#475569">{max_v:.0f}</text>')
    out.append(f'<text x="{left - 8}" y="{top + plot_h}" font-size="10" text-anchor="end" fill="#475569">0</text>')
    out.append(f'<text x="{width/2}" y="{height - 16}" font-size="11" text-anchor="middle" fill="#64748b">Solid black: Actual PM2.5 | Dashed green: AR(p) 1h prediction | Sampled every 6h</text>')
    out.append("</svg>")
    (CHARTS_DIR / "forecast_actual_vs_predicted.svg").write_text("\n".join(out), encoding="utf-8")


def build_latency_svg(bench: Dict[str, Any]) -> None:
    norm = bench["e2e_normal_reading_latency"]
    haz = bench["e2e_hazard_reading_latency"]
    width, height = 740, 340
    left, top, bar_h, gap = 210, 90, 26, 12
    max_ms = max(norm["max_ms"], haz["max_ms"], 1.0)
    max_w = 430

    rows = [
        ("Normal E2E Median", norm["median_ms"], "#2563eb"),
        ("Normal E2E P95", norm["p95_ms"], "#1d4ed8"),
        ("Normal E2E Max", norm["max_ms"], "#1e40af"),
        ("Hazard+Actuator Median", haz["median_ms"], "#ea580c"),
        ("Hazard+Actuator P95", haz["p95_ms"], "#c2410c"),
        ("Hazard+Actuator Max", haz["max_ms"], "#9a3412"),
    ]
    out = [
        svg_header(
            width,
            height,
            "End-to-End Request Processing Latency (Desktop Benchmark)",
            f"Mode: {bench['provenance']} (n_normal={norm['n']}, n_hazard={haz['n']}) | Units: milliseconds (ms)",
        )
    ]
    for i, (lbl, val, col) in enumerate(rows):
        y = top + i * (bar_h + gap)
        bw = (val / max_ms) * max_w
        out.append(f'<text x="{left - 10}" y="{y + 17}" font-size="11" text-anchor="end" fill="#1e293b">{lbl}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{max_w}" height="{bar_h}" fill="#f1f5f9" rx="4"/>')
        out.append(f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{bar_h}" fill="{col}" rx="4"/>')
        out.append(f'<text x="{left + bw + 8}" y="{y + 17}" font-size="11" font-weight="600" fill="#0f172a">{val:.2f} ms</text>')
    out.append(f'<text x="{width/2}" y="{height - 14}" font-size="11" text-anchor="middle" fill="#64748b">Measured via FastAPI TestClient in-process on Windows desktop; not UNO Q LAN hardware timing.</text>')
    out.append("</svg>")
    (CHARTS_DIR / "e2e_latency_distribution.svg").write_text("\n".join(out), encoding="utf-8")


def main() -> None:
    data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    build_confusion_matrix_svg(data["gasnet_evaluation"])
    build_source_f1_svg(data["source_classifier_evaluation"])
    build_anomaly_timeline_svg(data["anomaly_evaluation"])
    build_forecast_svg(data["forecast_evaluation"])
    build_latency_svg(data["e2e_and_benchmarks"])
    print("Generated 5 SVG charts in", CHARTS_DIR)


if __name__ == "__main__":
    main()

