#!/usr/bin/env python3
"""
Website Audit Script — Summit Digital
Runs 50+ comprehensive checks and outputs structured JSON.

Usage: python3 audit-site.py <url>
"""

import sys
import json
import time
import re
from urllib.parse import urlparse, urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing dependencies...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "-q"])
    import requests
    from bs4 import BeautifulSoup


UA = "SummitDigital-AuditBot/1.0"


def check_url(url):
    """Normalize and validate URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def check_response(url):
    """Check HTTP response, timing, redirects."""
    results = {
        "url": url,
        "status_code": None,
        "ttfb_ms": None,
        "total_time_ms": None,
        "redirects": [],
        "final_url": None,
        "uses_https": False,
        "content_length": None,
        "content_encoding": None,
        "server": None,
        "errors": []
    }

    resp = None
    try:
        start = time.time()
        resp = requests.get(url, timeout=15, allow_redirects=True,
                            headers={"User-Agent": UA, "Accept-Encoding": "gzip, deflate, br"})
        total = (time.time() - start) * 1000

        results["status_code"] = resp.status_code
        results["total_time_ms"] = round(total, 1)
        results["final_url"] = resp.url
        results["uses_https"] = resp.url.startswith("https://")
        results["content_length"] = len(resp.content)
        results["content_encoding"] = resp.headers.get("Content-Encoding")
        results["server"] = resp.headers.get("Server")

        for r in resp.history:
            results["redirects"].append({"status": r.status_code, "url": r.url})

        if hasattr(resp, 'elapsed'):
            results["ttfb_ms"] = round(resp.elapsed.total_seconds() * 1000, 1)

    except requests.exceptions.SSLError:
        results["errors"].append("SSL certificate error")
    except requests.exceptions.ConnectionError:
        results["errors"].append("Connection failed")
    except requests.exceptions.Timeout:
        results["errors"].append("Request timed out (>15s)")
    except Exception as e:
        results["errors"].append(str(e))

    if results["status_code"]:
        return results, resp
    return results, None


def make_check(id, name, category, status, severity, current_value, recommendation, how_to_fix):
    return {
        "id": id,
        "name": name,
        "category": category,
        "status": status,
        "severity": severity,
        "current_value": str(current_value),
        "recommendation": recommendation,
        "how_to_fix": how_to_fix
    }


def run_seo_checks(soup, resp, response_data, robots_sitemap):
    """Run all SEO checks. Returns list of check dicts."""
    checks = []
    url = response_data["final_url"] or response_data["url"]
    parsed_url = urlparse(url)

    # 1. Title tag presence
    title_tag = soup.find("title")
    title_text = title_tag.get_text().strip() if title_tag else ""
    if not title_tag or not title_text:
        checks.append(make_check("seo-title-present", "Title Tag Present", "seo", "fail", "critical",
            "Missing", "Add a unique, descriptive <title> tag to every page.",
            "WordPress: Install Yoast SEO, go to each page and fill in the 'SEO title' field. Squarespace: Settings > SEO > Homepage Title. Wix: Pages > SEO > Title Tag. Shopify: Online Store > Preferences > Title. Custom: Add <title>Your Title</title> inside <head>."))
    else:
        checks.append(make_check("seo-title-present", "Title Tag Present", "seo", "pass", "critical",
            title_text[:80], "Title tag is present.", "No action needed."))

    # 2. Title length
    title_len = len(title_text)
    if title_text:
        if 30 <= title_len <= 60:
            checks.append(make_check("seo-title-length", "Title Tag Length", "seo", "pass", "warning",
                f"{title_text} ({title_len} chars)", "Title length is optimal (30-60 characters).", "No action needed."))
        elif title_len < 30:
            checks.append(make_check("seo-title-length", "Title Tag Length", "seo", "warning", "warning",
                f"{title_text} ({title_len} chars)", f"Title is too short at {title_len} characters. Aim for 30-60 characters to maximize search visibility.",
                "WordPress: Edit the SEO title in Yoast/RankMath to include your primary keyword + brand. Squarespace: Settings > SEO > edit title. Wix: Pages > SEO basics > Title. Shopify: Online Store > Preferences. Custom: Edit the <title> tag in your HTML <head>."))
        else:
            checks.append(make_check("seo-title-length", "Title Tag Length", "seo", "warning", "warning",
                f"{title_text[:50]}... ({title_len} chars)", f"Title is too long at {title_len} characters. Google truncates at ~60 chars.",
                "WordPress: Shorten the SEO title in Yoast/RankMath. Squarespace: Settings > SEO > shorten title. Wix: Pages > SEO basics > shorten title. Shopify: Online Store > Preferences > shorten. Custom: Edit <title> tag to under 60 characters."))

    # 3. Meta description
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc_text = desc_tag.get("content", "").strip() if desc_tag else ""
    if not desc_text:
        checks.append(make_check("seo-meta-description", "Meta Description", "seo", "fail", "critical",
            "Missing", "Add a compelling meta description (70-160 chars) with your target keyword.",
            "WordPress: Yoast SEO > Edit page > Meta description field. Squarespace: Page Settings > SEO > Description. Wix: Pages > SEO > Description. Shopify: Online Store > Preferences > Description. Custom: Add <meta name=\"description\" content=\"Your description\"> in <head>."))
    elif len(desc_text) < 70:
        checks.append(make_check("seo-meta-description", "Meta Description", "seo", "warning", "warning",
            f"{desc_text} ({len(desc_text)} chars)", f"Meta description too short ({len(desc_text)} chars). Aim for 70-160 characters.",
            "Expand your meta description to include a call-to-action and target keyword. Same edit locations as above."))
    elif len(desc_text) > 160:
        checks.append(make_check("seo-meta-description", "Meta Description", "seo", "warning", "warning",
            f"{desc_text[:80]}... ({len(desc_text)} chars)", f"Meta description too long ({len(desc_text)} chars). Google truncates at ~160 chars.",
            "Trim your meta description to under 160 characters while keeping the key message upfront."))
    else:
        checks.append(make_check("seo-meta-description", "Meta Description", "seo", "pass", "warning",
            f"{desc_text[:80]}... ({len(desc_text)} chars)", "Meta description length is optimal.", "No action needed."))

    # 4. Canonical URL
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        checks.append(make_check("seo-canonical", "Canonical URL", "seo", "pass", "warning",
            canonical["href"], "Canonical tag is present.", "No action needed."))
    else:
        checks.append(make_check("seo-canonical", "Canonical URL", "seo", "fail", "warning",
            "Missing", "Add a canonical URL to prevent duplicate content issues.",
            "WordPress: Yoast SEO adds this automatically; check in Advanced > Canonical URL. Squarespace: Added automatically. Wix: Added automatically. Shopify: Added automatically via theme. Custom: Add <link rel=\"canonical\" href=\"https://yoursite.com/page\"> in <head>."))

    # 5. Open Graph tags
    og_tags = soup.find_all("meta", attrs={"property": re.compile(r"^og:")})
    og_dict = {t.get("property"): t.get("content") for t in og_tags}
    required_og = ["og:title", "og:description", "og:image", "og:url"]
    missing_og = [t for t in required_og if t not in og_dict]
    if not missing_og:
        checks.append(make_check("seo-og-tags", "Open Graph Tags", "seo", "pass", "warning",
            f"All present: {', '.join(required_og)}", "Open Graph tags are complete for social sharing.", "No action needed."))
    else:
        checks.append(make_check("seo-og-tags", "Open Graph Tags", "seo", "fail" if len(missing_og) >= 3 else "warning", "warning",
            f"Missing: {', '.join(missing_og)}", f"Add missing OG tags ({', '.join(missing_og)}) to improve social media sharing previews.",
            "WordPress: Yoast SEO > Social tab on each page. Squarespace: Page Settings > Social Image. Wix: SEO > Social Share. Shopify: Theme customizer > Social media. Custom: Add <meta property=\"og:title\" content=\"...\"> etc. in <head>."))

    # 6. H1 tag
    h1_tags = soup.find_all("h1")
    h1_count = len(h1_tags)
    if h1_count == 1:
        checks.append(make_check("seo-h1", "H1 Tag", "seo", "pass", "critical",
            h1_tags[0].get_text().strip()[:80], "Single H1 tag present — good.", "No action needed."))
    elif h1_count == 0:
        checks.append(make_check("seo-h1", "H1 Tag", "seo", "fail", "critical",
            "Missing", "Add exactly one H1 tag per page with your primary keyword.",
            "WordPress: The page title is usually H1 in most themes. Check your theme. Squarespace: The page title auto-generates H1. Wix: Add a heading block set to H1. Shopify: The page title is H1. Custom: Add <h1>Your Main Heading</h1> as the first heading on the page."))
    else:
        checks.append(make_check("seo-h1", "H1 Tag", "seo", "warning", "warning",
            f"{h1_count} H1 tags found", f"Multiple H1 tags ({h1_count}) — should have exactly one per page.",
            "WordPress: Edit page, ensure only the page title is H1; change others to H2. Squarespace: Check all text blocks, change extra H1s to H2. Wix: Edit headings in text blocks. Shopify: Edit page content in rich text editor. Custom: Find all <h1> tags and change extras to <h2>."))

    # 7. robots.txt
    if robots_sitemap["robots_txt"]:
        checks.append(make_check("seo-robots-txt", "robots.txt", "seo", "pass", "warning",
            "Found", "robots.txt is present.", "No action needed."))
    else:
        checks.append(make_check("seo-robots-txt", "robots.txt", "seo", "fail", "warning",
            "Missing", "Add a robots.txt file to guide search engine crawlers.",
            "WordPress: Yoast SEO creates this automatically; check Settings > Reading. Squarespace: Auto-generated. Wix: Auto-generated. Shopify: Auto-generated. Custom: Create a robots.txt file in your root directory with 'User-agent: *\\nAllow: /\\nSitemap: https://yoursite.com/sitemap.xml'."))

    # 8. sitemap.xml
    if robots_sitemap["sitemap_xml"]:
        checks.append(make_check("seo-sitemap", "XML Sitemap", "seo", "pass", "warning",
            "Found", "XML sitemap is present.", "No action needed."))
    else:
        checks.append(make_check("seo-sitemap", "XML Sitemap", "seo", "fail", "warning",
            "Missing", "Create and submit an XML sitemap so search engines can discover all your pages.",
            "WordPress: Yoast SEO auto-generates at /sitemap_index.xml. Squarespace: Auto-generated at /sitemap.xml. Wix: Auto-generated. Shopify: Auto-generated at /sitemap.xml. Custom: Use a sitemap generator tool, upload to root, and submit in Google Search Console."))

    # 9. Favicon
    favicon = soup.find("link", attrs={"rel": re.compile(r"icon", re.I)})
    if favicon:
        checks.append(make_check("seo-favicon", "Favicon", "seo", "pass", "info",
            favicon.get("href", "Present"), "Favicon is present.", "No action needed."))
    else:
        checks.append(make_check("seo-favicon", "Favicon", "seo", "fail", "info",
            "Missing", "Add a favicon for better brand recognition in browser tabs and bookmarks.",
            "WordPress: Appearance > Customize > Site Identity > Site Icon. Squarespace: Design > Browser Icon. Wix: Settings > Favicon. Shopify: Online Store > Themes > Customize > Theme Settings > Favicon. Custom: Add <link rel=\"icon\" href=\"/favicon.ico\"> in <head>."))

    # 10. Language attribute
    html_tag = soup.find("html")
    lang = html_tag.get("lang") if html_tag else None
    if lang:
        checks.append(make_check("seo-lang", "Language Attribute", "seo", "pass", "info",
            lang, "Language attribute is set on <html> tag.", "No action needed."))
    else:
        checks.append(make_check("seo-lang", "Language Attribute", "seo", "fail", "info",
            "Missing", "Add lang attribute to <html> tag for better SEO and accessibility.",
            "WordPress: Usually set by theme; check header.php for <html lang>. Squarespace: Set automatically. Wix: Set automatically. Shopify: Check theme.liquid. Custom: Add lang=\"en\" to your <html> tag."))

    # 11. Schema.org / JSON-LD
    json_ld = soup.find_all("script", attrs={"type": "application/ld+json"})
    if json_ld:
        try:
            schema_data = json.loads(json_ld[0].string or "{}")
            schema_type = schema_data.get("@type", "Unknown")
        except (json.JSONDecodeError, TypeError):
            schema_type = "Present (parse error)"
        checks.append(make_check("seo-schema", "Schema.org / JSON-LD", "seo", "pass", "warning",
            f"Found {len(json_ld)} block(s), type: {schema_type}", "Structured data is present.", "No action needed."))
    else:
        checks.append(make_check("seo-schema", "Schema.org / JSON-LD", "seo", "fail", "warning",
            "Missing", "Add JSON-LD structured data to help search engines understand your content and enable rich snippets.",
            "WordPress: Install Schema Pro or use Yoast's built-in schema. Squarespace: Add via Code Injection (Settings > Advanced > Code Injection). Wix: Add via Custom Code in head. Shopify: Many themes include it; add via theme.liquid. Custom: Add a <script type=\"application/ld+json\"> block with Organization, LocalBusiness, or WebPage schema."))

    # 12. Apple touch icon / theme-color
    apple_icon = soup.find("link", attrs={"rel": "apple-touch-icon"})
    theme_color = soup.find("meta", attrs={"name": "theme-color"})
    mobile_meta_status = "pass" if (apple_icon and theme_color) else ("warning" if (apple_icon or theme_color) else "fail")
    parts = []
    if apple_icon: parts.append("apple-touch-icon: present")
    else: parts.append("apple-touch-icon: missing")
    if theme_color: parts.append(f"theme-color: {theme_color.get('content', 'set')}")
    else: parts.append("theme-color: missing")
    checks.append(make_check("seo-mobile-meta", "Mobile Meta (apple-touch-icon, theme-color)", "seo",
        mobile_meta_status, "info", "; ".join(parts),
        "Add apple-touch-icon and theme-color meta for better mobile experience.",
        "WordPress: Appearance > Customize > Site Identity for icon; add theme-color in header.php or via plugin. Squarespace: Design > Browser Icon covers apple-touch-icon. Wix: Settings > Favicon. Shopify: Theme settings for icon. Custom: Add <link rel=\"apple-touch-icon\" href=\"/apple-touch-icon.png\"> and <meta name=\"theme-color\" content=\"#hexcolor\"> in <head>."))

    # 13. URL slug cleanliness
    path = parsed_url.path
    slug_clean = True
    slug_issues = []
    if re.search(r'[A-Z]', path):
        slug_issues.append("uppercase characters")
        slug_clean = False
    if re.search(r'[_]', path):
        slug_issues.append("underscores (use hyphens)")
        slug_clean = False
    if re.search(r'\.html?$|\.php$|\.asp', path):
        slug_issues.append("file extensions visible")
        slug_clean = False
    if re.search(r'[?&].*=', parsed_url.query):
        slug_issues.append("query parameters in URL")
    if slug_clean and not slug_issues:
        checks.append(make_check("seo-url-slug", "URL Slug Cleanliness", "seo", "pass", "info",
            path or "/", "URL structure is clean and SEO-friendly.", "No action needed."))
    else:
        checks.append(make_check("seo-url-slug", "URL Slug Cleanliness", "seo", "warning", "info",
            f"{path} — issues: {', '.join(slug_issues)}", "Clean up URL structure: use lowercase, hyphens, no file extensions.",
            "WordPress: Settings > Permalinks > Post name. Squarespace: Pages > Settings > URL Slug. Wix: Pages > SEO > URL. Shopify: Edit URL handle in page/product settings. Custom: Configure URL rewriting in .htaccess or nginx config."))

    # 14. Heading hierarchy (no skipped levels)
    heading_levels_found = []
    for level in range(1, 7):
        if soup.find(f"h{level}"):
            heading_levels_found.append(level)
    skipped = False
    for i in range(len(heading_levels_found) - 1):
        if heading_levels_found[i + 1] - heading_levels_found[i] > 1:
            skipped = True
            break
    if not skipped and heading_levels_found:
        checks.append(make_check("seo-heading-hierarchy", "Heading Hierarchy", "seo", "pass", "info",
            f"Levels used: {', '.join(f'H{l}' for l in heading_levels_found)}", "Heading hierarchy is logical with no skipped levels.", "No action needed."))
    elif not heading_levels_found:
        checks.append(make_check("seo-heading-hierarchy", "Heading Hierarchy", "seo", "fail", "warning",
            "No headings found", "Add proper heading structure (H1 > H2 > H3) for SEO and accessibility.",
            "Structure your content with a clear H1 > H2 > H3 hierarchy. Don't skip levels (e.g., H1 to H3)."))
    else:
        checks.append(make_check("seo-heading-hierarchy", "Heading Hierarchy", "seo", "warning", "info",
            f"Levels used: {', '.join(f'H{l}' for l in heading_levels_found)} (skipped levels)", "Heading levels are skipped. Use H1 > H2 > H3 in order without gaps.",
            "WordPress: Edit page content, change heading levels in block editor dropdown. Squarespace: Edit text blocks > change heading sizes. Wix: Edit heading elements. Shopify: Edit in rich text editor. Custom: Ensure <h1> then <h2> then <h3> — never skip a level."))

    # 15. Page indexability (noindex)
    noindex_meta = soup.find("meta", attrs={"name": "robots", "content": re.compile(r"noindex", re.I)})
    noindex_header = resp.headers.get("X-Robots-Tag", "") if resp else ""
    if noindex_meta or "noindex" in noindex_header.lower():
        checks.append(make_check("seo-indexability", "Page Indexability", "seo", "fail", "critical",
            "NOINDEX detected", "This page is blocked from search engine indexing! Remove the noindex directive if you want it to appear in search results.",
            "WordPress: Edit page > Yoast SEO > Advanced > set 'Allow search engines to show this page' to Yes. Squarespace: Page Settings > uncheck 'Disable Indexing'. Wix: Pages > SEO > remove noindex. Shopify: Check theme header for noindex meta. Custom: Remove <meta name=\"robots\" content=\"noindex\"> from <head>."))
    else:
        checks.append(make_check("seo-indexability", "Page Indexability", "seo", "pass", "critical",
            "Indexable", "Page is indexable by search engines.", "No action needed."))

    # 16. Twitter card meta
    twitter_tags = soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")})
    tw_dict = {t.get("name"): t.get("content") for t in twitter_tags}
    if "twitter:card" in tw_dict:
        checks.append(make_check("seo-twitter-card", "Twitter Card Meta", "seo", "pass", "info",
            f"card={tw_dict.get('twitter:card')}, {len(tw_dict)} tags total", "Twitter Card meta tags are present.", "No action needed."))
    else:
        checks.append(make_check("seo-twitter-card", "Twitter Card Meta", "seo", "warning", "info",
            "Missing", "Add Twitter Card meta tags for better link previews on Twitter/X.",
            "WordPress: Yoast SEO > Social > Twitter tab. Squarespace: Settings > Social Links + page social images. Wix: SEO > Social Share. Shopify: Most themes auto-generate from OG. Custom: Add <meta name=\"twitter:card\" content=\"summary_large_image\">, twitter:title, twitter:description, twitter:image in <head>."))

    # 17. Keyword alignment (title vs H1)
    h1_text = h1_tags[0].get_text().strip().lower() if h1_tags else ""
    title_lower = title_text.lower()
    if h1_text and title_text:
        h1_words = set(re.findall(r'\w+', h1_text)) - {"the", "a", "an", "and", "or", "of", "in", "to", "for", "is", "on", "at", "by"}
        title_words = set(re.findall(r'\w+', title_lower)) - {"the", "a", "an", "and", "or", "of", "in", "to", "for", "is", "on", "at", "by"}
        overlap = h1_words & title_words
        if len(overlap) >= 2 or (len(h1_words) <= 3 and len(overlap) >= 1):
            checks.append(make_check("seo-keyword-alignment", "Title/H1 Keyword Alignment", "seo", "pass", "info",
                f"Shared keywords: {', '.join(list(overlap)[:5])}", "Title and H1 share key terms — good keyword alignment.", "No action needed."))
        else:
            checks.append(make_check("seo-keyword-alignment", "Title/H1 Keyword Alignment", "seo", "warning", "info",
                f"Title: '{title_text[:40]}' vs H1: '{h1_text[:40]}'", "Title and H1 don't share keywords. Align them around your primary keyword for stronger SEO signals.",
                "Edit your H1 and title tag to include the same primary keyword. They don't need to be identical, but should target the same search intent."))
    else:
        checks.append(make_check("seo-keyword-alignment", "Title/H1 Keyword Alignment", "seo", "warning", "info",
            "Cannot compare — missing title or H1", "Ensure both title and H1 are present and share primary keywords.",
            "Add both a <title> and <h1> tag containing your target keyword."))

    # 18. Structured data completeness
    if json_ld:
        try:
            all_schema = []
            for s in json_ld:
                d = json.loads(s.string or "{}")
                all_schema.append(d)
            has_name = any(d.get("name") for d in all_schema)
            has_url = any(d.get("url") for d in all_schema)
            has_desc = any(d.get("description") for d in all_schema)
            completeness = sum([has_name, has_url, has_desc])
            if completeness >= 2:
                checks.append(make_check("seo-schema-complete", "Structured Data Completeness", "seo", "pass", "info",
                    f"Has name: {has_name}, url: {has_url}, description: {has_desc}", "Structured data has good field coverage.", "No action needed."))
            else:
                checks.append(make_check("seo-schema-complete", "Structured Data Completeness", "seo", "warning", "info",
                    f"Has name: {has_name}, url: {has_url}, description: {has_desc}", "Structured data is incomplete. Add name, URL, and description fields at minimum.",
                    "Expand your JSON-LD to include name, url, description, and image fields. Use Google's Rich Results Test to validate."))
        except (json.JSONDecodeError, TypeError):
            checks.append(make_check("seo-schema-complete", "Structured Data Completeness", "seo", "warning", "info",
                "Parse error in JSON-LD", "Fix JSON-LD syntax errors. Validate at search.google.com/test/rich-results.",
                "Check your JSON-LD for syntax errors. Use Google's Rich Results Test or Schema.org validator."))
    else:
        checks.append(make_check("seo-schema-complete", "Structured Data Completeness", "seo", "fail", "info",
            "No structured data found", "Add comprehensive JSON-LD structured data.",
            "Start with Organization or LocalBusiness schema. Include name, url, logo, description, and contactPoint."))

    return checks


def run_security_checks(resp, soup, response_data):
    """Run all security checks."""
    checks = []
    headers = resp.headers if resp else {}

    # 1. HTTPS
    if response_data["uses_https"]:
        checks.append(make_check("sec-https", "HTTPS", "security", "pass", "critical",
            "Yes", "Site uses HTTPS.", "No action needed."))
    else:
        checks.append(make_check("sec-https", "HTTPS", "security", "fail", "critical",
            "No — site uses HTTP", "Your site is not using HTTPS. This is critical for security, SEO, and user trust.",
            "WordPress: Install Really Simple SSL plugin or configure in hosting panel. Squarespace: Enabled by default. Wix: Enabled by default. Shopify: Enabled by default. Custom: Get a free SSL certificate from Let's Encrypt (certbot) and configure your web server."))

    # Security headers
    sec_headers = {
        "strict-transport-security": ("sec-hsts", "HSTS (Strict-Transport-Security)", "critical",
            "Enforce HTTPS with HSTS header to prevent downgrade attacks.",
            "WordPress: Add to .htaccess or use a security plugin (Wordfence, Sucuri). Squarespace: Not configurable (handled by platform). Wix: Not configurable. Shopify: Not configurable. Custom: Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains' in your server config (nginx.conf / .htaccess)."),
        "content-security-policy": ("sec-csp", "Content Security Policy", "warning",
            "Add CSP header to prevent XSS and code injection attacks.",
            "WordPress: Use Security Headers plugin or add to .htaccess. Squarespace: Not configurable. Wix: Not configurable. Shopify: Limited via app. Custom: Add Content-Security-Policy header in server config. Start with 'default-src self' and expand as needed."),
        "x-content-type-options": ("sec-xcto", "X-Content-Type-Options", "warning",
            "Add 'X-Content-Type-Options: nosniff' to prevent MIME type sniffing.",
            "WordPress: Add to .htaccess: Header set X-Content-Type-Options nosniff. Custom: Add to server config. Most hosting panels have a security headers section."),
        "x-frame-options": ("sec-xfo", "X-Frame-Options", "warning",
            "Add X-Frame-Options to prevent clickjacking attacks.",
            "WordPress: Add to .htaccess: Header set X-Frame-Options SAMEORIGIN. Custom: Add to server config. Squarespace/Wix/Shopify: Handled by platform."),
        "referrer-policy": ("sec-referrer", "Referrer-Policy", "info",
            "Add Referrer-Policy header to control referrer information sent to other sites.",
            "WordPress: Add to .htaccess or via security plugin. Custom: Add 'Referrer-Policy: strict-origin-when-cross-origin' to server config."),
        "permissions-policy": ("sec-permissions", "Permissions-Policy", "info",
            "Add Permissions-Policy to control which browser features your site can use.",
            "WordPress: Add via security plugin or .htaccess. Custom: Add 'Permissions-Policy: geolocation=(), camera=(), microphone=()' to server config."),
        "x-xss-protection": ("sec-xxss", "X-XSS-Protection", "info",
            "Add X-XSS-Protection header as defense-in-depth against XSS.",
            "WordPress: Add to .htaccess: Header set X-XSS-Protection '1; mode=block'. Custom: Add to server config.")
    }

    for header_name, (check_id, check_name, sev, rec, fix) in sec_headers.items():
        val = headers.get(header_name)
        if val:
            checks.append(make_check(check_id, check_name, "security", "pass", sev,
                val[:100], f"{check_name} is set.", "No action needed."))
        else:
            checks.append(make_check(check_id, check_name, "security", "fail", sev,
                "Missing", rec, fix))

    # Mixed content check
    if response_data["uses_https"] and soup:
        http_resources = []
        for tag in soup.find_all(["img", "script", "link", "iframe"]):
            src = tag.get("src") or tag.get("href") or ""
            if src.startswith("http://"):
                http_resources.append(src[:60])
        if http_resources:
            checks.append(make_check("sec-mixed-content", "Mixed Content", "security", "fail", "critical",
                f"{len(http_resources)} HTTP resources on HTTPS page", "Fix mixed content — HTTP resources on an HTTPS page trigger browser warnings and break the padlock icon.",
                "WordPress: Install Better Search Replace, change http:// to https:// in database. Or use Really Simple SSL. Squarespace: Re-upload images, update embed URLs. Wix: Re-add external content with https. Shopify: Update image URLs in content. Custom: Find all http:// references and change to https:// or use protocol-relative //."))
        else:
            checks.append(make_check("sec-mixed-content", "Mixed Content", "security", "pass", "critical",
                "No mixed content detected", "No HTTP resources on HTTPS page.", "No action needed."))
    else:
        checks.append(make_check("sec-mixed-content", "Mixed Content", "security", "warning", "critical",
            "Site not using HTTPS — mixed content check not applicable", "Enable HTTPS first.",
            "Enable HTTPS first, then check for mixed content."))

    # Cookie security flags
    set_cookie = headers.get("Set-Cookie", "")
    if set_cookie:
        has_secure = "secure" in set_cookie.lower()
        has_httponly = "httponly" in set_cookie.lower()
        has_samesite = "samesite" in set_cookie.lower()
        flags = []
        if not has_secure: flags.append("Secure")
        if not has_httponly: flags.append("HttpOnly")
        if not has_samesite: flags.append("SameSite")
        if not flags:
            checks.append(make_check("sec-cookies", "Cookie Security Flags", "security", "pass", "warning",
                "Secure, HttpOnly, SameSite all set", "Cookie security flags are properly configured.", "No action needed."))
        else:
            checks.append(make_check("sec-cookies", "Cookie Security Flags", "security", "warning", "warning",
                f"Missing flags: {', '.join(flags)}", f"Cookies are missing security flags: {', '.join(flags)}. This increases risk of session hijacking.",
                "WordPress: Add to wp-config.php or use a security plugin. Custom: Set cookie flags in your application code or server config. Example: Set-Cookie: session=abc; Secure; HttpOnly; SameSite=Lax"))
    else:
        checks.append(make_check("sec-cookies", "Cookie Security Flags", "security", "pass", "warning",
            "No cookies set on initial page load", "No cookies detected — no flags to check.", "No action needed."))

    # Server version disclosure
    server = headers.get("Server", "")
    x_powered = headers.get("X-Powered-By", "")
    disclosed = []
    if server and re.search(r'\d', server):
        disclosed.append(f"Server: {server}")
    if x_powered:
        disclosed.append(f"X-Powered-By: {x_powered}")
    if disclosed:
        checks.append(make_check("sec-server-disclosure", "Server Version Disclosure", "security", "warning", "warning",
            "; ".join(disclosed), "Server is disclosing version information, which helps attackers target known vulnerabilities.",
            "WordPress: Add to .htaccess: Header unset X-Powered-By and ServerTokens Prod. Squarespace/Wix/Shopify: Managed by platform. Custom: In nginx: server_tokens off; In Apache: ServerTokens Prod, ServerSignature Off."))
    else:
        checks.append(make_check("sec-server-disclosure", "Server Version Disclosure", "security", "pass", "warning",
            "No version info disclosed", "Server is not disclosing version details.", "No action needed."))

    # CORS headers
    cors = headers.get("Access-Control-Allow-Origin", "")
    if cors == "*":
        checks.append(make_check("sec-cors", "CORS Configuration", "security", "warning", "warning",
            f"Access-Control-Allow-Origin: {cors}", "CORS is set to allow all origins (*). This may expose your API to cross-origin attacks.",
            "WordPress: Configure via plugin or .htaccess. Custom: Restrict Access-Control-Allow-Origin to specific trusted domains instead of *."))
    elif cors:
        checks.append(make_check("sec-cors", "CORS Configuration", "security", "pass", "info",
            f"Access-Control-Allow-Origin: {cors}", "CORS is configured with specific origin.", "No action needed."))
    else:
        checks.append(make_check("sec-cors", "CORS Configuration", "security", "pass", "info",
            "No CORS headers (default same-origin policy)", "No CORS headers set — browser enforces same-origin policy by default.", "No action needed."))

    # Subresource integrity on external scripts
    if soup:
        external_scripts = [s for s in soup.find_all("script", src=True)
                           if s["src"].startswith("http") and urlparse(s["src"]).netloc != urlparse(response_data["final_url"] or response_data["url"]).netloc]
        if external_scripts:
            with_sri = sum(1 for s in external_scripts if s.get("integrity"))
            without_sri = len(external_scripts) - with_sri
            if without_sri == 0:
                checks.append(make_check("sec-sri", "Subresource Integrity (SRI)", "security", "pass", "info",
                    f"All {len(external_scripts)} external scripts have SRI", "All external scripts have integrity hashes.", "No action needed."))
            else:
                checks.append(make_check("sec-sri", "Subresource Integrity (SRI)", "security", "warning", "info",
                    f"{without_sri}/{len(external_scripts)} external scripts missing SRI", f"{without_sri} external scripts lack integrity attributes. SRI protects against CDN compromises.",
                    "Add integrity and crossorigin attributes to external script tags. Use srihash.org to generate hashes. Example: <script src=\"...\" integrity=\"sha384-...\" crossorigin=\"anonymous\">"))
        else:
            checks.append(make_check("sec-sri", "Subresource Integrity (SRI)", "security", "pass", "info",
                "No external scripts found", "No external scripts to check.", "No action needed."))

    return checks


def run_performance_checks(resp, soup, response_data):
    """Run all performance checks."""
    checks = []
    headers = resp.headers if resp else {}

    # 1. Response time / TTFB
    ttfb = response_data.get("ttfb_ms") or 5000
    if ttfb < 200:
        checks.append(make_check("perf-ttfb", "Time to First Byte (TTFB)", "performance", "pass", "critical",
            f"{ttfb}ms", "Excellent TTFB — server responds quickly.", "No action needed."))
    elif ttfb < 600:
        checks.append(make_check("perf-ttfb", "Time to First Byte (TTFB)", "performance", "pass", "warning",
            f"{ttfb}ms", "TTFB is acceptable but could be faster.", "No action needed, but consider server-side caching or a CDN for improvement."))
    elif ttfb < 1500:
        checks.append(make_check("perf-ttfb", "Time to First Byte (TTFB)", "performance", "warning", "warning",
            f"{ttfb}ms", f"TTFB is slow ({ttfb}ms). Aim for under 600ms. Slow servers hurt SEO and user experience.",
            "WordPress: Install a caching plugin (WP Rocket, W3 Total Cache). Use a CDN (Cloudflare, free tier). Squarespace: Already optimized; check third-party scripts. Wix: Already CDN-backed. Shopify: Already CDN-backed; check app bloat. Custom: Enable server caching (Redis/Memcached), use a CDN, optimize database queries."))
    else:
        checks.append(make_check("perf-ttfb", "Time to First Byte (TTFB)", "performance", "fail", "critical",
            f"{ttfb}ms", f"TTFB is very slow ({ttfb}ms). This severely impacts SEO rankings and user experience.",
            "WordPress: Install caching (WP Rocket), use CDN (Cloudflare), upgrade hosting. Squarespace: Check for heavy custom code. Shopify: Remove excessive apps. Custom: Profile server response, add caching layers, upgrade hosting, use CDN."))

    # 2. Image count + lazy loading
    if soup:
        images = soup.find_all("img")
        total_imgs = len(images)
        lazy_loaded = sum(1 for img in images if img.get("loading") == "lazy" or "lazy" in (img.get("class") or []) or img.get("data-src"))
        if total_imgs == 0:
            checks.append(make_check("perf-images", "Image Optimization & Lazy Loading", "performance", "pass", "info",
                "No images found", "No images on page.", "No action needed."))
        elif total_imgs <= 5:
            checks.append(make_check("perf-images", "Image Optimization & Lazy Loading", "performance", "pass", "info",
                f"{total_imgs} images, {lazy_loaded} lazy-loaded", "Low image count — good for performance.", "No action needed."))
        elif lazy_loaded >= total_imgs * 0.5:
            checks.append(make_check("perf-images", "Image Optimization & Lazy Loading", "performance", "pass", "warning",
                f"{total_imgs} images, {lazy_loaded} lazy-loaded", "Good use of lazy loading on images.", "No action needed."))
        else:
            checks.append(make_check("perf-images", "Image Optimization & Lazy Loading", "performance", "warning", "warning",
                f"{total_imgs} images, only {lazy_loaded} lazy-loaded", f"Only {lazy_loaded}/{total_imgs} images use lazy loading. Lazy loading defers off-screen images, speeding up initial page load.",
                "WordPress: Enabled by default since WP 5.5; check theme compatibility. Squarespace: Built-in. Wix: Built-in. Shopify: Add loading=\"lazy\" to theme image tags. Custom: Add loading=\"lazy\" attribute to all <img> tags below the fold."))

    # 3. Render-blocking scripts
    if soup:
        scripts = soup.find_all("script", src=True)
        head_scripts = soup.find("head")
        blocking = []
        if head_scripts:
            for s in head_scripts.find_all("script", src=True):
                if not s.get("async") and not s.get("defer") and s.get("type", "text/javascript") != "module":
                    blocking.append(s["src"][:60])
        if not blocking:
            checks.append(make_check("perf-render-blocking", "Render-Blocking Scripts", "performance", "pass", "warning",
                "No render-blocking scripts in <head>", "All scripts use async/defer or are in body.", "No action needed."))
        else:
            checks.append(make_check("perf-render-blocking", "Render-Blocking Scripts", "performance", "warning", "warning",
                f"{len(blocking)} render-blocking scripts in <head>", f"{len(blocking)} scripts in <head> without async/defer are blocking page render.",
                "WordPress: Use Autoptimize or WP Rocket to defer scripts. Squarespace: Move custom scripts to footer injection. Wix: Managed automatically. Shopify: Move scripts to before </body> or add defer. Custom: Add 'defer' or 'async' attribute to <script> tags, or move scripts to end of <body>."))

    # 4. Gzip/Brotli compression
    encoding = response_data.get("content_encoding", "")
    if encoding and ("gzip" in encoding.lower() or "br" in encoding.lower()):
        checks.append(make_check("perf-compression", "Compression (gzip/brotli)", "performance", "pass", "warning",
            f"Content-Encoding: {encoding}", "Response is compressed — good for performance.", "No action needed."))
    else:
        checks.append(make_check("perf-compression", "Compression (gzip/brotli)", "performance", "fail", "warning",
            "No compression detected", "Enable gzip or brotli compression to reduce page size by 60-80%.",
            "WordPress: Enable in .htaccess or via caching plugin (WP Rocket). Squarespace: Enabled by default. Wix: Enabled by default. Shopify: Enabled by default. Custom: In nginx: gzip on; gzip_types text/html text/css application/javascript; In Apache: Enable mod_deflate."))

    # 5. Cache-Control headers
    cache_control = headers.get("Cache-Control", "")
    if cache_control and ("max-age" in cache_control.lower() or "public" in cache_control.lower()):
        checks.append(make_check("perf-cache", "Cache-Control Headers", "performance", "pass", "warning",
            f"Cache-Control: {cache_control[:80]}", "Cache headers are set — browsers will cache static assets.", "No action needed."))
    elif cache_control:
        checks.append(make_check("perf-cache", "Cache-Control Headers", "performance", "warning", "info",
            f"Cache-Control: {cache_control[:80]}", "Cache-Control is set but may not be optimal. Consider adding max-age for static assets.",
            "Configure Cache-Control headers with appropriate max-age values. Static assets: max-age=31536000. HTML: max-age=0, must-revalidate."))
    else:
        checks.append(make_check("perf-cache", "Cache-Control Headers", "performance", "fail", "warning",
            "No Cache-Control header", "Add Cache-Control headers to enable browser caching and reduce repeat load times.",
            "WordPress: Caching plugin (WP Rocket, W3TC) handles this. Squarespace: Handled automatically. Shopify: Handled automatically. Custom: Add Cache-Control headers in server config. Static assets: Cache-Control: public, max-age=31536000."))

    # 6. Total page weight
    content_length = response_data.get("content_length", 0)
    if content_length:
        kb = content_length / 1024
        mb = kb / 1024
        if kb < 500:
            checks.append(make_check("perf-page-weight", "Total Page Weight", "performance", "pass", "warning",
                f"{kb:.0f} KB", "Page is lightweight — good for performance.", "No action needed."))
        elif kb < 2000:
            checks.append(make_check("perf-page-weight", "Total Page Weight", "performance", "warning", "warning",
                f"{kb:.0f} KB ({mb:.1f} MB)", f"Page is {kb:.0f} KB. Aim for under 500 KB for fastest load times.",
                "WordPress: Optimize images (ShortPixel, Imagify), minify CSS/JS (Autoptimize). Squarespace: Compress images before uploading. Shopify: Optimize images, reduce app scripts. Custom: Compress images, minify CSS/JS, remove unused code."))
        else:
            checks.append(make_check("perf-page-weight", "Total Page Weight", "performance", "fail", "critical",
                f"{kb:.0f} KB ({mb:.1f} MB)", f"Page is {mb:.1f} MB — this is very heavy and will load slowly on mobile.",
                "WordPress: Compress images, enable lazy loading, minify all assets. Consider a performance audit with GTmetrix. Squarespace: Reduce image sizes, limit video embeds. Shopify: Audit theme and apps for heavy scripts. Custom: Audit with Chrome DevTools Network tab, compress assets, implement code splitting."))
    else:
        checks.append(make_check("perf-page-weight", "Total Page Weight", "performance", "warning", "info",
            "Could not determine", "Unable to measure page weight.", "Check page weight using Chrome DevTools > Network tab."))

    # 7. External resources count
    if soup:
        ext_resources = set()
        base_domain = urlparse(response_data["final_url"] or response_data["url"]).netloc
        for tag in soup.find_all(["script", "link", "img", "iframe"]):
            src = tag.get("src") or tag.get("href") or ""
            if src.startswith("http"):
                domain = urlparse(src).netloc
                if domain and domain != base_domain:
                    ext_resources.add(domain)
        ext_count = len(ext_resources)
        if ext_count <= 5:
            checks.append(make_check("perf-external-resources", "External Resource Domains", "performance", "pass", "info",
                f"{ext_count} external domains", "Low number of external dependencies.", "No action needed."))
        elif ext_count <= 15:
            checks.append(make_check("perf-external-resources", "External Resource Domains", "performance", "warning", "info",
                f"{ext_count} external domains: {', '.join(list(ext_resources)[:5])}...", f"Loading resources from {ext_count} external domains. Each domain requires a DNS lookup.",
                "Audit external resources. Self-host critical fonts and scripts where possible. Remove unused third-party scripts."))
        else:
            checks.append(make_check("perf-external-resources", "External Resource Domains", "performance", "fail", "warning",
                f"{ext_count} external domains", f"Loading from {ext_count} external domains is excessive. This adds significant latency.",
                "Audit and remove unnecessary third-party scripts. Self-host fonts, combine where possible, use resource hints (dns-prefetch, preconnect)."))

    # 8. Inline CSS/JS size
    if soup:
        inline_css_size = sum(len(s.string or "") for s in soup.find_all("style"))
        inline_js_size = sum(len(s.string or "") for s in soup.find_all("script") if not s.get("src"))
        total_inline = inline_css_size + inline_js_size
        total_kb = total_inline / 1024
        if total_kb < 20:
            checks.append(make_check("perf-inline-size", "Inline CSS/JS Size", "performance", "pass", "info",
                f"CSS: {inline_css_size/1024:.1f} KB, JS: {inline_js_size/1024:.1f} KB", "Inline code is minimal.", "No action needed."))
        elif total_kb < 100:
            checks.append(make_check("perf-inline-size", "Inline CSS/JS Size", "performance", "warning", "info",
                f"CSS: {inline_css_size/1024:.1f} KB, JS: {inline_js_size/1024:.1f} KB ({total_kb:.0f} KB total)", "Moderate amount of inline CSS/JS. Consider moving to external files for caching.",
                "Move large inline <style> and <script> blocks to external .css and .js files so browsers can cache them."))
        else:
            checks.append(make_check("perf-inline-size", "Inline CSS/JS Size", "performance", "fail", "warning",
                f"CSS: {inline_css_size/1024:.1f} KB, JS: {inline_js_size/1024:.1f} KB ({total_kb:.0f} KB total)", f"Excessive inline code ({total_kb:.0f} KB). This bloats every page load and can't be cached.",
                "WordPress: Dequeue inline styles, use external stylesheets. Custom: Extract inline styles/scripts into external files. Use critical CSS inlining only for above-the-fold content."))

    return checks


def run_accessibility_checks(soup, response_data):
    """Run all accessibility checks."""
    checks = []

    # 1. Image alt text
    if soup:
        images = soup.find_all("img")
        total = len(images)
        missing_alt = sum(1 for img in images if not img.get("alt") and img.get("alt") != "")
        if total == 0:
            checks.append(make_check("a11y-img-alt", "Image Alt Text", "accessibility", "pass", "info",
                "No images found", "No images to check.", "No action needed."))
        elif missing_alt == 0:
            checks.append(make_check("a11y-img-alt", "Image Alt Text", "accessibility", "pass", "critical",
                f"All {total} images have alt text", "All images have alt attributes — great for screen readers.", "No action needed."))
        else:
            checks.append(make_check("a11y-img-alt", "Image Alt Text", "accessibility", "fail", "critical",
                f"{missing_alt}/{total} images missing alt text", f"{missing_alt} images are missing alt text. Screen readers cannot describe these to visually impaired users.",
                "WordPress: Edit each image in Media Library, fill in Alt Text field. Squarespace: Click image > Design > Image Alt Text. Wix: Click image > Settings > Alt Text. Shopify: Products/Pages > click image > Edit alt text. Custom: Add alt=\"descriptive text\" to every <img> tag. Use empty alt=\"\" only for decorative images."))

    # 2. Viewport meta
    viewport = soup.find("meta", attrs={"name": "viewport"}) if soup else None
    if viewport:
        checks.append(make_check("a11y-viewport", "Mobile Viewport", "accessibility", "pass", "critical",
            viewport.get("content", "Set"), "Viewport meta tag is present for mobile responsiveness.", "No action needed."))
    else:
        checks.append(make_check("a11y-viewport", "Mobile Viewport", "accessibility", "fail", "critical",
            "Missing", "Add viewport meta tag. Without it, mobile users see a desktop-sized page.",
            "WordPress: Most themes include this; check header.php. Squarespace: Included automatically. Wix: Included automatically. Shopify: Check theme.liquid. Custom: Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"> in <head>."))

    # 3. Form input labels
    if soup:
        inputs = soup.find_all(["input", "textarea", "select"])
        inputs = [i for i in inputs if i.get("type") not in ("hidden", "submit", "button", "reset", "image")]
        unlabeled = []
        for inp in inputs:
            inp_id = inp.get("id")
            has_label = False
            if inp_id:
                label = soup.find("label", attrs={"for": inp_id})
                if label:
                    has_label = True
            if not has_label and inp.get("aria-label"):
                has_label = True
            if not has_label and inp.get("aria-labelledby"):
                has_label = True
            if not has_label and inp.find_parent("label"):
                has_label = True
            if not has_label:
                unlabeled.append(inp.get("name") or inp.get("id") or inp.get("type", "unknown"))
        if not inputs:
            checks.append(make_check("a11y-form-labels", "Form Input Labels", "accessibility", "pass", "info",
                "No form inputs found", "No form inputs to check.", "No action needed."))
        elif not unlabeled:
            checks.append(make_check("a11y-form-labels", "Form Input Labels", "accessibility", "pass", "warning",
                f"All {len(inputs)} inputs have labels", "All form inputs are properly labeled.", "No action needed."))
        else:
            checks.append(make_check("a11y-form-labels", "Form Input Labels", "accessibility", "fail", "warning",
                f"{len(unlabeled)}/{len(inputs)} inputs missing labels: {', '.join(unlabeled[:3])}", f"{len(unlabeled)} form inputs lack labels. Screen reader users cannot identify these fields.",
                "WordPress: Edit forms in your form plugin (Contact Form 7, Gravity Forms) and ensure labels are enabled. Squarespace: Form blocks auto-label; check custom code. Wix: Form fields include labels by default. Shopify: Check theme form templates. Custom: Add <label for=\"input-id\">Label Text</label> for each input, or use aria-label attribute."))

    # 4. ARIA landmarks / semantic HTML5
    if soup:
        has_main = soup.find("main") is not None
        has_nav = soup.find("nav") is not None
        has_footer = soup.find("footer") is not None
        has_header = soup.find("header") is not None
        has_role_main = soup.find(attrs={"role": "main"}) is not None
        has_role_nav = soup.find(attrs={"role": "navigation"}) is not None
        landmarks = {"main": has_main or has_role_main, "nav": has_nav or has_role_nav, "footer": has_footer, "header": has_header}
        present = [k for k, v in landmarks.items() if v]
        missing = [k for k, v in landmarks.items() if not v]
        if len(present) >= 3:
            checks.append(make_check("a11y-landmarks", "Semantic HTML5 / ARIA Landmarks", "accessibility", "pass", "warning",
                f"Found: {', '.join(present)}", "Good use of semantic HTML5 elements.", "No action needed."))
        elif present:
            checks.append(make_check("a11y-landmarks", "Semantic HTML5 / ARIA Landmarks", "accessibility", "warning", "warning",
                f"Found: {', '.join(present)}; Missing: {', '.join(missing)}", f"Missing semantic elements: {', '.join(missing)}. These help screen readers navigate your page.",
                "WordPress: Choose a modern theme with semantic markup. Check theme source for <main>, <nav>, <header>, <footer>. Squarespace: Modern templates include these. Wix: Mostly handled. Shopify: Check theme code. Custom: Wrap your main content in <main>, navigation in <nav>, use <header> and <footer>."))
        else:
            checks.append(make_check("a11y-landmarks", "Semantic HTML5 / ARIA Landmarks", "accessibility", "fail", "warning",
                "No semantic landmarks found", "Page lacks semantic HTML5 elements (<main>, <nav>, <header>, <footer>). Screen readers rely on these for navigation.",
                "WordPress: Switch to a modern, accessible theme (Flavor, flavor theme). Squarespace: Most templates include these. Custom: Add <header>, <nav>, <main>, and <footer> wrapper elements to your page structure."))

    # 5. Skip navigation link
    if soup:
        skip_link = None
        for a in soup.find_all("a", href=True)[:10]:
            href = a.get("href", "")
            text = a.get_text().strip().lower()
            if href.startswith("#") and ("skip" in text or "main" in text or "content" in text):
                skip_link = a
                break
        if skip_link:
            checks.append(make_check("a11y-skip-nav", "Skip Navigation Link", "accessibility", "pass", "info",
                f"Found: '{skip_link.get_text().strip()}'", "Skip-nav link is present for keyboard users.", "No action needed."))
        else:
            checks.append(make_check("a11y-skip-nav", "Skip Navigation Link", "accessibility", "warning", "info",
                "Not found", "Add a 'Skip to main content' link for keyboard and screen reader users.",
                "WordPress: Many accessible themes include this; add to header.php if missing. Squarespace: Add via Code Injection. Custom: Add <a href=\"#main-content\" class=\"skip-link\">Skip to main content</a> as the first element in <body>, with CSS to hide visually but show on focus."))

    # 6. Empty links/buttons
    if soup:
        empty_links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text().strip()
            has_img = a.find("img", alt=True)
            has_aria = a.get("aria-label") or a.get("aria-labelledby") or a.get("title")
            if not text and not has_img and not has_aria:
                empty_links.append(a.get("href", "")[:40])
        empty_buttons = []
        for btn in soup.find_all("button"):
            text = btn.get_text().strip()
            has_aria = btn.get("aria-label") or btn.get("aria-labelledby") or btn.get("title")
            if not text and not has_aria:
                empty_buttons.append("button")
        total_empty = len(empty_links) + len(empty_buttons)
        if total_empty == 0:
            checks.append(make_check("a11y-empty-interactive", "Empty Links/Buttons", "accessibility", "pass", "warning",
                "All links and buttons have accessible text", "All interactive elements have descriptive text.", "No action needed."))
        else:
            checks.append(make_check("a11y-empty-interactive", "Empty Links/Buttons", "accessibility", "fail", "warning",
                f"{total_empty} empty elements ({len(empty_links)} links, {len(empty_buttons)} buttons)", f"{total_empty} links/buttons have no accessible text. Screen readers will announce these as unlabeled.",
                "WordPress: Edit link/button text in page editor. For icon links, add aria-label. Squarespace: Check icon links, add descriptions. Wix: Click element > Accessibility > add label. Shopify: Edit theme code, add aria-label to icon links. Custom: Add descriptive text or aria-label=\"Description\" to all <a> and <button> elements."))

    # 7. Outline:none in inline styles
    if soup:
        outline_none_count = 0
        for el in soup.find_all(style=True):
            if "outline" in el.get("style", "").lower() and ("none" in el["style"].lower() or "0" in el["style"]):
                outline_none_count += 1
        if outline_none_count == 0:
            checks.append(make_check("a11y-outline", "Focus Outline (inline styles)", "accessibility", "pass", "info",
                "No outline:none in inline styles", "No inline styles removing focus outlines.", "No action needed."))
        else:
            checks.append(make_check("a11y-outline", "Focus Outline (inline styles)", "accessibility", "fail", "warning",
                f"{outline_none_count} elements with outline:none/0 in inline styles", f"{outline_none_count} elements have outline removed via inline styles. Keyboard users cannot see which element is focused.",
                "WordPress: Check theme customizer CSS or custom CSS. Squarespace: Check custom CSS. Custom: Remove 'outline: none' or 'outline: 0' from inline styles. Instead, provide a visible focus style: :focus {{ outline: 2px solid #2563eb; outline-offset: 2px; }}"))

    return checks


def run_content_checks(soup, resp):
    """Run content quality checks."""
    checks = []

    if not soup:
        return checks

    # Make a fresh copy for content analysis
    content_soup = BeautifulSoup(str(soup), "html.parser")
    for tag in content_soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = content_soup.get_text(separator=" ", strip=True)
    words = text.split()
    word_count = len(words)

    # 1. Word count / content depth
    if word_count >= 300:
        checks.append(make_check("content-word-count", "Content Depth (Word Count)", "content", "pass", "warning",
            f"{word_count} words", "Good amount of content for SEO.", "No action needed."))
    elif word_count >= 100:
        checks.append(make_check("content-word-count", "Content Depth (Word Count)", "content", "warning", "warning",
            f"{word_count} words", f"Only {word_count} words. Search engines prefer pages with 300+ words of substantive content.",
            "WordPress: Edit page and add more content — explain your services, add FAQ, include testimonials. Squarespace: Add more content blocks. Wix: Expand text sections. Shopify: Add product descriptions, FAQs. Custom: Expand your page content to at least 300 words."))
    else:
        checks.append(make_check("content-word-count", "Content Depth (Word Count)", "content", "fail", "warning",
            f"{word_count} words", f"Very thin content ({word_count} words). This is a major SEO disadvantage.",
            "Add substantial content: service descriptions, benefits, FAQs, testimonials, case studies. Aim for 300-1000 words per page."))

    # 2. Internal links
    links = soup.find_all("a", href=True)
    parsed_base = urlparse(resp.url if resp else "")
    internal = sum(1 for l in links
                   if not l["href"].startswith(("#", "javascript:", "mailto:", "tel:"))
                   and (not urlparse(urljoin(resp.url if resp else "", l["href"])).netloc
                        or urlparse(urljoin(resp.url if resp else "", l["href"])).netloc == parsed_base.netloc))
    if internal >= 3:
        checks.append(make_check("content-internal-links", "Internal Linking", "content", "pass", "info",
            f"{internal} internal links", "Good internal linking for SEO.", "No action needed."))
    elif internal >= 1:
        checks.append(make_check("content-internal-links", "Internal Linking", "content", "warning", "info",
            f"Only {internal} internal link(s)", "Add more internal links to help search engines discover your other pages.",
            "Link to related pages, your blog, services, and contact page from within your content."))
    else:
        checks.append(make_check("content-internal-links", "Internal Linking", "content", "fail", "info",
            "No internal links found", "No internal links. Search engines use internal links to discover and rank your pages.",
            "Add links to your other pages within the content. Link to services, about, contact, and blog pages."))

    # 3. External links
    external = sum(1 for l in links
                   if l["href"].startswith("http")
                   and urlparse(l["href"]).netloc != parsed_base.netloc)
    if external >= 1:
        checks.append(make_check("content-external-links", "External Links", "content", "pass", "info",
            f"{external} external links", "External links show your content references authoritative sources.", "No action needed."))
    else:
        checks.append(make_check("content-external-links", "External Links", "content", "warning", "info",
            "No external links", "Consider adding relevant external links. Google sees outbound links to authoritative sources as a quality signal.",
            "Link to relevant industry resources, tools, or references from your content."))

    # 4. Heading usage in content
    headings_in_content = soup.find_all(["h2", "h3", "h4"])
    if len(headings_in_content) >= 2:
        checks.append(make_check("content-headings", "Content Structure (Subheadings)", "content", "pass", "info",
            f"{len(headings_in_content)} subheadings (H2-H4)", "Good use of subheadings to organize content.", "No action needed."))
    elif len(headings_in_content) == 1:
        checks.append(make_check("content-headings", "Content Structure (Subheadings)", "content", "warning", "info",
            "Only 1 subheading", "Add more subheadings (H2, H3) to break up content and improve readability and SEO.",
            "WordPress: Use the Heading block in the editor. Squarespace: Add heading text blocks. Wix: Add heading elements. Shopify: Use heading formatting in rich text. Custom: Add <h2> and <h3> tags to organize your content into scannable sections."))
    else:
        checks.append(make_check("content-headings", "Content Structure (Subheadings)", "content", "fail", "info",
            "No subheadings found", "No H2/H3/H4 subheadings. Break your content into sections with descriptive headings.",
            "Add subheadings every 200-300 words. Use H2 for main sections, H3 for subsections. Include relevant keywords naturally."))

    # 5. Call to action presence
    cta_keywords = ["contact", "get started", "sign up", "buy now", "learn more", "free", "schedule", "book", "call us", "request", "subscribe", "try", "demo", "quote"]
    links_text = [a.get_text().strip().lower() for a in soup.find_all("a", href=True)]
    buttons_text = [b.get_text().strip().lower() for b in soup.find_all("button")]
    all_cta_text = links_text + buttons_text
    found_ctas = [kw for kw in cta_keywords if any(kw in t for t in all_cta_text)]
    if found_ctas:
        checks.append(make_check("content-cta", "Call to Action", "content", "pass", "warning",
            f"Found CTAs: {', '.join(found_ctas[:4])}", "Page includes clear calls to action.", "No action needed."))
    else:
        checks.append(make_check("content-cta", "Call to Action", "content", "warning", "warning",
            "No clear CTA found", "Add clear calls to action (Contact Us, Get Started, Learn More) to guide visitors.",
            "WordPress: Add a button block with clear CTA text. Squarespace: Add button blocks. Wix: Add button elements. Shopify: Add CTA buttons in sections. Custom: Add <a> or <button> elements with action-oriented text like 'Get Started' or 'Contact Us'."))

    return checks


def check_robots_sitemap(base_url):
    """Check for robots.txt and sitemap.xml."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    results = {"robots_txt": False, "sitemap_xml": False}

    try:
        r = requests.get(f"{root}/robots.txt", timeout=5, headers={"User-Agent": UA})
        results["robots_txt"] = r.status_code == 200
    except Exception:
        pass

    try:
        r = requests.get(f"{root}/sitemap.xml", timeout=5, headers={"User-Agent": UA})
        results["sitemap_xml"] = r.status_code == 200
    except Exception:
        pass

    return results


