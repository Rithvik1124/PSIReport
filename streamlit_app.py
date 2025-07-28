import os
import json
import subprocess
import shutil
from pathlib import Path

import streamlit as st
from docx import Document
import openai

# ----------- Helpers --------------
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
            result[gid].append((aid, a.get("title"), a.get("displayValue"), a.get("score"),
                                a.get("scoreDisplayMode"), a.get("description")))
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
    audits = lhr.get("audits", {})
    cats = lhr.get("categories", {})

    def safe_display_value(audit_key):
        return audits.get(audit_key, {}).get("displayValue", "N/A")

    def safe_score(category_key):
        return pct(cats.get(category_key, {}).get("score"))

    data = {
        "perf_score": safe_score("performance"),
        "lcp": safe_display_value("largest-contentful-paint"),
        "fcp": safe_display_value("first-contentful-paint"),
        "cls": safe_display_value("cumulative-layout-shift"),
        "si":  safe_display_value("speed-index"),
        "tbt": safe_display_value("total-blocking-time"),
        "access_score": safe_score("accessibility"),
        "bp_score": safe_score("best-practices"),
        "seo_score": safe_score("seo"),
    }

    # Safely group audits
    def safe_group(category, groups):
        try:
            return group_audits_by_category(lhr, category, groups)
        except Exception:
            return {gid: [] for gid in groups}

    data["perf_diagnostics"] = safe_group("performance", ["diagnostics", "load-opportunities", "metrics"]).get("diagnostics", [])
    data["perf_insights"] = safe_group("performance", ["diagnostics", "load-opportunities", "metrics"]).get("load-opportunities", [])

    data["a11y_groups"] = safe_group("accessibility", [
        "a11y-names-labels", "a11y-best-practices", "a11y-color-contrast", "a11y-aria", "a11y-navigation"
    ])
    data["seo_groups"] = safe_group("seo", ["seo-crawl", "seo-content"])
    data["bp_groups"] = safe_group("best-practices", [
        "best-practices-general", "best-practices-ux", "best-practices-trust-safety"
    ])

    # Safe passed/failed grouping
    def safe_list(category):
        try:
            return list_passed_failed(lhr, category)
        except Exception:
            return [], [], []

    data["perf_passed"], data["perf_failed"], _ = safe_list("performance")
    data["access_passed"], data["access_failed"], _ = safe_list("accessibility")
    data["bp_passed"], data["bp_failed"], _ = safe_list("best-practices")
    data["seo_passed"], data["seo_failed"], _ = safe_list("seo")

    return data


def render_prompt(url, d):
    def bullets(items):
        if not items:
            return "None"
        return "\n".join([f"- {title} ({display or ''})" for (title, display) in items])

    return f"""
Act like an expert web performance consultant. I run a Shopify site and I'm a novice.
Give me a structured, step-by-step improvement plan:
- Split by Performance, Accessibility, Best Practices, SEO
- Explain what each issue means in plain English
- Why it matters
- Exactly how to fix it (with code/config/server header examples)
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
"""

def get_ai_advice(model: str, url: str, lhr: dict) -> str:
    data = extract(lhr)
    prompt = render_prompt(url, data)
    api_key = os.getenv("OPENAI_API_KEY", None)
    if not api_key:
        st.warning("OPENAI_API_KEY not set. Skipping AI advice.")
        return "No API key configured."

    client = openai.OpenAI(api_key=api_key)
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
    for line in text.split("\n"):
        doc.add_paragraph(line)
    doc.save(path)

def run_lighthouse(url: str, out_prefix: Path, strategy: str):
    cmd = [
        "lighthouse",
        url,
        "--output=json",
        "--output=html",
        f"--output-path={out_prefix}",
        "--chrome-flags=--headless --no-sandbox --disable-gpu",
        f"--preset={strategy}",
    ]
    subprocess.run(cmd, check=True)

# ----------- Streamlit UI --------------
st.set_page_config(page_title="Lighthouse + AI Audit", layout="wide")
st.title("📊 Lighthouse + OpenAI Report Generator")

url = st.text_input("Enter website URL", "https://example.com")
strategy = st.selectbox("Audit Strategy", ["mobile", "desktop"])
model = st.selectbox("OpenAI Model", ["gpt-4o", "gpt-4", "gpt-3.5-turbo"])
run = st.button("🚀 Run Audit and Generate Report")

if run:
    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    out_prefix = out_dir / "report"

    with st.spinner("Running Lighthouse..."):
        try:
            run_lighthouse(url, out_prefix, strategy)
        except Exception as e:
            st.error(f"Lighthouse failed: {e}")
            st.stop()

    json_path = Path(f"{out_prefix}.report.json")
    if not json_path.exists():
        st.error("Audit JSON not found.")
        st.stop()

    with json_path.open(encoding="utf-8") as f:
        lhr = json.load(f)["lighthouseResult"]

    st.success("✅ Lighthouse audit completed.")

    if os.getenv("OPENAI_API_KEY"):
        with st.spinner("Calling OpenAI for step-by-step advice..."):
            advice = get_ai_advice(model, url, lhr)
            docx_path = out_dir / "advice.docx"
            write_docx(advice, docx_path)
            with open(docx_path, "rb") as f:
                st.download_button("📥 Download AI Advice DOCX", f, file_name="ai_advice.docx")
    else:
        st.warning("No OPENAI_API_KEY found in environment. Skipping AI report.")
