from fastapi import FastAPI, Request
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
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
    if mobile:
        mobile_emulation = { "deviceName": "Pixel 2" }
        chrome_options.add_experimental_option("mobileEmulation", mobile_emulation)
    return webdriver.Chrome(options=chrome_options)

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
    prompt = f'''Prompt for Advice on Optimizing My Webpage:
                                *"Act like an expert web performance consultant. I am running a Shopify website and I am a novice developer
                                who is not experienced with SEO or performance optimization.
                                I will paste the output from a Lighthouse / PageSpeed Insights / Playwright report.
                                Go through the results and give me a structured improvement plan:
                                Break it down by category: Performance, Accessibility, Best Practices, SEO.
                                Explain what the issue is in plain English.
                                Tell me why it matters and exactly how to fix it.
                                Include examples of the code changes, server headers, or settings to adjust.

                                Don't assume I know SEO or Core Web Vitals—spell out every step."*
                                 Page URL: {url}
                                 
                                ---
                                
                                1. **Performance Report:**
                                - **Performance Score (Mobile):** {performance_data['perf_mob']}  
                                - **Core Web Vitals:**  
                                  - **Largest Contentful Paint (LCP):** {performance_data['lcp']}
                                  - **Cumulative Layout Shift (CLS):** {performance_data['cls']}
                                - **Speed Index:** {performance_data['si']}
                                - **Total Blocking Time (TBT):** {performance_data['tbt']}  
                                - **First Contentful Paint (FCP):** {performance_data['fcp']}  
                                - **Diagnostics:** {performance_data['diag']}  
                                - **Performance Insights:** {performance_data['perf_insights']}  
                                - **Performance Passed:** {performance_data['perf_passed']}  
                                
                                ---
                                
                                2. **Accessibility Report:**
                                - **Accessibility Score:** {performance_data['access_score']}  
                                - **Color Contrast Issues:** {performance_data['color_cont']}
                                - **ARIA Issues:** {performance_data['aria']}
                                - **Navigation Issues:**  
                                  *(List any issues related to focus management, keyboard navigation, etc.)*  
                                - **Semantic HTML Issues:**  
                                  *(Are headings, lists, buttons used correctly?)*  
                                - **Accessible Forms Issues:**  
                                  *(Missing form labels or other issues with form elements)*  
                                - **Other Accessibility Issues:**  
                                  *(Any other problems like missing language attributes, screen reader issues, etc.)*  
                                - **Accessibility Passed:** {performance_data['access_passed']}  
                                
                                ---
                                
                                3. **Best Practices Report:**
                                - **Best Practices Score:** {performance_data['bp_score']} 
                                - **General Best Practices:** {performance_data['bp_gen']}
                                - **UX Best Practices:** {performance_data['bp_ux']}
                                - **Trust & Safety Best Practices:** {performance_data['bp_ts']}
                                - **Best Practices Passed:** {performance_data['bp_passed']}  
                                
                                ---
                                
                                4. **SEO Report:**
                                - **SEO Score:** {performance_data['seo_score']}
                                - **SEO Crawl Issues:** {performance_data['seo_crawl']}  
                                - **SEO Content Best Practices:** {performance_data['seo_bp']}  
                                - **SEO Passed:** {performance_data['seo_passed']}
                                
                                ---
                                
                                **Go through the above data and give me specific advice on how to improve each area (performance, accessibility, best practices, SEO)
                                and actionable steps for optimizing your webpage. Assume any unpecified/errors as not applicable**
                                '''
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a detailed web performance optimization expert."},
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

        time.sleep(25)  # crude wait for PSI to finish

        desktop_data = extract_data(desktop_driver)
        desktop_shot = screenshot_base64(desktop_driver)
        mobile_shot = screenshot_base64(mobile_driver)

        advice = generate_advice(url, desktop_data)

        return {
            "url": url,
            "advice": advice,
            "metrics": desktop_data,
            "screenshot_desktop": desktop_shot,
            "screenshot_mobile": mobile_shot
        }

    finally:
        desktop_driver.quit()
        mobile_driver.quit()
