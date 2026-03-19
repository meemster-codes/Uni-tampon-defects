import os
import requests
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import re

# --- Zendesk credentials ---
ZD_SUBDOMAIN = os.getenv("ZD_SUBDOMAIN")
ZD_EMAIL = os.getenv("ZD_EMAIL")
ZD_API_TOKEN = os.getenv("ZD_API_TOKEN")

# --- Google Sheets setup ---
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = "/etc/secrets/google-credentials.json"

# Authenticate with Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

# --- CLEAR SHEET (keep header row) ---
existing_data = sheet.get_all_values()
if len(existing_data) > 1:
    sheet.resize(rows=1)

# Query Zendesk (NOW FILTERING BY TAG)
query = "type:ticket tags:applicator_tampon created>2026-03-10"

session = requests.Session()
session.auth = (f"{ZD_EMAIL}/token", ZD_API_TOKEN)
zd_url = f"https://{ZD_SUBDOMAIN}.zendesk.com/api/v2/search.json"
response = session.get(zd_url, params={"query": query})
response.raise_for_status()
results = response.json()["results"]

print(f"Zendesk returned {len(results)} tickets")

# Helper: clean and trim ticket description
def clean_description(raw_html):
    text = BeautifulSoup(raw_html, "html.parser").get_text()
    cut_patterns = [
        r"On .* wrote:",
        r"Sent from.*",
        r"--\s*\n",
        r"#yiv.*"
    ]
    for pattern in cut_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            text = text[:match.start()]
    return text.strip()

# Prepare rows
new_rows = []
for ticket in results:
    ticket_id = str(ticket.get("id"))
    subject = ticket.get("subject", "").strip()
    raw_description = ticket.get("description", "").strip()
    cleaned_description = clean_description(raw_description)
    created_date = ticket.get("created_at", "")[:10]
    ticket_url = f"https://{ZD_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket_id}"

    if cleaned_description:
        new_rows.append([
            created_date,
            ticket_id,
            subject,
            cleaned_description,
            ticket_url
        ])

# Sort and batch insert
if new_rows:
    new_rows.sort(key=lambda x: x[0], reverse=True)
    sheet.insert_rows(new_rows, row=2)

    print(f"Inserted {len(new_rows)} rows.")
else:
    print("No tickets found.")
