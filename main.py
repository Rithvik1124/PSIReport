from fastapi import FastAPI
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import openai
import time
import base64
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

class URLRequest(BaseModel):
    url: str

def setup_driver(mobile=False):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.binary_location = "/usr/bin/chromium"

    if mobile:
        chrome_options.add_experimental_option("mobileEmulation", {"deviceName": "Pixel 2"})

    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)

def extract_data(driver):
    selectors = {
        'Performance Score': '.lh-exp-gauge__percentage',
        'LCP': '#largest-contentful-paint',
        'CLS': '#cumulative-layout-shift',
        'SI': '#speed-index',
        'TBT': '#total-blocking-time',
        'FCP': '#first-contentful-paint',
        'Diagnostics': '.lh-audit-group--diagnostics',
        'Insights': '.lh-audit-group--insights'
    }
    data = {}
    for label, selector in selectors.items():
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            el = driver.find_element(By.CSS_SELECTOR, selector)
            driver.execute_script("arguments[0].scrollIntoView();", el)
            time.sleep(0.5)
            data[label] = el.text
        except Exception as e:
            data[label] = f"Error: {str(e)}"
    return data

def screenshot_base64(driver):
    png = driver.get_screenshot_as_png()
    return base64.b64encode(png).decode()

def generate_advice(url, data):
    prompt = f"""
Act like a web performance consultant for this Shopify site:
URL: {url}

Audit Data:
- Performance Score: {data.get('Performance Score')}
- LCP: {data.get('LCP')}
- CLS: {data.get('CLS')}
- Speed Index: {data.get('SI')}
- TBT: {data.get('TBT')}
- FCP: {data.get('FCP')}
- Diagnostics: {data.get('Diagnostics')}
- Insights: {data.get('Insights')}

Give a detailed, plain-English optimization plan for Performance, Accessibility, SEO, and Best Practices.
Explain what’s wrong and exactly how to fix it.
"""
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful web performance optimization expert."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

@app.post("/analyze")
async def analyze(request: URLRequest):
    url = request.url
    full_url = f"https://pagespeed.web.dev/analysis?url={url}"

    desktop_driver = setup_driver(mobile=False)
    mobile_driver = setup_driver(mobile=True)

    try:
        desktop_driver.get(full_url)
        mobile_driver.get(full_url)
        time.sleep(25)  # crude wait for PSI to finish rendering

        metrics = extract_data(desktop_driver)
        screenshot_desktop = screenshot_base64(desktop_driver)
        screenshot_mobile = screenshot_base64(mobile_driver)
        advice = generate_advice(url, metrics)

        return {
            "url": url,
            "metrics": metrics,
            "advice": advice,
            "screenshot_desktop": screenshot_desktop,
            "screenshot_mobile": screenshot_mobile
        }

    finally:
        desktop_driver.quit()
        mobile_driver.quit()
