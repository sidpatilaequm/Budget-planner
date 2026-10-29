# Budget planner version 2: actuals, Tally, TDS and simulations

Version 2 brings in what actually happened. Sources:
- **Tally:** fees and other money received, and expenses booked.
- **The new Actuals screen:** typed in, or imported from Excel.

The actuals feed four things:
- **Budget vs actual:** budget against actual, line by line and month by month.
- **Plan next year:** plan from actuals, or a forecast, instead of only last year's budget.
- **TDS:** a report with deposits, quarterly statements and alerts.
- **Simulations:** saved "what if" scenarios that can become next year's budget.

## 1. Updating the server

Nothing in `.env` changes.

```bash
git pull                       # or: git am 0001-Budget-planner-version-2.patch
docker compose -f docker-compose.prod.yml up -d --build
```

When the API starts:
- **New tables.** It creates the new tables (actuals, ledger mapping, TDS, scenarios, alerts). Nothing existing is changed. A DBA can apply `database/upgrade_v2_actuals_tds.sql` instead.
- **TDS rates.** It fills in the TDS rate table.
- **Role permissions.** It gives existing roles the new permissions once, and only where the role has no setting for them yet:
  - **Finance manager:** everything new.
  - **Department editor:** view actuals.
  - **Viewer:** view actuals and TDS.
  - **Other roles:** nothing until you tick it in **Users and roles**.

New permissions, under **Users and roles**:
- **Actuals and Tally:** view actuals; enter and import actuals; set up Tally and ledger mapping.
- **TDS:** view the TDS report and alerts; edit TDS rates and payees, and record deposits and returns.
- **Planning:** run budget simulations.

## 2. Actuals until Tally is connected

**Actuals → Add entry.**
1. Enter the date, whether it is income received or an expense, and the head and line.
2. Enter the amount before TDS, who it was paid to or received from, and the voucher number.
3. For payments, also enter the TDS category and the TDS deducted.

You can enter actuals only for the heads your user may change.

**Import Excel.** Download the template for the year and fill one row per entry:
- **Head and line:** use the names shown on the template's "Lines" sheet.
- **TDS codes:** listed on the "TDS categories" sheet.

The file is checked first: if any row has a problem, nothing is imported and you see which rows to fix.

Entered and imported rows can be edited and deleted. Rows from Tally can only be changed in Tally.

## 3. Connecting Tally

Tally Prime (and Tally.ERP 9) answers requests on the computer where it runs, on port 9000. This app runs on the internet and can't see that computer, so a small **bridge** on the Tally computer sends the data.

1. **In Tally:** **F1 Help › Settings › Connectivity**. Set "TallyPrime acts as" to **Both** and the port to **9000**. Keep the company open.
2. **In the planner:** **Actuals › Tally › Create an integration key**. Copy it: it is shown once. Creating a new key stops the old one.
3. **Download the bridge.** Save `tally_bridge.py` on the Tally computer. It needs Python 3.9 or later and nothing else.
4. **Test it once:**
   ```
   python tally_bridge.py --app https://budget.nexdaequmsupport.com --key tb_… --company "Company name in Tally"
   ```
   It sends this financial year, month by month, and prints what arrived.
5. **Schedule it.** Run it every 15 minutes with Windows Task Scheduler, or leave it running with `--every 15`.

**Each sync replaces Tally's entries for the period**, so vouchers changed or deleted in Tally are updated here. Cancelled and optional vouchers are left out.

**Direct connection:** if this server can reach the Tally computer (same network or VPN), enter its address under **Or connect directly**, then use **Test connection** and **Sync now**.

**Ledger mapping (once).** Under **Actuals › Tally**, map each Tally ledger to what it is:
- **Expense or income ledgers:** to a budget line. Expense debits and income credits count.
- **The TDS payable ledger(s):** to "TDS". Their credit on a voucher becomes the TDS deducted on that voucher's expenses.
- **Bank, cash, party and other balance-sheet ledgers:** to "Ignore".

Entries on ledgers not mapped yet wait under "To map", and there is an alert for them. Mapping a ledger updates the entries already received. Mapping is by ledger name and stays the same every year.

## 4. Budget vs actual, and planning from actuals

**Budget vs actual** shows, for each head and line:
- budget and actual to date
- the difference, which turns red when spending is above budget or income below it
- how much of the year's budget is used
- a forecast: actuals so far, budget for the rest

"To date" runs to the latest month that has any actual. The month view shows actuals for past months and the budget, in grey, for later months.

**Plan next year → Plan from** offers three bases:
- **Its budget:** as before.
- **Its actuals:** only what was really received and spent.
- **A forecast:** actuals for the months so far, budget for the rest. This is usually the best base mid-year.

Every percentage, fixed budget and limit works the same on any base.

## 5. TDS

From **1 April 2026** TDS falls under **section 393 of the Income-tax Act, 2025**. Rates and thresholds carried over from the 1961 Act. The app shows both the new reference and the old section, for example "393(1) Table Sl. 6(i) · old 194C". The rate table under **TDS › Rates and thresholds** starts with these figures; confirm them with your CA and change them when the law changes.

