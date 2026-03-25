#!/usr/bin/env python3
"""
Generate HTML audit report from JSON audit data.
Usage: python3 generate-report.py <audit.json> [output.html]
"""

import sys
import json


def score_color(score):
    if score >= 80: return "#22c55e"  # green
    elif score >= 60: return "#eab308"  # yellow
    else: return "#ef4444"  # red


def grade_color(grade):
    colors = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}
    return colors.get(grade, "#6b7280")


def severity(issue):
    critical = ["critical", "missing <title>", "not using https", "missing meta description"]
    important = ["missing", "too short", "too long", "multiple h1"]
    if any(c in issue.lower() for c in critical):
        return "critical", "#ef4444", "🔴"
    elif any(i in issue.lower() for i in important):
        return "warning", "#f97316", "🟠"
    else:
        return "info", "#3b82f6", "🔵"


def generate_html(audit):
    scores = audit["scores"]
    
    # Score ring SVG helper
    def score_ring(score, label, size=120):
        radius = 45
        circumference = 2 * 3.14159 * radius
        offset = circumference - (score / 100) * circumference
        color = score_color(score)
        return f'''
        <div style="text-align:center;">
            <svg width="{size}" height="{size}" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="{radius}" fill="none" stroke="#e5e7eb" stroke-width="8"/>
                <circle cx="50" cy="50" r="{radius}" fill="none" stroke="{color}" stroke-width="8"
                    stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"
                    stroke-linecap="round" transform="rotate(-90 50 50)"
                    style="transition: stroke-dashoffset 1s ease;"/>
                <text x="50" y="50" text-anchor="middle" dy="8" font-size="24" font-weight="bold" fill="{color}">{score}</text>
            </svg>
            <div style="font-size:14px;color:#6b7280;margin-top:4px;">{label}</div>
        </div>'''

    # Issues HTML
    issues_html = ""
    for issue in audit["all_issues"]:
        sev, color, icon = severity(issue)
        issues_html += f'''
        <div style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:#f9fafb;border-radius:8px;margin-bottom:8px;border-left:4px solid {color};">
            <span style="font-size:18px;">{icon}</span>
            <span style="color:#374151;font-size:14px;">{issue}</span>
        </div>'''

    # Security headers table
    sec_rows = ""
    for name, data in audit["security_headers"]["headers"].items():
        status = "✅" if data["present"] else "❌"
        value = data["value"][:60] if data["value"] else "—"
        sec_rows += f"<tr><td style='padding:8px 12px;border-bottom:1px solid #f3f4f6;font-family:monospace;font-size:13px;'>{name}</td><td style='padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:center;'>{status}</td><td style='padding:8px 12px;border-bottom:1px solid #f3f4f6;font-size:13px;color:#6b7280;'>{value}</td></tr>"

    # Meta tags summary
    meta = audit["meta_tags"]
    title_display = meta["title"] or "❌ Missing"
    desc_display = (meta["description"][:120] + "...") if meta["description"] and len(meta["description"]) > 120 else (meta["description"] or "❌ Missing")
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Website Audit Report — {audit["url"]}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #ffffff; color: #1f2937; line-height: 1.6; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 40px 24px; }}
        .header {{ text-align: center; margin-bottom: 48px; }}
        .logo {{ font-size: 24px; font-weight: 700; color: #2563eb; margin-bottom: 8px; }}
        .subtitle {{ color: #6b7280; font-size: 14px; }}
        .grade-badge {{ display: inline-flex; align-items: center; justify-content: center; width: 80px; height: 80px; border-radius: 50%; font-size: 40px; font-weight: 800; color: white; margin: 24px 0; }}
        .section {{ margin-bottom: 40px; }}
        .section-title {{ font-size: 20px; font-weight: 700; color: #1f2937; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e5e7eb; }}
        .scores-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin: 24px 0; }}
        .meta-row {{ display: flex; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f3f4f6; }}
        .meta-label {{ font-weight: 600; min-width: 140px; color: #374151; font-size: 14px; }}
        .meta-value {{ color: #6b7280; font-size: 14px; word-break: break-all; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; padding: 10px 12px; background: #f9fafb; font-size: 13px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; }}
        .cta {{ text-align: center; margin: 48px 0; padding: 32px; background: linear-gradient(135deg, #2563eb, #7c3aed); border-radius: 16px; }}
        .cta h2 {{ color: white; margin-bottom: 12px; }}
        .cta p {{ color: rgba(255,255,255,0.85); margin-bottom: 20px; font-size: 15px; }}
        .cta-btn {{ display: inline-block; padding: 14px 32px; background: white; color: #2563eb; font-weight: 700; font-size: 16px; border-radius: 8px; text-decoration: none; }}
        .footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb; }}
        @media (max-width: 640px) {{ .scores-grid {{ grid-template-columns: repeat(3, 1fr); }} }}
        @media print {{ .cta {{ display: none; }} }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="logo">⚡ Summit Web Audit</div>
        <div class="subtitle">Website Audit Report</div>
        <div style="margin-top:24px;">
            <div style="font-size:16px;color:#6b7280;">Audit for</div>
            <div style="font-size:22px;font-weight:700;color:#1f2937;margin-top:4px;">{audit["url"]}</div>
            <div style="font-size:13px;color:#9ca3af;margin-top:4px;">{audit["audit_date"]}</div>
        </div>
        <div class="grade-badge" style="background:{grade_color(scores['grade'])};">{scores["grade"]}</div>
        <div style="font-size:16px;color:#6b7280;">Overall Score: <strong style="color:{score_color(scores['overall'])}">{scores["overall"]}/100</strong></div>
        <div style="font-size:14px;color:#9ca3af;margin-top:4px;">{audit["issue_count"]} issues found</div>
    </div>

    <div class="section">
        <div class="section-title">📊 Score Breakdown</div>
        <div class="scores-grid">
            {score_ring(scores["seo"], "SEO")}
            {score_ring(scores["security"], "Security")}
            {score_ring(scores["performance"], "Performance")}
            {score_ring(scores["accessibility"], "Accessibility")}
            {score_ring(scores["content"], "Content")}
        </div>
    </div>

    <div class="section">
        <div class="section-title">🚨 Issues Found ({audit["issue_count"]})</div>
        {issues_html}
    </div>

    <div class="section">
        <div class="section-title">🔍 SEO Analysis</div>
        <div class="meta-row"><span class="meta-label">Page Title</span><span class="meta-value">{title_display} ({meta["title_length"]} chars)</span></div>
        <div class="meta-row"><span class="meta-label">Meta Description</span><span class="meta-value">{desc_display} ({meta["description_length"]} chars)</span></div>
        <div class="meta-row"><span class="meta-label">Canonical URL</span><span class="meta-value">{meta["canonical"] or "❌ Missing"}</span></div>
        <div class="meta-row"><span class="meta-label">Open Graph Tags</span><span class="meta-value">{"✅ Present" if meta["og_tags"] else "❌ Missing"}</span></div>
        <div class="meta-row"><span class="meta-label">Viewport</span><span class="meta-value">{"✅ Set" if meta["viewport"] else "❌ Missing"}</span></div>
        <div class="meta-row"><span class="meta-label">Language</span><span class="meta-value">{meta["language"] or "❌ Missing"}</span></div>
        <div class="meta-row"><span class="meta-label">Favicon</span><span class="meta-value">{"✅ Present" if meta["favicon"] else "❌ Missing"}</span></div>
        <div class="meta-row"><span class="meta-label">H1 Tags</span><span class="meta-value">{audit["headings"]["headings"]["h1"]["count"]}</span></div>
        <div class="meta-row"><span class="meta-label">robots.txt</span><span class="meta-value">{"✅ Found" if audit["robots_sitemap"]["robots_txt"] else "❌ Missing"}</span></div>
        <div class="meta-row"><span class="meta-label">sitemap.xml</span><span class="meta-value">{"✅ Found" if audit["robots_sitemap"]["sitemap_xml"] else "❌ Missing"}</span></div>
    </div>

    <div class="section">
        <div class="section-title">🔒 Security Headers</div>
        <table>
            <tr><th>Header</th><th>Status</th><th>Value</th></tr>
            {sec_rows}
        </table>
    </div>

    <div class="section">
        <div class="section-title">📝 Content & Structure</div>
        <div class="meta-row"><span class="meta-label">Word Count</span><span class="meta-value">{audit["content"]["word_count"]}</span></div>
        <div class="meta-row"><span class="meta-label">Total Images</span><span class="meta-value">{audit["images"]["total_images"]}</span></div>
        <div class="meta-row"><span class="meta-label">Missing Alt Text</span><span class="meta-value">{audit["images"]["missing_alt"]}</span></div>
        <div class="meta-row"><span class="meta-label">Internal Links</span><span class="meta-value">{audit["links"]["internal"]}</span></div>
        <div class="meta-row"><span class="meta-label">External Links</span><span class="meta-value">{audit["links"]["external"]}</span></div>
    </div>

    <div class="section">
        <div class="section-title">⚡ Performance</div>
        <div class="meta-row"><span class="meta-label">Response Time</span><span class="meta-value">{audit["response"]["ttfb_ms"]}ms TTFB / {audit["response"]["total_time_ms"]}ms total</span></div>
        <div class="meta-row"><span class="meta-label">HTTPS</span><span class="meta-value">{"✅ Yes" if audit["response"]["uses_https"] else "❌ No"}</span></div>
        <div class="meta-row"><span class="meta-label">Redirects</span><span class="meta-value">{len(audit["response"]["redirects"])}</span></div>
    </div>

    <div class="cta">
        <h2>Want help fixing these issues?</h2>
        <p>Get a detailed action plan with step-by-step instructions for every issue found in your audit.</p>
        <a href="https://summitwebaudit.com/check" class="cta-btn">Check Another Website Free →</a>
    </div>

    <div class="footer">
        <p>Generated by Summit Web Audit · summitwebaudit.com</p>
        <p>Questions about this report? Reply to the email it came with — we read every one.</p>
    </div>
</div>
</body>
</html>'''
    
    return html


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
