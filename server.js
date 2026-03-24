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
const ANALYTICS_FILE = path.join(__dirname, 'analytics.csv');
app.use((req, res, next) => {
  // Only log GET requests to pages (not API calls, assets, etc.)
  if (req.method === 'GET' && !req.path.match(/\.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|map)$/)) {
    const line = `${new Date().toISOString()},${req.path},${req.query.utm_source || ''},${req.headers.referer || ''},${(req.headers['user-agent'] || '').substring(0, 100)}\n`;
    fs.appendFile(ANALYTICS_FILE, line, () => {});
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
    const freeIssues = issues.slice(0, 3);
    const hiddenCount = Math.max(issues.length - 3, 2); // Always imply there's more
    
    res.json({
      url: targetUrl,
      issuesFound: issues.length,
      freePreview: freeIssues,
      moreIssues: hiddenCount,
      score: Math.max(15, 100 - (issues.length * 7)),
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
  fs.appendFileSync(path.join(__dirname, 'leads.csv'), leadLine);

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
          to: email,
          subject: `Your Website Score: ${score || '??'}/100 — Here's What to Fix`,
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
                <a href="https://buy.stripe.com/7sYeVfdxJ8HL4mN2ktes003" style="display: inline-block; padding: 14px 36px; background: #2563eb; color: white; font-weight: 700; border-radius: 8px; text-decoration: none;">Get Your Full Audit — $9 (Intro Price)</a>
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
  fs.appendFileSync(path.join(__dirname, 'leads.csv'), leadLine);

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

  // Auto-reply
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

  res.json({ received: true });
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

app.get('/blog/5-website-mistakes-costing-customers', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'blog', '5-website-mistakes-costing-customers.html'));
});

// Quick analytics stats endpoint (internal use)
app.get('/api/stats', (req, res) => {
  try {
    if (!fs.existsSync(ANALYTICS_FILE)) return res.json({ views: 0, message: 'No data yet' });
    const lines = fs.readFileSync(ANALYTICS_FILE, 'utf8').trim().split('\n').filter(l => l);
    const today = new Date().toISOString().split('T')[0];
    const todayLines = lines.filter(l => l.startsWith(today));
    const pages = {};
    todayLines.forEach(l => {
      const p = l.split(',')[1] || '/';
      pages[p] = (pages[p] || 0) + 1;
    });
    res.json({ total_views: lines.length, today_views: todayLines.length, today_pages: pages });
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
