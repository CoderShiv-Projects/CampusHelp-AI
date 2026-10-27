"""Database layer for CampusHelp AI (python-oracledb, Thin mode -- no Instant Client).

All ticket mutations go through the PL/SQL package PKG_TICKET_WORKFLOW.
Every query uses bind variables; user input is never concatenated into SQL.
Errors are converted to short, secret-free messages (DBError).
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager

import oracledb
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
oracledb.defaults.fetch_lobs = False  # return CLOB columns as plain str

_pool = None


class DBError(Exception):
    """A friendly database error that is safe to show in the UI."""


# ----------------------------------------------------------------- config ---
def get_dsn() -> str:
    return os.getenv("ORACLE_DSN") or "localhost:1521/FREEPDB1"


def config_status() -> dict:
    """Which settings exist (never returns the password itself)."""
    return {
        "ORACLE_USER": bool(os.getenv("ORACLE_USER")),
        "ORACLE_PASSWORD": bool(os.getenv("ORACLE_PASSWORD")),
        "ORACLE_DSN": get_dsn(),
    }


_RULES = [
    (("ORA-01017", "DPY-3015"),
     "Invalid Oracle username or password. Check ORACLE_USER / ORACLE_PASSWORD in .env."),
    (("DPY-6001", "ORA-12514", "ORA-12154"),
     "The listener answered but the service name was not found. Check ORACLE_DSN "
     "(Oracle Free normally uses localhost:1521/FREEPDB1, not FREE)."),
    (("DPY-6005", "ORA-12541", "ORA-12170", "Connection refused", "WinError 10061", "timed out"),
     "Cannot reach the Oracle listener. Is the Oracle Database Free service running, and are "
     "host/port in ORACLE_DSN correct?"),
    (("ORA-00942",),
     "Table or view not found. Run schema.sql as the application user inside the correct PDB (FREEPDB1)."),
    (("PLS-00201", "ORA-06550", "ORA-04063", "ORA-04068", "PLS-00905"),
     "PL/SQL package PKG_TICKET_WORKFLOW is missing or invalid. Re-run schema.sql and check SHOW ERRORS."),
    (("ORA-02291",), "A referenced record (user, location, ...) does not exist."),
    (("ORA-01950", "ORA-01031"), "The database user lacks quota or privileges. See the grants in README / schema.sql."),
]


def explain(exc: Exception) -> str:
    """Turn a driver exception into a short message without secrets."""
    text = str(exc)
    m = re.search(r"ORA-20\d{3}: (.*)", text)  # our own RAISE_APPLICATION_ERROR messages
    if m:
        return m.group(1).strip().splitlines()[0]
    for needles, message in _RULES:
        if any(n in text for n in needles):
            return message
    first = text.strip().splitlines()[0] if text.strip() else type(exc).__name__
    pw = os.getenv("ORACLE_PASSWORD")
    if pw:
        first = first.replace(pw, "***")
    return f"Database error: {first[:220]}"


# ------------------------------------------------------------ connections ---
def reset_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.close(force=True)
        except Exception:
            pass
    _pool = None


def _get_pool():
    global _pool
    if _pool is None:
        user, pw = os.getenv("ORACLE_USER"), os.getenv("ORACLE_PASSWORD")
        if not user or not pw:
            raise DBError("ORACLE_USER / ORACLE_PASSWORD are not set. Copy .env.example to .env and fill them in.")
        try:
            _pool = oracledb.create_pool(user=user, password=pw, dsn=get_dsn(), min=1, max=5, increment=1)
        except oracledb.Error as exc:
            raise DBError(explain(exc)) from None
    return _pool


@contextmanager
def _conn():
    pool = _get_pool()
    try:
        conn = pool.acquire()
    except oracledb.Error as exc:
        reset_pool()
        raise DBError(explain(exc)) from None
    try:
        yield conn
    finally:
        try:
            pool.release(conn)
        except Exception:
            pass


def _query(sql: str, params: dict | None = None) -> pd.DataFrame:
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute(sql, params or {})
            cols = [d[0].lower() for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
    except oracledb.Error as exc:
        raise DBError(explain(exc)) from None


def _plsql(proc: str, args: list, outs: tuple = ()) -> list:
    """Call a PL/SQL procedure; `outs` are python types for trailing OUT parameters."""
    try:
        with _conn() as conn, conn.cursor() as cur:
            out_vars = [cur.var(t) for t in outs]
            cur.callproc(proc, list(args) + out_vars)
            return [v.getvalue() for v in out_vars]
    except oracledb.Error as exc:
        raise DBError(explain(exc)) from None


# ----------------------------------------------------------------- status ---
def check_connection() -> dict:
    """Diagnostics used by the login page and the System Status page."""
    res = {"ok": False, "usable": False, "message": "", "pdb": None, "tickets": None,
           "schema_ready": False, "package_valid": False, "trigger_valid": False}
    try:
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT SYS_CONTEXT('USERENV','CON_NAME') FROM dual")
            res["pdb"] = cur.fetchone()[0]
            res["ok"] = True
            try:
                cur.execute("SELECT COUNT(*) FROM tickets")
                res["tickets"] = cur.fetchone()[0]
                res["schema_ready"] = True
            except oracledb.Error:
                res["message"] = ("Connected, but the CampusHelp tables do not exist in this schema/PDB. "
                                  "Run schema.sql as the application user inside FREEPDB1.")
            cur.execute("SELECT object_type FROM user_objects WHERE status = 'VALID' AND "
                        "((object_name = 'PKG_TICKET_WORKFLOW' AND object_type = 'PACKAGE BODY') OR "
                        " (object_name = 'TRG_TICKET_HISTORY' AND object_type = 'TRIGGER'))")
            kinds = {r[0] for r in cur.fetchall()}
            res["package_valid"] = "PACKAGE BODY" in kinds
            res["trigger_valid"] = "TRIGGER" in kinds
            res["usable"] = res["schema_ready"] and res["package_valid"] and res["trigger_valid"]
            if res["schema_ready"] and not res["usable"]:
                res["message"] = "Connected, but PKG_TICKET_WORKFLOW / TRG_TICKET_HISTORY is missing or INVALID. Re-run schema.sql."
            if res["usable"]:
                res["message"] = "Connected."
    except DBError as exc:
        res["message"] = str(exc)
    except oracledb.Error as exc:
        res["message"] = explain(exc)
    return res


# ---------------------------------------------------------------- lookups ---
def _records(df: pd.DataFrame) -> list[dict]:
    out = []
    for rec in df.to_dict("records"):
        out.append({k: (None if (v is None or (isinstance(v, float) and pd.isna(v))) else v) for k, v in rec.items()})
    return out


def get_users() -> list[dict]:
    df = _query("SELECT u.user_id, u.username, u.full_name, u.role, u.dept_id, d.name AS department "
                "FROM users u LEFT JOIN departments d ON d.dept_id = u.dept_id "
                "ORDER BY CASE u.role WHEN 'ADMIN' THEN 1 WHEN 'STAFF' THEN 2 ELSE 3 END, u.full_name")
    users = _records(df)
    for u in users:
        u["user_id"] = int(u["user_id"])
        u["dept_id"] = int(u["dept_id"]) if u["dept_id"] is not None else None
    return users


def get_lookups() -> dict:
    return {
        "departments": _records(_query("SELECT dept_id, name FROM departments ORDER BY name")),
        "categories": _records(_query("SELECT category_id, name FROM categories ORDER BY name")),
        "locations": _records(_query("SELECT location_id, name FROM campus_locations ORDER BY name")),
    }


def get_staff(dept_id: int) -> list[dict]:
    df = _query("SELECT user_id, full_name FROM users WHERE role = 'STAFF' AND dept_id = :d ORDER BY full_name",
                {"d": int(dept_id)})
    return _records(df)


# ---------------------------------------------------------------- tickets ---
def _scope(user: dict) -> tuple[str, dict]:
    """Role-based row filter (constant SQL fragments + bind variables only)."""
    if user["role"] == "STUDENT":
        return "student_id = :student_id", {
        "student_id": int(user["user_id"])
    }
    if user["role"] == "STAFF":
        return "dept_id = :dept", {"dept": int(user["dept_id"])}
    return "1 = 1", {}  # ADMIN


def get_tickets(user: dict) -> pd.DataFrame:
    where, params = _scope(user)
    return _query(f"SELECT * FROM v_ticket_overview WHERE {where} ORDER BY created_at DESC", params)


def get_timeline(ticket_id: int) -> list[dict]:
    df = _query(
        "SELECT 'status' AS kind, h.changed_at AS at_time, u.full_name AS actor, h.old_status, h.new_status, h.note AS text "
        "FROM ticket_history h LEFT JOIN users u ON u.user_id = h.changed_by WHERE h.ticket_id = :tid "
        "UNION ALL "
        "SELECT 'comment', c.created_at, u.full_name, CAST(NULL AS VARCHAR2(15)), CAST(NULL AS VARCHAR2(15)), c.body "
        "FROM ticket_comments c JOIN users u ON u.user_id = c.user_id WHERE c.ticket_id = :tid "
        "ORDER BY 2", {"tid": int(ticket_id)})
    events = _records(df)
    for e in events:
        e["at"] = e.pop("at_time")
    return events


def get_ai_analysis(ticket_id: int) -> dict | None:
    df = _query("SELECT model_name, ai_category, ai_department, ai_priority, summary, reason, created_at "
                "FROM ai_analyses WHERE ticket_id = :tid ORDER BY created_at DESC FETCH FIRST 1 ROWS ONLY",
                {"tid": int(ticket_id)})
    recs = _records(df)
    return recs[0] if recs else None


# ------------------------------------------- PL/SQL-backed write operations ---
def create_ticket(title, description, student_id, category, department, priority, location_id):
    """Calls PKG_TICKET_WORKFLOW.CREATE_TICKET. Returns (ticket_id, escalated_flag)."""
    tid, esc = _plsql("pkg_ticket_workflow.create_ticket",
                      [title, description, int(student_id), category, department, priority,
                       int(location_id) if location_id is not None else None],
                      outs=(int, str))
    return int(tid), esc


def record_ai_analysis(ticket_id, model, category, department, priority, summary, reason):
    _plsql("pkg_ticket_workflow.record_ai_analysis",
           [int(ticket_id), model, category, department, priority, summary, reason])


def assign_ticket(ticket_id, assignee_id, actor_id, category=None, department=None, priority=None):
    _plsql("pkg_ticket_workflow.assign_ticket",
           [int(ticket_id), int(assignee_id), int(actor_id), category, department, priority])


def update_status(ticket_id, new_status, actor_id, note=None):
    _plsql("pkg_ticket_workflow.update_ticket_status", [int(ticket_id), new_status, int(actor_id), note])


def resolve_ticket(ticket_id, actor_id, note):
    _plsql("pkg_ticket_workflow.resolve_ticket", [int(ticket_id), int(actor_id), note])


def add_comment(ticket_id, user_id, body):
    _plsql("pkg_ticket_workflow.add_comment", [int(ticket_id), int(user_id), body])


def plsql_report() -> pd.DataFrame:
    """PKG_TICKET_WORKFLOW.TICKET_REPORT returns a SYS_REFCURSOR with per-department aggregates."""
    try:
        with _conn() as conn, conn.cursor() as cur, conn.cursor() as out:
            cur.callproc("pkg_ticket_workflow.ticket_report", [out])
            cols = [d[0].lower() for d in out.description]
            return pd.DataFrame(out.fetchall(), columns=cols)
    except oracledb.Error as exc:
        raise DBError(explain(exc)) from None
