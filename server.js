// Allow scanning sites with self-signed or incomplete certificate chains
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

const express = require('express');
const path = require('path');
const { execSync, spawn } = require('child_process');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

const app = express();
const fs = require('fs');
const PORT = process.env.PORT || 3000;

// Simple analytics — log page views
// Use persistent volume if available, fall back to local
const DATA_DIR = fs.existsSync('/data') ? '/data' : __dirname;
const ANALYTICS_FILE = path.join(DATA_DIR, 'analytics.csv');
const LEADS_FILE = path.join(DATA_DIR, 'leads.csv');
const SCANS_FILE = path.join(DATA_DIR, 'scans.csv');
const SHARES_DIR = path.join(DATA_DIR, 'shares');
if (!fs.existsSync(SHARES_DIR)) fs.mkdirSync(SHARES_DIR, { recursive: true });
console.log(`Data directory: ${DATA_DIR} (persistent: ${fs.existsSync('/data')})`);
// Known page routes (only log these)
const KNOWN_PAGES = ['/', '/check', '/blog', '/content', '/thank-you', '/order'];
const BOT_PATTERNS = /bot|crawler|spider|scan|curl|python|go-http|wget|headless|phantom|selenium|scrapy|slurp|yahoo|bing|yandex|baidu|semrush|ahrefs|mj12|dotbot|petalbot|ahc\//i;

app.use((req, res, next) => {
  if (req.method === 'GET') {
    const p = req.path.toLowerCase();
    const ua = req.headers['user-agent'] || '';
    // Only log real pages, skip bots
    const isKnownPage = KNOWN_PAGES.includes(p) || p.startsWith('/blog/');
    const isBot = BOT_PATTERNS.test(ua) || (!ua && !req.headers.referer);
    if (isKnownPage && !isBot) {
      const line = `${new Date().toISOString()},${req.path},${req.query.utm_source || ''},${req.headers.referer || ''},${ua.substring(0, 100)}\n`;
      fs.appendFile(ANALYTICS_FILE, line, () => {});
    }
  }
  next();
});

// Stripe webhook needs raw body
app.post('/webhook', express.raw({ type: 'application/json' }), async (req, res) => {
  const sig = req.headers['stripe-signature'];
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, sig, webhookSecret);
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object;
    const customerEmail = session.customer_details?.email || session.customer_email;
    const websiteUrl = session.custom_fields?.[0]?.text?.value || 
                       session.metadata?.website_url || 
                       'No URL provided';
    
    console.log(`New order: ${customerEmail} wants audit of ${websiteUrl}`);

    // Run the audit in background
    try {
      const child = spawn('python3', [
        path.join(__dirname, 'scripts', 'run-audit-and-email.py'),
        websiteUrl,
        customerEmail
      ], {
        detached: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env }
      });

      child.stdout.on('data', (data) => console.log(`Audit stdout: ${data}`));
      child.stderr.on('data', (data) => console.error(`Audit stderr: ${data}`));
      child.on('close', (code) => console.log(`Audit process exited with code ${code}`));
      child.unref();
    } catch (err) {
      console.error('Failed to start audit:', err);
    }
  }

  res.json({ received: true });
});

// Clean redirect for payment link
app.get('/order', (req, res) => {
  res.redirect(302, 'https://buy.stripe.com/7sYeVfdxJ8HL4mN2ktes003');
});

