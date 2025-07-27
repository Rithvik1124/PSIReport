#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
import shutil
from pathlib import Path
from textwrap import dedent
from docx import Document
import openai

# ---------------- CONFIG -----------------
# You control the model from CLI; OPENAI_API_KEY must be in env.
# -----------------------------------------

# ---- YOUR ORIGINAL HELPERS (KEPT AS-IS, except tiny I/O glue) ----
def pct(score):
    return None if score is None else int(round(score * 100))

def group_audits_by_category(lhr, category_id, group_ids):
    cat = lhr["categories"][category_id]
    audits = lhr["audits"]
    result = {gid: [] for gid in group_ids}
    for ref in cat["auditRefs"]:
        aid = ref["id"]
        a = audits[aid]
        gid = ref.get("group")
        if gid in result:
            result[gid].append((
                aid,
                a.get("title"),
                a.get("displayValue"),
                a.get("score"),
                a.get("scoreDisplayMode"),
                a.get("description"),
            ))
    return result

def list_passed_failed(lhr, category_id):
    cat = lhr["categories"][category_id]
    audits = lhr["audits"]
    passed, failed, not_applicable = [], [], []
    for ref in cat["auditRefs"]:
        a = audits[ref["id"]]
        score = a.get("score")
        mode = a.get("scoreDisplayMode")
        title = a.get("title")
        display = a.get("displayValue")
        if mode == "notApplicable":
            not_applicable.append((title, display))
        elif score == 1:
            passed.append((title, display))
        elif score == 0:
            failed.append((title, display))
    return passed, failed, not_applicable

def extract(lhr):
    audits = lhr["audits"]
    cats = lhr["categories"]

    perf = cats["performance"]
    acc  = cats["accessibility"]
    bp   = cats["best-practices"]
    seo  = cats["seo"]

    data = {
        "perf_score": pct(perf["score"]),
        "lcp": audits["largest-contentful-paint"]["displayValue"],
        "fcp": audits["first-contentful-paint"]["displayValue"],
        "cls": audits["cumulative-layout-shift"]["displayValue"],
        "si":  audits["speed-index"]["displayValue"],
        "tbt": audits["total-blocking-time"]["displayValue"],

        "access_score": pct(acc["score"]),
        "bp_score": pct(bp["score"]),
        "seo_score": pct(seo["score"]),
    }

    perf_groups = group_audits_by_category(
        lhr, "performance", ["diagnostics", "load-opportunities", "metrics"]
    )
    data["perf_diagnostics"] = perf_groups.get("diagnostics", [])
    data["perf_insights"] = perf_groups.get("load-opportunities", [])

    acc_groups = group_audits_by_category(
        lhr,
        "accessibility",
        [
            "a11y-names-labels", "a11y-best-practices",
            "a11y-color-contrast", "a11y-aria", "a11y-navigation"
        ]
    )
    data["a11y_groups"] = acc_groups

    seo_groups = group_audits_by_category(
        lhr, "seo", ["seo-crawl", "seo-content"]
    )
    data["seo_groups"] = seo_groups

    bp_groups = group_audits_by_category(
        lhr,
        "best-practices",
        ["best-practices-general", "best-practices-ux", "best-practices-trust-safety"]
    )
    data["bp_groups"] = bp_groups

    data["perf_passed"], data["perf_failed"], _ = list_passed_failed(lhr, "performance")
    data["access_passed"], data["access_failed"], _ = list_passed_failed(lhr, "accessibility")
    data["bp_passed"], data["bp_failed"], _ = list_passed_failed(lhr, "best-practices")
    data["seo_passed"], data["seo_failed"], _ = list_passed_failed(lhr, "seo")

    return data

