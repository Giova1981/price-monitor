Farmasave Price Monitor
An automated price-monitoring system for products listed on Farmasave.
The application periodically checks configured products, compares the detected Farmasave price with a custom threshold, and sends email notifications when relevant price events occur.
The system runs entirely in the cloud through GitHub Actions, so no computer needs to remain powered on.
Features
- Automatic Farmasave price checks
- Custom price threshold for each product
- Multiple recipients per product
- Email alerts when a product drops below its threshold
- Additional alerts when a new lower price is detected
- One-time notification when the price returns above the threshold
- Automatic handling of newly added recipients
- Persistent product state
- Automatic error tracking
- No repeated alerts when nothing relevant changes
- Manual or scheduled execution
- API keys and email addresses stored securely as GitHub Secrets
How It Works
Products are configured in:
prodotti.json
Each product contains:
- a unique and stable ID;
- product name;
- Farmasave URL;
- price threshold;
- one or more notification recipients.
Example:
{
  "id": "sun-secure-spf50",
  "nome": "Sun Secure Eau Solaire SPF50+ 200 ml",
  "url": "https://www.farmasave.it/sun-secure-eau-solaire-spf50.html",
  "soglia": 12.00,
  "destinatari": [
    "EMAIL_MANDARINO"
  ]
}
Real email addresses and API keys are not stored in the repository. They are provided to the application through GitHub Actions Secrets.
Architecture
The system uses four main components:
Python
monitor.py contains the application logic.
For each run, the script:
1. loads prodotti.json;
2. validates the product configuration;
3. requests the Farmasave pages through TinyFish Fetch;
4. extracts the Farmasave price;
5. compares the price with the configured threshold;
6. checks the previous product state;
7. determines whether a notification is required;
8. sends notifications through Brevo;
9. updates stato.json.
GitHub Actions
GitHub Actions runs the monitor automatically.
The workflow is stored in:
.github/workflows/monitor.yml
The monitor is currently scheduled four times per day:
Check	Time (Europe/Rome)
Morning	08:00
Midday	13:00
Afternoon	18:00
Evening	22:00


A manual check can also be started at any time from:
GitHub → Actions → Price Monitor → Run workflow
The workflow automatically commits changes to stato.json.
Concurrency control is enabled so that two Price Monitor executions do not update the state file at the same time.
TinyFish Fetch API
TinyFish Fetch is used to retrieve Farmasave product pages.
Direct requests from cloud runners may be blocked by Farmasave's anti-bot protection. TinyFish Fetch retrieves the page content and makes it available to the Python script.
The monitor searches the returned content for the Prezzo Farmasave value and extracts the corresponding price.
TinyFish Fetch Limits
At the time this README was prepared, the relevant published limits for TinyFish Fetch were:
Limit	TinyFish Fetch
Cost per fetched URL	$0
Maximum rate	150 URLs/minute
Daily limit	1,000 URLs/day
Separate monthly Fetch limit	None published
Credit card required for this usage	No


TinyFish currently states that Fetch can continue to operate at a $0 wallet balance.
Service limits and pricing can change, so the official TinyFish documentation should be checked periodically.
Current TinyFish Usage
With the current configuration:
- 5 products
- 4 checks per day
the application fetches:
5 products × 4 checks = 20 URLs/day
Estimated usage:
Period	URLs fetched
One check	5
One day	20
30 days	600
31 days	620


Compared with a limit of 1,000 URLs/day, the current configuration uses approximately:
20 / 1,000 = 2% of the daily limit
With four checks per day, the purely mathematical daily-limit ceiling would be:
1,000 / 4 = 250 products
This is only a theoretical value. With a much larger number of products, request size, processing time, API behavior, GitHub Actions execution time, and other technical limits would also need to be considered.
Because no separate monthly Fetch quota is currently published, the daily quota is the main TinyFish limit relevant to this project.
Brevo Transactional Email
Brevo is used to send transactional email notifications.
The monitor uses the Brevo API.
Credentials are stored as GitHub Secrets:
BREVO_API_KEY
BREVO_SENDER
Recipient email addresses are also stored as Secrets, for example:
EMAIL_ME
EMAIL_MANDARINO
This prevents email addresses and API credentials from being exposed in a public repository.
Brevo Free Plan Limits
At the time this README was prepared, the relevant Brevo Free plan limit was:
Limit	Brevo Free
Email sending limit	300 emails/day
Approximate 30-day maximum at full daily usage	9,000 emails
Transactional API	Available
SMTP	Available
Unused daily quota carried forward	No


