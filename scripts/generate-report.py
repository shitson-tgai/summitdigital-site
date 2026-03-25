#!/usr/bin/env python3
"""
Generate HTML audit report from JSON audit data.
Usage: python3 generate-report.py <audit.json> [output.html]
"""

import sys
import json
import html as html_mod


def score_color(score):
    if score >= 80: return "#22c55e"
    elif score >= 60: return "#eab308"
    else: return "#ef4444"


def grade_color(grade):
    return {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}.get(grade, "#6b7280")


def h(text):
    """HTML-escape text."""
    return html_mod.escape(str(text)) if text else ""


def generate_executive_summary(audit):
    """Generate a dynamic executive summary from audit data."""
    scores = audit["scores"]
    checks = audit.get("checks", [])
    overall = scores["overall"]
    grade = scores["grade"]

    # Find strengths
    cat_scores = {k: scores[k] for k in ["seo", "security", "performance", "accessibility", "content"] if k in scores}
    best_cat = max(cat_scores, key=cat_scores.get)
    best_score = cat_scores[best_cat]
    worst_cat = min(cat_scores, key=cat_scores.get)
    worst_score = cat_scores[worst_cat]

    cat_names = {"seo": "SEO", "security": "Security", "performance": "Performance", "accessibility": "Accessibility", "content": "Content Quality"}

    # Count passes/fails
    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    critical_fails = [c for c in checks if c["status"] == "fail" and c["severity"] == "critical"]

    # Build summary
    if overall >= 80:
        opener = f"This website is performing well with an overall score of {overall}/100 (Grade {grade})."
    elif overall >= 60:
        opener = f"This website has a solid foundation but needs attention in key areas, scoring {overall}/100 (Grade {grade})."
    else:
        opener = f"This website needs significant improvement, scoring only {overall}/100 (Grade {grade})."

    strength = f"{cat_names[best_cat]} is the strongest area at {best_score}/100."
    weakness = f"{cat_names[worst_cat]} needs the most attention at {worst_score}/100."

    if critical_fails:
        top_fix = critical_fails[0]
        priority = f"Top priority: {top_fix['recommendation']}"
    elif failed > 0:
        fail_checks = [c for c in checks if c["status"] == "fail"]
        priority = f"Top priority: {fail_checks[0]['recommendation']}" if fail_checks else "Review warning items for quick wins."
    else:
        priority = "Focus on the warning items below for further optimization."

    return f"{opener} {strength} {weakness} {priority}"


def score_ring_svg(score, label, size=120):
    radius = 45
    circumference = 2 * 3.14159 * radius
    offset = circumference - (score / 100) * circumference
    color = score_color(score)
    return f'''<div style="text-align:center;flex:1;min-width:100px;">
    <svg width="{size}" height="{size}" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="{radius}" fill="none" stroke="#e5e7eb" stroke-width="8"/>
        <circle cx="50" cy="50" r="{radius}" fill="none" stroke="{color}" stroke-width="8"
            stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"
            stroke-linecap="round" transform="rotate(-90 50 50)"/>
        <text x="50" y="50" text-anchor="middle" dy="8" font-size="24" font-weight="bold" fill="{color}">{score}</text>
    </svg>
    <div style="font-size:13px;color:#6b7280;margin-top:2px;font-weight:600;">{label}</div>
</div>'''


def benchmark_bar(label, score, benchmark, max_val=100):
    bar_w = max(score / max_val * 100, 2)
    bench_w = max(benchmark / max_val * 100, 2)
    color = score_color(score)
    diff = score - benchmark
    diff_text = f"+{diff}" if diff > 0 else str(diff)
    diff_color = "#22c55e" if diff > 0 else "#ef4444" if diff < 0 else "#6b7280"
    return f'''<div style="margin-bottom:16px;">
    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
        <span style="font-size:13px;font-weight:600;color:#374151;">{label}</span>
        <span style="font-size:13px;font-weight:700;color:{diff_color};">{score} vs {benchmark} avg ({diff_text})</span>
    </div>
    <div style="position:relative;height:24px;background:#f3f4f6;border-radius:6px;overflow:hidden;">
        <div style="position:absolute;height:100%;width:{bar_w:.1f}%;background:{color};border-radius:6px;opacity:0.9;"></div>
        <div style="position:absolute;height:100%;width:2px;left:{bench_w:.1f}%;background:#374151;opacity:0.5;"></div>
    </div>
</div>'''