def render_prompt(url, d):
    def bullets(items):
        if not items:
            return "None"
        return "\n".join([f"- {title} ({display or ''})" for (title, display) in items])

    return dedent(f"""
    Act like an expert web performance consultant. I run a Shopify site and I'm a novice.
    I will paste the Lighthouse JSON-derived results below. Give me a structured, step-by-step improvement plan:
    - Split by Performance, Accessibility, Best Practices, SEO
    - Explain what each issue means in plain English
    - Why it matters
    - Exactly how to fix (include code/config/server header examples)
    - Don't assume I know SEO or Core Web Vitals

    **Page URL:** {url}

    ---
    1) **Performance**
       - **Performance Score (Mobile):** {d['perf_score']}
       - **LCP:** {d['lcp']}
       - **FCP:** {d['fcp']}
       - **CLS:** {d['cls']}
       - **Speed Index:** {d['si']}
       - **TBT:** {d['tbt']}
       - **Diagnostics (top items):**
         {bullets([(t, dv) for _, t, dv, *_ in d['perf_diagnostics']][:10])}
       - **Insights / Opportunities (top items):**
         {bullets([(t, dv) for _, t, dv, *_ in d['perf_insights']][:10])}
       - **Passed Audits (sample):**
         {bullets(d['perf_passed'][:10])}

    ---
    2) **Accessibility**
       - **Score:** {d['access_score']}
       - **Passed Audits (sample):**
         {bullets(d['access_passed'][:10])}
       - **Failed Audits (sample):**
         {bullets(d['access_failed'][:10])}

    ---
    3) **Best Practices**
       - **Score:** {d['bp_score']}
       - **Passed Audits (sample):**
         {bullets(d['bp_passed'][:10])}
       - **Failed Audits (sample):**
         {bullets(d['bp_failed'][:10])}

    ---
    4) **SEO**
       - **Score:** {d['seo_score']}
       - **Passed Audits (sample):**
         {bullets(d['seo_passed'][:10])}
       - **Failed Audits (sample):**
         {bullets(d['seo_failed'][:10])}
    """)

# ---- PDF maker via Chromium headless (no Selenium) ----
def html_to_pdf(html_path: Path, pdf_path: Path):
    # Try common chromium binaries
    candidates = [
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chrome"),
    ]
    bin_path = next((c for c in candidates if c), None)
    if not bin_path:
        raise RuntimeError("No Chromium/Chrome binary found in container.")

    cmd = [
        bin_path,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        str(html_path.resolve().as_uri()),
    ]
    subprocess.run(cmd, check=True)

# ---- OpenAI call ----
def get_ai_advice(model: str, url: str, lhr: dict) -> str:
    data = extract(lhr)
    prompt = render_prompt(url, data)
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a detailed web performance optimization expert."},
            {"role": "user", "content": prompt}
        ],
    )
    return resp.choices[0].message.content

def write_docx(text: str, path: Path):
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)

# ---- Lighthouse runner ----
def run_lighthouse(url: str, out_prefix: Path, strategy: str):
    # Lighthouse will create out_prefix.report.json & out_prefix.report.html
    cmd = [
        "lighthouse",
        url,
        "--output=json",
        "--output=html",
        f"--output-path={out_prefix}",
        "--chrome-flags=--headless --no-sandbox --disable-gpu",
        f"--preset={strategy}",  # "desktop" or "mobile"
    ]
    subprocess.run(cmd, check=True)

def main():
    parser = argparse.ArgumentParser(description="Run Lighthouse, create PDF, generate OpenAI advice DOCX.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--strategy", default="mobile", choices=["mobile", "desktop"])
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--prefix", default="report")
    parser.add_argument("--skip-openai", action="store_true", help="Skip OpenAI call (no docx).")
    args = parser.parse_args()

    if "OPENAI_API_KEY" not in os.environ and not args.skip_openai:
        sys.exit("OPENAI_API_KEY env var missing.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_prefix = out_dir / args.prefix
    print(f"Running Lighthouse for {args.url} ({args.strategy})...")
    run_lighthouse(args.url, out_prefix, args.strategy)

    json_path = Path(f"{out_prefix}.report.json")
    html_path = Path(f"{out_prefix}.report.html")
    pdf_path  = Path(f"{out_prefix}.report.pdf")
    if not json_path.exists() or not html_path.exists():
        sys.exit("Lighthouse did not output expected files.")

    print("Converting HTML to PDF...")
    html_to_pdf(html_path, pdf_path)
    print(f"PDF written to: {pdf_path}")

    if not args.skip_openai:
        print("Generating OpenAI advice (DOCX)...")
        with json_path.open(encoding="utf-8") as f:
            lhr = json.load(f)["lighthouseResult"]

        advice = get_ai_advice(args.model, args.url, lhr)
        docx_path = out_dir / "advice.docx"
        write_docx(advice, docx_path)
        print(f"DOCX written to: {docx_path}")

    print("Done.")

if __name__ == "__main__":
    main()
