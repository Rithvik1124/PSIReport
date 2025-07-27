import streamlit as st
import base64
import time
import datetime
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
import openai
from docx import Document

# ---------------- CONFIG -----------------
MODEL = "gpt-4o"  # or "gpt-4o-mini"
openai.api_key = st.secrets.get("OPENAI_API_KEY", "")
# -----------------------------------------

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
        time.sleep(70)  # Wait for the analysis
        pdf = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(pdf['data']))
    finally:
        driver.quit()

def generate_docx_from_advice(advice: str, output_path: str):
    doc = Document()
    doc.add_paragraph(advice)
    doc.save(output_path)

# ---------- STREAMLIT UI ----------
st.title("Shopify Site Performance Report Generator (Selenium with undetected-chromedriver)")

url_input = st.text_input("Enter your site URL (e.g., https://example.com):")

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

        st.success("PDF Reports Generated!")
        st.download_button("Download Mobile Report (PDF)", open(mobile_pdf, "rb"), file_name=mobile_pdf)
        st.download_button("Download Desktop Report (PDF)", open(desktop_pdf, "rb"), file_name=desktop_pdf)
