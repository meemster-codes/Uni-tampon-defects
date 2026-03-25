import os
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

# --- Zendesk credentials ---
ZD_SUBDOMAIN = os.getenv("ZD_SUBDOMAIN")
ZD_EMAIL = os.getenv("ZD_EMAIL")
ZD_API_TOKEN = os.getenv("ZD_API_TOKEN")

# --- Google Sheets setup ---
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDENTIALS_FILE = "/etc/secrets/google-credentials.json"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"

# --- Slack ---
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Authenticate Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

existing_data = sheet.get_all_values()

# --- Ensure header ---
if not existing_data:
    sheet.append_row(["Date", "Ticket ID", "Subject", "Ticket", "URL", "Absorbency"])
    existing_ids = set()
else:
    existing_ids = set()
    for row in existing_data[1:]:
        if len(row) > 1:
            existing_ids.add(row[1])

# --- LOOKBACK WINDOW (14 days) ---
lookback_date = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")

query = f'type:ticket tags:"product_issue applicator_tampon st_product" created>={lookback_date}'

url = f"https://{ZD_SUBDOMAIN}.zendesk.com/api/v2/search.json"
auth = (f"{ZD_EMAIL}/token", ZD_API_TOKEN)

all_tickets = []
params = {
    "query": query,
    "sort_by": "created_at",
    "sort_order": "desc"
}

# --- Pagination loop ---
while url:
    response = requests.get(url, auth=auth, params=params)

    if response.status_code != 200:
        print("Zendesk API error:", response.status_code, response.text)
        break

    data = response.json()

    results = data.get("results", [])
    all_tickets.extend(results)

    print(f"Fetched {len(results)} tickets, total so far: {len(all_tickets)}")

    params = {}  # only used on first request
    url = data.get("next_page")

print(f"Total tickets fetched: {len(all_tickets)}")

# --- Absorbency mapping ---
ABSORBENCY_MAP = {
    "light_tampon_absorbency": "Light",
    "regular_tampon_absorbency": "Regular",
    "super_tampon_absorbency": "Super",
    "super_plus_tampon_absorbency": "Super Plus"
}

# --- Clean description ---
def clean_description(raw_html):
    text = BeautifulSoup(raw_html, "html.parser").get_text()
    for pattern in [r"On .* wrote:", r"Sent from.*", r"--\s*\n", r"#yiv.*"]:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            text = text[:match.start()]
    return text.strip()

# --- Build rows ---
new_rows = []

for ticket in all_tickets:
    ticket_id = str(ticket.get("id"))

    # Deduplicate
    if ticket_id in existing_ids:
        continue

    tags = set(ticket.get("tags", []))

    absorbency = "Unknown"
    for tag in tags:
        if tag in ABSORBENCY_MAP:
            absorbency = ABSORBENCY_MAP[tag]
            break

    new_rows.append([
        ticket.get("created_at", "")[:10],
        ticket_id,
        ticket.get("subject", "").strip(),
        clean_description(ticket.get("description", "")),
        f"https://{ZD_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket_id}",
        absorbency
    ])

# --- Sort newest first ---
new_rows.sort(key=lambda x: int(x[1]), reverse=True)

# --- Write to sheet ---
if new_rows:
    sheet.insert_rows(new_rows, row=2)
    print(f"Inserted {len(new_rows)} new rows")
else:
    print("No new tickets")

# --- Slack notification ---
if SLACK_WEBHOOK_URL:
    if new_rows:
        newest_date = new_rows[0][0]
        oldest_date = new_rows[-1][0]
        count_text = f"{len(new_rows)} new tickets"
    else:
        newest_date = "N/A"
        oldest_date = "N/A"
        count_text = "No new tickets"

    message = (
        f"✅ Uni tampon sheet updated\n"
        f"{count_text}\n"
        f"{oldest_date} → {newest_date}\n"
        f"{SHEET_URL}"
    )

    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": message})
        print("Slack notification sent")
    except Exception as e:
        print(f"Slack error: {e}")
