#!/usr/bin/env python3
"""Build static Help / Privacy / Terms pages for site/ (GitHub Pages)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
SITE = ROOT / "site"

REPO = "https://github.com/eliornl/rolemule"
QUICK = f"{REPO}#quick-start"


def strip_first_script_element(html: str) -> str:
    """Remove the first <script>...</script> block from trusted template HTML.

    Uses index scans (not a tag-filter regexp) so closing tags with whitespace or
    extra attributes (e.g. ``</script >``, ``</script foo="bar">``) are still removed.
    """
    lower = html.lower()
    start = lower.find("<script")
    if start < 0:
        return html
    open_end = html.find(">", start)
    if open_end < 0:
        return html
    close = lower.find("</script", open_end)
    if close < 0:
        return html
    close_end = html.find(">", close)
    if close_end < 0:
        return html
    return html[:start] + html[close_end + 1 :]


def extract_style(html: str) -> str:
    m = re.search(
        r'<style[^>]*>\s*(.*?)\s*</style>',
        html,
        flags=re.DOTALL,
    )
    if not m:
        return ""
    return m.group(1).strip()


def extract_content(html: str) -> str:
    m = re.search(
        r"\{%\s*block content\s*%\}(.*?)\{%\s*endblock\s*%\}",
        html,
        flags=re.DOTALL,
    )
    if not m:
        raise SystemExit("content block not found")
    content = m.group(1)
    # Drop jinja nonce scripts used only for app back-link switching
    content = strip_first_script_element(content)
    # App-only absolute paths → marketing / GitHub equivalents
    content = content.replace('href="/dashboard/new-application"', f'href="{QUICK}"')
    content = content.replace('href="/dashboard"', 'href="index.html"')
    content = content.replace('href="/settings"', f'href="{QUICK}"')
    content = content.replace("{{ asset_url('js/help.js') }}", "assets/js/help.js")
    content = content.replace("{{ app_name or \"RoleMule\" }}", "RoleMule")
    return content.strip()


def page_shell(
    *,
    title: str,
    description: str,
    styles: str,
    body: str,
    extra_scripts: str = "",
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <link rel="canonical" href="https://eliornl.github.io/rolemule/">

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="assets/vendor/fontawesome/css/all.min.css">
    <link rel="stylesheet" href="assets/css/base/variables.css">
    <link rel="stylesheet" href="assets/css/landing.css">
    <link rel="stylesheet" href="assets/css/app.css">
    <link rel="stylesheet" href="assets/css/marketing.css">
    <link rel="icon" type="image/svg+xml" href="assets/img/favicon.svg">
    <link rel="icon" type="image/png" href="assets/favicon.png">
    <link rel="icon" type="image/x-icon" href="assets/favicon.ico">
    <style>
{styles}
    </style>
</head>
<body>
    <div class="bg-glow bg-glow-1"></div>
    <div class="bg-glow bg-glow-2"></div>

    <nav class="navbar navbar-expand-lg">
        <div class="container">
            <a class="navbar-brand" href="index.html">
                <div class="brand-icon">
                    <img src="assets/img/rolemule-icon.png" alt="" width="36" height="36">
                </div>
                <span class="brand-text">Role<span class="brand-accent">Mule</span></span>
            </a>
            <a href="index.html" class="nav-back-btn">
                <i class="fas fa-arrow-left"></i>Back to Home
            </a>
        </div>
    </nav>

{body}

    <footer class="footer">
        <div class="container">
            <div class="footer-content">
                <div class="footer-brand">
                    <div class="brand-icon">
                        <img src="assets/img/rolemule-icon.png" alt="" width="36" height="36">
                    </div>
                    <span class="brand-text">Role<span class="brand-accent">Mule</span></span>
                </div>
                <div class="footer-links">
                    <a href="help.html">Help &amp; FAQ</a>
                    <a href="privacy.html">Privacy</a>
                    <a href="terms.html">Terms</a>
                </div>
                <div class="footer-meta">
                    <a href="{REPO}" target="_blank" rel="noopener noreferrer" class="footer-github">
                        <i class="fab fa-github"></i> Open Source on GitHub
                    </a>
                    <p>© 2026 RoleMule</p>
                </div>
            </div>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
{extra_scripts}
</body>
</html>
"""


