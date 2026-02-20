import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Tuple

import streamlit as st


# ----------------------------
# Safety / non-diagnostic guardrails
# ----------------------------
SAFETY_BANNER = """
**Non-diagnostic demo:** This app helps caregivers *organize* notes.  
It **does not** provide medical diagnosis, treatment advice, or medication changes.
If there are urgent symptoms or safety concerns, contact local emergency services or a clinician.
"""


# ----------------------------
# Rule-based patterns / keywords
# ----------------------------
RED_FLAG_PATTERNS = [
    (re.compile(r"\b(chest pain|pressure in chest|can'?t breathe|shortness of breath)\b", re.I),
     "Possible breathing/chest emergency"),
    (re.compile(r"\b(fainted|passed out|unresponsive|seizure)\b", re.I),
     "Loss of consciousness / seizure concern"),
    (re.compile(r"\b(suicid(al)?|self[- ]harm)\b", re.I),
     "Self-harm risk"),
    (re.compile(r"\b(fall|fell|slipped)\b", re.I),
     "Fall occurred (assess for injury)"),
    (re.compile(r"\b(bleeding|blood)\b", re.I),
     "Bleeding mentioned"),
    (re.compile(r"\b(very confused|new confusion|disoriented)\b", re.I),
     "New confusion/disorientation"),
]

# NOTE: These are only for organizing and highlighting; not for advice.
TASK_TRIGGERS = [
    (re.compile(r"\b(remind|remember to|please)\b", re.I), "Reminder"),
    (re.compile(r"\b(check|monitor|watch)\b", re.I), "Check/Monitor"),
    (re.compile(r"\b(call|message|text)\b", re.I), "Contact"),
    (re.compile(r"\b(pick up|refill|pharmacy)\b", re.I), "Pharmacy/Refill"),
    (re.compile(r"\b(clean|laundry|cook|meal)\b", re.I), "Household"),
]

APPT_PATTERN = re.compile(
    r"\b(appointment|appt|doctor|dr\.|clinic|therapy|pt|ot)\b.*?\b(on|at)?\s*([A-Za-z]{3,9}\s+\d{1,2}|\d{1,2}\/\d{1,2}|\d{4}-\d{2}-\d{2})?\s*(at\s*)?(\d{1,2}(:\d{2})?\s*(am|pm)?)?",
    re.I
)

TIME_PATTERN = re.compile(r"\b(\d{1,2}(:\d{2})?\s*(am|pm))\b", re.I)
DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\w*\s+\d{1,2})\b", re.I)

MED_PATTERN = re.compile(
    r"\b(took|given|administered)\b\s*(?:the\s*)?([\w\-]+(?:\s+[\w\-]+){0,2})\s*(\d+(\.\d+)?)?\s*(mg|mcg|g|ml|units)?",
    re.I
)

VITALS_PATTERN = re.compile(r"\b(bp|blood pressure|temp|temperature|pulse|hr|heart rate|spo2|o2)\b[:\s-]*([0-9]{2,3}(\/[0-9]{2,3})?(\.[0-9])?)", re.I)

MOOD_KEYWORDS = {
    "calm": ["calm", "okay", "fine", "relaxed"],
    "anxious": ["anxious", "worried", "restless", "panic"],
    "sad": ["sad", "down", "crying"],
    "irritable": ["irritable", "angry", "snappy"],
    "confused": ["confused", "disoriented", "forgetful"],
}

EATING_KEYWORDS = ["ate", "eating", "meal", "breakfast", "lunch", "dinner", "snack"]
SLEEP_KEYWORDS = ["slept", "sleep", "nap", "insomnia", "awake"]
PAIN_KEYWORDS = ["pain", "ache", "sore", "hurt"]


@dataclass
class ParsedNote:
    created_at: str
    raw_text: str
    summary: Dict[str, str]
    tasks: List[Dict[str, str]]
    appointments: List[str]
    meds_mentioned: List[str]
    vitals_mentioned: List[str]
    safety_flags: List[str]


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_simple_sections(text: str) -> Dict[str, str]:
    """
    Rule-based highlights; not medical interpretation.
    """
    t = text.lower()
    summary = {}

    # Mood (keyword buckets)
    mood_found = []
    for mood, kws in MOOD_KEYWORDS.items():
        if any(kw in t for kw in kws):
            mood_found.append(mood)
    summary["Mood (keywords)"] = ", ".join(sorted(set(mood_found))) if mood_found else "—"

    # Eating / hydration
    summary["Eating mentioned"] = "Yes" if any(kw in t for kw in EATING_KEYWORDS) else "No"
    summary["Sleep mentioned"] = "Yes" if any(kw in t for kw in SLEEP_KEYWORDS) else "No"
    summary["Pain mentioned"] = "Yes" if any(kw in t for kw in PAIN_KEYWORDS) else "No"

    # Dates/times spotted
    dates = DATE_PATTERN.findall(text)
    times = TIME_PATTERN.findall(text)
    summary["Dates spotted"] = ", ".join(sorted(set([d[0] if isinstance(d, tuple) else d for d in dates]))) if dates else "—"
    summary["Times spotted"] = ", ".join(sorted(set([tm[0] for tm in times]))) if times else "—"

    return summary


