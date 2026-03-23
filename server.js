const express = require('express');
const path = require('path');
const { execSync, spawn } = require('child_process');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

const app = express();
const PORT = process.env.PORT || 3000;

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
    const https = require('https');
    const http = require('http');
    const { URL } = require('url');
    
    let targetUrl = url.startsWith('http') ? url : `https://${url}`;
    const parsed = new URL(targetUrl);
    const issues = [];
    
    const fetcher = targetUrl.startsWith('https') ? https : http;
    
    const fetchPage = () => new Promise((resolve, reject) => {
      const req = fetcher.get(targetUrl, { timeout: 10000, headers: { 'User-Agent': 'SummitWebAudit/1.0' } }, (response) => {
        let data = '';
        response.on('data', chunk => data += chunk);
        response.on('end', () => resolve({ headers: response.headers, statusCode: response.statusCode, body: data }));
      });
      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    });
    
    const start = Date.now();
    const result = await fetchPage();
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
    
    // Show max 3 free, tease the rest
    const freeIssues = issues.slice(0, 3);
    const hiddenCount = Math.max(issues.length - 3, 2); // Always imply there's more
    
    res.json({
      url: targetUrl,
      issuesFound: issues.length,
      freePreview: freeIssues,
      moreIssues: hiddenCount,
      score: Math.max(20, 100 - (issues.length * 12)),
      orderLink: 'https://buy.stripe.com/7sYeVfdxJ8HL4mN2ktes003'
    });
  } catch (err) {
    res.status(500).json({ error: `Could not scan site: ${err.message}` });
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

// Catch-all: serve index.html for SPA-like routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Summit Web Audit server running on port ${PORT}`);
});
