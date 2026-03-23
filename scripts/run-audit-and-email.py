#!/usr/bin/env python3
"""
End-to-end: Run audit → Generate report → Email to customer
Called by the webhook server when a Stripe checkout completes.

Usage: python3 run-audit-and-email.py <website_url> <customer_email>
"""

import sys
import os
import json
import subprocess
import smtplib
import tempfile
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS', 'summitdigitalceo@gmail.com')
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_APP_PASSWORD', '')

def run_audit(url):
    """Run the audit script and return JSON results."""
    result = subprocess.run(
        ['python3', str(SCRIPT_DIR / 'audit-site.py'), url],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        print(f"Audit script error: {result.stderr}")
        return None
    
    # Parse JSON from stdout (skip any non-JSON lines)
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if line.startswith('{'):
            return json.loads(line)
    
    # Try parsing entire output
    return json.loads(result.stdout.strip())

def generate_report(audit_data, output_path):
    """Generate HTML report from audit data."""
    # Write audit data to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(audit_data, f)
        json_path = f.name
    
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'generate-report.py'), json_path, output_path],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"Report generation error: {result.stderr}")
            return False
        return True
    finally:
        os.unlink(json_path)

def send_email(to_email, website_url, report_path):
    """Send the audit report via email."""
    msg = MIMEMultipart()
    msg['From'] = f'Summit Web Audit <{GMAIL_ADDRESS}>'
    msg['To'] = to_email
    msg['Subject'] = f'Your Website Audit Report — {website_url}'
    
    body = f"""Hi there,

Your website audit report for {website_url} is ready!

Please find the detailed report attached. It covers:
• SEO Analysis
• Security Scan  
• Performance Check
• Accessibility Review
• Content Quality Assessment

Each section is scored A–F with specific, actionable recommendations.

If you have any questions about the findings or need help implementing the fixes, just reply to this email — we're happy to help.

Thank you for choosing Summit Web Audit!

Best,
Summit Web Audit Team
summitwebaudit.com
"""
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach the HTML report
    with open(report_path, 'rb') as f:
        attachment = MIMEBase('text', 'html')
        attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        
        safe_name = website_url.replace('https://', '').replace('http://', '').replace('/', '_')
        attachment.add_header('Content-Disposition', f'attachment; filename="audit-report-{safe_name}.html"')
        msg.attach(attachment)
    
    # Send via Gmail SMTP
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    
    print(f"Report sent to {to_email}")

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
    
    print("Audit complete. Generating report...")
    
    # Step 2: Generate HTML report
    with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
        report_path = f.name
    
    try:
        success = generate_report(audit_data, report_path)
        if not success:
            print("ERROR: Report generation failed")
            sys.exit(1)
        
        print("Report generated. Sending email...")
        
        # Step 3: Email the report
        send_email(customer_email, website_url, report_path)
        
        print(f"SUCCESS: Report for {website_url} sent to {customer_email}")
    finally:
        if os.path.exists(report_path):
            os.unlink(report_path)

if __name__ == '__main__':
    main()
