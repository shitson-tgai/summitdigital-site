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


def send_email(to_email, website_url, report_path, audit_data):
    """Send the audit report via Resend."""
    scores = audit_data.get('scores', {})
    overall = scores.get('overall', '?')
    grade = scores.get('grade', '?')
    issue_count = audit_data.get('issue_count', 0)
    
    # Read report HTML and base64 encode for attachment
    with open(report_path, 'rb') as f:
        report_content = f.read()
    report_b64 = base64.b64encode(report_content).decode()
    
    safe_name = website_url.replace('https://', '').replace('http://', '').replace('/', '_').replace(':', '')
    
    body_html = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <h2 style="color:#1e293b;">Your Website Audit Report is Ready! 📊</h2>
        <p>Hey there,</p>
        <p>Your comprehensive audit report for <strong>{website_url}</strong> is attached to this email.</p>
        
        <div style="background:#f1f5f9;border-radius:12px;padding:24px;text-align:center;margin:24px 0;">
            <div style="font-size:48px;font-weight:800;color:{'#22c55e' if overall >= 70 else '#eab308' if overall >= 50 else '#ef4444'};">{overall}/100</div>
            <div style="color:#64748b;">Overall Score — Grade: <strong>{grade}</strong></div>
            <div style="color:#64748b;margin-top:4px;">{issue_count} issues found</div>
        </div>
        
        <p>Your report includes:</p>
        <ul>
            <li>📊 Detailed score breakdown (SEO, Security, Performance, Accessibility, Content)</li>
            <li>🚨 Every issue found with severity ratings</li>
            <li>🔒 Full security headers analysis</li>
            <li>🔍 Complete SEO analysis (meta tags, headings, structured data)</li>
            <li>⚡ Performance metrics (response time, HTTPS, redirects)</li>
        </ul>
        
        <p><strong>Open the attached HTML file in any browser to view your interactive report.</strong></p>
        
        <p>Need help fixing these issues? Just reply to this email — we're happy to point you in the right direction.</p>
        
        <p>Best,<br>Steve<br>Summit Web Audit<br><a href="https://summitwebaudit.com">summitwebaudit.com</a></p>
    </div>
    """
    
    body_text = f"""Your Website Audit Report for {website_url}

Overall Score: {overall}/100 (Grade: {grade})
Issues Found: {issue_count}

Your detailed report is attached as an HTML file. Open it in any browser to view the full interactive report.

The report covers:
- SEO Analysis (meta tags, headings, structure)
- Security Headers (HSTS, CSP, X-Frame-Options)  
- Performance (response time, HTTPS)
- Accessibility (alt tags, viewport, language)
- Content Quality (word count, links)

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
            "filename": f"audit-report-{safe_name}.html",
            "content": report_b64,
            "content_type": "text/html"
        }]
    })
    
    print(f"Report email sent to {to_email} via Resend: {r}")


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
