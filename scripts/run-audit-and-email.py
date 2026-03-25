#!/usr/bin/env python3
"""
End-to-end: Run audit → Generate HTML report → Convert to PDF → Email to customer via Resend
Called by the webhook server when a Stripe checkout completes.

Usage: python3 run-audit-and-email.py <website_url> <customer_email>
"""

import sys
import os
import json
import subprocess
import tempfile
import base64
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# Load env
from dotenv import load_dotenv
load_dotenv('/home/shitson/.openclaw/agents/ceo/.env')

try:
    import resend
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'resend', '-q'])
    import resend

resend.api_key = os.environ.get('RESEND_API_KEY')


def run_audit(url):
    """Run the audit script and return JSON results."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / 'audit-site.py'), url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"Audit script error: {result.stderr}")
        return None
    
    # Find the JSON object in output (skip pip/debug lines)
    output = result.stdout.strip()
    # Try to find the last { ... } block which should be the JSON
    brace_depth = 0
    json_start = -1
    for i, ch in enumerate(output):
        if ch == '{':
            if brace_depth == 0:
                json_start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and json_start >= 0:
                try:
                    return json.loads(output[json_start:i+1])
                except json.JSONDecodeError:
                    json_start = -1
    
    return json.loads(output)


def generate_report(audit_data, output_path):
    """Generate HTML report from audit data."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(audit_data, f)
        json_path = f.name
    
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / 'generate-report.py'), json_path, output_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"Report generation error: {result.stderr}")
            return False
        return True
    finally:
        os.unlink(json_path)


def html_to_pdf(html_path, pdf_path):
    """Convert HTML report to PDF using Chromium."""
    result = subprocess.run([
        'chromium', '--headless', '--disable-gpu', '--no-sandbox',
        '--print-to-pdf=' + pdf_path,
        '--no-pdf-header-footer',
        html_path
    ], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"PDF conversion warning: {result.stderr[:200]}")
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0


def send_email(to_email, website_url, report_path, audit_data):
    """Send summary email with PDF report attached."""
    scores = audit_data.get('scores', {})
    overall = scores.get('overall', '?')
    grade = scores.get('grade', '?')
    issue_count = audit_data.get('issue_count', 0)
    
    # Get category scores for summary
    categories = audit_data.get('categories', {})
    seo_score = categories.get('seo', {}).get('score', '?')
    security_score = categories.get('security', {}).get('score', '?')
    performance_score = categories.get('performance', {}).get('score', '?')
    accessibility_score = categories.get('accessibility', {}).get('score', '?')
    content_score = categories.get('content', {}).get('score', '?')
    
    # Get top 3 critical issues for summary
    issues = audit_data.get('issues', [])
    critical_issues = [i for i in issues if i.get('severity') in ('critical', 'high')][:3]
    if not critical_issues:
        critical_issues = issues[:3]
    
    safe_name = website_url.replace('https://', '').replace('http://', '').replace('/', '_').replace(':', '')
    
    # Convert HTML to PDF
    pdf_path = report_path.replace('.html', '.pdf')
    pdf_success = html_to_pdf(report_path, pdf_path)
    
    if pdf_success:
        with open(pdf_path, 'rb') as f:
            attachment_content = base64.b64encode(f.read()).decode()
        attachment_filename = f"audit-report-{safe_name}.pdf"
        attachment_type = "application/pdf"
        attachment_note = "Your full report is attached as a PDF."
    else:
        # Fallback to HTML if PDF conversion fails
        print("PDF conversion failed, falling back to HTML attachment")
        with open(report_path, 'rb') as f:
            attachment_content = base64.b64encode(f.read()).decode()
        attachment_filename = f"audit-report-{safe_name}.html"
        attachment_type = "text/html"
        attachment_note = "Your full report is attached as an HTML file — open it in any browser."
    
    # Build critical issues HTML
    issues_html = ""
    for issue in critical_issues:
        severity = issue.get('severity', 'medium')
        color = '#dc2626' if severity == 'critical' else '#ea580c' if severity == 'high' else '#ca8a04'
        issues_html += f'<li style="margin-bottom:8px;"><span style="color:{color};font-weight:700;">[{severity.upper()}]</span> {issue.get("title", issue.get("issue", "Issue found"))}</li>'
    
    def score_color(s):
        if isinstance(s, (int, float)):
            return '#22c55e' if s >= 70 else '#eab308' if s >= 50 else '#ef4444'
        return '#64748b'
    
    body_html = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <h2 style="color:#1e293b;">Your Website Audit Report 📊</h2>
        <p>Hey there,</p>
        <p>Your comprehensive audit for <strong>{website_url}</strong> is complete. Here's the summary — full report is attached.</p>
        
        <div style="background:#f1f5f9;border-radius:12px;padding:24px;text-align:center;margin:24px 0;">
            <div style="font-size:48px;font-weight:800;color:{score_color(overall)};">{overall}/100</div>
            <div style="color:#64748b;">Overall Score — Grade: <strong>{grade}</strong></div>
            <div style="color:#64748b;margin-top:4px;">{issue_count} issues found</div>
        </div>
        
        <h3 style="color:#1e293b;margin-bottom:12px;">Score Breakdown</h3>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
            <tr><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">🔍 SEO</td><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:700;color:{score_color(seo_score)};">{seo_score}/100</td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">🔒 Security</td><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:700;color:{score_color(security_score)};">{security_score}/100</td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">⚡ Performance</td><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:700;color:{score_color(performance_score)};">{performance_score}/100</td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;">♿ Accessibility</td><td style="padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:700;color:{score_color(accessibility_score)};">{accessibility_score}/100</td></tr>
            <tr><td style="padding:8px 12px;">📝 Content</td><td style="padding:8px 12px;text-align:right;font-weight:700;color:{score_color(content_score)};">{content_score}/100</td></tr>
        </table>
        
        {'<h3 style="color:#1e293b;margin-bottom:12px;">Top Issues to Fix</h3><ul style="padding-left:20px;">' + issues_html + '</ul>' if issues_html else ''}
        
        <p style="margin-top:24px;">{attachment_note} It includes detailed findings, fix instructions, and a prioritized action plan.</p>
        
        <p>Need help implementing the fixes? Just reply to this email — happy to point you in the right direction.</p>
        
        <p>Best,<br>Steve<br>Summit Web Audit<br><a href="https://summitwebaudit.com">summitwebaudit.com</a></p>
    </div>
    """
    
    body_text = f"""Your Website Audit Report for {website_url}

