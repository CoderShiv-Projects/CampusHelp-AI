"""AI Tools Lab UI: AI Quiz Lab + AI Insights (Streamlit rendering only).
Model calls live in ai_service.py; this module never touches the database."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import ai_service

NAVY, BLUE = "#0B1F3A", "#1F6FEB"
MAX_ANALYZE = 40  # most recent complaints analysed per run (limits API calls)

EXAMPLE_MATERIAL = """CampusHelp support guidelines

Complaints are submitted through the CampusHelp portal with a title, a description and a location. Every complaint becomes a ticket with a unique number and starts in the Open status.

Tickets are routed to a department: IT Support handles Wi-Fi, network and classroom equipment; Facilities handles electricity, water and building repairs; Hostel Administration handles hostel maintenance; the Library handles library services; Academic Administration handles fees, records and portal issues; Housekeeping handles cleanliness and waste.

Priority levels define the response target: Critical tickets (fire, sparking wires, gas leaks, flooding or injury risk) must be handled within 4 hours; High tickets within 24 hours; Medium tickets within 72 hours; Low tickets within 120 hours. Complaints that mention safety hazards are automatically raised to Critical, and staff cannot lower that priority.

A staff member of the responsible department assigns the ticket, moves it to In Progress, and resolves it with a written resolution note of at least 10 characters. Only Assigned or In Progress tickets can be resolved. A resolved ticket can be reopened to In Progress if the problem returns, or closed once the student is satisfied.