The operational limit is 300 emails per day.
The approximately 9,000 emails/month figure is the mathematical equivalent of using all 300 daily emails for 30 days; the daily quota remains the actual constraint and unused daily capacity is not accumulated.
Service limits and pricing can change, so the official Brevo documentation should be checked periodically.
Current Brevo Usage
The monitor does not send an email at every price check.
Emails are sent only when a relevant event occurs. Therefore, under normal conditions, email usage is expected to remain far below the Brevo Free daily limit.
The exact number of emails depends on:
- how often prices cross thresholds;
- how often new price lows occur;
- how many recipients are assigned to each product;
- whether products return above their thresholds;
- whether repeated technical errors trigger an error notification.
Notification Logic
Price Drops Below the Threshold
When a product changes from:
ABOVE THRESHOLD → BELOW THRESHOLD
an email notification is sent.
Example:
Threshold:      €15.00
Previous price: €15.86
New price:      €14.70
An alert is sent.
New Product Already Below the Threshold
If a newly added product is already below its threshold during its first successful check, an initial notification is sent.
Product Remains Below the Threshold
If the product remains below the threshold but does not reach a new low:
No additional email is sent.
This prevents repeated notifications at every scheduled check.
New Price Low
If a product is already below its threshold and reaches a price lower than the last notified minimum, a new price-drop notification is sent.
Example:
Previously notified minimum: €8.27
Current price:               €8.27
No email.
Later:
New price: €7.99
A new price-drop email is sent.
Price Returns Above the Threshold
When the product changes from:
BELOW THRESHOLD → ABOVE THRESHOLD
one informational email is sent.
No additional above-threshold emails are sent while the product remains above the threshold.
If the price later drops below the threshold again, a new notification cycle begins.
Recipient Management
Each product can have different recipients.
Example:
"destinatari": [
  "EMAIL_MANDARINO",
  "EMAIL_ME"
]
The monitor records which symbolic recipients have already been notified during the current below-threshold cycle.
If a new recipient is added while the product is already below its threshold, only the newly added recipient receives the current below-threshold notification.
Existing recipients do not receive the same alert again.
If a new recipient is added at the same time that a new price low is detected, a single new-low notification is sent to all currently configured recipients. This prevents the new recipient from receiving two emails during the same execution.
State Management
The file:
stato.json
is maintained automatically by the monitor.
For each product, it records information such as:
- whether the product is above or below its threshold;
- last detected price;
- last notified minimum price;
- configured threshold;
- recipients already notified during the current cycle;
- consecutive error count;
- whether an error notification has already been sent.
Under normal operation, stato.json should not be edited manually.
The main file used to manage products is:
prodotti.json
Adding a Product
Add another object to prodotti.json.
Example:
{
  "id": "new-product",
  "nome": "Product Name",
  "url": "https://www.farmasave.it/product.html",
  "soglia": 10.00,
  "destinatari": [
    "EMAIL_ME"
  ]
}
The product ID must be unique and should remain stable.
On the next run, the monitor automatically creates the corresponding state entry.
Removing a Product
Remove the product from prodotti.json.
On the next execution, the corresponding entry is automatically removed from stato.json.
Changing a Price Threshold
The threshold can be changed directly in prodotti.json:
"soglia": 15.00
The monitor detects the change and realigns the product state.
A threshold change by itself does not generate an email, because it is a configuration change rather than an actual price movement.
Error Handling
Technical errors are kept separate from price events.
If the page cannot be retrieved or a valid Farmasave price cannot be extracted, the failure is not interpreted as a price change.
After:
3 consecutive failed checks
for the same product, one error notification is sent.
Additional error notifications are suppressed while the failure continues.
When a successful check occurs:
- the consecutive-error counter is reset;
- the error-notification state is reset;
- normal price monitoring resumes.
A later independent sequence of three consecutive errors can therefore trigger a new error notification.
Security
Sensitive information is not stored directly in the repository.
GitHub Actions Secrets are used for:
- TinyFish API key;
- Brevo API key;
- Brevo sender address;
- recipient email addresses.
Current Secrets include:
TINYFISH_API_KEY
BREVO_API_KEY
BREVO_SENDER
EMAIL_MANDARINO
EMAIL_ME
If a new symbolic recipient is created, for example:
EMAIL_PAOLO
it must be:
1. created as a GitHub Repository Secret;
2. exposed as an environment variable in monitor.yml;
3. referenced in prodotti.json.
Project Structure
price-monitor/
│
├── monitor.py
├── prodotti.json
├── stato.json
├── requirements.txt
│
└── .github/
    └── workflows/
        └── monitor.yml
monitor.py
Contains the application logic.
prodotti.json
Contains the product configuration.
This is the main file that normally needs to be edited.
stato.json
Contains the persistent monitoring state and is maintained automatically.
requirements.txt
Contains the required Python packages.
Current dependency:
requests
monitor.yml
Defines the GitHub Actions workflow and scheduled checks.
Current System Capacity
With the current configuration:
- 5 products
- 4 checks per day
the monitor performs:
20 product-page fetches per day
or approximately:
- 600 fetches in 30 days
- 620 fetches in 31 days
Against a TinyFish Fetch limit of 1,000 URLs/day, this is approximately 2% of the available daily quota.
For Brevo, the Free plan allows up to 300 emails/day, while this monitor sends messages only when meaningful events occur.
Under normal usage, both services therefore provide substantial headroom for the current configuration.
Services Used
- GitHub — source repository and GitHub Actions automation
- Python — application logic
- TinyFish Fetch API — retrieval of Farmasave product pages
- Brevo Transactional Email API — email notifications
- Farmasave — source website for monitored prices
Project Goal
The project provides an automated price-monitoring solution that:
- runs entirely in the cloud;
- does not require a computer to remain powered on;
- does not require an external database;
- maintains persistent product state;
- supports different recipients for different products;
- avoids repetitive notifications;
- tracks new price lows;
- handles temporary technical failures;
- supports manual and scheduled checks;
- currently operates within the free usage limits of TinyFish Fetch and Brevo Free.
Important Note About Service Limits
TinyFish and Brevo are external services. Their free-plan quotas, pricing, API availability, and terms may change independently of this project.
The limits documented above reflect the values used when this README was prepared and should be periodically compared with the providers' official documentation.
