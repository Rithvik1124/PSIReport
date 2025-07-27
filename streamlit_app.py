import streamlit as st
import base64
import time
import datetime
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from docx import Document
from textwrap import dedent
import openai
import json
import re

# ---------------- CONFIG -----------------
MODEL = "gpt-4o"  # or "gpt-4o-mini"
openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
# -----------------------------------------

# ---------- UTILITIES FOR DOCX PARSING ----------
def generate_docx_from_advice(advice: str, output_path: str):
    doc = Document()
    doc.add_paragraph(advice)
    doc.save(output_path)

# ---------- SELENIUM (undetected-chromedriver) ----------
def create_driver():
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    return uc.Chrome(options=chrome_options)

def get_url(url):
    driver = create_driver()
    try:
        target_url = f"https://pagespeed.web.dev/analysis?url={url}"
        st.write(f"Navigating to {target_url}")
        driver.get(target_url)
        time.sleep(15)  # Wait for PageSpeed Insights to load
        new_url = driver.current_url.split('?')[0]
        return new_url
    finally:
        driver.quit()

def print_to_pdf(url: str, pdf_path: str = "output.pdf"):
    driver = create_driver()
    try:
        driver.get(url)
        wait_time = 70  # seconds
        progress_bar = st.progress(0)
        for i in range(wait_time):
            time.sleep(1)
            progress_bar.progress(int((i + 1) / wait_time * 100))
        pdf = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(pdf['data']))
        progress_bar.empty()
    finally:
        driver.quit()
# ---------- LIGHTHOUSE JSON PARSING ----------
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
            result[gid].append((aid, a.get("title"), a.get("displayValue"),
                                a.get("score"), a.get("scoreDisplayMode"), a.get("description")))
    return result

def list_passed_failed(lhr, category_id):
    cat = lhr["categories"][category_id]
    audits = lhr["audits"]
    passed = []
    failed = []
    not_applicable = []

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
    acc = cats["accessibility"]
    bp = cats["best-practices"]
    seo = cats["seo"]

    data = {
        "perf_score": pct(perf["score"]),
        "lcp": audits["largest-contentful-paint"]["displayValue"],
        "fcp": audits["first-contentful-paint"]["displayValue"],
        "cls": audits["cumulative-layout-shift"]["displayValue"],
        "si": audits["speed-index"]["displayValue"],
        "tbt": audits["total-blocking-time"]["displayValue"],
        "access_score": pct(acc["score"]),
        "bp_score": pct(bp["score"]),
        "seo_score": pct(seo["score"]),
    }

    perf_groups = group_audits_by_category(
        lhr,
        "performance",
        ["diagnostics", "load-opportunities", "metrics"]
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
        lhr,
        "seo",
        ["seo-crawl", "seo-content"]
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

# ---------- STREAMLIT UI ----------
st.title("Shopify Site Performance Report Generator (undetected-chromedriver)")

url_input = st.text_input("Enter your site URL (e.g., https://example.com):")
lighthouse_json = st.file_uploader("Upload Lighthouse JSON (optional)", type=["json"])

if st.button("Generate Report"):
    if not url_input:
        st.error("Please enter a URL")
    else:
        with st.spinner("Analyzing with PageSpeed Insights..."):
            result_url = get_url(url_input)

            mobile_pdf = f"mobile_{datetime.date.today()}.pdf"
            desktop_pdf = f"desktop_{datetime.date.today()}.pdf"
            print_to_pdf(f"{result_url}?form_factor=mobile", mobile_pdf)
            print_to_pdf(f"{result_url}?form_factor=desktop", desktop_pdf)

        if lighthouse_json:
            lhr = json.load(lighthouse_json)
            data = extract(lhr)
            prompt = render_prompt(url_input, data)

            st.info("Generating advice with AI...")
            resp = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a detailed web performance optimization expert."},
                    {"role": "user", "content": prompt}
                ]
            )
            advice = resp.choices[0].message.content
            docx_name = f"advice_{datetime.date.today()}.docx"
            generate_docx_from_advice(advice, docx_name)
            st.download_button("Download AI Advice (DOCX)", open(docx_name, "rb"), file_name=docx_name)

        st.download_button("Download Mobile Report (PDF)", open(mobile_pdf, "rb"), file_name=mobile_pdf)
        st.download_button("Download Desktop Report (PDF)", open(desktop_pdf, "rb"), file_name=desktop_pdf)
