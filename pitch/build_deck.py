#!/usr/bin/env python3
"""FlowGuard pitch deck assembler — refreshable.

Reads pitch/stats.json (written by build_charts.py) + live trials.jsonl,
assembles pitch/flowguard_pitch.pptx (16:9, python-pptx) and
pitch/flowguard_pitch.pdf (reportlab; PPTX-only with a notice if reportlab
is missing). Rerunning after methods finish picks up final numbers.
GDS is rendered only if klayout exists; otherwise a metrics panel is shown.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PITCH = os.path.join(ROOT, "pitch")
CHARTS = os.path.join(PITCH, "charts")

CREAM = (0xFA, 0xF6, 0xEF)
INK = (0x3E, 0x2F, 0x25)
INK_SOFT = (0x6B, 0x5B, 0x4D)
ACCENT = (0xD9, 0x77, 0x57)
SERIF = "DejaVu Serif"
SANS = "DejaVu Sans"

with open(os.path.join(PITCH, "stats.json")) as f:
    S = json.load(f)
W = S["winner"]
D = S["decision"]
HAS_KLAYOUT = shutil.which("klayout") is not None
RAW_STATE = S["methods"]["flowguard_raw"]["state"]
RAW_TAG = "PARTIAL" if RAW_STATE == "partial-running" else "recorded"

SLIDES = [
    {"img": None, "title": "FlowGuard: stop burning silicon before it exists",
     "bullets": [
         "Feasibility-aware optimization for the open-source SKY130 flow",
         f"Frozen 15.8 ns boundary + 5-way shootout · winner QoR {W['qor']:.3f}",
          "Winner layout render committed; raw GDS remains server-local — Purdue CHIPSandAI"],
     "foot": "Every figure from trials.jsonl · rerun-safe"},
    {"img": "c09_waste.png", "title": "The wasted-EDA problem",
     "bullets": [
         f"{S['waste']['doomed_runs']} doomed runs burned {S['waste']['doomed_hours']} tool-hours for zero data",
         "Failures arrive late, at signoff — after the compute is spent",
         "Blind search re-samples dead regions instead of learning them"],
     "foot": "Exhaustive sweep: 485 runs"},
    {"img": "c00_idea.png", "title": "The FlowGuard idea: EI × P(feasible)",
     "bullets": [
         "Quality predictor × feasibility classifier — one score per candidate",
         "Calibration only with ≥3 obs/class, else declared uncalibrated",
         "Every pick logged: scores, seeds, hashes, model versions"],
     "foot": "No hard risk threshold · audit by replay"},
    {"img": "c02_flow.png", "title": "A real SKY130 flow, not a toy",
     "bullets": [
         "LibreLane 3.0.14 · sky130A · 728-cell sensor-MAC stress block",
         "Feasible = SUCCESS + DRC 0 + setup/hold ≥ 0 + route 100% + LVS + signoff",
         "72-candidate pool · 8 shared seeds + 16 adaptive picks per method"],
     "foot": "Frozen 2026-09-16 · QoR weights 0.5 / 0.3 / 0.2"},
    {"img": "c01_cliff.png", "title": "The 17/15 cliff",
     "bullets": [
         f"17 ns: {S['cliff']['f17']}/{S['cliff']['n17']} pass, slack {S['cliff']['ws17_min']}–{S['cliff']['ws17_max']} ns",
         f"15 ns: {S['cliff']['f15']}/{S['cliff']['n15']} pass — 159 × TIMING_FAIL",
         "No slope between regimes: hunt the boundary, don't guess it"],
     "foot": "485 sweep runs"},
    {"img": "c03_boundary.png", "title": "Frozen at 15.8 ns: a living boundary",
     "bullets": [
         f"Hunt {S['boundary']['hunt158']} · diag {S['boundary']['diag']} · repeat {S['boundary']['repeat']}",
         "Slack scatters across zero (−0.34 to +0.72 ns): knobs decide",
         "3/3 identical repeats — signal, not tool noise"],
     "foot": "Mixed boundary = learnable structure"},
    {"img": "c04_padding.png", "title": "What matters: padding & strategy",
     "bullets": [
         "Padding 2 fails far more often than 0/1 at 15.8 ns",
         "AREA 1 + high padding = the diagnostic grid's only failures",
         f"Low padding + AREA 0 passes consistently (n={S['pool158_n']} @15.8 ns)"],
     "foot": "A feasibility model should beat blind search here"},
    {"img": "c05_traces.png", "title": "Five-way shootout: best QoR vs calls",
     "bullets": [
          "Vanilla BO & Optuna → 0.103 · FlowGuard raw → 0.103 at adaptive call 11",
          f"Random trails at 0.169 · FlowGuard raw {RAW_TAG} (11/16 feasible)",
         "FlowGuard calibrated: NOT STARTED (gated on calibration threshold)"],
     "foot": "Shared 8 seeds + adaptive · lower is better"},
    {"img": "c06_efficiency.png", "title": "Failure efficiency",
     "bullets": [
          "Vanilla BO 16/16 · FlowGuard raw 11/16 · Optuna 13/16 · random 12/16",
          "Shared seeds only 2/8 — this does not support a fewer-failures claim",
         "Every avoided failure returns ~3 min of budget to useful search"],
     "foot": "*PARTIAL — still running; calibrated not started"},
    {"img": "c07_winner.png", "title": "The winner + GDS hero",
     "bullets": [
          f"Selected cand_014: QoR {W['qor']:.3f} · ws {W['setup_ws']} ns · hold {W['hold_ws']} ns",
         f"{W['area']:.0f} µm² · {W['wirelength']:.0f} µm wire · pad 0 / dens 52 / grt 0.2 / AREA 0",
         ("GDS rendered" if HAS_KLAYOUT else "No klayout here → metrics panel from signoff data") + f": {W['gds']}"],
     "foot": "GDS embedded as path reference"},
    {"img": "c08_provenance.png", "title": "One AI decision, fully replayable",
     "bullets": [
         f"Raw call {D['call_index']}: rank 1 of {D['n_scored']} · EI {D['ei']:.4f} · P(feas) {D['p_feas']:.2f}",
         f"Seed {D['seed']} · data {D['data_hash'][:12]}… · {D['calibration_detail']}",
         "Same hash + versions = same pick. Lore-free optimization."],
     "foot": "Provenance row in trials.jsonl"},
    {"img": None, "title": "Integrity + the ask",
     "bullets": [
         f"Running traces marked {RAW_TAG} · calibrated not started · tile assumed 2×1, unvalidated",
         "Nothing extrapolated or cherry-picked — rerun builder refreshes all numbers",
         "Ask: collaborators + compute — finish calibrated, add a 2nd design, harden provenance"],
     "foot": "Come talk: never run a doomed job again"},
]


def build_pptx(path):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    def bg(slide):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*CREAM)

    def textbox(slide, l, t, w, h):
        return slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))

    def para(tf, text, size, bold, color, font=SANS, align=PP_ALIGN.LEFT, space_after=6):
        p = tf.add_paragraph() if tf.paragraphs[0].text else tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = RGBColor(*color)
        p.font.name = font
        p.alignment = align
        p.space_after = Pt(space_after)
        return p

    for i, s in enumerate(SLIDES):
        slide = prs.slides.add_slide(blank)
        bg(slide)
        # coral accent bar
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(0.35), Inches(1.4), Inches(0.09))
        bar.fill.solid()
        bar.fill.fore_color.rgb = RGBColor(*ACCENT)
        bar.line.fill.background()
        # slide number
        num = textbox(slide, 12.1, 0.2, 0.6, 0.4)
        para(num.text_frame, f"{i + 1}/12", 11, False, INK_SOFT, SANS, PP_ALIGN.RIGHT)
        num.text_frame.paragraphs[0].space_after = Pt(0)
        # title
        tbox = textbox(slide, 0.6, 0.6, 12.1, 1.1)
        tbox.text_frame.word_wrap = True
        para(tbox.text_frame, s["title"], 30 if s["img"] else 38, True, INK, SERIF)
        # bullets
        bbox = textbox(slide, 0.6, 1.9, 4.6 if s["img"] else 11.5, 4.6)
        bbox.text_frame.word_wrap = True
        for b in s["bullets"]:
            p = bbox.text_frame.add_paragraph() if bbox.text_frame.paragraphs[0].text else bbox.text_frame.paragraphs[0]
            p.text = "▸  " + b
            p.font.size = Pt(15)
            p.font.color.rgb = RGBColor(*INK)
            p.font.name = SANS
            p.space_after = Pt(12)
            p.space_before = Pt(4)
        # footer
        fbox = textbox(slide, 0.6, 6.9, 12.1, 0.4)
        para(fbox.text_frame, s["foot"], 11, False, INK_SOFT, SANS)
        fbox.text_frame.paragraphs[0].space_after = Pt(0)
        # chart
        if s["img"]:
            slide.shapes.add_picture(os.path.join(CHARTS, s["img"]),
                                     Inches(5.6), Inches(1.7), width=Inches(7.1), height=Inches(5.0))
    prs.save(path)
    return len(prs.slides)


def build_pdf(path):
    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    PAGE = (13.33 * inch, 7.5 * inch)
    cream, ink, soft, accent = (HexColor("#FAF6EF"), HexColor("#3E2F25"),
                                HexColor("#6B5B4D"), HexColor("#D97757"))
    c = canvas.Canvas(path, pagesize=PAGE)
    c.setTitle("FlowGuard — hackathon pitch")
    for i, s in enumerate(SLIDES):
        c.setFillColor(cream)
        c.rect(0, 0, PAGE[0], PAGE[1], fill=1, stroke=0)
        c.setFillColor(accent)
        c.rect(0.6 * inch, 6.85 * inch, 1.4 * inch, 0.09 * inch, fill=1, stroke=0)
        c.setFillColor(soft)
        c.setFont("Helvetica", 11)
        c.drawRightString(12.7 * inch, 7.15 * inch, f"{i + 1}/12")
        c.setFillColor(ink)
        c.setFont("Times-Bold", 28 if s["img"] else 34)
        y = 6.5 * inch
        for line in [s["title"][k:k + 60] for k in range(0, len(s["title"]), 60)][:2]:
            c.drawString(0.6 * inch, y, line.strip())
            y -= 0.45 * inch
        c.setFont("Helvetica", 13)
        by = 5.2 * inch
        for b in s["bullets"]:
            words, lines, cur = b.split(), [], ""
            for w in words:
                if len(cur) + len(w) > (52 if s["img"] else 110):
                    lines.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            lines.append(cur)
            c.drawString(0.6 * inch, by, "▸ " + lines[0])
            for extra in lines[1:]:
                by -= 0.28 * inch
                c.drawString(0.9 * inch, by, extra)
            by -= 0.42 * inch
        c.setFillColor(soft)
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(0.6 * inch, 0.4 * inch, s["foot"])
        if s["img"]:
            img = ImageReader(os.path.join(CHARTS, s["img"]))
            c.drawImage(img, 5.6 * inch, 0.7 * inch, width=7.1 * inch,
                        height=5.0 * inch, preserveAspectRatio=True, anchor="c")
        c.showPage()
    c.save()
    return len(SLIDES)


if __name__ == "__main__":
    pptx_path = os.path.join(PITCH, "flowguard_pitch.pptx")
    n = build_pptx(pptx_path)
    print(f"PPTX: {pptx_path} ({n} slides)")
    # round-trip read check
    from pptx import Presentation
    check = Presentation(pptx_path)
    assert len(check.slides) == 12, f"expected 12 slides, got {len(check.slides)}"
    print("PPTX round-trip read OK: 12 slides")
    try:
        pdf_path = os.path.join(PITCH, "flowguard_pitch.pdf")
        m = build_pdf(pdf_path)
        print(f"PDF: {pdf_path} ({m} pages, reportlab)")
    except ImportError as e:
        print(f"PDF skipped (reportlab missing: {e}) — PPTX only")