// Free quick check API
app.post('/api/quick-check', express.json(), async (req, res) => {
  const { url } = req.body;
  if (!url) return res.status(400).json({ error: 'URL required' });

  try {
    const fetch = require('node-fetch');
    const { URL } = require('url');
    
    let targetUrl = url.startsWith('http') ? url : `https://${url}`;
    const parsed = new URL(targetUrl);
    const issues = [];
    
    const start = Date.now();
    const response = await fetch(targetUrl, {
      timeout: 10000,
      follow: 5,
      headers: { 'User-Agent': 'SummitWebAudit/1.0' }
    });
    const body = await response.text();
    const result = { headers: Object.fromEntries(response.headers.entries()), statusCode: response.status, body };
    const loadTime = (Date.now() - start) / 1000;
    
    if (loadTime > 3) issues.push({ icon: '⚠️', issue: `Slow load time: ${loadTime.toFixed(1)}s`, detail: 'Should be under 3 seconds for best user experience and Google rankings.' });
    if (!result.headers['strict-transport-security']) issues.push({ icon: '🔒', issue: 'Missing HSTS security header', detail: 'Browsers aren\'t forced to use secure HTTPS connections.' });
    if (!result.headers['content-security-policy']) issues.push({ icon: '🛡️', issue: 'No Content Security Policy', detail: 'Your site may be vulnerable to cross-site scripting attacks.' });
    
    // Check meta tags
    const titleMatch = result.body.match(/<title[^>]*>(.*?)<\/title>/is);
    if (!titleMatch || titleMatch[1].trim().length < 10) issues.push({ icon: '📝', issue: 'Weak or missing title tag', detail: 'This is the #1 factor for Google click-through rates.' });
    
    const metaDesc = result.body.match(/<meta\s+name=["']description["']\s+content=["']([^"']*)["']/i);
    if (!metaDesc || metaDesc[1].trim().length < 20) issues.push({ icon: '📝', issue: 'Missing or weak meta description', detail: 'Google won\'t show a compelling snippet for your site in search results.' });
    
    // Count images without alt
    const imgMatches = result.body.match(/<img[^>]*>/gi) || [];
    const noAlt = imgMatches.filter(img => !img.match(/alt=["'][^"']+["']/i)).length;
    if (noAlt > 2) issues.push({ icon: '🖼️', issue: `${noAlt} images missing alt text`, detail: 'Hurts SEO and makes your site inaccessible to visually impaired visitors.' });

    // Additional checks for more realistic scoring
    if (!result.headers['x-frame-options'] && !result.headers['content-security-policy']?.includes('frame-ancestors')) {
      issues.push({ icon: '🛡️', issue: 'Missing X-Frame-Options header', detail: 'Your site could be embedded in malicious iframes (clickjacking risk).' });
    }
    if (!result.headers['x-content-type-options']) {
      issues.push({ icon: '🔒', issue: 'Missing X-Content-Type-Options header', detail: 'Browsers might misinterpret file types, opening door to attacks.' });
    }
    if (!result.headers['referrer-policy']) {
      issues.push({ icon: '🔒', issue: 'No Referrer-Policy set', detail: 'Your URLs may leak to third parties when visitors click external links.' });
    }
    const ogTitle = result.body.match(/<meta\s+property=["']og:title["']/i);
    const ogDesc = result.body.match(/<meta\s+property=["']og:description["']/i);
    const ogImage = result.body.match(/<meta\s+property=["']og:image["']/i);
    if (!ogTitle || !ogDesc || !ogImage) {
      issues.push({ icon: '📱', issue: 'Incomplete Open Graph tags', detail: 'Your site won\'t look great when shared on social media (Facebook, LinkedIn, etc).' });
    }
    const canonical = result.body.match(/<link\s+rel=["']canonical["']/i);
    if (!canonical) {
      issues.push({ icon: '🔗', issue: 'Missing canonical URL tag', detail: 'Google may index duplicate versions of your pages, diluting your SEO.' });
    }
    const viewport = result.body.match(/<meta\s+name=["']viewport["']/i);
    if (!viewport) {
      issues.push({ icon: '📱', issue: 'Missing viewport meta tag', detail: 'Your site may not display properly on mobile devices.' });
    }
    const h1Match = result.body.match(/<h1[^>]*>/gi);
    if (!h1Match) {
      issues.push({ icon: '📝', issue: 'No H1 heading found', detail: 'Every page needs one clear H1 heading for SEO and accessibility.' });
    } else if (h1Match.length > 1) {
      issues.push({ icon: '📝', issue: `Multiple H1 headings (${h1Match.length})`, detail: 'Best practice is exactly one H1 per page for clear content hierarchy.' });
    }
    const structuredData = result.body.match(/<script\s+type=["']application\/ld\+json["']/i);
    if (!structuredData) {
      issues.push({ icon: '🔍', issue: 'No structured data (Schema.org)', detail: 'You\'re missing out on rich snippets in Google search results.' });
    }
    
    // Show max 3 free, tease the rest
    // Show ALL issues free — builds trust, increases engagement
    // Email gate is now for PDF report + fix instructions (stronger value exchange)
    const freeIssues = issues;
    const hiddenCount = Math.max(issues.length, 3); // Full audit finds even more
    const score = Math.max(15, 100 - (issues.length * 7));

    // Log every scan for warm lead tracking
    const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress || '';
    const referer = req.headers.referer || '';
    const scanLine = `${new Date().toISOString()},${targetUrl},${score},${issues.length},${ip.split(',')[0].trim()},${referer}\n`;
    fs.appendFile(SCANS_FILE, scanLine, () => {});
    console.log(`SCAN: ${targetUrl} | score: ${score} | issues: ${issues.length}`);

    res.json({
      url: targetUrl,
      issuesFound: issues.length,
      freePreview: freeIssues,
      moreIssues: hiddenCount,
      score,
      orderLink: 'https://buy.stripe.com/7sYeVfdxJ8HL4mN2ktes003'
    });
  } catch (err) {
    res.status(500).json({ error: `Could not scan site: ${err.message}` });
  }
});

// Create Stripe Checkout Session with pre-filled email (captures lead even if they abandon)
app.post('/api/create-checkout', express.json(), async (req, res) => {
  const { email, url } = req.body;
  if (!email || !email.includes('@')) return res.status(400).json({ error: 'Valid email required' });

  console.log(`CHECKOUT INITIATED: ${email} | site: ${url}`);

  // Log lead immediately (before they even complete checkout)
  const fs = require('fs');
  const leadLine = `${new Date().toISOString()},${email},${url || ''},checkout_initiated,pre-payment\n`;
  fs.appendFileSync(LEADS_FILE, leadLine);

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      customer_email: email,
      line_items: [{
        price: 'price_1TECTeRz4FTeJoj7NbHBkNty', // $9 intro price
        quantity: 1,
      }],
      metadata: {
        website_url: url,
        source: 'free_checker_upsell'
      },
      success_url: `https://summitwebaudit.com/thank-you?email=${encodeURIComponent(email)}&url=${encodeURIComponent(url || '')}`,
      cancel_url: 'https://summitwebaudit.com/check',
    });
    
    console.log(`Stripe session created: ${session.id} for ${email}`);
    res.json({ checkoutUrl: session.url });
  } catch (err) {
    console.error('Stripe checkout error:', err.message);
    res.status(500).json({ error: 'Could not create checkout. Please try again.' });
  }
});

// Email lead capture from free checker
app.post('/api/capture-lead', express.json(), async (req, res) => {
  const { email, url, score, issues } = req.body;
  if (!email || !email.includes('@')) return res.status(400).json({ error: 'Valid email required' });

  console.log(`LEAD CAPTURED: ${email} | site: ${url} | score: ${score} | issues: ${issues}`);

  // Send results email via Resend
  try {
    const resendKey = process.env.RESEND_API_KEY;
    if (resendKey) {
      const fetch = require('node-fetch');
      await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${resendKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: 'Steve at Summit Web Audit <steve@summitwebaudit.com>',
          reply_to: 'steve@summitwebaudit.com',
          to: email,
          subject: `Your Website Score: ${score || '??'}/100 — Here's What to Fix`,
          headers: {
            'List-Unsubscribe': '<mailto:steve@summitwebaudit.com?subject=unsubscribe>',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'
          },
          text: `Your Website Health Report\n\nHey there,\n\nThanks for running your site through our free checker. Here's a quick summary:\n\nScore: ${score || '??'}/100 for ${url || 'your site'}\nIssues found: ${issues || 'several'}\n\n3 quick wins you can do right now:\n1. Check your page speed — Run your site through Google PageSpeed (https://pagespeed.web.dev) and aim for 60+ on mobile.\n2. Add missing meta descriptions — Every page needs a unique, compelling 150-character description.\n3. Verify your SSL certificate — Make sure the padlock icon shows on every page.\n\nWant the full picture? Get a comprehensive 50-point audit for $9 (intro price):\nhttps://summitwebaudit.com/check\n\nQuestions? Just reply to this email. I read every one.\n\n— Steve\nSummit Web Audit`,
          html: `
            <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
              <h2 style="color: #1e293b;">Your Website Health Report</h2>
              <p>Hey there,</p>
              <p>Thanks for running your site through our free checker. Here's a quick summary:</p>
              <div style="background: #f1f5f9; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0;">
                <div style="font-size: 48px; font-weight: 800; color: ${(score >= 70) ? '#16a34a' : (score >= 40) ? '#ca8a04' : '#dc2626'};">${score || '??'}/100</div>
                <div style="color: #64748b; margin-top: 4px;">Website Health Score for ${url || 'your site'}</div>
              </div>
              <p>We found <strong>${issues || 'several'} issues</strong> during the scan. Here are 3 quick wins you can do right now:</p>
              <ol>
                <li><strong>Check your page speed</strong> — Run your site through <a href="https://pagespeed.web.dev">Google PageSpeed</a> and aim for 60+ on mobile.</li>
                <li><strong>Add missing meta descriptions</strong> — Every page needs a unique, compelling 150-character description.</li>
                <li><strong>Verify your SSL certificate</strong> — Make sure the padlock icon shows on every page, not just the homepage.</li>
              </ol>
              <p>Want the full picture? Our comprehensive 50-point audit covers everything — SEO, security, performance, accessibility, mobile, and content — with specific fix instructions for each issue.</p>
              <div style="text-align: center; margin: 24px 0;">
                <a href="https://summitwebaudit.com/check" style="display: inline-block; padding: 14px 36px; background: #2563eb; color: white; font-weight: 700; border-radius: 8px; text-decoration: none;">Get Your Full Audit — $9 (Intro Price)</a>
              </div>
              <p style="color: #64748b; font-size: 0.85rem;">Questions? Just reply to this email. I read every one.</p>
              <p>— Steve<br>Summit Web Audit</p>
            </div>
          `
        })
      });
      console.log(`Results email sent to ${email}`);
    }
  } catch (err) {
    console.error('Failed to send lead email:', err.message);
  }

  // Log to a leads file for tracking
  const fs = require('fs');
  const leadLine = `${new Date().toISOString()},${email},${url || ''},${score || ''},${issues || ''}\n`;
  fs.appendFileSync(LEADS_FILE, leadLine);

  res.json({ ok: true });
});

// Inbound email webhook (Resend)
app.post('/inbound', express.json(), async (req, res) => {
  const data = req.body;
  console.log('Inbound email received:', JSON.stringify(data).substring(0, 500));

  // Loop prevention — aggressive
  const from = (data.from || '').toLowerCase();
  const subject = (data.subject || '').toLowerCase();
  const isLoop = from.includes('summitwebaudit.com') ||
    from.includes('noreply') || from.includes('no-reply') || from.includes('donotreply') ||
    from.includes('mailer-daemon') || from.includes('postmaster') ||
    subject.startsWith('automatic reply') || subject.startsWith('auto-reply') ||
    subject.startsWith('out of office') || subject.includes('auto-notification') ||
    subject.match(/^re:\s*re:/i) ||  // Double Re: = auto-reply chain
    (subject.match(/^re:/i) && from.includes('app@')) ||  // App auto-responders
    subject.includes('undeliverable') || subject.includes('delivery status') ||
    subject.includes('your mail to');  // Generic auto-reply pattern
  if (isLoop) {
    console.log(`Skipping auto-reply (loop prevention): from=${from} subject=${subject}`);
    return res.json({ received: true, skipped: true });
  }

  // Auto-reply ONLY to new conversations (not replies)
  const isReply = subject.startsWith('re:');
  if (!isReply) {
    try {
      const resendKey = process.env.RESEND_API_KEY;
      if (resendKey && from) {
        const fetch = require('node-fetch');
        await fetch('https://api.resend.com/emails', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${resendKey}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from: 'Steve at Summit Web Audit <steve@summitwebaudit.com>',
            to: from,
            subject: `Re: ${data.subject || 'Your message'}`,
            html: `<p>Hey! Thanks for reaching out. I got your message and will get back to you within 24 hours.</p><p>In the meantime, you can check your website health score for free at <a href="https://summitwebaudit.com/check">summitwebaudit.com/check</a>.</p><p>— Steve<br>Summit Web Audit</p>`
          })
        });
        console.log(`Auto-reply sent to ${from}`);
      }
    } catch (err) {
      console.error('Auto-reply error:', err.message);
    }
  } else {
    console.log(`Skipping auto-reply (is a reply): from=${from} subject=${subject}`);
  }

  res.json({ received: true });
});

// Internal API: get scan log (protected by simple key)
app.get('/api/scans', (req, res) => {
  const key = req.query.key;
  if (key !== process.env.INTERNAL_API_KEY) return res.status(403).json({ error: 'unauthorized' });
  try {
    const data = fs.readFileSync(SCANS_FILE, 'utf8');
    const lines = data.trim().split('\n').filter(l => l);
    const scans = lines.map(l => {
      const [timestamp, url, score, issues, ip, referer] = l.split(',');
      return { timestamp, url, score, issues, ip, referer };
    });
    res.json({ count: scans.length, scans });
  } catch (e) {
    res.json({ count: 0, scans: [] });
  }
});

// Internal API: get leads log (protected by simple key)
app.get('/api/leads', (req, res) => {
  const key = req.query.key;
  if (key !== process.env.INTERNAL_API_KEY) return res.status(403).json({ error: 'unauthorized' });
  try {
    const data = fs.readFileSync(LEADS_FILE, 'utf8');
    const lines = data.trim().split('\n').filter(l => l);
    const leads = lines.map(l => {
      const parts = l.split(',');
      return { timestamp: parts[0], email: parts[1], url: parts[2], score: parts[3], status: parts[4] };
    });
    res.json({ count: leads.length, leads });
  } catch (e) {
    res.json({ count: 0, leads: [] });
  }
});

// --- PDF Lead Magnet email gate ---
app.post('/api/pdf-lead', express.json(), async (req, res) => {
  const { email, source } = req.body;
  if (!email || !email.includes('@')) return res.status(400).json({ error: 'Valid email required' });
  console.log(`PDF LEAD: ${email} | source: ${source || 'unknown'}`);

  // Log lead
  const leadLine = `${new Date().toISOString()},${email},,pdf_download,${source || 'blog'}\n`;
  fs.appendFileSync(LEADS_FILE, leadLine);

  // Send email with PDF link + upsell
  try {
    const resendKey = process.env.RESEND_API_KEY;
    if (resendKey) {
      const fetch = require('node-fetch');
      await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${resendKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: 'Steve at Summit Web Audit <steve@summitwebaudit.com>',
          reply_to: 'steve@summitwebaudit.com',
          to: email,
          subject: 'Your Free 10-Point Website Audit Checklist',
          headers: { 'List-Unsubscribe': '<mailto:steve@summitwebaudit.com?subject=unsubscribe>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click' },
          text: `Here's your free 10-Point Website Audit Checklist:\n\nhttps://summitwebaudit.com/10-point-website-audit.pdf\n\nThis covers the 10 most critical things every business website needs to get right — from SSL and speed to SEO and mobile.\n\nWant us to run all 50 checks on your site? Get a full audit report for just $9:\nhttps://summitwebaudit.com/check\n\n— Steve\nSummit Web Audit`,
          html: `<div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
            <h2 style="color:#1e293b;">Your Free 10-Point Website Audit Checklist</h2>
            <p>Hey there! Here's your checklist as promised:</p>
            <div style="text-align:center;margin:24px 0;">
              <a href="https://summitwebaudit.com/10-point-website-audit.pdf" style="display:inline-block;padding:14px 36px;background:#2563eb;color:white;font-weight:700;border-radius:8px;text-decoration:none;">📥 Download Your PDF</a>
            </div>
            <p>This covers the 10 most critical things every business website needs to get right — from SSL and speed to SEO and mobile.</p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
            <p><strong>Want the full picture?</strong> Our comprehensive 50-point audit covers everything the checklist does and more — with specific fix instructions for your site.</p>
            <div style="text-align:center;margin:20px 0;">
              <a href="https://summitwebaudit.com/check" style="display:inline-block;padding:12px 32px;background:#7c3aed;color:white;font-weight:700;border-radius:8px;text-decoration:none;">Get Your Full Audit — $9</a>
            </div>
            <p style="color:#64748b;font-size:0.85rem;">Questions? Just reply to this email.</p>
            <p>— Steve<br>Summit Web Audit</p>
          </div>`
        })
      });
    }
  } catch (err) { console.error('PDF lead email error:', err.message); }

  res.json({ ok: true, downloadUrl: '/10-point-website-audit.pdf' });
});

// --- Dynamic OG Score Image ---
app.get('/og/:id.png', (req, res) => {
  const filePath = path.join(SHARES_DIR, `${req.params.id}.json`);
  let data = null;
  try { data = JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch (e) {}
  if (!data) return res.status(404).send('Not found');

  const score = data.score;
  const color = score >= 70 ? '#34d399' : score >= 40 ? '#fbbf24' : '#f87171';
  const label = score >= 70 ? 'Good' : score >= 40 ? 'Needs Work' : 'Critical Issues';
  const domain = data.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  const issues = data.issuesFound || '?';

  // Generate SVG
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
    <rect width="1200" height="630" fill="#0f172a"/>
    <circle cx="600" cy="240" r="130" fill="none" stroke="${color}" stroke-width="16"/>
    <text x="600" y="260" text-anchor="middle" font-family="Arial,sans-serif" font-size="96" font-weight="bold" fill="${color}">${score}</text>
    <text x="600" y="310" text-anchor="middle" font-family="Arial,sans-serif" font-size="24" fill="#94a3b8">/100</text>
    <text x="600" y="410" text-anchor="middle" font-family="Arial,sans-serif" font-size="32" font-weight="bold" fill="${color}">${label}</text>
    <text x="600" y="460" text-anchor="middle" font-family="Arial,sans-serif" font-size="24" fill="#94a3b8">${domain} · ${issues} issues found</text>
    <text x="600" y="560" text-anchor="middle" font-family="Arial,sans-serif" font-size="22" fill="#60a5fa">summitwebaudit.com/check</text>
    <text x="600" y="590" text-anchor="middle" font-family="Arial,sans-serif" font-size="16" fill="#475569">Free Website Health Check</text>
  </svg>`;

  // Convert SVG to PNG using ImageMagick
  const { execSync } = require('child_process');
  try {
    const pngBuffer = execSync('convert svg:- png:-', { input: svg, maxBuffer: 2 * 1024 * 1024 });
    res.set('Content-Type', 'image/png');
    res.set('Cache-Control', 'public, max-age=86400');
    res.send(pngBuffer);
  } catch (err) {
    // Fallback: serve SVG directly
    res.set('Content-Type', 'image/svg+xml');
    res.set('Cache-Control', 'public, max-age=86400');
    res.send(svg);
  }
});

// --- Share Your Score feature ---
const crypto = require('crypto');

// Create a shareable result
app.post('/api/share-result', express.json(), (req, res) => {
  const { url, score, issuesFound } = req.body;
  if (!url || score === undefined) return res.status(400).json({ error: 'url and score required' });
  const id = crypto.randomBytes(6).toString('hex'); // 12-char unique id
  const shareData = { id, url, score, issuesFound, created: new Date().toISOString() };
  fs.writeFileSync(path.join(SHARES_DIR, `${id}.json`), JSON.stringify(shareData));
  console.log(`SHARE CREATED: ${id} | ${url} | score ${score}`);
  res.json({ shareUrl: `https://summitwebaudit.com/results/${id}` });
});

// Serve shareable results page with dynamic OG tags
app.get('/results/:id', (req, res) => {
  const filePath = path.join(SHARES_DIR, `${req.params.id}.json`);
  let data = null;
  try { data = JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch (e) {}
  if (!data) return res.status(404).send('Result not found');

  const scoreColor = data.score >= 70 ? '#34d399' : data.score >= 40 ? '#fbbf24' : '#f87171';
  const scoreLabel = data.score >= 70 ? 'Good' : data.score >= 40 ? 'Needs Work' : 'Critical Issues';
  const domain = data.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  const ogTitle = `${domain} scored ${data.score}/100 — Website Health Check`;
  const ogDesc = `${data.issuesFound || 'Multiple'} issues found. Check your own site free at Summit Web Audit.`;

  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${ogTitle}</title>
  <meta name="description" content="${ogDesc}">
  <meta property="og:title" content="${ogTitle}">
  <meta property="og:description" content="${ogDesc}">
  <meta property="og:url" content="https://summitwebaudit.com/results/${data.id}">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://summitwebaudit.com/og/${data.id}.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${ogTitle}">
  <meta name="twitter:description" content="${ogDesc}">
  <meta name="twitter:site" content="@SummitWebAudit">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { max-width: 520px; width: 100%; margin: 40px 24px; text-align: center; }
    .score-ring { width: 180px; height: 180px; border-radius: 50%; border: 8px solid ${scoreColor}; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
    .score-num { font-size: 3.5rem; font-weight: 800; color: ${scoreColor}; }
    .score-label { font-size: 1.1rem; color: ${scoreColor}; font-weight: 600; margin-bottom: 8px; }
    .domain { font-size: 1.4rem; color: #94a3b8; margin-bottom: 4px; word-break: break-all; }
    .issues { color: #94a3b8; margin-bottom: 32px; }
    .cta { display: inline-block; padding: 16px 48px; background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; font-weight: 700; font-size: 1.1rem; border-radius: 12px; text-decoration: none; margin-bottom: 16px; }
    .cta:hover { transform: translateY(-1px); }
    .powered { color: #475569; font-size: 0.85rem; margin-top: 24px; }
    .powered a { color: #60a5fa; text-decoration: none; }
    .share-row { display: flex; gap: 12px; justify-content: center; margin-top: 20px; flex-wrap: wrap; }
    .share-btn { padding: 10px 20px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; text-decoration: none; color: white; }
    .share-tw { background: #1da1f2; }
    .share-li { background: #0077b5; }
    .share-fb { background: #1877f2; }
  </style>
</head>
<body>
  <div class="card">
    <div class="score-ring"><span class="score-num">${data.score}</span></div>
    <div class="score-label">${scoreLabel}</div>
    <div class="domain">${domain}</div>
    <div class="issues">${data.issuesFound || 'Multiple'} issues found</div>
    <a class="cta" href="/check">Check Your Website Free →</a>
    <div class="share-row">
      <a class="share-btn share-tw" href="https://twitter.com/intent/tweet?text=${encodeURIComponent(`My website scored ${data.score}/100 on a health check 👀 Check yours free:`)}&url=${encodeURIComponent(`https://summitwebaudit.com/results/${data.id}`)}" target="_blank">𝕏 Tweet</a>
      <a class="share-btn share-li" href="https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(`https://summitwebaudit.com/results/${data.id}`)}" target="_blank">LinkedIn</a>
      <a class="share-btn share-fb" href="https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(`https://summitwebaudit.com/results/${data.id}`)}" target="_blank">Facebook</a>
    </div>
    <div class="powered">Powered by <a href="/">Summit Web Audit</a></div>
  </div>
</body>
</html>`);
});

// Engagement tracking endpoint
const ENGAGE_FILE = path.join(DATA_DIR, 'engagement.csv');
app.post('/api/engage', express.json(), (req, res) => {
  const { page, timeOnPage, maxScroll, scanClicked, utm } = req.body || {};
  const line = `${new Date().toISOString()},${page || ''},${timeOnPage || 0},${maxScroll || 0},${scanClicked || false},${utm || ''}\n`;
  fs.appendFile(ENGAGE_FILE, line, () => {});
  res.json({ ok: true });
});

// --- Dynamic OG image generator ---
app.get('/og/:id.png', async (req, res) => {
  try {
    const shareFile = path.join(SHARES_DIR, `${req.params.id}.json`);
    let data;
    try { data = JSON.parse(fs.readFileSync(shareFile, 'utf8')); } catch(e) { return res.status(404).send('Not found'); }
    
    const { createCanvas } = require('canvas');
    const canvas = createCanvas(1200, 630);
    const ctx = canvas.getContext('2d');
    
    // Background
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, 1200, 630);
    
    // Score circle
    const score = data.score || 0;
    const cx = 600, cy = 240, r = 120;
    const color = score >= 70 ? '#34d399' : score >= 40 ? '#fbbf24' : '#f87171';
    
    // Circle background
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 16;
    ctx.stroke();
    
    // Score arc
    const startAngle = -Math.PI / 2;
    const endAngle = startAngle + (score / 100) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = color;
    ctx.lineWidth = 16;
    ctx.lineCap = 'round';
    ctx.stroke();
    
    // Score text
    ctx.fillStyle = color;
    ctx.font = 'bold 72px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${score}`, cx, cy - 5);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '24px sans-serif';
    ctx.fillText('/100', cx, cy + 40);
    
    // Domain
    const domain = (data.url || '').replace(/^https?:\/\//, '').replace(/\/.*$/, '');
    ctx.fillStyle = '#e2e8f0';
    ctx.font = 'bold 36px sans-serif';
    ctx.fillText(domain, cx, 410);
    
    // Issues
    ctx.fillStyle = '#94a3b8';
    ctx.font = '24px sans-serif';
    ctx.fillText(`${data.issuesFound || 'Multiple'} issues found`, cx, 455);
    
    // Branding
    ctx.fillStyle = '#60a5fa';
    ctx.font = 'bold 28px sans-serif';
    ctx.fillText('⚡ Summit Web Audit', cx, 560);
    ctx.fillStyle = '#64748b';
    ctx.font = '20px sans-serif';
    ctx.fillText('summitwebaudit.com/check', cx, 595);
    
    res.setHeader('Content-Type', 'image/png');
    res.setHeader('Cache-Control', 'public, max-age=86400');
    canvas.createPNGStream().pipe(res);
  } catch(err) {
    console.error('OG image error:', err);
    res.status(500).send('Error generating image');
  }
});

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Free checker page
app.get('/check', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'check.html'));
});

// Blog content service page
app.get('/content', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'content.html'));
});

// Blog posts
app.get('/blog/free-website-audit-checklist', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'free-website-audit-checklist.html'));
});

app.get('/blog/why-small-business-website-security-matters', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'why-small-business-website-security-matters.html'));
});

