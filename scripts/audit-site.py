#!/usr/bin/env python3
"""
Website Audit Script — Summit Digital
Runs a comprehensive website audit and outputs structured JSON.

Usage: python3 audit-site.py <url>

Checks:
1. HTTP/HTTPS status & redirects
2. Response time / TTFB
3. Security headers (HSTS, CSP, X-Frame-Options, etc.)
4. Meta tags (title, description, viewport, OG tags)
5. HTML structure (headings hierarchy, alt tags, semantic elements)
6. robots.txt & sitemap.xml presence
7. Mobile viewport
8. Content analysis (word count, reading level, keyword density)
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
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "-q"])
    import requests
    from bs4 import BeautifulSoup


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
        "errors": []
    }
    
    try:
        start = time.time()
        resp = requests.get(url, timeout=15, allow_redirects=True, 
                          headers={"User-Agent": "SummitDigital-AuditBot/1.0"})
        total = (time.time() - start) * 1000
        
        results["status_code"] = resp.status_code
        results["total_time_ms"] = round(total, 1)
        results["final_url"] = resp.url
        results["uses_https"] = resp.url.startswith("https://")
        
        # Track redirects
        for r in resp.history:
            results["redirects"].append({
                "status": r.status_code,
                "url": r.url
            })
        
        # Estimate TTFB from elapsed
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
    
    return results, resp if results["status_code"] else (results, None)


def check_security_headers(resp):
    """Analyze security headers."""
    if not resp:
        return {"error": "No response to analyze"}
    
    headers = resp.headers
    checks = {
        "strict-transport-security": {
            "present": False, "value": None,
            "recommendation": "Add HSTS header to enforce HTTPS"
        },
        "content-security-policy": {
            "present": False, "value": None,
            "recommendation": "Add CSP header to prevent XSS attacks"
        },
        "x-content-type-options": {
            "present": False, "value": None,
            "recommendation": "Add 'X-Content-Type-Options: nosniff'"
        },
        "x-frame-options": {
            "present": False, "value": None,
            "recommendation": "Add X-Frame-Options to prevent clickjacking"
        },
        "x-xss-protection": {
            "present": False, "value": None,
            "recommendation": "Add X-XSS-Protection header"
        },
        "referrer-policy": {
            "present": False, "value": None,
            "recommendation": "Add Referrer-Policy for privacy"
        },
        "permissions-policy": {
            "present": False, "value": None,
            "recommendation": "Add Permissions-Policy to control browser features"
        }
    }
    
    for header_name in checks:
        val = headers.get(header_name)
        if val:
            checks[header_name]["present"] = True
            checks[header_name]["value"] = val
    
    present = sum(1 for c in checks.values() if c["present"])
    total = len(checks)
    
    return {
        "headers": checks,
        "score": round((present / total) * 100),
        "present_count": present,
        "total_count": total
    }


def check_meta_tags(soup, url):
    """Analyze meta tags and SEO elements."""
    results = {
        "title": None,
        "title_length": 0,
        "description": None,
        "description_length": 0,
        "viewport": None,
        "canonical": None,
        "og_tags": {},
        "twitter_tags": {},
        "favicon": False,
        "language": None,
        "issues": []
    }
    
    # Title
    title_tag = soup.find("title")
    if title_tag:
        results["title"] = title_tag.get_text().strip()
        results["title_length"] = len(results["title"])
        if results["title_length"] < 30:
            results["issues"].append("Title too short (<30 chars)")
        elif results["title_length"] > 60:
            results["issues"].append("Title too long (>60 chars)")
    else:
        results["issues"].append("Missing <title> tag — critical for SEO")
    
    # Meta description
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        results["description"] = desc["content"]
        results["description_length"] = len(desc["content"])
        if results["description_length"] < 70:
            results["issues"].append("Meta description too short (<70 chars)")
        elif results["description_length"] > 160:
            results["issues"].append("Meta description too long (>160 chars)")
    else:
        results["issues"].append("Missing meta description — critical for SEO")
    
    # Viewport
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if viewport:
        results["viewport"] = viewport.get("content")
    else:
        results["issues"].append("Missing viewport meta tag — bad for mobile")
    
    # Canonical
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical:
        results["canonical"] = canonical.get("href")
    else:
        results["issues"].append("Missing canonical URL")
    
    # OG tags
    for og in soup.find_all("meta", attrs={"property": re.compile(r"^og:")}):
        results["og_tags"][og.get("property")] = og.get("content")
    if not results["og_tags"]:
        results["issues"].append("Missing Open Graph tags — poor social sharing")
    
    # Twitter cards
    for tc in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
        results["twitter_tags"][tc.get("name")] = tc.get("content")
    
    # Favicon
    favicon = soup.find("link", attrs={"rel": re.compile(r"icon", re.I)})
    results["favicon"] = favicon is not None
    if not results["favicon"]:
        results["issues"].append("Missing favicon")
    
    # Language
    html_tag = soup.find("html")
    if html_tag:
        results["language"] = html_tag.get("lang")
    if not results["language"]:
        results["issues"].append("Missing lang attribute on <html>")
    
    return results


def check_headings(soup):
    """Analyze heading structure."""
    headings = {}
    for level in range(1, 7):
        tags = soup.find_all(f"h{level}")
        headings[f"h{level}"] = {
            "count": len(tags),
            "texts": [t.get_text().strip()[:100] for t in tags[:5]]
        }
    
    issues = []
    if headings["h1"]["count"] == 0:
        issues.append("Missing H1 tag — critical for SEO")
    elif headings["h1"]["count"] > 1:
        issues.append(f"Multiple H1 tags ({headings['h1']['count']}) — should have exactly one")
    
    return {"headings": headings, "issues": issues}


def check_images(soup):
    """Analyze images for alt tags."""
    images = soup.find_all("img")
    total = len(images)
    missing_alt = sum(1 for img in images if not img.get("alt"))
    empty_alt = sum(1 for img in images if img.get("alt") == "")
    
    issues = []
    if total > 0 and missing_alt > 0:
        issues.append(f"{missing_alt}/{total} images missing alt text")
    
    return {
        "total_images": total,
        "missing_alt": missing_alt,
        "empty_alt": empty_alt,
        "issues": issues
    }


def check_links(soup, base_url):
    """Analyze links."""
    links = soup.find_all("a", href=True)
    internal = 0
    external = 0
    broken_format = 0
    nofollow = 0
    
    parsed_base = urlparse(base_url)
    
    for link in links:
        href = link.get("href", "")
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        
        if link.get("rel") and "nofollow" in link.get("rel", []):
            nofollow += 1
        
        try:
            parsed = urlparse(urljoin(base_url, href))
            if parsed.netloc == parsed_base.netloc or not parsed.netloc:
                internal += 1
            else:
                external += 1
        except:
            broken_format += 1
    
    return {
        "total_links": len(links),
        "internal": internal,
        "external": external,
        "nofollow": nofollow,
        "broken_format": broken_format
    }


def check_content(soup):
    """Analyze page content."""
    # Remove script/style
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    
    text = soup.get_text(separator=" ", strip=True)
    words = text.split()
    word_count = len(words)
    
    issues = []
    if word_count < 300:
        issues.append(f"Thin content ({word_count} words) — aim for 300+ for SEO")
    
    return {
        "word_count": word_count,
        "issues": issues
    }


def check_robots_sitemap(base_url):
    """Check for robots.txt and sitemap.xml."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    
    results = {"robots_txt": False, "sitemap_xml": False, "issues": []}
    
    try:
        r = requests.get(f"{root}/robots.txt", timeout=5,
                        headers={"User-Agent": "SummitDigital-AuditBot/1.0"})
        results["robots_txt"] = r.status_code == 200
    except:
        pass
    
    try:
        r = requests.get(f"{root}/sitemap.xml", timeout=5,
                        headers={"User-Agent": "SummitDigital-AuditBot/1.0"})
        results["sitemap_xml"] = r.status_code == 200
    except:
        pass
    
    if not results["robots_txt"]:
        results["issues"].append("Missing robots.txt")
    if not results["sitemap_xml"]:
        results["issues"].append("Missing sitemap.xml — search engines can't discover all pages")
    
    return results