def calculate_scores(checks):
    """Calculate section scores and overall grade from checks array."""
    categories = {}
    for c in checks:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed_critical": 0, "failed_warning": 0}
        categories[cat]["total"] += 1
        if c["status"] == "pass":
            categories[cat]["passed"] += 1
        elif c["status"] == "fail":
            if c["severity"] == "critical":
                categories[cat]["failed_critical"] += 1
            else:
                categories[cat]["failed_warning"] += 1
        # warning status counts partially

    scores = {}
    for cat, data in categories.items():
        if data["total"] == 0:
            scores[cat] = 50
            continue
        # Base score from pass rate
        base = (data["passed"] / data["total"]) * 100
        # Penalty for critical failures
        critical_penalty = data["failed_critical"] * 8
        warning_penalty = data["failed_warning"] * 3
        scores[cat] = max(0, min(100, round(base - critical_penalty - warning_penalty)))

    # Ensure all categories exist
    for cat in ["seo", "security", "performance", "accessibility", "content"]:
        if cat not in scores:
            scores[cat] = 50

    # Overall weighted score
    weights = {"seo": 0.3, "security": 0.2, "performance": 0.2, "accessibility": 0.15, "content": 0.15}
    scores["overall"] = round(sum(scores.get(k, 50) * v for k, v in weights.items()))

    # Letter grade
    overall = scores["overall"]
    if overall >= 90: scores["grade"] = "A"
    elif overall >= 80: scores["grade"] = "B"
    elif overall >= 70: scores["grade"] = "C"
    elif overall >= 60: scores["grade"] = "D"
    else: scores["grade"] = "F"

    return scores