def difficulty_badge(difficulty):
    colors = {"Easy": ("#dcfce7", "#166534"), "Medium": ("#fef9c3", "#854d0e"), "Hard": ("#fecaca", "#991b1b")}
    bg, fg = colors.get(difficulty, ("#f3f4f6", "#374151"))
    return f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;background:{bg};color:{fg};">{difficulty}</span>'


def impact_badge(impact):
    colors = {"High": ("#fecaca", "#991b1b"), "Medium": ("#fef9c3", "#854d0e"), "Low": ("#e0e7ff", "#3730a3")}
    bg, fg = colors.get(impact, ("#f3f4f6", "#374151"))
    return f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;background:{bg};color:{fg};">{impact}</span>'


def generate_html(audit):
    scores = audit["scores"]
    checks = audit.get("checks", [])
    url = audit["url"]
    audit_date = audit["audit_date"]

    # ── 1. HEADER ──
    header_html = f'''
    <div style="text-align:center;padding:40px 0 32px;">
        <div style="font-size:28px;font-weight:800;background:linear-gradient(135deg,#2563eb,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.5px;">Summit Digital</div>
        <div style="font-size:13px;color:#9ca3af;margin-top:2px;">Professional Website Audit</div>
        <div style="margin-top:24px;">
            <div style="font-size:14px;color:#6b7280;">Audit for</div>
            <div style="font-size:20px;font-weight:700;color:#1f2937;margin-top:4px;word-break:break-all;">{h(url)}</div>
            <div style="font-size:12px;color:#9ca3af;margin-top:4px;">{h(audit_date)}</div>
        </div>
        <div style="display:inline-flex;align-items:center;justify-content:center;width:80px;height:80px;border-radius:50%;font-size:40px;font-weight:800;color:white;margin:24px 0;background:{grade_color(scores['grade'])};">{scores["grade"]}</div>
        <div style="font-size:16px;color:#6b7280;">Overall Score: <strong style="color:{score_color(scores['overall'])}">{scores["overall"]}/100</strong></div>
        <div style="font-size:13px;color:#9ca3af;margin-top:4px;">{len(checks)} checks performed &middot; {audit.get("issue_count", 0)} issues found</div>
    </div>'''

    # ── 2. EXECUTIVE SUMMARY ──
    summary_text = generate_executive_summary(audit)
    exec_summary_html = f'''
    <div style="margin-bottom:40px;padding:24px;background:linear-gradient(135deg,#eff6ff,#f5f3ff);border-radius:12px;border:1px solid #dbeafe;">
        <div style="font-size:18px;font-weight:700;color:#1e40af;margin-bottom:12px;">Executive Summary</div>
        <p style="font-size:15px;color:#374151;line-height:1.7;margin:0;">{h(summary_text)}</p>
    </div>'''

    # ── 3. SCORE BREAKDOWN ──
    score_rings = f'''
    <div class="section">
        <div class="section-title">Score Breakdown</div>
        <div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;">
            {score_ring_svg(scores.get("seo", 0), "SEO")}
            {score_ring_svg(scores.get("security", 0), "Security")}
            {score_ring_svg(scores.get("performance", 0), "Performance")}
            {score_ring_svg(scores.get("accessibility", 0), "Accessibility")}
            {score_ring_svg(scores.get("content", 0), "Content")}
        </div>
    </div>'''

    # ── 4. INDUSTRY BENCHMARKS ──
    benchmarks = {"seo": 52, "security": 45, "performance": 58, "accessibility": 55, "content": 50}
    bench_html = '<div class="section"><div class="section-title">Industry Benchmarks</div><div style="font-size:13px;color:#6b7280;margin-bottom:16px;">Your scores compared to the average website</div>'
    for cat_key, cat_name in [("seo", "SEO"), ("security", "Security"), ("performance", "Performance"), ("accessibility", "Accessibility"), ("content", "Content")]:
        bench_html += benchmark_bar(cat_name, scores.get(cat_key, 0), benchmarks[cat_key])
    bench_html += '</div>'

    # ── 5. PRIORITY ACTION PLAN ──
    # Rank fails by severity then warnings
    failed_checks = [c for c in checks if c["status"] == "fail"]
    warning_checks = [c for c in checks if c["status"] == "warning"]
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    failed_checks.sort(key=lambda c: severity_order.get(c["severity"], 9))
    top_issues = (failed_checks + warning_checks)[:5]

    action_cards = ""
    for i, issue in enumerate(top_issues, 1):
        sev = issue["severity"]
        is_critical = sev == "critical"
        is_fail = issue["status"] == "fail"
        difficulty = "Easy" if sev == "info" else ("Hard" if is_critical else "Medium")
        impact_level = "High" if is_critical else ("Medium" if sev == "warning" else "Low")
        border_color = "#ef4444" if is_critical else ("#f97316" if sev == "warning" else "#3b82f6")

        # Business impact
        cat = issue["category"]
        impact_map = {
            "seo": "Hurts your Google rankings and organic traffic.",
            "security": "Puts your site and visitors at risk of attacks.",
            "performance": "Slow load times cause visitors to leave — 53% abandon after 3 seconds.",
            "accessibility": "Excludes users with disabilities and may create legal liability.",
            "content": "Weak content signals low authority to search engines."
        }
        why = impact_map.get(cat, "Impacts overall site quality.")

        action_cards += f'''
        <div style="margin-bottom:16px;padding:20px;border-radius:12px;border-left:4px solid {border_color};background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-size:15px;font-weight:700;color:#1f2937;">#{i}. {h(issue["name"])}</span>
                <div>{difficulty_badge(difficulty)} {impact_badge(impact_level)}</div>
            </div>
            <div style="font-size:14px;color:#dc2626;font-weight:600;margin-bottom:6px;">{h(issue["recommendation"])}</div>
            <div style="font-size:13px;color:#6b7280;margin-bottom:8px;"><strong>Why it matters:</strong> {h(why)}</div>
            <div style="font-size:13px;color:#374151;background:#f9fafb;padding:12px;border-radius:8px;line-height:1.6;"><strong>How to fix:</strong> {h(issue.get("how_to_fix", "See detailed findings below."))}</div>
        </div>'''

    action_html = f'''
    <div class="section">
        <div class="section-title">Priority Action Plan</div>
        <div style="font-size:13px;color:#6b7280;margin-bottom:16px;">Top issues ranked by severity and impact — fix these first</div>
        {action_cards}
    </div>'''

    # ── 6. WHAT IS WORKING WELL ──
    passing_checks = [c for c in checks if c["status"] == "pass"]
    pass_items = ""
    for pc in passing_checks:
        pass_items += f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;"><span style="color:#22c55e;font-size:16px;flex-shrink:0;">&#10003;</span><span style="font-size:13px;color:#374151;">{h(pc["name"])}</span><span style="font-size:11px;color:#9ca3af;margin-left:auto;text-transform:uppercase;">{h(pc["category"])}</span></div>'

    working_html = f'''
    <div class="section">
        <div style="font-size:20px;font-weight:700;color:#166534;margin-bottom:8px;padding-bottom:8px;border-bottom:2px solid #bbf7d0;">What Is Working Well ({len(passing_checks)} checks passing)</div>
        <div style="background:#f0fdf4;border-radius:12px;padding:20px;border:1px solid #bbf7d0;">
            {pass_items}
        </div>
    </div>'''

    # ── 7. DETAILED FINDINGS BY CATEGORY ──
    cat_names = {"seo": "SEO", "security": "Security", "performance": "Performance", "accessibility": "Accessibility", "content": "Content Quality"}
    cat_icons = {"seo": "&#128270;", "security": "&#128274;", "performance": "&#9889;", "accessibility": "&#9855;", "content": "&#128196;"}
    cat_order = ["seo", "security", "performance", "accessibility", "content"]

    detail_html = '<div class="section"><div class="section-title">Detailed Findings by Category</div>'
    for cat in cat_order:
        cat_checks = [c for c in checks if c["category"] == cat]
        if not cat_checks:
            continue
        cat_passed = sum(1 for c in cat_checks if c["status"] == "pass")
        detail_html += f'''<div style="margin-bottom:24px;">
            <div style="font-size:16px;font-weight:700;color:#1f2937;margin-bottom:12px;display:flex;align-items:center;gap:8px;">
                <span>{cat_icons.get(cat, "")}</span> {cat_names.get(cat, cat)} <span style="font-size:12px;font-weight:400;color:#6b7280;">({cat_passed}/{len(cat_checks)} passing)</span>
            </div>'''
        for c in cat_checks:
            if c["status"] == "pass":
                badge = '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#dcfce7;color:#166534;">PASS</span>'
            elif c["status"] == "fail":
                badge = '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#fecaca;color:#991b1b;">FAIL</span>'
            else:
                badge = '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:#fef9c3;color:#854d0e;">WARN</span>'

            rec_section = ""
            if c["status"] != "pass":
                rec_section = f'<div style="font-size:12px;color:#6b7280;margin-top:4px;">{h(c["recommendation"])}</div>'

            detail_html += f'''<div style="padding:10px 14px;margin-bottom:6px;border-radius:8px;background:#f9fafb;border:1px solid #f3f4f6;">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    {badge}
                    <span style="font-size:13px;font-weight:600;color:#374151;">{h(c["name"])}</span>
                    <span style="font-size:12px;color:#9ca3af;margin-left:auto;">{h(c["current_value"][:60])}</span>
                </div>
                {rec_section}
            </div>'''
        detail_html += '</div>'
    detail_html += '</div>'

    # ── 8. SECURITY HEADERS TABLE ──
    sec_rows = ""
    if "security_headers" in audit and "headers" in audit["security_headers"]:
        for name, data in audit["security_headers"]["headers"].items():
            status = "&#10003;" if data["present"] else "&#10007;"
            status_color = "#22c55e" if data["present"] else "#ef4444"
            value = h((data["value"] or "")[:60]) or "&mdash;"
            sec_rows += f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;font-family:monospace;font-size:12px;">{h(name)}</td><td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:center;color:{status_color};font-size:16px;">{status}</td><td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;font-size:12px;color:#6b7280;">{value}</td></tr>'

    sec_table_html = f'''
    <div class="section">
        <div class="section-title">Security Headers</div>
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;">
            <tr><th style="text-align:left;padding:10px 12px;background:#f9fafb;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Header</th><th style="padding:10px 12px;background:#f9fafb;font-size:12px;color:#6b7280;text-transform:uppercase;">Status</th><th style="text-align:left;padding:10px 12px;background:#f9fafb;font-size:12px;color:#6b7280;text-transform:uppercase;">Value</th></tr>
            {sec_rows}
        </table>
        </div>
    </div>'''

    # ── 9. TECHNICAL DETAILS ──
    resp = audit.get("response", {})
    page_kb = (resp.get("content_length") or 0) / 1024
    tech_html = f'''
    <div class="section">
        <div class="section-title">Technical Details</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div style="padding:16px;background:#f9fafb;border-radius:8px;">
                <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Response Time (TTFB)</div>
                <div style="font-size:22px;font-weight:700;color:#1f2937;margin-top:4px;">{resp.get("ttfb_ms", "N/A")}ms</div>
            </div>
            <div style="padding:16px;background:#f9fafb;border-radius:8px;">
                <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Total Load Time</div>
                <div style="font-size:22px;font-weight:700;color:#1f2937;margin-top:4px;">{resp.get("total_time_ms", "N/A")}ms</div>
            </div>
            <div style="padding:16px;background:#f9fafb;border-radius:8px;">
                <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Page Weight</div>
                <div style="font-size:22px;font-weight:700;color:#1f2937;margin-top:4px;">{page_kb:.0f} KB</div>
            </div>
            <div style="padding:16px;background:#f9fafb;border-radius:8px;">
                <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Redirects</div>
                <div style="font-size:22px;font-weight:700;color:#1f2937;margin-top:4px;">{len(resp.get("redirects", []))}</div>
            </div>
            <div style="padding:16px;background:#f9fafb;border-radius:8px;">
                <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Compression</div>
                <div style="font-size:22px;font-weight:700;color:#1f2937;margin-top:4px;">{h(resp.get("content_encoding") or "None")}</div>
            </div>
            <div style="padding:16px;background:#f9fafb;border-radius:8px;">
                <div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">HTTPS</div>
                <div style="font-size:22px;font-weight:700;color:{'#22c55e' if resp.get('uses_https') else '#ef4444'};margin-top:4px;">{'Yes' if resp.get('uses_https') else 'No'}</div>
            </div>
        </div>
    </div>'''

    # ── 10. NEXT STEPS ──
    next_steps_html = '''
    <div class="section no-print">
        <div style="text-align:center;padding:32px;background:linear-gradient(135deg,#2563eb,#7c3aed);border-radius:16px;">
            <div style="font-size:22px;font-weight:700;color:white;margin-bottom:8px;">Need Help Fixing These Issues?</div>
            <p style="font-size:15px;color:rgba(255,255,255,0.85);margin-bottom:4px;">Reply to this email if you want help implementing these fixes.</p>
            <p style="font-size:13px;color:rgba(255,255,255,0.7);">We offer one-time fix packages and ongoing optimization plans.</p>
        </div>
    </div>'''

    # ── 11. FOOTER ──
    footer_html = '''
    <div style="text-align:center;color:#9ca3af;font-size:11px;margin-top:48px;padding-top:24px;border-top:1px solid #e5e7eb;">
        <p>Generated by Summit Digital</p>
        <p style="margin-top:4px;">steve@summitwebaudit.com</p>
    </div>'''

    # ── ASSEMBLE ──
    full_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Website Audit Report — {h(url)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #ffffff; color: #1f2937; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 24px; }}
        .section {{ margin-bottom: 40px; }}
        .section-title {{ font-size: 20px; font-weight: 700; color: #1f2937; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e5e7eb; }}
        table {{ width: 100%; border-collapse: collapse; }}
        @media (max-width: 640px) {{
            .container {{ padding: 16px; }}
            .section-title {{ font-size: 18px; }}
        }}
        @media (max-width: 480px) {{
            div[style*="grid-template-columns: 1fr 1fr"] {{ grid-template-columns: 1fr !important; }}
        }}
        @media print {{
            .no-print {{ display: none !important; }}
            body {{ font-size: 12px; }}
            .container {{ max-width: 100%; padding: 0; }}
            .section {{ page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
<div class="container">
    {header_html}
    {exec_summary_html}
    {score_rings}
    {bench_html}
    {action_html}
    {working_html}
    {detail_html}
    {sec_table_html}
    {tech_html}
    {next_steps_html}
    {footer_html}
</div>
</body>
</html>'''

    return full_html


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate-report.py <audit.json> [output.html]")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        audit = json.load(f)

    html = generate_html(audit)

    output = sys.argv[2] if len(sys.argv) > 2 else "report.html"
    with open(output, "w") as f:
        f.write(html)

    print(f"Report generated: {output}")