def build_from_template(
    src: Path,
    dest_name: str,
    *,
    title: str,
    description: str,
    extra_scripts: str = "",
) -> None:
    raw = src.read_text()
    styles = extract_style(raw)
    # Subpage nav uses .navbar without landing fixed-top; keep brand-icon scale
    styles += """
        .brand-icon img {
            transform: scale(1.28);
            transform-origin: center center;
        }
        .nav-back-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
        }
        .nav-back-btn:hover {
            color: var(--accent-primary);
        }
"""
    content = extract_content(raw)
    # Drop trailing page_scripts jinja if present inside content (help has separate block)
    html = page_shell(
        title=title,
        description=description,
        styles=styles,
        body=content,
        extra_scripts=extra_scripts,
    )
    out = SITE / dest_name
    out.write_text(html)
    print(f"Wrote {out.relative_to(ROOT)} ({len(html)} bytes)")


def main() -> None:
    SITE.mkdir(exist_ok=True)

    # help.js from Vite dist (latest hashed) or source build — prefer copying from dist
    dist = UI / "static" / "dist" / "js"
    help_js_candidates = sorted(dist.glob("help.*.js"), key=lambda p: p.stat().st_mtime, reverse=True)
    help_js_dest = SITE / "assets" / "js" / "help.js"
    help_js_dest.parent.mkdir(parents=True, exist_ok=True)
    if help_js_candidates:
        help_js_dest.write_bytes(help_js_candidates[0].read_bytes())
        print(f"Copied {help_js_candidates[0].name} → site/assets/js/help.js")
    else:
        # Minimal search fallback
        help_js_dest.write_text(
            """document.addEventListener('DOMContentLoaded',function(){
  var input=document.getElementById('helpSearch');
  if(!input)return;
  input.addEventListener('input',function(){
    var q=input.value.trim().toLowerCase();
    document.querySelectorAll('.faq-item,.help-section').forEach(function(el){
      el.style.display=!q||el.textContent.toLowerCase().includes(q)?'':'none';
    });
  });
});
"""
        )
        print("Wrote fallback site/assets/js/help.js")

    build_from_template(
        UI / "legal" / "privacy.html",
        "privacy.html",
        title="Privacy Policy | RoleMule",
        description="Privacy Policy for RoleMule — self-hosted; your data stays on your instance.",
    )
    build_from_template(
        UI / "legal" / "terms.html",
        "terms.html",
        title="Terms of Service | RoleMule",
        description="Terms of Service for RoleMule — open-source, self-hosted software.",
    )

    # Help: content block may still include leading script — already stripped once
    help_raw = (UI / "help.html").read_text()
    # Also strip page_scripts from being confused — content ends before page_scripts
    help_content_match = re.search(
        r"\{%\s*block content\s*%\}(.*?)\{%\s*endblock\s*%\}",
        help_raw,
        flags=re.DOTALL,
    )
    assert help_content_match
    help_body = help_content_match.group(1)
    help_body = strip_first_script_element(help_body)
    help_body = help_body.replace('href="/dashboard/new-application"', f'href="{QUICK}"')
    help_body = help_body.replace('href="/dashboard"', "href=\"index.html\"")
    help_body = help_body.strip()

    styles = extract_style(help_raw)
    styles += """
        .brand-icon img {
            transform: scale(1.28);
            transform-origin: center center;
        }
        .nav-back-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
        }
        .nav-back-btn:hover {
            color: var(--accent-primary);
        }
"""
    html = page_shell(
        title="Help & FAQ | RoleMule",
        description="Get help with RoleMule — FAQ, guides, and support.",
        styles=styles,
        body=help_body,
        extra_scripts='    <script src="assets/js/help.js"></script>\n',
    )
    (SITE / "help.html").write_text(html)
    print(f"Wrote site/help.html ({len(html)} bytes)")


if __name__ == "__main__":
    main()
