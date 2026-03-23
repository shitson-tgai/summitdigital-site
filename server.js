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
  res.redirect(302, 'https://buy.stripe.com/5kQbJ31P11fj7yZgbjes000');
});

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// Catch-all: serve index.html for SPA-like routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Summit Web Audit server running on port ${PORT}`);
});
