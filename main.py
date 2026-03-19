import os
import requests
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

# --- CLEAR SHEET ---
existing_data = sheet.get_all_values()
if not existing_data:
    sheet.append_row(["Date", "Ticket ID", "Subject", "Description", "URL"])
else:
    header = existing_data[0]
    sheet.clear()
    sheet.append_row(header)

# --- Zendesk query (UPDATED instead of CREATED) ---
query = "type:ticket updated>2026-03-10"

session = requests.Session()
session.auth = (f"{ZD_EMAIL}/token", ZD_API_TOKEN)
zd_url = f"https://{ZD_SUBDOMAIN}.zendesk.com/api/v2/search.json"

response = session.get(zd_url, params={"query": query})
response.raise_for_status()
results = response.json()["results"]

print(f"Zendesk returned {len(results)} tickets")

# --- REQUIRED TAGS ---
REQUIRED_TAGS = {"applicator_tampon", "product_issue", "st_product"}

def clean_description(raw_html):
    text = BeautifulSoup(raw_html, "html.parser").get_text()
    for pattern in [r"On .* wrote:", r"Sent from.*", r"--\s*\n", r"#yiv.*"]:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            text = text[:match.start()]
    return text.strip()

rows_to_write = []

for ticket in results:
    tags = set(ticket.get("tags", []))

    if not REQUIRED_TAGS.issubset(tags):
        continue

    rows_to_write.append([
        ticket.get("created_at", "")[:10],
        str(ticket.get("id")),
        ticket.get("subject", "").strip(),
        clean_description(ticket.get("description", "")),
        f"https://{ZD_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket.get('id')}"
    ])

print(f"After filtering: {len(rows_to_write)} tickets")

rows_to_write.sort(key=lambda x: x[0], reverse=True)

if rows_to_write:
    sheet.append_rows(rows_to_write)
    print(f"Wrote {len(rows_to_write)} rows.")
else:
    print("No tickets found.")
