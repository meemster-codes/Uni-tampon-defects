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
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"

# --- Slack ---
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Authenticate with Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

# --- CLEAR SHEET BUT KEEP HEADER ---
existing_data = sheet.get_all_values()
if not existing_data:
    sheet.append_row(["Date", "Ticket ID", "Subject", "Ticket", "URL", "Absorbency", "Won't Expel"])
else:
    header = existing_data[0]
    sheet.clear()
    sheet.append_row(header)

# --- ZENDESK QUERY (DO NOT TOUCH) ---
query = 'type:ticket tags:"product_issue applicator_tampon st_product" created>2026-03-10'

session = requests.Session()
session.auth = (f"{ZD_EMAIL}/token", ZD_API_TOKEN)
url = f"https://{ZD_SUBDOMAIN}.zendesk.com/api/v2/search.json"

response = session.get(url, params={"query": query})
response.raise_for_status()
results = response.json()["results"]

print(f"Zendesk returned {len(results)} tickets")

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
rows_to_write = []

for ticket in results:
    tags = ticket.get("tags", [])

    # --- Absorbency ---
    absorbency = ""
    for tag in tags:
        if tag in ABSORBENCY_MAP:
            absorbency = ABSORBENCY_MAP[tag]
            break

    if not absorbency:
        absorbency = "Unknown"

    # --- Cleaned text ---
    cleaned_description = clean_description(ticket.get("description", ""))
    text = cleaned_description.lower()

    # --- Won't Expel logic (strict) ---
    wont_expel = any([
        "won't expel" in text,
        "wont expel" in text,
        "won't release" in text,
        "wont release" in text,
        "doesn't release" in text,
        "doesnt release" in text,
        "won't come out" in text,
        "wont come out" in text,
        "stuck inside" in text
    ])

    wont_expel_value = "X" if wont_expel else ""

    rows_to_write.append([
        ticket.get("created_at", "")[:10],
        str(ticket.get("id")),
        ticket.get("subject", "").strip(),
        cleaned_description,
        f"https://{ZD_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket.get('id')}",
        absorbency,
        wont_expel_value
    ])

# --- Sort newest first ---
rows_to_write.sort(key=lambda x: x[0], reverse=True)

# --- WRITE TO SHEET ---
if rows_to_write:
    sheet.append_rows(rows_to_write)
    print(f"Wrote {len(rows_to_write)} rows.")
else:
    print("No tickets found.")

# --- DATE RANGE ---
if rows_to_write:
    newest_date = rows_to_write[0][0]
    oldest_date = rows_to_write[-1][0]
else:
    newest_date = "N/A"
    oldest_date = "N/A"

# --- SLACK NOTIFICATION ---
if SLACK_WEBHOOK_URL:
    message = (
        f"✅ Uni tampon sheet updated\n"
        f"{len(rows_to_write)} tickets\n"
        f"{oldest_date} → {newest_date}\n"
        f"{SHEET_URL}"
    )

    slack_message = {"text": message}

    try:
        resp = requests.post(SLACK_WEBHOOK_URL, json=slack_message)
        resp.raise_for_status()
        print("Slack notification sent")
    except Exception as e:
        print(f"Slack error: {e}")
else:
    print("No Slack webhook configured")