def extract_tasks(text: str) -> List[Dict[str, str]]:
    """
    Heuristic: split into sentences/bullets and flag lines that look like tasks.
    """
    lines = re.split(r"(?:\n|•|- |\u2022)", text)
    tasks = []
    for line in lines:
        line_clean = normalize_whitespace(line)
        if len(line_clean) < 3:
            continue

        # If it contains a trigger verb, treat as a task candidate
        task_type = None
        for pat, label in TASK_TRIGGERS:
            if pat.search(line_clean):
                task_type = label
                break

        # Also treat checkbox-style
        if re.search(r"\b(todo|to do|task)\b", line_clean, re.I):
            task_type = task_type or "Task"

        if task_type:
            tasks.append({
                "type": task_type,
                "task": line_clean
            })

    # de-duplicate (simple)
    uniq = []
    seen = set()
    for t in tasks:
        key = t["task"].lower()
        if key not in seen:
            uniq.append(t)
            seen.add(key)
    return uniq


def extract_appointments(text: str) -> List[str]:
    appts = []
    for m in APPT_PATTERN.finditer(text):
        snippet = normalize_whitespace(text[m.start(): min(len(text), m.end() + 40)])
        appts.append(snippet)

    # De-dupe
    out = []
    seen = set()
    for a in appts:
        key = a.lower()
        if key not in seen:
            out.append(a)
            seen.add(key)
    return out


def extract_meds(text: str) -> List[str]:
    meds = []
    for m in MED_PATTERN.finditer(text):
        verb = m.group(1)
        name = (m.group(2) or "").strip()
        dose = m.group(3) or ""
        unit = m.group(5) or ""
        if name:
            meds.append(normalize_whitespace(f"{verb}: {name} {dose}{unit}".strip()))
    return sorted(set(meds), key=str.lower)


def extract_vitals(text: str) -> List[str]:
    vitals = []
    for m in VITALS_PATTERN.finditer(text):
        label = m.group(1)
        value = m.group(2)
        vitals.append(normalize_whitespace(f"{label}: {value}"))
    return sorted(set(vitals), key=str.lower)


def extract_safety_flags(text: str) -> List[str]:
    flags = []
    for pat, label in RED_FLAG_PATTERNS:
        if pat.search(text):
            flags.append(label)
    return sorted(set(flags))


def parse_note(text: str) -> ParsedNote:
    text = text.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = extract_simple_sections(text)
    tasks = extract_tasks(text)
    appts = extract_appointments(text)
    meds = extract_meds(text)
    vitals = extract_vitals(text)
    flags = extract_safety_flags(text)

    return ParsedNote(
        created_at=now,
        raw_text=text,
        summary=summary,
        tasks=tasks,
        appointments=appts,
        meds_mentioned=meds,
        vitals_mentioned=vitals,
        safety_flags=flags,
    )


# ----------------------------
# Streamlit UI
# ----------------------------
st.set_page_config(page_title="Caregiver Handoff (Rule-Based Demo)", page_icon="🧩", layout="wide")
st.title("🧩 Caregiver Handoff (Rule-Based Demo)")
st.info(SAFETY_BANNER)

with st.sidebar:
    st.header("Care Context (optional)")
    care_recipient = st.text_input("Care recipient name", value="")
    caregiver_name = st.text_input("Caregiver name", value="")
    st.caption("These fields are just for labeling the handoff summary.")

if "notes" not in st.session_state:
    st.session_state.notes = []  # list[dict]

tab1, tab2, tab3 = st.tabs(["✍️ Add Note", "📋 Dashboard", "🧪 Sample Notes"])

