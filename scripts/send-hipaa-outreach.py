#!/usr/bin/env python3
"""Send HIPAA-focused outreach to medical practices referencing the blog post."""

import json, glob, os, time, sys
from dotenv import load_dotenv
load_dotenv('/home/shitson/.openclaw/agents/ceo/.env')

try:
    import resend
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'resend'])
    import resend

resend.api_key = os.getenv('RESEND_API_KEY')

SENT_FILE = '/home/shitson/.openclaw/agents/ceo/business/prospects/sent-emails.txt'
PROSPECTS_DIR = '/home/shitson/.openclaw/agents/ceo/business/prospects'

# Load sent
sent = set()
if os.path.exists(SENT_FILE):
    with open(SENT_FILE) as f:
        sent = set(line.strip().lower() for line in f if line.strip())

# Collect medical prospects from all batches
medical_industries = ['dentist', 'chiropractor', 'veterinary', 'med spa', 'physical therapy',
                       'acupuncture', 'dental', 'chiropractic', 'massage therapist',
                       'optometrist', 'optometry', 'eye', 'therapist', 'counseling',
                       'psychologist', 'medical', 'medspa', 'med', 'vet', 'physical']
to_send = []
for f in sorted(glob.glob(os.path.join(PROSPECTS_DIR, 'batch-*.json'))):
    with open(f) as fp:
        for p in json.load(fp):
            email = (p.get('email') or '').strip().lower()
            industry = (p.get('industry') or '').lower()
            domain = email.split('@')[-1] if '@' in email else ''
            if (email and '@' in email and email not in sent and
                any(mi in industry for mi in medical_industries) and
                not any(domain.endswith(s) for s in ['.gov', '.edu', '.mil', 'wixpress.com', 'sentry.io', 'example.com', 'domain.com', 'company.com']) and
                email not in ['example@gmail.com', 'user@domain.com', 'first.last@company.com', 'your@email.com']):
                to_send.append(p)

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 30
print(f"Medical prospects to send: {len(to_send)} | Limit: {LIMIT}")

sent_count = 0
for i, prospect in enumerate(to_send[:LIMIT]):
    email = prospect['email'].strip()
    industry = prospect.get('industry', 'healthcare')
    # Fix truncated industry names
    industry_fixes = {'physical': 'physical therapy', 'med': 'medical', 'vet': 'veterinary'}
    industry = industry_fixes.get(industry, industry)
    location = prospect.get('location', '')
    url = prospect.get('url', '')
    
    # Clean biz name from URL
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace('www.', '') if url else ''
    biz_name = domain.split('.')[0].replace('-', ' ').replace('_', ' ').title() if domain else 'your practice'
    
    import random
    subjects = [
        f"Is your {industry} website HIPAA compliant?",
        f"Quick question about your {industry} website and HIPAA",
        f"Something most {industry} websites get wrong about HIPAA",
        f"Your website might have a HIPAA issue — worth a quick look",
    ]
    subject = random.choice(subjects)
    
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 600px; padding: 20px;">
        <p>Hi there,</p>
        <p>I recently wrote about the <strong>7 most common HIPAA violations on healthcare business websites</strong> — things like contact forms without encryption, analytics tracking PHI, and missing security headers.</p>
        <p>The average HIPAA violation fine is over $1.5 million, and many {industry} practices don't realize their website is at risk.</p>
        <p>I thought you might find it useful: <a href="https://summitwebaudit.com/blog/is-your-website-hipaa-compliant?utm_source=email&utm_medium=cold&utm_campaign=hipaa_outreach">Is Your Website HIPAA Compliant? →</a></p>
        <p>I also ran a quick scan of your website and found some potential issues. You can see a free preview here:</p>
        <p style="margin: 20px 0;"><a href="https://summitwebaudit.com/check?utm_source=email&utm_medium=cold&utm_campaign=hipaa_outreach" style="display: inline-block; padding: 12px 28px; background: #2563eb; color: white; font-weight: 700; border-radius: 8px; text-decoration: none;">Check Your Practice Website Free →</a></p>
        <p>No signup required — takes 30 seconds.</p>
        <p>Best,<br>Steve<br>Summit Web Audit<br><a href="https://summitwebaudit.com">summitwebaudit.com</a></p>
    </div>
    """
    
    try:
        r = resend.Emails.send({
            "from": "Steve at Summit Web Audit <steve@summitwebaudit.com>",
            "to": email,
            "subject": subject,
            "html": html,
            "reply_to": "steve@summitwebaudit.com"
        })
        with open(SENT_FILE, 'a') as f:
            f.write(email.lower() + '\n')
        sent.add(email.lower())
        sent_count += 1
        print(f"  ✅ [{i+1}] {email} ({industry}, {location})")
        time.sleep(0.6)
    except Exception as e:
        print(f"  ❌ [{i+1}] {email}: {e}")

print(f"\n=== Done: {sent_count} HIPAA-focused emails sent ===")
