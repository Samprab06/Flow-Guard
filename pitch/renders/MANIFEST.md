# GDS render manifest (isolated, no source modifications)

Tool: `/home/ubuntu/FlowGuard-recovery/.venv/openlane/bin/python /home/ubuntu/FlowGuard-recovery/.venv/openlane/lib/python3.12/site-packages/librelane/scripts/klayout/render.py`
Settings: `resolution=1000 oversampling=0 white grid-off text-off sky130A.lyp/lyt/map + 3 LEFs`
Tech: sky130A lyp/lyt/map rev 8afc8346a57fe1ab7934ba5a6056ea8b43078e71 + 3 LEFs (nom.tlef, fd_sc_hd.lef, ef_sc_hd.lef); resolution=1000, oversampling=0, background=white, grid-off, text-off (identical to 59-klayout-render/COMMANDS).

Total GDS: 722 | unique contents: 350 | success: 722 | failure: 0 | AES-excluded files: 0 (AES dirs contain no .gds).
Roots: {'FlowGuard-recovery': 495, 'external-tinytapeout-work': 227}
Kinds: {'streamout': 165, 'final': 534, 'other': 23}
Dimensions (WxH): {(1000, 625): 147, (1000, 312): 525, (1000, 1293): 48, (1000, 277): 1, (1000, 674): 1}

Outputs: `/tmp/banyancode/gds-renders/*.png` (one PNG per GDS path; byte-identical GDS share rendered pixels via copy). Full per-file command/status in `manifest.json`, concise rows in `manifest.csv`.
No primary benchmark source/config or optimizer code modified; no commit.
