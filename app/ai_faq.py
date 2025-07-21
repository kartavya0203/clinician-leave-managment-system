import os
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-2.5-flash")

# Cache the NJ sick leave page text
def fetch_sick_leave_policy():
    url = "https://www.nj.gov/labor/myworkrights/leave-benefits/sick-leave/"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    content = soup.find("main") or soup.body
    return content.get_text(separator="\n", strip=True)

SCRAPED_POLICY = fetch_sick_leave_policy()

def ask_policy_faq(query: str) -> str:
    prompt = f"""
You are a helpful assistant answering questions about New Jersey's official Sick Leave policy.
Use only the context provided below from NJ.gov.

CONTEXT:
{SCRAPED_POLICY}

QUESTION:
{query}

Answer clearly and concisely. If you're unsure, say: "Please check the official NJ sick leave website."
"""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error generating answer: {e}"
