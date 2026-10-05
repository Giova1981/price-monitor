Universal Price Monitor
A lightweight, cloud-based price monitoring system written in Python.
The project monitors product pages from different e-commerce websites,
detects the current selling price, compares it with a configurable
threshold, keeps track of price state, and sends email notifications
through Brevo when relevant events occur.
It is designed to run without a permanently powered-on computer and,
with the services currently used by the project, can operate entirely on
free tiers.
Main Features
- Multi-site product monitoring from normal product URLs.
- No site-specific configuration required in prodotti.json.
- Hybrid TinyFish extraction: structured JSON first, automatic HTML
  fallback when needed.
- Protection against unit prices, list/old prices, unrelated product
  prices, and recommendation-section prices.
- Threshold alerts and new-low notifications.
- One recovery notification when a price returns above threshold.
- Multiple recipients per product.
- Automatic notification of newly added recipients while a product is
  already below threshold.
- Consecutive-error tracking and one error notification after repeated
  failures.
- Automatic state management through stato.json.
- Automatic addition/removal of products in the state file.
- Safe threshold changes without artificial alerts.
- Cloud execution through GitHub Actions.
- External scheduling through cron-job.org.
- No local PC needs to remain powered on.
Architecture
prodotti.json
     |
     v
monitor.py
     |
     v
TinyFish Fetch API
     |
     +-- JSON structured document
     |       |
     |       +-- reliable price found --> price validation
     |       |
     |       `-- no reliable price
     |               |
     |               v
     |          HTML fallback
     |               |
     +---------------+
             |
             v
      Threshold comparison
             |
       +-----+-----+
       |           |
       v           v
  stato.json   Brevo Email API
Scheduled execution:
cron-job.org
     |
     v
GitHub Actions workflow_dispatch
     |
     v
monitor.py
Price Extraction Strategy
1. TinyFish JSON extraction
The first request uses TinyFish Fetch with:
{
  "format": "json",
  "ttl": 0
}
TinyFish returns a structured document tree together with page metadata
such as title and description. The monitor tries to identify a reliable
current price from this structured content.
For example, a product page may contain:
60 pz
0.33 EUR / 1 pz       -> unit price, ignored
19.79 EUR             -> current selling price
27.50 EUR             -> list price, ignored
When independent parts of the returned data agree on the same price,
confidence is increased.
2. Automatic HTML fallback
Some websites expose the product price in TinyFish HTML but omit it from
the structured JSON document.
When JSON extraction cannot determine a sufficiently reliable price, the
monitor automatically requests the same URL in HTML format and analyzes
the main product area.
TinyFish JSON
     |
     +-- price found --> use JSON price
     |
     `-- no reliable price
             |
             v
       TinyFish HTML
             |
             v
       product-area analysis
             |
             v
         current price
3. Safety first
If neither JSON nor HTML provides a sufficiently reliable result, the
monitor does not guess. It records an extraction error instead.
A missed check is preferable to a false price alert.
Websites Tested
  Website       Successful extraction method
  Farmasave     HTML fallback / Farmasave-compatible extraction
  Farmavola     Generic HTML product-area extraction
  Redcare       TinyFish JSON structured extraction
  SpesaSicura   Generic HTML product-area fallback
These are tested examples, not a fixed whitelist. The monitor attempts
extraction from other public e-commerce product pages without requiring
dedicated site configuration.
Compatibility can still depend on how a store exposes prices, anti-bot
protections, JavaScript rendering, authentication,
geographic/session-specific pricing, and future changes to page
structure.
Product Configuration
Products are configured in prodotti.json.
[
  {
    "id": "example-product",
    "nome": "Example Product",
    "url": "https://example.com/product",
    "soglia": 15.00,
    "destinatari": ["EMAIL_ME"]
  }
]
  Field                               Description
  id                                Stable unique product identifier.
                                      Do not change it casually because
                                      it links the product to its saved
                                      state.
  nome                              Human-readable product name used in
                                      logs and emails.
  url                               Direct product-page URL.
  soglia                            Price threshold.
  destinatari                       Symbolic
                                      secret/environment-variable names
                                      containing recipient email
                                  addresses.
