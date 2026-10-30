"""CampusHelp AI -- Streamlit UI only. Database logic: db.py | AI logic: ai_service.py"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import ai_service
import db
import lab_ui

st.set_page_config(page_title="CampusHelp AI", page_icon="🎓", layout="wide")

NAVY, BLUE = "#0B1F3A", "#1F6FEB"
STATUS_ICON = {"Open": "🔵", "Assigned": "🟣", "In Progress": "🟠", "Resolved": "🟢", "Closed": "⚫"}
PRIO_ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}
PRIO_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
STATUSES = ["Open", "Assigned", "In Progress", "Resolved", "Closed"]
ACTIVE = ["Open", "Assigned", "In Progress"]
SLA_HOURS = {"Critical": 4, "High": 24, "Medium": 72, "Low": 120}
UI_TRANSITIONS = {"Open": ["Closed"], "Assigned": ["In Progress", "Closed"],
                  "In Progress": ["Assigned", "Closed"], "Resolved": ["In Progress", "Closed"], "Closed": []}
NAV = {
    "STUDENT": ["Dashboard", "Submit Complaint", "My Tickets", "AI Quiz Lab", "About / System Status"],
    "STAFF": ["Dashboard", "Staff Ticket Queue", "Analytics", "AI Insights", "AI Quiz Lab", "About / System Status"],
    "ADMIN": ["Dashboard", "Staff Ticket Queue", "Analytics", "AI Insights", "AI Quiz Lab", "About / System Status"],
}
EMERGENCY_RE = re.compile(r"(^|[^a-z])(fire|smoke|gas leak|short[- ]?circuit|sparking|sparks|electric shock|"
                          r"electrocut[a-z]*|exposed wires?|flood(ed|ing)?|injur(y|ed)|collapse[a-z]*)([^a-z]|$)", re.I)

CSS = f"""
<style>
.block-container {{padding-top: 1.5rem;}}
[data-testid="stSidebar"] {{background: {NAVY};}}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] span {{color: #E8EEF8;}}
[data-testid="stSidebar"] button p, [data-testid="stSidebar"] button span {{color: {NAVY} !important;}}
.hero {{background: linear-gradient(120deg, {NAVY}, {BLUE}); color: #fff; padding: 1.4rem 1.8rem; border-radius: 14px; margin-bottom: 1rem;}}
.hero h1 {{color:#fff; margin:0; font-size:2rem;}} .hero p {{color:#DCE9FB; margin:.2rem 0 0 0;}}
.kpi {{background:#fff; border-radius:12px; padding:.9rem 1.1rem; box-shadow:0 1px 4px rgba(11,31,58,.12);}}
.kpi-label {{color:#5B6B82; font-size:.8rem; text-transform:uppercase; letter-spacing:.04em;}}
.kpi-value {{color:{NAVY}; font-size:1.9rem; font-weight:700; line-height:1.2;}}
.kpi-sub {{color:#7A8aa0; font-size:.75rem;}}
</style>"""


# ============================================================ state & helpers ==
def init_state():
    for k, v in {"user": None, "mode": None, "nonce": 0, "preview": None, "flash": None}.items():
        st.session_state.setdefault(k, v)


def is_live() -> bool:
    return st.session_state.get("mode") == "oracle"


def flash(kind: str, msg: str):
    st.session_state.flash = (kind, msg)


def show_flash():
    f = st.session_state.pop("flash", None)
    if f:
        {"success": st.success, "warning": st.warning, "error": st.error}.get(f[0], st.info)(f[1])


def oracle_status(force: bool = False) -> dict:
    if force or "ora_status" not in st.session_state:
        if force:
            db.reset_pool()
        st.session_state.ora_status = db.check_connection()
    return st.session_state.ora_status


def kpi(label, value, sub="", color=BLUE):
    st.markdown(f"<div class='kpi' style='border-left:6px solid {color}'><div class='kpi-label'>{label}</div>"
                f"<div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)


def _s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


# ================================================================ demo data ====
DEMO_USERS = [
    {"user_id": 1, "username": "aarav", "full_name": "Aarav Sharma", "role": "STUDENT", "dept_id": None, "department": None},
    {"user_id": 2, "username": "simran", "full_name": "Simran Kaur", "role": "STUDENT", "dept_id": None, "department": None},
    {"user_id": 3, "username": "it_rahul", "full_name": "Rahul Verma", "role": "STAFF", "dept_id": 1, "department": "IT Support"},
    {"user_id": 4, "username": "fac_meera", "full_name": "Meera Nair", "role": "STAFF", "dept_id": 2, "department": "Facilities"},
    {"user_id": 5, "username": "host_anil", "full_name": "Anil Gupta", "role": "STAFF", "dept_id": 3, "department": "Hostel Administration"},
    {"user_id": 9, "username": "admin", "full_name": "Dr. Kavita Rao", "role": "ADMIN", "dept_id": None, "department": None},
]
DEMO_DEPT_ID = {n: i + 1 for i, n in enumerate(ai_service.DEPARTMENTS)}
DEMO_LOCATIONS = ["Main Library", "Computer Lab 2", "Classroom A-101", "Boys Hostel", "Girls Hostel",
                  "Cafeteria", "Admin Block", "Sports Complex", "Campus-wide / Other"]


def _drow(now, i, title, desc, status, prio, cat, dept, loc, sid, assignee, hrs, res_hrs=None, esc="N", note=None):
    users = {u["user_id"]: u for u in DEMO_USERS}
    asg = next((u for u in DEMO_USERS if u["username"] == assignee), None)
    created = now - timedelta(hours=hrs)
    age = float(res_hrs) if res_hrs else float(hrs)
    return {"ticket_id": i, "title": title, "description": desc, "status": status, "priority": prio,
            "escalated_flag": esc, "category": cat, "department": dept, "dept_id": DEMO_DEPT_ID[dept],
            "location": loc, "student_id": sid, "student_name": users[sid]["full_name"],
            "assigned_to": asg["user_id"] if asg else None, "assignee_name": asg["full_name"] if asg else None,
            "resolution_note": note, "created_at": created, "updated_at": created,
            "resolved_at": created + timedelta(hours=res_hrs) if res_hrs else None, "age_hours": age,
            "sla_target_hours": SLA_HOURS[prio],
            "sla_breached": "Y" if age > SLA_HOURS[prio] else "N"}


def ensure_demo():
    if "demo_df" in st.session_state:
        return
    now = datetime.now()
    rows = [
        _drow(now, 101, "Wi-Fi down in Computer Lab 2", "Wi-Fi unavailable since morning; about 40 students affected.", "In Progress", "High", "IT & Network", "IT Support", "Computer Lab 2", 1, "it_rahul", 6),
        _drow(now, 102, "Projector not working in A-101", "No signal from any laptop.", "Open", "Medium", "Classroom Equipment", "IT Support", "Classroom A-101", 2, None, 50),
        _drow(now, 103, "Water leakage in hostel bathroom", "Ceiling leaking on the second floor.", "Resolved", "High", "Hostel Maintenance", "Hostel Administration", "Boys Hostel", 1, "host_anil", 30, 20, note="Plumber replaced the damaged pipe joint."),
        _drow(now, 104, "Exposed wire sparking near cafeteria", "Wire sparks when it rains.", "In Progress", "Critical", "Utilities", "Facilities", "Cafeteria", 2, "fac_meera", 9, esc="Y"),
        _drow(now, 105, "Library AC not cooling", "Reading hall is warm in the afternoons.", "Open", "Low", "Library", "Library", "Main Library", 2, None, 100),
        _drow(now, 106, "Garbage overflowing near Boys Hostel", "Bins not emptied for three days.", "Open", "Medium", "Cleanliness", "Housekeeping", "Boys Hostel", 1, None, 20),
    ]
    st.session_state.demo_df = pd.DataFrame(rows)
    ev, ai = {}, {}
    for r in rows:
        ev[r["ticket_id"]] = [{"kind": "status", "at": r["created_at"], "actor": r["student_name"], "old_status": None,
                               "new_status": "Open", "text": "Ticket created"}]
        if r["assignee_name"]:
            ev[r["ticket_id"]].append({"kind": "status", "at": r["created_at"] + timedelta(hours=1), "actor": r["assignee_name"],
                                       "old_status": "Open", "new_status": "Assigned", "text": f"Assigned to {r['assignee_name']}"})
    st.session_state.demo_events, st.session_state.demo_ai = ev, ai


def lookups() -> dict:
    if is_live():
        return db.get_lookups()
    return {"departments": [{"dept_id": DEMO_DEPT_ID[n], "name": n} for n in ai_service.DEPARTMENTS],
            "categories": [{"category_id": i, "name": n} for i, n in enumerate(ai_service.CATEGORIES)],
            "locations": [{"location_id": i + 1, "name": n} for i, n in enumerate(DEMO_LOCATIONS)]}


# ============================================================ data accessors ===
def df_for_user(user: dict) -> pd.DataFrame:
    if is_live():
        return db.get_tickets(user)
    df = st.session_state.demo_df
    if user["role"] == "STUDENT":
        return df[df.student_id == user["user_id"]].copy()
    if user["role"] == "STAFF":
        return df[df.dept_id == user["dept_id"]].copy()
    return df.copy()


def get_events(tid: int) -> list[dict]:
    return db.get_timeline(tid) if is_live() else st.session_state.demo_events.get(tid, [])


def get_ai(tid: int):
    return db.get_ai_analysis(tid) if is_live() else st.session_state.demo_ai.get(tid)


def decorate(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["Ticket"] = d["ticket_id"].map(lambda i: f"#{i}")
    d["Title"] = d["title"]
    d["Priority"] = d["priority"].map(lambda p: f"{PRIO_ICON.get(p, '⚪')} {p}")
    d["Status"] = d["status"].map(lambda s: f"{STATUS_ICON.get(s, '⚪')} {s}")
    d["SLA"] = d["sla_breached"].map({"Y": "⚠️ Breached", "N": "✅ Within"})
    d["Category"], d["Department"] = d["category"], d["department"]
    d["Assigned to"] = d["assignee_name"].fillna("— unassigned")
    d["Created"] = pd.to_datetime(d["created_at"]).dt.strftime("%d %b, %H:%M")
    d["Age (h)"] = d["age_hours"]
    return d


COLS_STUDENT = ["Ticket", "Title", "Status", "Priority", "Category", "Assigned to", "Created", "Age (h)"]
COLS_STAFF = ["Ticket", "Title", "Status", "Priority", "SLA", "Department", "Assigned to", "Created", "Age (h)"]


def kpi_row(df: pd.DataFrame):
    total = len(df)
    active = int(df.status.isin(ACTIVE).sum())
    done = int(df.status.isin(["Resolved", "Closed"]).sum())
    breached = int(((df.sla_breached == "Y") & df.status.isin(ACTIVE)).sum())
    res = df[df.resolved_at.notna()]
    avg = f"{float(res.age_hours.astype(float).mean()):.1f} h" if len(res) else "—"
    c = st.columns(5)
    with c[0]: kpi("Total tickets", total)
    with c[1]: kpi("Active", active, "open / assigned / in progress", "#F59E0B")
    with c[2]: kpi("Resolved", done, "resolved or closed", "#16A34A")
    with c[3]: kpi("SLA breached", breached, "active tickets past target", "#DC2626")
    with c[4]: kpi("Avg resolution", avg, "resolved tickets")


# ===================================================================== login ===
def login_page():
    st.markdown("<div class='hero'><h1>🎓 CampusHelp AI</h1><p>Campus complaint management with AI triage "
                "· Python · Oracle PL/SQL · Groq LLM</p></div>", unsafe_allow_html=True)
    stt = oracle_status()
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Sign in (demo accounts)")
        st.caption("Demo-only login: pick an account, no password. Real password authentication is not implemented.")
        if stt["usable"]:
            st.success(f"Oracle connected (PDB: {stt['pdb']}) — PL/SQL package and trigger are valid.")
            try:
                users = db.get_users()
            except db.DBError as e:
                st.error(str(e)); return
            i = st.selectbox("Account", range(len(users)), format_func=lambda k: f"{users[k]['full_name']} — {users[k]['role'].title()}"
                             + (f" ({users[k]['department']})" if users[k]["department"] else ""))
            if st.button("Sign in", type="primary"):
                st.session_state.update(user=users[i], mode="oracle")
                st.session_state.pop("nav", None)
                st.rerun()
        else:
            st.error(f"Oracle is not usable: {stt['message']}")
            st.info("You can still demonstrate Python + AI in **Demo mode** (sample data held in memory; "
                    "no Oracle, no PL/SQL, staff actions disabled).")
            c1, c2 = st.columns(2)
            if c1.button("🔄 Retry Oracle connection"):
                oracle_status(force=True); st.rerun()
            if c2.button("▶ Continue in Demo mode", type="primary"):
                st.session_state.mode = "demo"; ensure_demo()
            if st.session_state.get("mode") == "demo":
                i = st.selectbox("Demo account", range(len(DEMO_USERS)), format_func=lambda k: f"{DEMO_USERS[k]['full_name']} — {DEMO_USERS[k]['role'].title()}")
                if st.button("Sign in (demo mode)", type="primary"):
                    st.session_state.user = DEMO_USERS[i]
                    st.session_state.pop("nav", None)
                    st.rerun()
    with right:
        st.subheader("Status")
        st.write(f"**Database:** {'🟢 connected' if stt['ok'] else '🔴 unavailable'}")
        st.write(f"**AI (Groq):** {'🟢 key configured' if ai_service.is_configured() else '🟠 GROQ_API_KEY not set'} · model `{ai_service.get_model()}`")


# ================================================================== sidebar ====
def sidebar(user: dict) -> str:
    with st.sidebar:
        st.markdown("## 🎓 CampusHelp AI")
        st.markdown(f"**{user['full_name']}**  \n{user['role'].title()}" + (f" · {user['department']}" if user.get("department") else ""))
        page = st.radio("Navigation", NAV[user["role"]], key="nav", label_visibility="collapsed")
        st.markdown("🟢 **Oracle live**" if is_live() else "🟠 **Demo mode** (no Oracle)")
        if st.button("Log out"):
            for k in ("user", "mode", "preview", "nav"):
                st.session_state.pop(k, None)
            st.rerun()
    return page


# ============================================================== ticket detail ==
def _post_comment(tid: int, user: dict):
    body = st.session_state.get(f"cm{tid}", "").strip()
    if len(body) < 2:
        flash("warning", "Write a comment first."); return
    try:
        if is_live():
            db.add_comment(tid, user["user_id"], body)
        else:
            st.session_state.demo_events.setdefault(tid, []).append(
                {"kind": "comment", "at": datetime.now(), "actor": user["full_name"], "old_status": None, "new_status": None, "text": body})
        st.session_state[f"cm{tid}"] = ""
        flash("success", "Comment added.")
    except db.DBError as e:
        flash("error", str(e))


def render_timeline(tid: int):
    events = sorted(get_events(tid), key=lambda e: pd.Timestamp(e["at"]))
    if not events:
        st.caption("No activity yet."); return
    for e in events:
        when = pd.Timestamp(e["at"]).strftime("%d %b %Y, %H:%M")
        actor, text = _s(e.get("actor")) or "system", _s(e.get("text"))
        if e["kind"] == "comment":
            st.markdown(f"💬 **{when}** · {actor}  \n{text}")
        else:
            old, new = _s(e.get("old_status")), _s(e.get("new_status"))
            arrow = f"{old} → {new}" if old and old != new else new
            st.markdown(f"🔷 **{when}** · {actor} — *{arrow}*" + (f"  \n{text}" if text else ""))


def render_ai_panel(tid: int, row):
    ai = get_ai(tid)
    st.markdown("#### 🤖 AI analysis")
    if not ai:
        st.caption("No AI analysis stored for this ticket (AI was unavailable at submission, or it is seed data)."); return
    st.write(f"**Summary:** {ai['summary']}")
    st.write(f"**Suggested:** {ai['ai_category']} · {ai['ai_department']} · {PRIO_ICON.get(ai['ai_priority'], '')} {ai['ai_priority']}")
    st.write(f"**Why:** {ai['reason']}")
    st.caption(f"Model: {ai.get('model_name') or 'n/a'} · AI output is a recommendation only; staff decide the final values.")


def render_detail(user: dict, tid: int, df: pd.DataFrame, staff: bool = False):
    match = df[df.ticket_id == tid]
    if match.empty:
        st.warning("Ticket not found or not visible to your role."); return
    row = match.iloc[0]
    with st.container(border=True):
        st.subheader(f"#{tid} · {row['title']}")
        st.write(f"{STATUS_ICON.get(row['status'], '')} **{row['status']}**  ·  {PRIO_ICON.get(row['priority'], '')} **{row['priority']}**"
                 + ("  ·  🚨 emergency rule applied" if row["escalated_flag"] == "Y" else "")
                 + ("  ·  ⚠️ SLA breached" if row["sla_breached"] == "Y" else ""))
        a, b = st.columns(2)
        a.write(f"**Reported by:** {row['student_name']}  \n**Location:** {_s(row['location']) or '—'}  \n**Created:** {pd.Timestamp(row['created_at']).strftime('%d %b %Y, %H:%M')}")
        b.write(f"**Category:** {row['category']}  \n**Department:** {row['department']}  \n**Assigned to:** {_s(row['assignee_name']) or '— unassigned'}  \n"
                f"**Age / SLA target:** {row['age_hours']} h / {row['sla_target_hours']} h")
        st.write(row["description"])
        if _s(row["resolution_note"]):
            st.success(f"**Resolution:** {row['resolution_note']}")
        render_ai_panel(tid, row)
        st.markdown("#### 🕒 Activity timeline")
        render_timeline(tid)
        if not is_live():
            st.caption("Demo mode: comments live in session memory only.")
        st.text_input("Add a comment", key=f"cm{tid}")
        st.button("Post comment", key=f"pc{tid}", on_click=_post_comment, args=(tid, user))
    if staff:
        render_actions(user, row)


# ============================================================ staff actions ====
def _apply_ai(tid: int, ai: dict, cats: list, depts: list):
    if ai["ai_category"] in cats: st.session_state[f"cat{tid}"] = ai["ai_category"]
    if ai["ai_department"] in depts: st.session_state[f"dep{tid}"] = ai["ai_department"]
    if ai["ai_priority"] in ai_service.PRIORITIES: st.session_state[f"pri{tid}"] = ai["ai_priority"]


def render_actions(user: dict, row):
    tid = int(row["ticket_id"])
    st.markdown("### 🛠 Staff actions")
    if not is_live():
        st.info("🔒 Assign / status / resolve call PL/SQL procedures and need a live Oracle connection. Disabled in demo mode.")
        return
    lk = lookups()
    cats, depts = [c["name"] for c in lk["categories"]], [d["name"] for d in lk["departments"]]
    dept_id = {d["name"]: int(d["dept_id"]) for d in lk["departments"]}
    ai = get_ai(tid)
    t1, t2, t3 = st.tabs(["Triage & assign", "Update status", "Resolve"])
    with t1:
        st.session_state.setdefault(f"cat{tid}", row["category"])
        st.session_state.setdefault(f"dep{tid}", row["department"])
        st.session_state.setdefault(f"pri{tid}", row["priority"])
        if ai:
            st.caption(f"AI suggests: {ai['ai_category']} · {ai['ai_department']} · {ai['ai_priority']}")
            st.button("Use AI suggestion", key=f"ua{tid}", on_click=_apply_ai, args=(tid, ai, cats, depts))
        c1, c2, c3 = st.columns(3)
        cat = c1.selectbox("Category", cats, key=f"cat{tid}")
        dep = c2.selectbox("Department", depts, key=f"dep{tid}")
        pri = c3.selectbox("Priority", ai_service.PRIORITIES, key=f"pri{tid}")
        if row["escalated_flag"] == "Y":
            st.warning("Emergency keyword rule: priority cannot be lowered below Critical (enforced in PL/SQL).")
        staff = db.get_staff(dept_id[dep])
        if not staff:
            st.warning("No staff members in this department.")
        else:
            names = {int(s["user_id"]): s["full_name"] for s in staff}
            ids = list(names)
            cur = row["assigned_to"]
            idx = ids.index(int(cur)) if _s(cur) and int(cur) in ids else 0
            who = st.selectbox("Assign to", ids, index=idx, format_func=names.get, key=f"who{tid}_{dep}")
            if st.button("Save triage & assign", type="primary", key=f"as{tid}"):
                try:
                    db.assign_ticket(tid, who, user["user_id"], cat, dep, pri)
                    flash("success", "Ticket updated via PKG_TICKET_WORKFLOW.ASSIGN_TICKET."); st.rerun()
                except db.DBError as e:
                    st.error(str(e))
    with t2:
        options = UI_TRANSITIONS.get(row["status"], [])
        if not options:
            st.info(f"No status changes available from '{row['status']}'.")
        else:
            new = st.selectbox("New status", options, key=f"ns{tid}")
            note = st.text_input("Note (optional)", key=f"sn{tid}")
            if st.button("Update status", key=f"us{tid}"):
                try:
                    db.update_status(tid, new, user["user_id"], note or None)
                    flash("success", f"Status changed to {new}."); st.rerun()
                except db.DBError as e:
                    st.error(str(e))
    with t3:
        if row["status"] not in ("Assigned", "In Progress"):
            st.info("Only Assigned or In Progress tickets can be resolved.")
        else:
            note = st.text_area("Resolution note (min. 10 characters)", key=f"rn{tid}")
            if st.button("Mark as resolved", type="primary", key=f"rs{tid}"):
                try:
                    db.resolve_ticket(tid, user["user_id"], note)
                    flash("success", "Ticket resolved via PKG_TICKET_WORKFLOW.RESOLVE_TICKET."); st.rerun()
                except db.DBError as e:
                    st.error(str(e))


# ==================================================================== pages ====
def page_dashboard(user: dict):
    st.title("Dashboard")
    df = df_for_user(user)
    scope = {"STUDENT": "your tickets", "STAFF": f"{user.get('department')} tickets", "ADMIN": "all campus tickets"}[user["role"]]
    st.caption(f"Showing {scope}")
    kpi_row(df)
    st.write("")
    if df.empty:
        st.info("No tickets yet."); return
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Recent tickets")
        cols = COLS_STUDENT if user["role"] == "STUDENT" else COLS_STAFF
        st.dataframe(decorate(df).sort_values("created_at", ascending=False).head(8)[cols], hide_index=True)
    with right:
        st.subheader("By status")
        s = df.status.value_counts().reindex(STATUSES, fill_value=0).reset_index()
        s.columns = ["Status", "Tickets"]
        fig = px.bar(s, x="Status", y="Tickets", color_discrete_sequence=[BLUE])
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig)
    if user["role"] != "STUDENT":
        urgent = df[df.priority.isin(["Critical", "High"]) & df.assigned_to.isna() & df.status.isin(ACTIVE)]
        if len(urgent):
            st.warning(f"{len(urgent)} High/Critical ticket(s) are still unassigned — see Staff Ticket Queue.")


def _complaint_form_keys():
    n = st.session_state.nonce
    return f"t{n}", f"d{n}", f"l{n}"


def _create_complaint(user, title, desc, loc_name, res):
    lk = lookups()
    loc_id = next(l["location_id"] for l in lk["locations"] if l["name"] == loc_name)
    if res.ok:
        cat, dept, prio = res.data["category"], res.data["department"], res.data["priority"]
    else:
        cat, dept, prio = "Other", "General Support", "Medium"   # manual-triage defaults, NOT an AI result
    if is_live():
        tid, esc = db.create_ticket(title, desc, user["user_id"], cat, dept, prio, loc_id)
        if res.ok:
            try:
                db.record_ai_analysis(tid, res.model, **{k: res.data[k] for k in ("category", "department", "priority", "summary", "reason")})
            except db.DBError as e:
                flash("warning", f"Ticket #{tid} created, but the AI analysis could not be stored: {e}")
    else:
        df = st.session_state.demo_df
        tid = int(df.ticket_id.max()) + 1
        esc = "Y" if EMERGENCY_RE.search(f"{title} {desc}") else "N"
        if esc == "Y":
            prio = "Critical"
        row = _drow(datetime.now(), tid, title, desc, "Open", prio, cat, dept, loc_name, user["user_id"], None, 0)
        row["escalated_flag"] = esc
        st.session_state.demo_df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        st.session_state.demo_events[tid] = [{"kind": "status", "at": datetime.now(), "actor": user["full_name"],
                                              "old_status": None, "new_status": "Open", "text": "Ticket created"}]
        if res.ok:
            st.session_state.demo_ai[tid] = {"model_name": res.model, "ai_category": res.data["category"], "ai_department": res.data["department"],
                                             "ai_priority": res.data["priority"], "summary": res.data["summary"], "reason": res.data["reason"]}
    msg = f"✅ Ticket #{tid} submitted."
    if esc == "Y":
        msg += " 🚨 Safety keywords detected: priority set to Critical by the deterministic rule."
    if not res.ok:
        msg += " (AI analysis was unavailable — staff will triage manually.)"
    if "flash" not in st.session_state or st.session_state.get("flash") is None:
        flash("success", msg)
    st.session_state.nonce += 1
    st.session_state.preview = None


def page_submit(user: dict):
    st.title("Submit Complaint")
    kt, kd, kl = _complaint_form_keys()
    left, right = st.columns([3, 2])
    with left:
        title = st.text_input("Title", key=kt, max_chars=150, placeholder="e.g. Wi-Fi not working in Computer Lab 2")
        desc = st.text_area("Describe the issue", key=kd, height=170, max_chars=3000, placeholder="What happened, since when, who is affected?")
        loc = st.selectbox("Location", [l["name"] for l in lookups()["locations"]], key=kl)
        b1, b2 = st.columns(2)
        do_preview = b1.button("🔍 Preview AI analysis", key=f"pv{st.session_state.nonce}")
        do_submit = b2.button("📨 Submit complaint", type="primary", key=f"sb{st.session_state.nonce}")
    if do_preview or do_submit:
        if len(title.strip()) < 5 or len(desc.strip()) < 10:
            st.warning("Please enter a title (5+ characters) and a description (10+ characters).")
        else:
            pv = st.session_state.preview
            if not pv or pv["key"] != (title.strip(), desc.strip()):
                with st.spinner("Analysing complaint with the AI model..."):
                    st.session_state.preview = {"key": (title.strip(), desc.strip()),
                                                "result": ai_service.analyze_complaint(title.strip(), desc.strip())}
            if do_submit:
                try:
                    _create_complaint(user, title.strip(), desc.strip(), loc, st.session_state.preview["result"])
                    st.rerun()
                except db.DBError as e:
                    st.error(f"Could not create the ticket: {e}")
    with right:
        with st.container(border=True):
            st.markdown("#### 🤖 AI analysis preview")
            pv = st.session_state.preview
            if not pv or pv["key"] != (title.strip(), desc.strip()):
                st.caption("Click **Preview AI analysis** to see the suggested category, department and priority before submitting.")
            elif pv["result"].ok:
                d = pv["result"].data
                st.write(f"**Category:** {d['category']}  \n**Department:** {d['department']}  \n**Priority:** {PRIO_ICON[d['priority']]} {d['priority']}")
                st.write(f"**Summary:** {d['summary']}")
                st.write(f"**Reason:** {d['reason']}")
                st.caption(f"Model: {pv['result'].model} · Recommendation only — staff can edit it; safety rules may raise priority.")
            else:
                st.warning(pv["result"].error)
                st.caption("You can still submit: the ticket is created with defaults (Other / General Support / Medium) "
                           "for manual triage. These defaults are NOT an AI result.")


def page_my_tickets(user: dict):
    st.title("My Tickets")
    df = df_for_user(user)
    if df.empty:
        st.info("You have not submitted any tickets yet."); return
    st.dataframe(decorate(df)[COLS_STUDENT], hide_index=True)
    labels = dict(zip(df.ticket_id.astype(int), df.title))
    tid = st.selectbox("Open ticket", list(labels), format_func=lambda i: f"#{i} — {labels[i]}")
    render_detail(user, int(tid), df)


def page_queue(user: dict):
    st.title("Staff Ticket Queue" if user["role"] == "STAFF" else "All Tickets")
    df = df_for_user(user)
    if df.empty:
        st.info("No tickets."); return
    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
    stat = f1.multiselect("Status", STATUSES, default=ACTIVE)
    prio = f2.multiselect("Priority", ai_service.PRIORITIES, default=ai_service.PRIORITIES)
    q = f3.text_input("Search title / description")
    unassigned = f4.checkbox("Unassigned only")
    if user["role"] == "ADMIN":
        dsel = st.multiselect("Department", sorted(df.department.unique()), default=sorted(df.department.unique()))
        df = df[df.department.isin(dsel)]
    view = df[df.status.isin(stat) & df.priority.isin(prio)]
    if q:
        view = view[view.title.str.contains(q, case=False, regex=False) | view.description.str.contains(q, case=False, regex=False)]
    if unassigned:
        view = view[view.assigned_to.isna()]
    view = view.assign(_r=view.priority.map(PRIO_RANK)).sort_values(["_r", "created_at"]).drop(columns="_r")
    st.caption(f"{len(view)} ticket(s)")
    st.dataframe(decorate(view)[COLS_STAFF] if len(view) else pd.DataFrame(columns=COLS_STAFF), hide_index=True)
    st.download_button("⬇️ Export filtered tickets (CSV)", view.drop(columns=["description"]).to_csv(index=False).encode("utf-8"),
                       "tickets.csv", "text/csv")
    if view.empty:
        return
    labels = dict(zip(view.ticket_id.astype(int), view.title))
    tid = st.selectbox("Review ticket", list(labels), format_func=lambda i: f"#{i} — {labels[i]}")
    render_detail(user, int(tid), df, staff=True)


def _fig(fig):
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig)


def page_analytics(user: dict):
    st.title("Analytics")
    df = df_for_user(user)
    if df.empty:
        st.info("No data to analyse yet."); return
    kpi_row(df)
    st.write("")
    blues = [NAVY, BLUE, "#5B9BF5", "#9CC3F9", "#DCE9FB"]
    c1, c2 = st.columns(2)
    with c1:
        s = df.status.value_counts().reindex(STATUSES, fill_value=0).reset_index(); s.columns = ["Status", "Tickets"]
        _fig(px.bar(s, x="Status", y="Tickets", title="Tickets by status", color_discrete_sequence=[BLUE]))
    with c2:
        p = df.priority.value_counts().reindex(ai_service.PRIORITIES, fill_value=0).reset_index(); p.columns = ["Priority", "Tickets"]
        _fig(px.pie(p, names="Priority", values="Tickets", hole=.5, title="Priority mix", color_discrete_sequence=blues))
    c3, c4 = st.columns(2)
    with c3:
        d = df.department.value_counts().reset_index(); d.columns = ["Department", "Tickets"]
        _fig(px.bar(d, x="Tickets", y="Department", orientation="h", title="Tickets by department", color_discrete_sequence=[NAVY]))
    with c4:
        c = df.category.value_counts().reset_index(); c.columns = ["Category", "Tickets"]
        _fig(px.bar(c, x="Tickets", y="Category", orientation="h", title="Tickets by category", color_discrete_sequence=[BLUE]))
    c5, c6 = st.columns(2)
    with c5:
        t = df.assign(Day=pd.to_datetime(df.created_at).dt.date).groupby("Day").size().reset_index(name="Tickets")
        _fig(px.line(t, x="Day", y="Tickets", markers=True, title="Tickets created per day", color_discrete_sequence=[BLUE]))
    with c6:
        r = df[df.resolved_at.notna()]
        if len(r):
            a = r.assign(h=r.age_hours.astype(float)).groupby("department")["h"].mean().round(1).reset_index()
            _fig(px.bar(a, x="department", y="h", title="Avg resolution time (hours)", labels={"department": "Department", "h": "Hours"}, color_discrete_sequence=[NAVY]))
        else:
            st.info("No resolved tickets yet.")
    st.download_button("⬇️ Export all tickets in scope (CSV)", df.drop(columns=["description"]).to_csv(index=False).encode("utf-8"), "analytics_tickets.csv", "text/csv")
    st.subheader("PL/SQL department report")
    if is_live():
        st.dataframe(db.plsql_report(), hide_index=True)
        st.caption("Produced by PKG_TICKET_WORKFLOW.TICKET_REPORT (PL/SQL, SYS_REFCURSOR).")
    else:
        st.info("🔒 Requires a live Oracle connection — the report is generated by a PL/SQL procedure.")


def page_about(user: dict):
    st.title("About / System Status")
    stt = oracle_status()
    cfg = db.config_status()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🗄 Oracle Database")
        if stt["usable"]:
            st.success(f"Connected · PDB `{stt['pdb']}` · {stt['tickets']} tickets")
        else:
            st.error(stt["message"] or "Not connected")
        st.write(f"Tables/schema: {'✅' if stt['schema_ready'] else '❌'}  ·  PKG_TICKET_WORKFLOW: {'✅' if stt['package_valid'] else '❌'}  ·  Trigger: {'✅' if stt['trigger_valid'] else '❌'}")
        st.write(f"Active mode: **{'Live Oracle' if is_live() else 'Demo mode (no Oracle)'}**")
        st.write(f"ORACLE_USER set: {'✅' if cfg['ORACLE_USER'] else '❌'} · ORACLE_PASSWORD set: {'✅' if cfg['ORACLE_PASSWORD'] else '❌'} · DSN: `{cfg['ORACLE_DSN']}`")
        if st.button("🔄 Re-check Oracle"):
            oracle_status(force=True); st.rerun()
    with c2:
        st.subheader("🤖 AI (Groq)")
        st.write(f"GROQ_API_KEY set: {'✅' if ai_service.is_configured() else '❌'} · model: `{ai_service.get_model()}`")
        if st.button("Run live AI test"):
            with st.spinner("Calling the model..."):
                res = ai_service.self_test()
            if res.ok:
                st.success("Real API call succeeded and the response passed validation.")
                st.json(res.data)
            else:
                st.error(res.error)
    st.subheader("What demonstrates what")
    st.table(pd.DataFrame([
        ["Python", "Streamlit UI, session state, role-based filtering, pandas analytics, CSV export, error handling"],
        ["Oracle SQL / PL/SQL", "Constrained tables, PKG_TICKET_WORKFLOW procedures/functions, history trigger, report cursor, view"],
        ["AI tools", "Groq LLM classifies complaints into validated JSON; staff can override; safety rules cannot be overridden by AI"],
    ], columns=["Subject", "Where"]))
    st.subheader("Needs live Oracle")
    st.write("Assign / status update / resolve (PL/SQL), persistent history, PL/SQL report. "
             "Demo mode supports: login, complaint submission + real AI analysis, viewing tickets, dashboard, analytics (in-memory data).")


def page_quiz(user: dict):
    lab_ui.quiz_page()


def page_insights(user: dict):
    lab_ui.insights_page(df_for_user(user), user)


PAGES = {"Dashboard": page_dashboard, "Submit Complaint": page_submit, "My Tickets": page_my_tickets,
         "Staff Ticket Queue": page_queue, "Analytics": page_analytics, "AI Insights": page_insights,
         "AI Quiz Lab": page_quiz, "About / System Status": page_about}


def main():
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    user = st.session_state.user
    if user is None:
        login_page(); return
    if st.session_state.mode == "demo":
        ensure_demo()
    page = sidebar(user)
    show_flash()
    try:
        PAGES[page](user)
    except db.DBError as e:
        st.error(f"Database error: {e}")


main()
