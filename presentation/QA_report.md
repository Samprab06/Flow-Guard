# Deck QA report

## Artifacts

- `FlowGuard_rebuilt_deck.pptx` — exactly nine slides; editable text, tables, chart, and embedded cb36_002 image.
- `FlowGuard_rebuilt_deck.pdf` — PowerPoint PDF fallback.
- `recording_script.md` — approximately four-minute narration with demo cue.
- `assets/cb36_002.png` — only extracted remote artifact; SHA-256 `35fbbd7e0a26f1a8b00f62bfc6b4fe38fdbbfaf35d7f6e1b6b26a744a12dc5de`.
- `rendered_powerpoint/slide-01.png` through `slide-09.png` — PowerPoint COM renders.

## Verified content checks

- Crossbar-v2 facts: 36 configurations, 6 feasible / 30 failed, 13 seeds, 3 methods, 24 evaluations including 8 shared initialization evaluations, no replay EDA.
- Slide 4: seed 11 FlowGuard-Calibrated call 10 selects cb36_002; checks and SHA match `06_demo.json`; separate-run physical-artifact provenance is explicit.
- Slide 6: required headline/subtitle/callout present; editable zero-based two-bar chart has 249.91 and 239.63 minutes. Derived 616.8 seconds = 10.28 minutes and 4.11% are explicitly shown from verified failed means.
- Slide 7: complete Vanilla / FlowGuard / EI-only table; failed means 13046.8 / 14378.0 / 14994.8 seconds; total means 17230.7 / 17307.3 / 17272.8 seconds; Vanilla emphasized as lowest on both costs; all final QoR ties.
- Slide 8: older TPE layout image is distinguished from FlowGuard decision record; stress evidence excluded; missing standalone combined-13 verification log and replay/oracle limitation stated.
- Slide 9: exact `python3 experiments/replay_demo.py` invitation.
- Speaker notes updated for all nine slides and aligned with the script.

## Rendering and inspection

- PowerPoint COM rendered all nine slides to PNG and exported the PDF.
- Inspected contact sheet and individual render geometry for clipping, chart labels, table readability, contrast, note consistency, and artifact provenance.
- Chart and tables remain editable PowerPoint objects.
- No LibreOffice used.

## Remaining limitations

- The replay is oracle/cache evidence and launches zero physical runs; cb36_002 image provenance is a separate earlier physical run by explicit design.
- No standalone combined-13 verification log exists.
- Runtime totals are estimated sequential costs from recorded physical runtimes; optimizer overhead is separate.
- The bundle does not establish general optimizer superiority because all methods tie final best QoR.