def run_audit(url):
    """Run full audit on a URL."""
    url = check_url(url)
    print(f"Auditing: {url}", file=sys.stderr)

    # 1. Response check
    response_data, resp = check_response(url)
    if not resp:
        return {"error": "Could not reach website", "details": response_data}

    # 2. Parse HTML
    soup = BeautifulSoup(resp.text, "html.parser")

    # 3. Check robots/sitemap
    robots_sitemap = check_robots_sitemap(response_data["final_url"] or url)

    # 4. Run all checks
    all_checks = []
    all_checks.extend(run_seo_checks(soup, resp, response_data, robots_sitemap))
    all_checks.extend(run_security_checks(resp, soup, response_data))
    all_checks.extend(run_performance_checks(resp, soup, response_data))
    all_checks.extend(run_accessibility_checks(soup, response_data))
    all_checks.extend(run_content_checks(soup, resp))

    # 5. Calculate scores
    scores = calculate_scores(all_checks)

    # 6. Collect all issues (backward compat)
    all_issues = []
    for c in all_checks:
        if c["status"] in ("fail", "warning"):
            all_issues.append(c["recommendation"])

    # 7. Build legacy data sections for backward compat
    meta_tags = {
        "title": soup.find("title").get_text().strip() if soup.find("title") else None,
        "title_length": len(soup.find("title").get_text().strip()) if soup.find("title") else 0,
        "description": None,
        "description_length": 0,
        "viewport": soup.find("meta", attrs={"name": "viewport"}) is not None,
        "canonical": None,
        "og_tags": {},
        "twitter_tags": {},
        "favicon": soup.find("link", attrs={"rel": re.compile(r"icon", re.I)}) is not None,
        "language": soup.find("html").get("lang") if soup.find("html") else None,
        "issues": []
    }
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        meta_tags["description"] = desc_tag.get("content", "")
        meta_tags["description_length"] = len(meta_tags["description"])
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical:
        meta_tags["canonical"] = canonical.get("href")
    for og in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
        meta_tags["og_tags"][og.get("property")] = og.get("content")
    for tc in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
        meta_tags["twitter_tags"][tc.get("name")] = tc.get("content")

    # Security headers legacy
    sec_header_names = ["strict-transport-security", "content-security-policy", "x-content-type-options",
                        "x-frame-options", "x-xss-protection", "referrer-policy", "permissions-policy"]
    sec_headers_data = {}
    for h in sec_header_names:
        val = resp.headers.get(h)
        sec_headers_data[h] = {
            "present": val is not None,
            "value": val,
            "recommendation": f"Add {h} header"
        }
    sec_present = sum(1 for v in sec_headers_data.values() if v["present"])

    # Headings legacy
    headings = {}
    fresh_soup = BeautifulSoup(resp.text, "html.parser")
    for level in range(1, 7):
        tags = fresh_soup.find_all(f"h{level}")
        headings[f"h{level}"] = {"count": len(tags), "texts": [t.get_text().strip()[:100] for t in tags[:5]]}

    # Images legacy
    images = soup.find_all("img")
    img_total = len(images)
    img_missing_alt = sum(1 for img in images if not img.get("alt") and img.get("alt") != "")

    # Links legacy
    links = soup.find_all("a", href=True)
    parsed_base = urlparse(response_data["final_url"] or url)
    internal_links = 0
    external_links = 0
    for link in links:
        href = link.get("href", "")
        if href.startswith(("#", "javascript:", "mailto:", "tel:")): continue
        try:
            parsed = urlparse(urljoin(response_data["final_url"] or url, href))
            if parsed.netloc == parsed_base.netloc or not parsed.netloc:
                internal_links += 1
            else:
                external_links += 1
        except Exception:
            pass

    # Content legacy
    content_soup = BeautifulSoup(resp.text, "html.parser")
    for tag in content_soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    content_text = content_soup.get_text(separator=" ", strip=True)
    word_count = len(content_text.split())

    audit = {
        "url": url,
        "final_url": response_data["final_url"],
        "audit_date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "response": response_data,
        "security_headers": {
            "headers": sec_headers_data,
            "score": round((sec_present / len(sec_header_names)) * 100),
            "present_count": sec_present,
            "total_count": len(sec_header_names)
        },
        "meta_tags": meta_tags,
        "headings": {"headings": headings, "issues": []},
        "images": {"total_images": img_total, "missing_alt": img_missing_alt, "empty_alt": 0, "issues": []},
        "links": {"total_links": len(links), "internal": internal_links, "external": external_links, "nofollow": 0, "broken_format": 0},
        "content": {"word_count": word_count, "issues": []},
        "robots_sitemap": robots_sitemap,
        "checks": all_checks,
        "scores": scores,
        "all_issues": all_issues,
        "issue_count": len(all_issues),
    }

    return audit


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 audit-site.py <url>")
        sys.exit(1)

    result = run_audit(sys.argv[1])
    print(json.dumps(result, indent=2))
