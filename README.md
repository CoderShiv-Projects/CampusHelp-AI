# 🎓 CampusHelp AI

Campus complaint / support-ticket system. One app, three subjects:

| Subject | Where it shows up |
|---|---|
| **Python** | `app.py` (Streamlit UI, session state, role filtering, pandas/Plotly analytics, CSV export), `db.py` (python-oracledb), `ai_service.py` |
| **Oracle SQL / PL/SQL** | `schema.sql`: 8 tables, package `PKG_TICKET_WORKFLOW`, trigger `TRG_TICKET_HISTORY`, view, report procedures |
| **AI tools** | Groq hosted LLM classifies each complaint (category, department, priority, summary, reason) as validated JSON |

```
CampusHelpAI/
  app.py  db.py  ai_service.py  schema.sql
  requirements.txt  .env.example  .gitignore  README.md
```

## Setup (Windows PowerShell)

```powershell
py -m venv .venv
# if activation is blocked:  Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env          # fill ORACLE_USER, ORACLE_PASSWORD, GROQ_API_KEY
```

Minimum `.env`: `ORACLE_USER`, `ORACLE_PASSWORD`, `GROQ_API_KEY` (`ORACLE_DSN` defaults to `localhost:1521/FREEPDB1`; `GROQ_MODEL` defaults to `llama-3.3-70b-versatile` — if Groq has retired it, set any current chat model from console.groq.com).

### Create the Oracle schema (inside the PDB `FREEPDB1`)

1. Connect as an admin **to the PDB** (not the root container) and create the app user:
   ```powershell
   sqlplus system/<your_admin_password>@localhost:1521/FREEPDB1
   ```
   ```sql
   CREATE USER campushelp IDENTIFIED BY "ChangeMe_123" QUOTA UNLIMITED ON users;
   GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE VIEW, CREATE PROCEDURE, CREATE TRIGGER TO campushelp;
   EXIT
   ```
2. Run the schema as that user (from the project folder):
   ```powershell
   sqlplus campushelp/ChangeMe_123@localhost:1521/FREEPDB1 @schema.sql
   ```
   (SQL Developer / SQLcl: connect as `campushelp` to `FREEPDB1` and run `schema.sql` as a script, F5.)
   Check there are no compile errors and the final queries show `VALID` for the package, trigger and view.
   `schema.sql` is re-runnable: section 0 drops and recreates only the CampusHelp objects (resets data).
3. Put `ORACLE_USER=campushelp` and the password in `.env`.

### Run

```powershell
python -m streamlit run app.py
```
Open **About / System Status** → *Run live AI test* to verify Groq, and check the Oracle panel for database diagnostics.

## Demo accounts (demo-only role picker — **no passwords**)

| Role | Username | Name | Department |
|---|---|---|---|
| Student | `aarav`, `simran` | Aarav Sharma, Simran Kaur | – |
| Staff | `it_rahul` | Rahul Verma | IT Support |
| Staff | `fac_meera` | Meera Nair | Facilities |
| Staff | `host_anil` | Anil Gupta | Hostel Administration |
| Staff | `house_sunita`, `lib_priya`, `acad_vikram`, `gen_neha` | | Housekeeping / Library / Academic Admin / General Support |
| Admin | `admin` | Dr. Kavita Rao | – |

Login is a **demo-only account selector**; real password authentication is not implemented (documented limitation).

## Demo mode (when Oracle is not available)
If Oracle cannot be reached, the login page shows the diagnostic and offers **Demo mode**: sample tickets held in memory.
Works: login, complaint submission with the real AI call, viewing tickets, dashboard, analytics, comments (session only).
**Requires live Oracle:** assign / status update / resolve (PL/SQL package), ticket history trigger, PL/SQL report, persistence.
The UI never claims PL/SQL ran in demo mode.

## Troubleshooting
| Message | Meaning |
|---|---|
| "Cannot reach the Oracle listener" | Oracle service not running, or wrong host/port. Windows: Services → `OracleServiceFREE` and `OracleOraDB23ai…TNSListener` |
| "service name was not found" | Wrong `ORACLE_DSN`. Use `localhost:1521/FREEPDB1` |
| "Invalid Oracle username or password" | Check `.env`; user must be created in the PDB |
| "Table or view not found" | `schema.sql` not run in this user/PDB |
| "PKG_TICKET_WORKFLOW … invalid" | Re-run `schema.sql`, read `SHOW ERRORS`. After re-running, refresh the browser / restart Streamlit |
| "GROQ_API_KEY is not set" | Add it to `.env` and restart Streamlit; complaints still submit with manual-triage defaults |

## 5-minute demo script for your teacher
1. **Architecture (30 s):** Streamlit UI → `db.py` → Oracle PL/SQL package; `ai_service.py` → Groq. Show **About / System Status** (Oracle ✅, package ✅, trigger ✅) and click *Run live AI test*.
2. **Student:** sign in as *Aarav Sharma* → **Submit Complaint**: "Water not coming in hostel tap" + description → *Preview AI analysis* (category/department/priority/summary/reason) → *Submit*. Open **My Tickets** and show the timeline.
3. **Safety rule:** submit "Exposed wire sparking near the lab" → priority is forced to **Critical** by PL/SQL (`IS_EMERGENCY`), regardless of AI.
4. **Staff:** log out, sign in as the matching staff user (e.g. *Meera Nair*) → **Staff Ticket Queue** → open the ticket → review the AI recommendation → *Triage & assign* → *Update status* to In Progress → *Resolve* with a note. Try an invalid action (e.g. resolve an Open ticket) to show the PL/SQL exception message.
5. **Trigger:** in SQL*Plus run `SELECT * FROM ticket_history ORDER BY history_id DESC FETCH FIRST 5 ROWS ONLY;` and `EXEC pkg_ticket_workflow.print_status_report`.
6. **Admin:** sign in as *Dr. Kavita Rao* → **Analytics** (charts, PL/SQL department report, CSV export).

## Security notes
Secrets only in `.env` (git-ignored); never shown in the UI. All SQL uses bind variables. AI output is validated in Python and is advisory only.

## Known limitations
No password auth; AI default model name may need updating; no automated test suite; UI row-click selection uses dropdowns; Streamlit/Oracle behaviour was not verified against your machine (see final notes).