app.get('/blog', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'index.html'));
});

app.get('/blog/is-your-website-hipaa-compliant', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'is-your-website-hipaa-compliant.html'));
});

app.get('/blog/5-website-mistakes-costing-customers', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', '5-website-mistakes-costing-customers.html'));
});
app.get('/blog/is-your-medical-website-hipaa-compliant', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'is-your-medical-website-hipaa-compliant.html'));
});
app.get('/blog/ecommerce-website-security-checklist', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'ecommerce-website-security-checklist.html'));
});
app.get('/blog/free-website-audit-tool-small-business', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', 'free-website-audit-tool-small-business.html'));
});

// Block common vulnerability probes
app.use((req, res, next) => {
  const blocked = ['.env', 'wp-login', 'wp-admin', 'xmlrpc', 'wlwmanifest', '.git', '.sql', 'phpmyadmin'];
  if (blocked.some(b => req.path.toLowerCase().includes(b))) {
    return res.status(404).send('Not found');
  }
  next();
});

// Quick analytics stats endpoint (internal use)
app.get('/api/stats', (req, res) => {
  try {
    if (!fs.existsSync(ANALYTICS_FILE)) return res.json({ views: 0, message: 'No data yet' });
    const lines = fs.readFileSync(ANALYTICS_FILE, 'utf8').trim().split('\n').filter(l => l);
    const dateFilter = req.query.date || new Date().toISOString().split('T')[0];
    const fromDate = req.query.from;
    const toDate = req.query.to;
    let filtered;
    if (fromDate && toDate) {
      filtered = lines.filter(l => l.substring(0,10) >= fromDate && l.substring(0,10) <= toDate);
    } else {
      filtered = lines.filter(l => l.startsWith(dateFilter));
    }
    const pages = {};
    const sources = {};
    filtered.forEach(l => {
      const parts = l.split(',');
      const p = parts[1] || '/';
      const src = parts[2] || 'direct';
      pages[p] = (pages[p] || 0) + 1;
      if (src) sources[src] = (sources[src] || 0) + 1;
    });
    res.json({ total_views: lines.length, filtered_views: filtered.length, date: fromDate ? `${fromDate} to ${toDate}` : dateFilter, pages, sources });
  } catch (e) {
    res.json({ error: e.message });
  }
});

// Thank you page after purchase
app.get('/thank-you', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'thank-you.html'));
});

// Catch-all: serve index.html for SPA-like routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Summit Web Audit server running on port ${PORT}`);
});