No site, CSS selector, variant, parser, or store-specific field is
required.
State Management
stato.json is managed automatically.
Example:
{
  "stato": "sopra",
  "ultimo_prezzo": 19.79,
  "minimo_notificato": null,
  "soglia": 15.0,
  "errori_consecutivi": 0,
  "errore_notificato": false,
  "destinatari_notificati": []
}
- stato: current threshold state (sopra or sotto).
- ultimo_prezzo: most recently detected valid price.
- minimo_notificato: lowest price already notified during the
  current below-threshold cycle.
- soglia: saved threshold.
- errori_consecutivi: consecutive failed checks.
- errore_notificato: prevents repeated error emails for the same
  failure period.
- destinatari_notificati: recipients already notified during the
  current below-threshold cycle.
Normally, stato.json should not be edited manually.
Notification Logic
First observation above threshold: state is initialized and no email
is sent.
First observation below threshold: an initial price alert is sent.
Still below threshold: no duplicate email is sent for the same or a
higher price. A new lower minimum generates a new-low notification.
New recipient added while already below threshold: only the new
recipient is notified.
Price returns above threshold: one recovery email is sent and the
below-threshold cycle is reset.
Future drop below threshold: a new notification cycle begins.
Threshold changed manually: the state is realigned without
generating an artificial alert solely because the configuration changed.
Error Handling
Each product tracks consecutive failures. After:
3 consecutive failures
the monitor sends one error notification. Further failures do not
repeatedly send the same warning.
After a successful check:
errori_consecutivi = 0
errore_notificato = false
Normal monitoring then resumes.
General TinyFish failures are also handled without treating missing data
as a real price change.
Email Delivery
Notifications use the Brevo transactional email API.
Required GitHub repository secrets:
BREVO_API_KEY
BREVO_SENDER
TINYFISH_API_KEY
Recipient addresses are also stored as secrets/environment variables,
for example:
EMAIL_ME
EMAIL_MANDARINO
EMAIL_LEO
prodotti.json stores only these symbolic names, not the real email
addresses.
GitHub Actions and Scheduling
The main GitHub Actions workflow is triggered with:
on:
  workflow_dispatch:
