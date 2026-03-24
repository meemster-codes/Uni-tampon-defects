# --- Zendesk Search ---
query = 'type:ticket tags:"product_issue applicator_tampon st_product" created>2026-03-10'

url = f"https://{ZD_SUBDOMAIN}.zendesk.com/api/v2/search.json"
auth = (f"{ZD_EMAIL}/token", ZD_API_TOKEN)

all_tickets = []
params = {
    "query": query,
    "sort_by": "created_at",
    "sort_order": "desc"
}

while url:
    response = requests.get(url, auth=auth, params=params)
    data = response.json()

    results = data.get("results", [])
    all_tickets.extend(results)

    print(f"Fetched {len(results)} tickets, total so far: {len(all_tickets)}")

    # After first request, params should not be passed again
    params = {}

    # Pagination
    url = data.get("next_page")

print(f"Total tickets fetched: {len(all_tickets)}")