Overall Score: {overall}/100 (Grade: {grade})
Issues Found: {issue_count}

Score Breakdown:
- SEO: {seo_score}/100
- Security: {security_score}/100
- Performance: {performance_score}/100
- Accessibility: {accessibility_score}/100
- Content: {content_score}/100

{attachment_note} It includes detailed findings, fix instructions, and a prioritized action plan.

Need help fixing these issues? Just reply to this email.

— Steve
Summit Web Audit
summitwebaudit.com
"""

    r = resend.Emails.send({
        "from": "Steve at Summit Web Audit <steve@summitwebaudit.com>",
        "to": to_email,
        "subject": f"Your Website Audit Report — {website_url} ({overall}/100)",
        "html": body_html,
        "text": body_text,
        "reply_to": "steve@summitwebaudit.com",
        "headers": {
            "List-Unsubscribe": "<mailto:steve@summitwebaudit.com?subject=unsubscribe>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"
        },
        "attachments": [{
            "filename": attachment_filename,
            "content": attachment_content,
            "content_type": attachment_type
        }]
    })
    
    print(f"Report email sent to {to_email} via Resend: {r}")
    
    # Clean up PDF
    if pdf_success and os.path.exists(pdf_path):
        os.unlink(pdf_path)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 run-audit-and-email.py <website_url> <customer_email>")
        sys.exit(1)
    
    website_url = sys.argv[1]
    customer_email = sys.argv[2]
    
    print(f"Starting audit for {website_url}...")
    
    # Step 1: Run the audit
    audit_data = run_audit(website_url)
    if not audit_data:
        print("ERROR: Audit failed")
        sys.exit(1)
    
    print(f"Audit complete. Score: {audit_data.get('scores', {}).get('overall', '?')}/100. Generating report...")
    
    # Step 2: Generate HTML report
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
        report_path = f.name
    
    try:
        success = generate_report(audit_data, report_path)
        if not success:
            print("ERROR: Report generation failed")
            sys.exit(1)
        
        print("Report generated. Sending email...")
        
        # Step 3: Email the report via Resend
        send_email(customer_email, website_url, report_path, audit_data)
        
        print(f"SUCCESS: Report for {website_url} sent to {customer_email}")
    finally:
        if os.path.exists(report_path):
            os.unlink(report_path)


if __name__ == '__main__':
    main()
