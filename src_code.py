# !pip install gradio python-docx PyPDF2 dateparser

import re
import gradio as gr
import PyPDF2, docx
import dateparser
from datetime import datetime

# --- Extract text from PDF/DOCX ---
def extract_text(file_path: str) -> str:
    if file_path.lower().endswith(".pdf"):
        reader = PyPDF2.PdfReader(file_path)
        return "\n".join([p.extract_text() or "" for p in reader.pages])
    if file_path.lower().endswith(".docx"):
        d = docx.Document(file_path)
        return "\n".join([para.text for para in d.paragraphs])
    return ""

# --- Helpers ---
def infer_context_year(text: str) -> int:
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else datetime.now().year

MONTH = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t)?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DOW   = r"(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\.?,?\s*"
DATE_PATTERN = re.compile(
    rf"(?:{DOW})?\s*{MONTH}\.?\s*\.?\s*(\d{{1,2}})(?:,\s*(\d{{4}}))?",
    re.IGNORECASE
)
EXAM_PATTERN = re.compile(r"\b(mini\s*[- ]?\s*exam|final\s+exam|exam\s*\d+)\b", re.IGNORECASE)

def clean_date_str(s: str) -> str:
    s = re.sub(r"(?<=\b[A-Za-z]{3})\s*\.\s*(\d{1,2})", r". \1", s)
    s = re.sub(r"\s+", " ", s).strip(" ,.;-–—")
    s = re.sub(r"\s+,", ",", s)
    return s

def find_nearest_date(text: str, anchor_idx: int, ctx_year: int, window: int = 90):
    start = max(0, anchor_idx - window)
    end   = min(len(text), anchor_idx + window)
    snippet = text[start:end]

    dates = []
    for m in DATE_PATTERN.finditer(snippet):
        abs_start = start + m.start()
        abs_end   = start + m.end()
        dates.append({
            "abs_start": abs_start,
            "abs_end": abs_end,
            "before": abs_end <= anchor_idx,
            "raw": snippet[m.start():m.end()],
        })

    if not dates:
        return None, None

    before = [d for d in dates if d["before"]]
    if before:
        chosen = max(before, key=lambda d: d["abs_end"])
    else:
        chosen = min(dates, key=lambda d: abs(d["abs_start"] - anchor_idx))

    date_str = clean_date_str(chosen["raw"])
    if not re.search(r"\b20\d{2}\b", date_str):
        date_str = f"{date_str}, {ctx_year}"

    parsed = dateparser.parse(date_str)
    return parsed, date_str


# --- Main pipeline with sanity checks after upload ---
def find_exams_strict(file_path: str):
    text = extract_text(file_path)
    if not text or not text.strip():
        return "⚠️ Could not extract text from the file."

    ctx_year = infer_context_year(text)
    results, seen = [], set()

    for m in EXAM_PATTERN.finditer(text):
        label = re.sub(r"\s+", " ", m.group(0).strip())
        label_norm = label.lower()
        parsed_dt, raw_dt = find_nearest_date(text, m.start(), ctx_year)

        key = (label_norm, raw_dt)
        if key in seen:
            continue
        seen.add(key)

        if parsed_dt:
            nice = parsed_dt.strftime("%A, %B %d, %Y")
            results.append(f"• {label.title()} — {nice}")
        else:
            results.append(f"• {label.title()} — {raw_dt} (date parse uncertain)")

    # --- Sanity checks on real syllabus content ---
    sanity_msgs = []
    try:
        # At least one exam should exist
        assert any("exam" in r.lower() for r in results)
        sanity_msgs.append("✔ Found at least one exam")

        # Dates should include a month
        assert any(re.search(r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", r) for r in results)
        sanity_msgs.append("✔ Dates look valid")

    except AssertionError as e:
        sanity_msgs.append(f"⚠️ Sanity check failed: {e}")

    if not results:
        return "✅ No exams with dates found."

    return "📘 Exams Found:\n" + "\n".join(results) + "\n\n" + " | ".join(sanity_msgs)


# --- Gradio UI ---
with gr.Blocks() as demo:
    gr.Markdown("# 🐢 Turtle — Exam Date Finder with Sanity Checks")
    gr.Markdown("Upload your syllabus (PDF or DOCX). Output shows exams and runs sanity checks.")

    file_input = gr.File(label="Upload Syllabus (PDF or DOCX)", type="filepath")
    output_box = gr.Textbox(label="Exam Information + Sanity Checks", lines=12)
    submit_btn = gr.Button("Find Exams")

    submit_btn.click(fn=find_exams_strict, inputs=file_input, outputs=output_box)

demo.launch()