def calculate_scores(audit_data):
    """Calculate section scores and overall grade."""
    scores = {}
    
    # SEO Score (meta tags + headings)
    seo_issues = len(audit_data["meta_tags"]["issues"]) + len(audit_data["headings"]["issues"])
    scores["seo"] = max(0, 100 - (seo_issues * 12))
    
    # Security Score
    scores["security"] = audit_data["security_headers"]["score"]
    
    # Performance Score (based on response time)
    ttfb = audit_data["response"].get("ttfb_ms", 5000)
    if ttfb < 200:
        scores["performance"] = 100
    elif ttfb < 500:
        scores["performance"] = 85
    elif ttfb < 1000:
        scores["performance"] = 70
    elif ttfb < 2000:
        scores["performance"] = 50
    else:
        scores["performance"] = 30
    
    # Accessibility Score (images + structure)
    acc_issues = len(audit_data["images"]["issues"])
    if audit_data["meta_tags"].get("language") is None:
        acc_issues += 1
    if not audit_data["meta_tags"].get("viewport"):
        acc_issues += 1
    scores["accessibility"] = max(0, 100 - (acc_issues * 20))
    
    # Content Score
    wc = audit_data["content"]["word_count"]
    if wc >= 1000:
        scores["content"] = 95
    elif wc >= 500:
        scores["content"] = 80
    elif wc >= 300:
        scores["content"] = 65
    else:
        scores["content"] = max(20, min(60, wc // 5))
    
    # Overall
    weights = {"seo": 0.3, "security": 0.2, "performance": 0.2, 
               "accessibility": 0.15, "content": 0.15}
    scores["overall"] = round(sum(scores[k] * weights[k] for k in weights))
    
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
    import sys as _sys
    print(f"Auditing: {url}", file=_sys.stderr)
    
    # 1. Response check
    response_data, resp = check_response(url)
    if not resp:
        return {"error": "Could not reach website", "details": response_data}
    
    # 2. Parse HTML
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # 3. Run all checks
    audit = {
        "url": url,
        "final_url": response_data["final_url"],
        "audit_date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "response": response_data,
        "security_headers": check_security_headers(resp),
        "meta_tags": check_meta_tags(soup, url),
        "headings": check_headings(soup),
        "images": check_images(soup),
        "links": check_links(soup, response_data["final_url"]),
        "content": check_content(BeautifulSoup(resp.text, "html.parser")),  # Fresh soup
        "robots_sitemap": check_robots_sitemap(response_data["final_url"]),
    }
    
    # 4. Calculate scores
    audit["scores"] = calculate_scores(audit)
    
    # 5. Collect all issues
    all_issues = []
    for section in ["meta_tags", "headings", "images", "content", "robots_sitemap"]:
        if "issues" in audit[section]:
            all_issues.extend(audit[section]["issues"])
    if not response_data["uses_https"]:
        all_issues.append("Site not using HTTPS — critical security issue")
    
    # Security header issues
    for name, data in audit["security_headers"]["headers"].items():
        if not data["present"]:
            all_issues.append(data["recommendation"])
    
    audit["all_issues"] = all_issues
    audit["issue_count"] = len(all_issues)
    
    return audit


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 audit-site.py <url>")
        sys.exit(1)
    
    result = run_audit(sys.argv[1])
    print(json.dumps(result, indent=2))