Scheduling is handled externally through cron-job.org, which calls the
GitHub API to dispatch the workflow.
Current schedule:
08:00
13:00
18:00
22:00
Europe/Rome
A fine-grained GitHub Personal Access Token can be used by cron-job.org,
restricted to the repository and to the minimum Actions permission
needed to dispatch the workflow.
Never commit that token to the repository.
Requirements
requirements.txt:
requests
No browser automation framework is required by the current version.
Repository Structure
price-monitor/
|
|-- monitor.py
|-- prodotti.json
|-- stato.json
|-- requirements.txt
|-- README.md
|
`-- .github/
    `-- workflows/
        |-- monitor.yml
        `-- test-tinyfish-json.yml   # optional diagnostic workflow
The TinyFish diagnostic workflow/script is useful while investigating
how a new website is represented in JSON or HTML, but it is not required
for normal scheduled monitoring.
Free-Tier Limits
TinyFish Fetch
TinyFish Fetch is currently free, does not draw from the TinyFish
Wallet, and requires no credit card to start.
Published limits:
150 URLs per minute
1,000 URLs per day
The monitor first fetches configured URLs in JSON. An additional HTML
fetch is performed only for products whose JSON result does not contain
a sufficiently reliable price.
With four checks per day:
JSON-only product:       about 4 fetched URLs/day
Always-HTML-fallback:    about 8 fetched URLs/day
TinyFish currently publishes a daily Fetch limit rather than a separate
monthly Fetch allowance.
Official pricing: https://www.tinyfish.ai/pricing
Brevo Free
Brevo Free currently includes:
300 email sends per day
Transactional email is supported. The full daily allowance corresponds
to approximately 9,000 sends over a 30-day month, but the operative
limit is daily and unused sends do not roll over.
No credit card is required for the Free plan.
Official information:
https://help.brevo.com/hc/en-us/articles/208589409-About-Brevo-s-pricing-plans
Normal monitor runs do not email every recipient for every product.
Emails are generated only when a notification condition occurs, so
typical usage should be far below the daily allowance.
Service limits and pricing can change. Check the official TinyFish and
Brevo documentation periodically.

Cost Model
The current architecture does not require:
- a paid VPS;
- a computer running 24/7;
- a paid browser automation service;
- TinyFish Agent;
- TinyFish Browser;
- a paid email plan.
The project uses TinyFish Fetch, not the paid TinyFish Agent or
Browser products.
As long as usage remains within the applicable free-tier limits, the
monitoring workflow can operate without a recurring service cost.
Adding a New Product
Add a new object to prodotti.json, assign a unique stable ID, provide
the direct product URL, set the threshold, and select the symbolic
recipient names.
{
  "id": "new-product",
  "nome": "New Product",
  "url": "https://shop.example.com/product/123",
  "soglia": 10.00,
  "destinatari": ["EMAIL_ME"]
}
No change to monitor.py should normally be required.
At the next run, the corresponding state entry is created automatically.
Removing a Product
Remove the product from prodotti.json.
At the next execution, its obsolete entry is automatically removed from
stato.json.
Testing a New Website
1. Add the product normally to prodotti.json.
2. Run the monitor manually through GitHub Actions.
3. Check the detected price and extraction method in the workflow log.
4. Compare the detected price with the retailer's product page.
Typical successful JSON extraction:
Detected price: 19.79 EUR
Extraction method: json_description+document
Typical HTML fallback:
JSON: price not identified. Trying TinyFish HTML fallback...
Detected price: 2.56 EUR
Extraction method: html_product_area
If no price can be identified with sufficient confidence, do not force a
random numeric match. Use the TinyFish diagnostic workflow/script to
inspect the JSON and HTML returned for that URL before changing the
extraction logic.
Security
Do not commit API keys, email addresses, or GitHub access tokens.
Keep sensitive values in GitHub Actions repository secrets and in the
private scheduler configuration.
Sensitive values include:
TINYFISH_API_KEY
BREVO_API_KEY
BREVO_SENDER
EMAIL_*
GitHub fine-grained PAT used by cron-job.org
This separation is especially important for public repositories.
Design Principles
1. Prefer reliable extraction over aggressive extraction.
2. Never treat an ambiguous number as a price merely because it looks
   like one.
3. Use structured JSON first and HTML only as a fallback.
4. Keep product configuration independent from individual websites.
5. Do not require CSS selectors or store-specific configuration for
   normal use.
6. Avoid duplicate notifications.
7. Preserve state between executions.
8. Keep secrets outside the repository.
9. Keep the system cloud-based and compatible with free tiers.
Current Status
The project now has a stable multi-site baseline using:
- Python;
- TinyFish Fetch JSON;
- TinyFish Fetch HTML fallback;
- Brevo transactional email;
- GitHub Actions;
- cron-job.org;
- JSON-based product configuration and persistent state.
The extraction strategy has been validated against multiple real
e-commerce page structures, including cases where structured JSON is
sufficient and cases where HTML fallback is necessary.
Future compatibility should be improved from real test cases rather than
by accumulating speculative store-specific parsers.
Disclaimer
This is a personal monitoring tool.
Website structures, prices, availability, terms of service, APIs, and
third-party service limits can change at any time. A successful
extraction today does not guarantee permanent compatibility with a
website.
Always verify important purchase decisions on the retailer's product
page before ordering.