with tab1:
    st.subheader("Paste a caregiver note")
    note_text = st.text_area(
        "Care note (free text)",
        height=220,
        placeholder="Example: Mom felt dizzy at 3pm. Please remind her to drink water. Appointment with Dr. Lee on 2/21 at 10am..."
    )

    colA, colB = st.columns([1, 1])
    with colA:
        if st.button("Parse & Save", type="primary", use_container_width=True, disabled=(not note_text.strip())):
            parsed = parse_note(note_text)
            record = asdict(parsed)
            record["care_recipient"] = care_recipient.strip() or "—"
            record["caregiver_name"] = caregiver_name.strip() or "—"
            st.session_state.notes.insert(0, record)
            st.success("Saved. See Dashboard tab for the structured output.")
    with colB:
        if st.button("Clear all saved notes", use_container_width=True, disabled=(len(st.session_state.notes) == 0)):
            st.session_state.notes = []
            st.warning("Cleared saved notes.")

    st.divider()
    st.subheader("Instant preview (does not save)")
    if note_text.strip():
        preview = parse_note(note_text)
        left, right = st.columns([1.1, 1])
        with left:
            st.markdown("#### Structured Summary")
            for k, v in preview.summary.items():
                st.write(f"**{k}:** {v}")

            st.markdown("#### Tasks (heuristic)")
            if preview.tasks:
                st.table(preview.tasks)
            else:
                st.caption("No task-like lines detected.")

        with right:
            st.markdown("#### Appointments (keyword + regex)")
            if preview.appointments:
                for a in preview.appointments:
                    st.write(f"- {a}")
            else:
                st.caption("No appointment-like text detected.")

            st.markdown("#### Meds mentioned (logged only)")
            if preview.meds_mentioned:
                for m in preview.meds_mentioned:
                    st.write(f"- {m}")
            else:
                st.caption("No meds detected.")

            st.markdown("#### Vitals mentioned (logged only)")
            if preview.vitals_mentioned:
                for v in preview.vitals_mentioned:
                    st.write(f"- {v}")
            else:
                st.caption("No vitals detected.")

            st.markdown("#### Safety flags (keyword-based)")
            if preview.safety_flags:
                st.error("Possible urgent/safety terms found:")
                for f in preview.safety_flags:
                    st.write(f"- {f}")
            else:
                st.success("No red-flag keywords detected.")

with tab2:
    st.subheader("Saved Notes Dashboard")

    if not st.session_state.notes:
        st.caption("No saved notes yet. Add one in the **Add Note** tab.")
    else:
        # Top-level list
        for idx, rec in enumerate(st.session_state.notes):
            header = f"🗒️ {rec['created_at']} • Recipient: {rec['care_recipient']} • Caregiver: {rec['caregiver_name']}"
            with st.expander(header, expanded=(idx == 0)):
                c1, c2 = st.columns([1.2, 1])

                with c1:
                    st.markdown("#### Structured Summary")
                    for k, v in rec["summary"].items():
                        st.write(f"**{k}:** {v}")

                    st.markdown("#### Tasks")
                    if rec["tasks"]:
                        st.table(rec["tasks"])
                    else:
                        st.caption("No tasks detected.")

                with c2:
                    st.markdown("#### Appointments")
                    if rec["appointments"]:
                        for a in rec["appointments"]:
                            st.write(f"- {a}")
                    else:
                        st.caption("No appointments detected.")

                    st.markdown("#### Meds mentioned (no advice)")
                    if rec["meds_mentioned"]:
                        for m in rec["meds_mentioned"]:
                            st.write(f"- {m}")
                    else:
                        st.caption("No meds detected.")

                    st.markdown("#### Vitals mentioned (no advice)")
                    if rec["vitals_mentioned"]:
                        for v in rec["vitals_mentioned"]:
                            st.write(f"- {v}")
                    else:
                        st.caption("No vitals detected.")

                    st.markdown("#### Safety flags")
                    if rec["safety_flags"]:
                        st.error("Potential safety/urgent keywords found:")
                        for f in rec["safety_flags"]:
                            st.write(f"- {f}")
                    else:
                        st.success("No red-flag keywords detected.")

                st.markdown("#### Original note text")
                st.code(rec["raw_text"])

with tab3:
    st.subheader("3 sample notes to copy/paste")

    sample1 = """Dad slept poorly and was anxious this morning.
Please remind him to drink water and eat lunch.
He took Tylenol 500 mg at 2pm. BP: 140/90.
Therapy appointment on 2/21 at 10am at the clinic.
"""

    sample2 = """Grandma felt dizzy and fell in the kitchen around 3:30 pm.
No bleeding seen. Please call my sister and keep an eye on her walking.
She said she is confused about where she left her phone.
"""

    sample3 = """Shift handoff:
- Please pick up refill from pharmacy tomorrow morning.
- Check temperature later. temp 99.8
- Appointment with Dr. Lee on Feb 22 at 9am.
She ate breakfast and seems calm now.
"""

    st.markdown("**Sample Note 1**")
    st.code(sample1)
    st.markdown("**Expected highlights**")
    st.write("- Mood keywords: anxious")
    st.write("- Sleep mentioned: Yes")
    st.write("- Tasks: remind drink water, eat lunch")
    st.write("- Meds: took Tylenol 500 mg")
    st.write("- Vitals: BP 140/90")
    st.write("- Appointment detected: therapy on 2/21 at 10am")

    st.divider()

    st.markdown("**Sample Note 2**")
    st.code(sample2)
    st.markdown("**Expected highlights**")
    st.write("- Safety flags: Fall occurred; New confusion/disorientation (keyword-based)")
    st.write("- Tasks: call sister; keep an eye on walking")

    st.divider()

    st.markdown("**Sample Note 3**")
    st.code(sample3)
    st.markdown("**Expected highlights**")
    st.write("- Tasks: pick up refill; check temperature")
    st.write("- Vitals: temp 99.8")
    st.write("- Appointment detected: Dr. Lee on Feb 22 at 9am")
    st.write("- Eating mentioned: Yes")
    st.write("- Mood keywords: calm")