| Category | Old | Rate | Threshold |
|---|---|---|---|
| Contractors (work, incl. supply of labour) | 194C | 1% individual/HUF, 2% others | ₹30,000 a payment or ₹1,00,000 a year |
| Professional fees | 194J | 10% | ₹50,000 a year |
| Technical fees | 194J | 2% | ₹50,000 a year |
| Rent: land, building, furniture | 194I(b) | 10% | ₹50,000 a month |
| Rent: plant, machinery, equipment | 194I(a) | 2% | ₹50,000 a month |
| Commission or brokerage | 194H | 2% | ₹20,000 a year |
| Interest other than on securities (e.g. NBFC loans) | 194A | 10% | ₹10,000 a year |
| Purchase of goods (buyer turnover above ₹10 crore) | 194Q | 0.1% | ₹50 lakh a year |

Without a PAN the rate is at least 20%. A payee's lower-deduction certificate rate applies until its end date.

**Where the category comes from.** The first of these that is set wins: the entry, its Tally ledger, its budget line (**TDS › Budget lines**), or the payee.

**What should have been deducted**, per payee and category for the year:
- **Contractors (single and yearly limits):** TDS applies to any payment above the single limit. Once the year's total passes the yearly limit, it applies to the whole year's total, including earlier payments.
- **Professional fees, commission, interest and goods (yearly limit only):** once the year's total passes the limit, TDS applies to the whole total.
- **Rent (monthly limit):** TDS applies to each month whose rent passes the limit.

The report compares that with what was deducted, and marks each payee **Short deducted**, **Near threshold** (80% of the yearly limit reached), **Correct**, **Deducted more** or **Below threshold**.

**TDS › Deposits and returns:**
- **Monthly deposits.** Tax deducted in a month is due by the 7th of the next month, or 30 April for March. Record each challan.
- **Quarterly statements.** These are the old Form 26Q. They are due 31 July, 31 October, 31 January and 31 May. Mark each as filed with its acknowledgement number.

**TDS › Budget lines** sets a TDS category for each expense line, for example consultants under professional fees and transport contractors under contractors. It also shows the **budgeted TDS** for each month, an estimate for planning cash. Interest paid to banks does not attract TDS, but interest to NBFCs such as Mahindra Finance or HDB Finance normally does.

**Payees:** enter the name exactly as on the entries or in Tally, with the PAN and any lower-deduction certificate. The PAN's 4th letter sets the type: P or H is an individual or HUF.

The report can be downloaded as a spreadsheet (CSV).

## 6. Alerts

The bell in the header and the **Alerts** tab show what needs attention. Alerts are worked out from the latest data each time:

- **TDS:**
  - TDS short-deducted for a payee
  - a payee without a PAN
  - a payee near a threshold
  - a month's TDS not deposited, due within 7 days or overdue
  - a quarterly statement due within 15 days or overdue
  - a lower-deduction certificate ending within 30 days
- **Budget:**
  - a head more than 10% over its budget to date, or over its full-year budget
  - income more than 15% behind budget
- **Tally:**
  - ledgers to map
  - no data from Tally for 3 days

**Dismiss** hides an alert for you, and it comes back if the situation changes. **Show dismissed alerts** brings them all back.

## 7. Simulations

**Simulations** tries changes without touching any budget:

- **Start from:** a year's budget, actuals or forecast.
- **Overall changes:** expenses, fees and other income, and student numbers. You can also give a head its own change.
- **Adjustments:** a % change or an amount, for a head or for all income or expenses, between two months. For example, a new bus loan EMI of ₹12,00,000 from October to March, or diesel up 10% from June.
- **Cash:** the share of fees collected in cash, and the opening cash balance.

The result shows:
- income, expenses and surplus against the base
- the cash month by month, with the closing balance and the lowest point
- each head before and after

**Saved scenarios.** Save a scenario to come back to it later. Tick two to four to compare their totals and their cash month by month.

**Create next year from this** makes the next year's budget from a scenario. Amount adjustments become new lines under their head. This needs "Plan next year".

## 8. Tests

`backend/tests/test_v2.py` covers:
- manual entry, Excel import, budget vs actual, and planning from actuals and forecast
- Tally XML parsing, the bridge push, key checks, ledger mapping and TDS from the voucher
- deleted vouchers
- the TDS rules: contractor, professional with no PAN, near threshold, monthly rent, and due dates
- alerts and dismissal
- simulations, comparison and applying
- permissions

Run `pytest -q` in `backend/`. All 29 tests pass on SQLite and on MySQL/MariaDB.

**What was not tested:** the bridge and direct pull against a real Tally installation, because none was available. The requests use Tally's standard XML export of vouchers and ledgers, and the parser was tested on a voucher response in Tally's format. Run the bridge once against your Tally with a short date range first, and check the entries under **Actuals**.