Students can add comments to their own tickets and follow every status change in the activity timeline. Administrators can view all tickets and the department statistics, but students can only see their own tickets."""

_SAMPLE = [
    ("Wi-Fi keeps dropping in Computer Lab 2", "Wi-Fi disconnects every few minutes during practicals. This has happened all week and nobody has fixed it.", "IT & Network", "High", "IT Support", 1),
    ("No internet in the library", "The reading hall has had no internet since Monday. Very frustrating before exams.", "IT & Network", "High", "IT Support", 2),
    ("Projector not working in A-101", "The projector shows no signal. Please check it when you can.", "Classroom Equipment", "Medium", "IT Support", 3),
    ("No water in boys hostel second floor", "There has been no water for two days. This is the third time this month!", "Hostel Maintenance", "High", "Hostel Administration", 3),
    ("Leaking tap in hostel bathroom", "The tap in the bathroom is leaking and the floor stays wet.", "Hostel Maintenance", "Medium", "Hostel Administration", 4),
    ("Sparking wire near cafeteria", "An exposed wire is sparking near the cafeteria entrance. Dangerous for students.", "Utilities", "Critical", "Facilities", 5),
    ("Garbage not collected", "Bins near the hostel gate have not been emptied for three days. Terrible smell.", "Cleanliness", "Medium", "Housekeeping", 6),
    ("Thanks for fixing the lab AC", "Just wanting to thank the facilities team for fixing the AC in the lab so quickly.", "Utilities", "Low", "Facilities", 7),
    ("Fee receipt missing on portal", "I paid my fees last week but the receipt is not visible in the portal.", "Administration", "Medium", "Academic Administration", 8),
    ("Library books not on shelf", "Several books listed as available in the catalogue are missing from the shelves.", "Library", "Low", "Library", 9),
    ("Wi-Fi slow in hostel block B", "The hostel Wi-Fi is extremely slow in the evenings. I have reported this before and nothing changed.", "IT & Network", "Medium", "IT Support", 10),
    ("Classroom fans not working", "Two ceiling fans in room B-204 are not working.", "Classroom Equipment", "Low", "Facilities", 11),
]


def sample_df() -> pd.DataFrame:
    now = datetime.now()
    return pd.DataFrame([{"ticket_id": i + 1, "title": t, "description": d, "category": c, "priority": p,
                          "department": dep, "created_at": now - timedelta(days=ago)}
                         for i, (t, d, c, p, dep, ago) in enumerate(_SAMPLE)])


def _kpi(label, value, sub="", color=BLUE):
    st.markdown(f"<div class='kpi' style='border-left:6px solid {color}'><div class='kpi-label'>{label}</div>"
                f"<div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>", unsafe_allow_html=True)


def _fig(fig, h=300):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig)


# ============================================================== AI Quiz Lab ==
def _load_example():
    st.session_state["quiz_src"] = EXAMPLE_MATERIAL


def _submit(answers: list):
    st.session_state.quiz_answers = answers
    st.session_state.quiz_submitted = True


def _retake():
    st.session_state.quiz_attempt += 1
    st.session_state.quiz_submitted = False
    st.session_state.quiz_answers = None


def quiz_page():
    ss = st.session_state
    for k, v in {"quiz": None, "quiz_attempt": 0, "quiz_submitted": False, "quiz_answers": None}.items():
        ss.setdefault(k, v)
    st.title("AI Quiz Lab")
    st.caption("🤖 Questions are generated by the hosted AI model from your text, then validated and scored by Python.")

    with st.container(border=True):
        st.markdown("#### 1 · Source material")
        st.button("📄 Load example campus-help material", on_click=_load_example)
        src = st.text_area("Paste campus FAQs, guidelines or procedures (200-6000 characters)", key="quiz_src", height=200)
        c1, c2, c3 = st.columns([1, 1, 1])
        n = c1.selectbox("Number of questions", [5, 10, 15])
        diff = c2.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1)
        c3.write("")
        gen = c3.button("✨ Generate quiz", type="primary")
    if gen:
        if not 200 <= len(src.strip()) <= 6000:
            st.warning(f"Material must be 200-6000 characters (currently {len(src.strip())}).")
        else:
            with st.spinner(f"Generating {n} {diff.lower()} questions..."):
                res = ai_service.generate_quiz(src.strip(), n, diff)
            if res.ok:
                ss.quiz = {"questions": res.data["questions"], "difficulty": diff, "model": res.model}
                _retake()
            else:
                st.error(res.error)
                if ss.quiz:
                    st.info("Your previous quiz is still available below.")

    quiz = ss.quiz
    if not quiz:
        st.info("Load or paste material, then click **Generate quiz**.")
        return
    qs, att, done = quiz["questions"], ss.quiz_attempt, ss.quiz_submitted
    st.markdown(f"#### 2 · Quiz — {len(qs)} questions · {quiz['difficulty']}")
    st.caption(f"Generated by `{quiz['model']}`. Correct answers stay hidden until you submit.")

    saved = ss.quiz_answers or [None] * len(qs)
    if done:  # score is computed in Python from the validated answer keys
        correct = sum(1 for q, a in zip(qs, saved) if a == q["options"][q["answer_index"]])
        pct = round(100 * correct / len(qs))
        c1, c2, c3 = st.columns(3)
        with c1: _kpi("Score", f"{correct} / {len(qs)}", "correct answers", "#16A34A" if pct >= 60 else "#DC2626")
        with c2: _kpi("Percentage", f"{pct}%", "computed from the answer keys")
        with c3: _kpi("Unanswered", sum(a is None for a in saved), "counted as incorrect", "#F59E0B")
        st.write("")

    current = []
    for i, q in enumerate(qs):
        with st.container(border=True):
            choice = st.radio(f"**Q{i+1}. {q['question']}**", q["options"], index=None, key=f"qa{att}_{i}", disabled=done)
            current.append(choice)
            if done:
                right = q["options"][q["answer_index"]]
                given = saved[i]
                if given == right:
                    st.success(f"✅ Correct: {right}")
                else:
                    st.error(f"❌ {'Not answered' if given is None else 'Your answer: ' + given} — correct answer: {right}")
                st.caption(f"💡 {q['explanation']}")
    if not done:
        missing = sum(a is None for a in current)
        if missing:
            st.caption(f"{missing} question(s) not answered yet (unanswered count as incorrect).")
        st.button("✅ Submit quiz", type="primary", on_click=_submit, args=(current,))
    else:
        st.button("🔁 Retake this quiz", on_click=_retake)


# ============================================================== AI Insights ==
def _key(tag: str, tid: int, text: str) -> str:
    return f"{tag}:{tid}:{hashlib.md5(text.encode()).hexdigest()[:10]}"


def insights_page(df: pd.DataFrame, user: dict):
    ss = st.session_state
    cache = ss.setdefault("ins_cache", {"sent": {}, "themes": {}})
    st.title("AI Insights")
    st.caption("🧮 Deterministic = counted from stored ticket fields  ·  🤖 AI prediction = labelled by the model, then counted by Python.")

    use_sample = df.empty
    if not df.empty:
        use_sample = st.checkbox("Use the labelled SAMPLE dataset instead of real tickets (for demonstration)")
    if use_sample:
        data, tag = sample_df(), "sample"
        st.warning("⚠️ No ticket records available, so a SAMPLE DATASET of 12 invented complaints is used for demonstration."
                   if df.empty else "⚠️ SAMPLE DATASET — 12 invented complaints for demonstration, not real campus data.")
    else:
        data, tag = df[["ticket_id", "title", "description", "category", "priority", "department", "created_at"]].copy(), "tickets"
    data["day"] = pd.to_datetime(data["created_at"]).dt.date

    f1, f2 = st.columns(2)
    lo, hi = data["day"].min(), data["day"].max()
    rng = f1.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
    start, end = (rng[0], rng[-1]) if isinstance(rng, (tuple, list)) and len(rng) else (rng, rng)
    depts = sorted(data["department"].unique())
    sel = f2.multiselect("Department", depts, default=depts)
    scope = data[(data["day"] >= start) & (data["day"] <= end) & data["department"].isin(sel)].copy()
    if scope.empty:
        st.info("No complaints match this date range / department."); return
    scope["text"] = scope["title"].astype(str) + ". " + scope["description"].astype(str)
    scope["key"] = [_key(tag, int(t), x) for t, x in zip(scope["ticket_id"], scope["text"])]
    batch = scope.sort_values("created_at", ascending=False).head(MAX_ANALYZE)
    theme_key = hashlib.md5("|".join(sorted(batch["key"])).encode()).hexdigest()

    if st.button("🤖 Run AI analysis", type="primary"):
        todo = [(int(r.ticket_id), r.text) for r in batch.itertuples() if r.key not in cache["sent"]]
        errors = []
        with st.spinner(f"Analysing {len(todo)} new complaint(s) ({len(batch) - len(todo)} cached)..."):
            if todo:
                labels, err = ai_service.analyze_sentiments(todo)
                for r in batch.itertuples():
                    if int(r.ticket_id) in labels and r.key not in cache["sent"]:
                        cache["sent"][r.key] = labels[int(r.ticket_id)]
                if err:
                    errors.append(err)
            if theme_key not in cache["themes"] and len(batch) >= 3:
                res = ai_service.find_themes([(int(r.ticket_id), r.text) for r in batch.itertuples()])
                if res.ok:
                    cache["themes"][theme_key] = res.data["themes"]
                else:
                    errors.append(res.error)
        for e in errors:
            st.error(f"AI analysis problem: {e}")
        if not errors:
            st.success("AI analysis complete (results are cached for this session).")

    st.markdown(f"**{len(scope)}** complaint(s) in scope" + (f" · AI analysis covers the {len(batch)} most recent" if len(scope) > MAX_ANALYZE else ""))

    # ---- deterministic section
    st.markdown("### 🧮 Recorded fields (deterministic counts)")
    st.caption("Category and urgency are the stored ticket values — AI-suggested at submission and editable by staff. "
               "For the sample dataset they are invented values.")
    c1, c2 = st.columns(2)
    with c1:
        c = scope["category"].value_counts().reset_index(); c.columns = ["Category", "Complaints"]
        _fig(px.bar(c, x="Complaints", y="Category", orientation="h", title="Issue category distribution", color_discrete_sequence=[BLUE]))
    with c2:
        order = ai_service.PRIORITIES
        p = scope["priority"].value_counts().reindex(order, fill_value=0).reset_index(); p.columns = ["Urgency", "Complaints"]
        _fig(px.bar(p, x="Urgency", y="Complaints", title="Suggested urgency distribution", color_discrete_sequence=[NAVY]))

    # ---- AI section
    st.markdown("### 🤖 AI predictions")
    scope["sentiment"] = scope["key"].map(cache["sent"])
    done = scope.dropna(subset=["sentiment"])
    if done.empty:
        st.info("No AI results yet. Click **Run AI analysis** (sentiment + recurring themes).")
        return
    st.caption(f"Sentiment labels exist for {len(done)} of {len(scope)} complaints in scope; percentages below use only those {len(done)}.")
    k = st.columns(4)
    for col, s_, colr in zip(k, ai_service.SENTIMENTS, ["#16A34A", "#6B7280", "#F59E0B", "#DC2626"]):
        n_ = int((done["sentiment"] == s_).sum())
        with col: _kpi(s_, n_, f"{round(100 * n_ / len(done))}% of analysed", colr)
    st.write("")
    d1, d2 = st.columns(2)
    with d1:
        s = done["sentiment"].value_counts().reindex(ai_service.SENTIMENTS, fill_value=0).reset_index(); s.columns = ["Sentiment", "Complaints"]
        _fig(px.bar(s, x="Sentiment", y="Complaints", title="Sentiment distribution (AI-labelled)", color_discrete_sequence=[BLUE]))
    with d2:
        x = done.groupby(["category", "sentiment"]).size().reset_index(name="Complaints")
        _fig(px.bar(x, x="category", y="Complaints", color="sentiment", title="Sentiment by category",
                    labels={"category": "Category", "sentiment": "Sentiment"},
                    category_orders={"sentiment": ai_service.SENTIMENTS}, color_discrete_sequence=[NAVY, BLUE, "#5B9BF5", "#9CC3F9"]))

    st.markdown("#### Recurring themes (AI-identified, counted in Python)")
    themes = cache["themes"].get(theme_key)
    if themes is None:
        st.info("Themes not generated yet for this selection — click **Run AI analysis**.")
    elif not themes:
        st.info("The AI found no theme shared by 2 or more of these complaints.")
    else:
        titles = dict(zip(scope["ticket_id"].astype(int), scope["title"]))
        for t in themes:
            with st.container(border=True):
                st.markdown(f"**{t['theme']}** — {t['count']} complaint(s)")
                st.write(t["summary"])
                st.caption("Tickets: " + "; ".join(f"#{i} {titles.get(i, '')}" for i in t["ticket_ids"][:5]))
    st.download_button("⬇️ Export analysed complaints (CSV)",
                       done[["ticket_id", "title", "department", "category", "priority", "sentiment"]].to_csv(index=False).encode("utf-8"),
                       "ai_insights.csv", "text/csv")
