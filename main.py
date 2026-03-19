import os
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Zendesk credentials ---
ZD_SUBDOMAIN = os.getenv("ZD_SUBDOMAIN")
ZD_EMAIL = os.getenv("ZD_EMAIL")
ZD_API_TOKEN = os.getenv("ZD_API_TOKEN")

# --- Google Sheets setup ---
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = "/etc/secrets/google-credentials.json"

# Authenticate
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

# --- CLEAR SHEET ---
sheet.clear()
sheet.append_row(["Ticket ID", "Subject"])

# --- EXACT QUERY (UI MATCH) ---
query = 'tags:"product_issue applicator_tampon st_product" created>2026-03-10'

session = requests.Session()
session.auth = (f"{ZD_EMAIL}/token", ZD_API_TOKEN)

url = f"https://{ZD_SUBDOMAIN}.zendesk.com/api/v2/search.json"

response = session.get(url, params={"query": query})
response.raise_for_status()

data = response.json()
results = data["results"]

print(f"Zendesk returned {len(results)} tickets")

# --- WRITE RESULTS ---
rows = []
for ticket in results:
    rows.append([
        str(ticket.get("id")),
        ticket.get("subject", "")
    ])

if rows:
    sheet.append_rows(rows)

print("Done")
