#!/usr/bin/env python3
"""Web server for viewing demonstrations and gripper calibrations."""

import argparse
import glob
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote, quote

ITEMS_PER_PAGE = 10

ERROR_STATUSES = {"error_both_manual", "error_both_auto"}
INVALID_STATUSES = {"invalid", "manual_invalid"}
VALID_STATUSES = {"valid", "manual_valid"}
AUTO_STATUSES = {"valid", "invalid"}
MANUAL_STATUSES = {"manual_valid", "manual_invalid"}


def get_demo_metadata(folder_path: str) -> dict:
    path = Path(folder_path)
    for json_file in sorted(path.glob("*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
            tasks = data.get("taskNames", [])
            session_name = str(data.get("sessionName", ""))
            if tasks or session_name:
                return {
                    "task_names": [str(t) for t in tasks],
                    "is_error_correction": bool(data.get("isErrorCorrection", False)),
                    "session_name": session_name,
                }
        except Exception:
            continue
    return {"task_names": [], "is_error_correction": False, "session_name": ""}


def find_entries(base_dir: str) -> list[dict]:
    base = Path(base_dir)
    entries = []
    for folder in sorted(base.rglob("*")):
        if not folder.is_dir():
            continue
        name = folder.name
        if name.endswith("_demonstration"):
            meta = get_demo_metadata(str(folder))
            entries.append({"type": "demonstration", "path": str(folder), "name": name, **meta})
        elif name.endswith("_grippercalibration"):
            meta = get_demo_metadata(str(folder))
            if not meta["session_name"]:
                parts = name.split('_')
                if len(parts) == 4:
                    meta["session_name"] = parts[2]
            entries.append({"type": "calibration", "path": str(folder), "name": name, **meta})
    return entries


def get_demo_status(folder_path: str) -> str:
    path = Path(folder_path)
    has_manual_invalid = (path / "manual_invalid.txt").exists()
    has_manual_valid = (path / "manual_valid.txt").exists()
    has_invalid = (path / "invalid.txt").exists()
    has_valid = (path / "valid.txt").exists()

    if has_manual_invalid and has_manual_valid:
        return "error_both_manual"
    if has_invalid and has_valid:
        return "error_both_auto"
    if has_manual_invalid:
        return "manual_invalid"
    if has_manual_valid:
        return "manual_valid"
    if has_valid:
        return "valid"
    if has_invalid:
        return "invalid"
    return "not_specified"


def get_demo_videos(folder_path: str) -> list[str]:
    path = Path(folder_path)
    combined = path / "combined_visualized.mp4"
    if combined.exists():
        return [str(combined)]
    videos = []
    for rgb in sorted(glob.glob(str(path / "*_rgb.mp4"))):
        side = Path(rgb).name.replace("_rgb.mp4", "")
        visualized = path / f"{side}_visualized.mp4"
        videos.append(str(visualized) if visualized.exists() else rgb)
    return videos


def get_calibration_videos(folder_path: str) -> list[str]:
    path = Path(folder_path)
    videos = sorted(glob.glob(str(path / "*_ultrawide_rgb.mp4")))
    if not videos:
        videos = sorted(glob.glob(str(path / "*ultrawidergb.mp4")))
    return videos


STATUS_BADGE = {
    "valid":            '<span class="badge valid">Valid (auto)</span>',
    "manual_valid":     '<span class="badge manual-valid">Valid (manual)</span>',
    "invalid":          '<span class="badge invalid">Invalid (auto)</span>',
    "manual_invalid":   '<span class="badge manual-invalid">Invalid (manual)</span>',
    "error_both_manual":'<span class="badge error">Error: conflicting manual labels</span>',
    "error_both_auto":  '<span class="badge error">Error: conflicting valid/invalid</span>',
    "not_specified":    '<span class="badge not-specified">Not Specified</span>',
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Demo Viewer</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #0f0f13; color: #e0e0e0; padding: 20px; }}
  h1 {{ font-size: 1.4rem; color: #fff; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 20px; word-break: break-all; }}
  .summary {{ color: #aaa; font-size: 0.85rem; margin-bottom: 16px; }}
  .summary b {{ color: #ddd; }}
  .entry {{ background: #1a1a24; border: 1px solid #2a2a3a; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
  .entry.entry-error {{ border-color: #5a3a10; background: #1a1510; }}
  .entry-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }}
  .entry-name {{ font-size: 0.85rem; color: #aaa; word-break: break-all; flex: 1; }}
  .type-badge {{ font-size: 0.7rem; padding: 2px 7px; border-radius: 4px; font-weight: 600; text-transform: uppercase; white-space: nowrap; }}
  .type-demo {{ background: #1e3a5f; color: #6ab0f5; }}
  .type-cal {{ background: #2a1e5f; color: #a06af5; }}
  .badge {{ font-size: 0.75rem; padding: 3px 8px; border-radius: 4px; font-weight: 600; white-space: nowrap; }}
  .badge.valid {{ background: #0d3320; color: #4caf7d; }}
  .badge.manual-valid {{ background: #0d3320; color: #4caf7d; border: 1px solid #4caf7d; }}
  .badge.invalid {{ background: #3a1010; color: #e57373; }}
  .badge.manual-invalid {{ background: #3a1010; color: #ff5252; border: 1px solid #ff5252; }}
  .badge.error {{ background: #3a2500; color: #ffab40; border: 1px solid #ffab40; }}
  .badge.not-specified {{ background: #2a2a1a; color: #aaa; }}
  .btn-invalid {{ background: #3a1010; color: #e57373; border: 1px solid #5a2020; border-radius: 5px; padding: 5px 12px; font-size: 0.78rem; cursor: pointer; transition: background 0.15s; white-space: nowrap; }}
  .btn-invalid:hover {{ background: #5a1a1a; }}
  .btn-valid {{ background: #0d3320; color: #4caf7d; border: 1px solid #1a5a35; border-radius: 5px; padding: 5px 12px; font-size: 0.78rem; cursor: pointer; transition: background 0.15s; white-space: nowrap; }}
  .btn-valid:hover {{ background: #0d4a2a; }}
  .btn-invalid:disabled, .btn-valid:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .btn-clear {{ background: #1a1a2a; color: #aaa; border: 1px solid #3a3a4a; border-radius: 5px; padding: 5px 12px; font-size: 0.78rem; cursor: pointer; transition: background 0.15s; white-space: nowrap; }}
  .btn-clear:hover {{ background: #2a2a3a; }}
  .btn-clear:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .videos {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  video {{ max-width: 100%; height: 500px; border-radius: 5px; background: #000; }}
  .video-label {{ font-size: 0.72rem; color: #666; margin-top: 3px; text-align: center; }}
  .video-wrap {{ display: flex; flex-direction: column; align-items: center; }}
  .no-video {{ color: #555; font-size: 0.82rem; font-style: italic; }}
  .pagination {{ display: flex; gap: 8px; align-items: center; justify-content: center; margin-top: 24px; flex-wrap: wrap; }}
  .pagination a, .pagination span {{ padding: 6px 14px; border-radius: 5px; font-size: 0.85rem; text-decoration: none; border: 1px solid #2a2a3a; color: #aaa; }}
  .pagination a:hover {{ background: #1a1a2a; color: #fff; }}
  .pagination .current {{ background: #1e3a5f; color: #6ab0f5; border-color: #1e3a5f; }}
  .pagination .disabled {{ opacity: 0.4; pointer-events: none; }}
  .filter-bar {{ display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; }}
  .filter-bar label {{ font-size: 0.82rem; color: #aaa; }}
  .filter-bar select {{ background: #1a1a24; color: #ddd; border: 1px solid #2a2a3a; border-radius: 5px; padding: 5px 10px; font-size: 0.82rem; }}
  .filter-bar a {{ color: #6ab0f5; font-size: 0.82rem; text-decoration: none; }}
  .filter-bar a:hover {{ text-decoration: underline; }}
  .filtered-stats {{ color: #888; font-size: 0.82rem; margin-bottom: 16px; }}
  .filtered-stats b {{ color: #bbb; }}
</style>
</head>
<body>
<h1>Demo Viewer</h1>
<div class="subtitle">{base_dir}</div>
<div class="summary">
  {n_demos} demos, {n_cals} calibrations
  &nbsp;|&nbsp;
  Valid: <b>{n_valid}</b> &nbsp; Invalid: <b>{n_invalid}</b> &nbsp; Not Specified: <b>{n_not_specified}</b> &nbsp; Error: <b>{n_error}</b>
</div>
<div class="filter-bar">
  <label>Type:</label>
  <select id="filter-type" onchange="applyFilter()">
    <option value="all"{sel_type_all}>All</option>
    <option value="demonstration"{sel_type_demo}>Demonstrations</option>
    <option value="calibration"{sel_type_cal}>Calibrations</option>
  </select>
  <label>Status:</label>
  <select id="filter-status" onchange="applyFilter()">
    <option value="all"{sel_status_all}>All</option>
    <option value="valid"{sel_status_valid}>Valid (any)</option>
    <option value="valid_auto"{sel_status_valid_auto}>Valid (auto)</option>
    <option value="valid_manual"{sel_status_valid_manual}>Valid (manual)</option>
    <option value="invalid"{sel_status_inv}>Invalid (any)</option>
    <option value="invalid_auto"{sel_status_inv_auto}>Invalid (auto)</option>
    <option value="invalid_manual"{sel_status_inv_manual}>Invalid (manual)</option>
    <option value="not_specified"{sel_status_ns}>Not specified</option>
    <option value="auto"{sel_status_auto}>Auto only</option>
    <option value="manual"{sel_status_manual}>Manual only</option>
    <option value="error"{sel_status_err}>Error only</option>
  </select>
  <label>Task:</label>
  <select id="filter-task" onchange="applyFilter()">
    <option value="all"{sel_task_all}>All tasks</option>
    {task_options}
  </select>
  <label>Session:</label>
  <select id="filter-session" onchange="applyFilter()">
    <option value="all"{sel_session_all}>All sessions</option>
    {session_options}
  </select>
  <label>Error correction:</label>
  <select id="filter-ec" onchange="applyFilter()">
    <option value="all"{sel_ec_all}>All</option>
    <option value="yes"{sel_ec_yes}>Error correction only</option>
    <option value="no"{sel_ec_no}>Non-error correction only</option>
  </select>
  <label>Sort:</label>
  <select id="filter-sort" onchange="applyFilter()">
    <option value="asc"{sel_sort_asc}>Oldest first</option>
    <option value="desc"{sel_sort_desc}>Newest first</option>
  </select>
  <a href="/?page=1">Reset</a>
</div>
<div class="filtered-stats">
  Showing <b>{start}–{end}</b> of <b>{total}</b> entries &nbsp;|&nbsp; After filtering: <b>{f_demos}</b> demos, <b>{f_cals}</b> calibrations
  &nbsp;|&nbsp;
  Valid: <b>{f_valid}</b> &nbsp; Invalid: <b>{f_invalid}</b> &nbsp; Not Specified: <b>{f_not_specified}</b> &nbsp; Error: <b>{f_error}</b>
</div>
{entries_html}
{pagination_html}
<script>
function applyFilter() {{
  var ftype = document.getElementById('filter-type').value;
  var fstatus = document.getElementById('filter-status').value;
  var ftask = document.getElementById('filter-task').value;
  var fsession = document.getElementById('filter-session').value;
  var fec = document.getElementById('filter-ec').value;
  var fsort = document.getElementById('filter-sort').value;
  window.location.href = '/?ftype=' + ftype + '&fstatus=' + fstatus + '&ftask=' + encodeURIComponent(ftask) + '&fsession=' + encodeURIComponent(fsession) + '&fec=' + fec + '&fsort=' + fsort + '&page=1';
}}
var FSTATUS_INCLUDES = {{
  'all':            ['valid','manual_valid','invalid','manual_invalid','not_specified','error_both_manual','error_both_auto'],
  'valid':          ['valid','manual_valid'],
  'valid_auto':     ['valid'],
  'valid_manual':   ['manual_valid'],
  'invalid':        ['invalid','manual_invalid'],
  'invalid_auto':   ['invalid'],
  'invalid_manual': ['manual_invalid'],
  'not_specified':  ['not_specified'],
  'auto':           ['valid','invalid'],
  'manual':         ['manual_valid','manual_invalid'],
  'error':          ['error_both_manual','error_both_auto'],
}};
function statusVisible(status) {{
  var fstatus = new URLSearchParams(window.location.search).get('fstatus') || 'all';
  var included = FSTATUS_INCLUDES[fstatus] || FSTATUS_INCLUDES['all'];
  return included.indexOf(status) !== -1;
}}
function updateEntry(encodedPath, newStatus, newBadgeHtml, newBtnsHtml) {{
  var entry = document.getElementById('entry-' + encodedPath);
  if (!entry || !statusVisible(newStatus)) {{ location.reload(); return; }}
  document.getElementById('badge-' + encodedPath).innerHTML = newBadgeHtml;
  document.getElementById('btns-' + encodedPath).innerHTML = newBtnsHtml;
}}
function markInvalid(encodedPath, btn) {{
  btn.disabled = true;
  btn.textContent = 'Saving…';
  fetch('/mark_invalid', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{path: encodedPath}})
  }}).then(r => r.json()).then(data => {{
    if (data.ok) {{
      var badge = '<span class=\\"badge manual-invalid\\">Invalid (manual)</span>';
      var btns = '<button class=\\"btn-valid\\" onclick=\\"markValid(\\'' + encodedPath + '\\', this)\\">Mark as Valid</button>'
               + '<button class=\\"btn-clear\\" onclick=\\"clearManual(\\'' + encodedPath + '\\', this)\\">Clear Manual</button>';
      updateEntry(encodedPath, 'manual_invalid', badge, btns);
    }} else {{ btn.disabled = false; btn.textContent = 'Mark as Invalid'; alert('Error: ' + data.error); }}
  }}).catch(() => {{ btn.disabled = false; btn.textContent = 'Mark as Invalid'; }});
}}
function markValid(encodedPath, btn) {{
  btn.disabled = true;
  btn.textContent = 'Saving…';
  fetch('/mark_valid', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{path: encodedPath}})
  }}).then(r => r.json()).then(data => {{
    if (data.ok) {{
      var badge = '<span class=\\"badge manual-valid\\">Valid (manual)</span>';
      var btns = '<button class=\\"btn-invalid\\" onclick=\\"markInvalid(\\'' + encodedPath + '\\', this)\\">Mark as Invalid</button>'
               + '<button class=\\"btn-clear\\" onclick=\\"clearManual(\\'' + encodedPath + '\\', this)\\">Clear Manual</button>';
      updateEntry(encodedPath, 'manual_valid', badge, btns);
    }} else {{ btn.disabled = false; btn.textContent = 'Mark as Valid'; alert('Error: ' + data.error); }}
  }}).catch(() => {{ btn.disabled = false; btn.textContent = 'Mark as Valid'; }});
}}
function clearManual(encodedPath, btn) {{
  btn.disabled = true;
  btn.textContent = 'Clearing…';
  fetch('/clear_manual', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{path: encodedPath}})
  }}).then(r => r.json()).then(data => {{
    if (data.ok) {{
      var badgeMap = {{
        'valid': '<span class=\\"badge valid\\">Valid (auto)</span>',
        'invalid': '<span class=\\"badge invalid\\">Invalid (auto)</span>',
        'not_specified': '<span class=\\"badge not-specified\\">Not Specified</span>',
        'error_both_manual': '<span class=\\"badge error\\">Error: conflicting manual labels</span>',
        'error_both_auto': '<span class=\\"badge error\\">Error: conflicting valid/invalid</span>'
      }};
      var badge = badgeMap[data.new_status] || '<span class=\\"badge not-specified\\">Not Specified</span>';
      var btns = '<button class=\\"btn-valid\\" onclick=\\"markValid(\\'' + encodedPath + '\\', this)\\">Mark as Valid</button>'
               + '<button class=\\"btn-invalid\\" onclick=\\"markInvalid(\\'' + encodedPath + '\\', this)\\">Mark as Invalid</button>';
      updateEntry(encodedPath, data.new_status, badge, btns);
    }} else {{ btn.disabled = false; btn.textContent = 'Clear Manual'; alert('Error: ' + data.error); }}
  }}).catch(() => {{ btn.disabled = false; btn.textContent = 'Clear Manual'; }});
}}
</script>
</body>
</html>"""


def render_entry(entry: dict, server_base: str, lightweight: bool = False, autoplay: bool = True) -> str:
    path = entry["path"]
    name = entry["name"]
    etype = entry["type"]

    if etype == "demonstration":
        type_badge = '<span class="type-badge type-demo">Demo</span>'
        status = get_demo_status(path)
        status_badge = STATUS_BADGE[status]

        encoded = quote(path, safe="")
        folder = Path(path)
        has_manual_invalid = (folder / "manual_invalid.txt").exists()
        has_manual_valid = (folder / "manual_valid.txt").exists()

        btns = []
        if not has_manual_valid:
            btns.append(
                f'<button class="btn-valid" onclick="markValid(\'{encoded}\', this)">Mark as Valid</button>'
            )
        if not has_manual_invalid:
            btns.append(
                f'<button class="btn-invalid" onclick="markInvalid(\'{encoded}\', this)">Mark as Invalid</button>'
            )
        if has_manual_valid or has_manual_invalid:
            btns.append(
                f'<button class="btn-clear" onclick="clearManual(\'{encoded}\', this)">Clear Manual</button>'
            )
        btn_html = "".join(btns)

        if not lightweight:
            videos = get_demo_videos(path)
            if videos:
                parts = []
                for v in videos:
                    label = Path(v).name
                    enc_v = quote(v, safe="")
                    parts.append(
                        f'<div class="video-wrap">'
                        f'<video controls preload="metadata" loop {"autoplay muted " if autoplay else ""}src="/video?path={enc_v}"></video>'
                        f'<div class="video-label">{label}</div>'
                        f"</div>"
                    )
                video_html = '<div class="videos">' + "".join(parts) + "</div>"
            else:
                video_html = '<div class="no-video">No video found</div>'
        else:
            video_html = ""

        entry_cls = " entry-error" if status in ERROR_STATUSES else ""
        return (
            f'<div class="entry{entry_cls}" id="entry-{encoded}">'
            '<div class="entry-header">'
            + type_badge
            + f'<span id="badge-{encoded}">{status_badge}</span>'
            + f'<span id="btns-{encoded}">{btn_html}</span>'
            + f'<div class="entry-name">{name}</div>'
            + "</div>"
            + video_html
            + "</div>"
        )

    else:  # calibration
        type_badge = '<span class="type-badge type-cal">Calibration</span>'

        if not lightweight:
            videos = get_calibration_videos(path)
            if videos:
                parts = []
                for v in videos:
                    label = Path(v).name
                    enc_v = quote(v, safe="")
                    parts.append(
                        f'<div class="video-wrap">'
                        f'<video controls preload="metadata" loop {"autoplay muted " if autoplay else ""}src="/video?path={enc_v}"></video>'
                        f'<div class="video-label">{label}</div>'
                        f"</div>"
                    )
                video_html = '<div class="videos">' + "".join(parts) + "</div>"
            else:
                video_html = '<div class="no-video">No ultrawide video found</div>'
        else:
            video_html = ""

        return (
            '<div class="entry">'
            '<div class="entry-header">'
            + type_badge
            + f'<div class="entry-name">{name}</div>'
            + "</div>"
            + video_html
            + "</div>"
        )


def build_page(entries: list[dict], page: int, ftype: str, fstatus: str, ftask: str, fsession: str, fec: str, fsort: str, base_dir: str, lightweight: bool = False, autoplay: bool = True) -> str:
    all_entries = entries

    def demo_status(e):
        return get_demo_status(e["path"]) if e["type"] == "demonstration" else None

    if ftype == "demonstration":
        filtered = [e for e in all_entries if e["type"] == "demonstration"]
    elif ftype == "calibration":
        filtered = [e for e in all_entries if e["type"] == "calibration"]
    else:
        filtered = all_entries

    if fstatus == "valid":
        filtered = [e for e in filtered if demo_status(e) in VALID_STATUSES]
    elif fstatus == "valid_auto":
        filtered = [e for e in filtered if demo_status(e) == "valid"]
    elif fstatus == "valid_manual":
        filtered = [e for e in filtered if demo_status(e) == "manual_valid"]
    elif fstatus == "invalid":
        filtered = [e for e in filtered if demo_status(e) in INVALID_STATUSES]
    elif fstatus == "invalid_auto":
        filtered = [e for e in filtered if demo_status(e) == "invalid"]
    elif fstatus == "invalid_manual":
        filtered = [e for e in filtered if demo_status(e) == "manual_invalid"]
    elif fstatus == "not_specified":
        filtered = [e for e in filtered if demo_status(e) == "not_specified"]
    elif fstatus == "auto":
        filtered = [e for e in filtered if demo_status(e) in AUTO_STATUSES]
    elif fstatus == "manual":
        filtered = [e for e in filtered if demo_status(e) in MANUAL_STATUSES]
    elif fstatus == "error":
        filtered = [e for e in filtered if demo_status(e) in ERROR_STATUSES]

    if ftask != "all":
        filtered = [e for e in filtered if ftask in e.get("task_names", [])]

    if fsession != "all":
        filtered = [e for e in filtered if e.get("session_name") == fsession]

    if fec == "yes":
        filtered = [e for e in filtered if e.get("is_error_correction")]
    elif fec == "no":
        filtered = [e for e in filtered if not e.get("is_error_correction")]

    if fsort == "desc":
        filtered = list(reversed(filtered))

    total = len(filtered)
    n_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(1, min(page, n_pages))
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_entries = filtered[start_idx:end_idx]

    n_demos = sum(1 for e in all_entries if e["type"] == "demonstration")
    n_cals = sum(1 for e in all_entries if e["type"] == "calibration")
    n_valid = sum(1 for e in all_entries if demo_status(e) in VALID_STATUSES)
    n_invalid = sum(1 for e in all_entries if demo_status(e) in INVALID_STATUSES)
    n_not_specified = sum(1 for e in all_entries if demo_status(e) == "not_specified")
    n_error = sum(1 for e in all_entries if demo_status(e) in ERROR_STATUSES)

    f_demos = sum(1 for e in filtered if e["type"] == "demonstration")
    f_cals = sum(1 for e in filtered if e["type"] == "calibration")
    f_valid = sum(1 for e in filtered if demo_status(e) in VALID_STATUSES)
    f_invalid = sum(1 for e in filtered if demo_status(e) in INVALID_STATUSES)
    f_not_specified = sum(1 for e in filtered if demo_status(e) == "not_specified")
    f_error = sum(1 for e in filtered if demo_status(e) in ERROR_STATUSES)

    entries_html = "".join(render_entry(e, base_dir, lightweight, autoplay) for e in page_entries)
    if not entries_html:
        entries_html = '<div class="no-video" style="padding:30px;text-align:center">No entries found.</div>'

    def page_url(p: int) -> str:
        return f"/?page={p}&ftype={ftype}&fstatus={fstatus}&ftask={quote(ftask, safe='')}&fsession={quote(fsession, safe='')}&fec={fec}&fsort={fsort}"

    pagination_parts = []
    prev_cls = "" if page > 1 else " disabled"
    pagination_parts.append(
        f'<a href="{page_url(page - 1)}" class="prev{prev_cls}">&larr; Prev</a>'
    )
    for p in range(1, n_pages + 1):
        if abs(p - page) <= 2 or p == 1 or p == n_pages:
            cls = " current" if p == page else ""
            pagination_parts.append(f'<a href="{page_url(p)}" class="{cls.strip()}">{p}</a>')
        elif abs(p - page) == 3:
            pagination_parts.append("<span>…</span>")
    next_cls = "" if page < n_pages else " disabled"
    pagination_parts.append(
        f'<a href="{page_url(page + 1)}" class="next{next_cls}">Next &rarr;</a>'
    )
    pagination_html = '<div class="pagination">' + "".join(pagination_parts) + "</div>"

    type_sel = {"all": "", "demonstration": "", "calibration": ""}
    type_sel[ftype if ftype in type_sel else "all"] = ' selected="selected"'
    status_keys = ["all", "valid", "valid_auto", "valid_manual", "invalid", "invalid_auto", "invalid_manual", "not_specified", "auto", "manual", "error"]
    status_sel = {k: "" for k in status_keys}
    status_sel[fstatus if fstatus in status_sel else "all"] = ' selected="selected"'

    all_task_names = sorted({t for e in all_entries for t in e.get("task_names", [])})
    task_option_parts = []
    for t in all_task_names:
        sel = ' selected="selected"' if t == ftask else ""
        task_option_parts.append(f'<option value="{t}"{sel}>{t}</option>')
    task_options = "".join(task_option_parts)

    all_session_names = sorted({e.get("session_name", "") for e in all_entries if e.get("session_name")})
    session_option_parts = []
    for s in all_session_names:
        sel = ' selected="selected"' if s == fsession else ""
        session_option_parts.append(f'<option value="{s}"{sel}>{s}</option>')
    session_options = "".join(session_option_parts)

    return HTML_TEMPLATE.format(
        base_dir=base_dir,
        start=start_idx + 1 if total > 0 else 0,
        end=min(end_idx, total),
        total=total,
        n_demos=n_demos,
        n_cals=n_cals,
        n_valid=n_valid,
        n_invalid=n_invalid,
        n_not_specified=n_not_specified,
        n_error=n_error,
        f_demos=f_demos,
        f_cals=f_cals,
        f_valid=f_valid,
        f_invalid=f_invalid,
        f_not_specified=f_not_specified,
        f_error=f_error,
        entries_html=entries_html,
        pagination_html=pagination_html,
        sel_type_all=type_sel["all"],
        sel_type_demo=type_sel["demonstration"],
        sel_type_cal=type_sel["calibration"],
        sel_status_all=status_sel["all"],
        sel_status_valid=status_sel["valid"],
        sel_status_valid_auto=status_sel["valid_auto"],
        sel_status_valid_manual=status_sel["valid_manual"],
        sel_status_inv=status_sel["invalid"],
        sel_status_inv_auto=status_sel["invalid_auto"],
        sel_status_inv_manual=status_sel["invalid_manual"],
        sel_status_ns=status_sel["not_specified"],
        sel_status_auto=status_sel["auto"],
        sel_status_manual=status_sel["manual"],
        sel_status_err=status_sel["error"],
        sel_task_all=' selected="selected"' if ftask == "all" else "",
        task_options=task_options,
        sel_session_all=' selected="selected"' if fsession == "all" else "",
        session_options=session_options,
        sel_ec_all=' selected="selected"' if fec == "all" else "",
        sel_ec_yes=' selected="selected"' if fec == "yes" else "",
        sel_ec_no=' selected="selected"' if fec == "no" else "",
        sel_sort_asc=' selected="selected"' if fsort != "desc" else "",
        sel_sort_desc=' selected="selected"' if fsort == "desc" else "",
    )


def serve_video(handler: "Handler", file_path: str) -> None:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        handler.send_error(404, "Video not found")
        return

    file_size = path.stat().st_size
    range_header = handler.headers.get("Range")

    if range_header:
        try:
            byte_range = range_header.strip().split("=")[1]
            parts = byte_range.split("-")
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else file_size - 1
        except Exception:
            handler.send_error(400, "Bad Range header")
            return
        end = min(end, file_size - 1)
        length = end - start + 1
        handler.send_response(206)
        handler.send_header("Content-Type", "video/mp4")
        handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        handler.send_header("Content-Length", str(length))
        handler.send_header("Accept-Ranges", "bytes")
        handler.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
    else:
        handler.send_response(200)
        handler.send_header("Content-Type", "video/mp4")
        handler.send_header("Content-Length", str(file_size))
        handler.send_header("Accept-Ranges", "bytes")
        handler.end_headers()
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _handle_clear_manual(handler: "Handler") -> None:
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length)
    try:
        data = json.loads(body)
        folder_path = unquote(data.get("path", ""))
        folder = Path(folder_path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")
        abs_folder = os.path.abspath(folder_path)
        abs_base = os.path.abspath(handler.base_dir)
        if not (abs_folder + os.sep).startswith(abs_base + os.sep):
            raise ValueError("Path not under base directory")
        for fname in ("manual_invalid.txt", "manual_valid.txt"):
            p = folder / fname
            if p.exists():
                p.unlink()
        new_status = get_demo_status(folder_path)
        resp = json.dumps({"ok": True, "new_status": new_status}).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
    except Exception as e:
        resp = json.dumps({"ok": False, "error": str(e)}).encode()
        handler.send_response(400)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)


def _handle_mark(handler: "Handler", filename: str, cleanup: str | None = None) -> None:
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length)
    try:
        data = json.loads(body)
        folder_path = unquote(data.get("path", ""))
        folder = Path(folder_path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")
        abs_folder = os.path.abspath(folder_path)
        abs_base = os.path.abspath(handler.base_dir)
        if not (abs_folder + os.sep).startswith(abs_base + os.sep):
            raise ValueError(f"Path not under base directory")
        if cleanup:
            cleanup_path = folder / cleanup
            if cleanup_path.exists():
                cleanup_path.unlink()
        (folder / filename).write_text("")
        resp = json.dumps({"ok": True}).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)
    except Exception as e:
        resp = json.dumps({"ok": False, "error": str(e)}).encode()
        handler.send_response(400)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(resp)))
        handler.end_headers()
        handler.wfile.write(resp)


class Handler(BaseHTTPRequestHandler):
    entries: list[dict] = []
    base_dir: str = ""
    lightweight: bool = False

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path in ("/", ""):
            page = int(qs.get("page", ["1"])[0])
            ftype = qs.get("ftype", ["all"])[0]
            fstatus = qs.get("fstatus", ["all"])[0]
            ftask = qs.get("ftask", ["all"])[0]
            fsession = qs.get("fsession", ["all"])[0]
            fec = qs.get("fec", ["all"])[0]
            fsort = qs.get("fsort", ["asc"])[0]
            html = build_page(self.entries, page, ftype, fstatus, ftask, fsession, fec, fsort, self.base_dir, self.lightweight, self.autoplay)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/video":
            file_path = unquote(qs.get("path", [""])[0])
            serve_video(self, file_path)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/mark_invalid":
            _handle_mark(self, "manual_invalid.txt", cleanup="manual_valid.txt")
        elif parsed.path == "/mark_valid":
            _handle_mark(self, "manual_valid.txt", cleanup="manual_invalid.txt")
        elif parsed.path == "/clear_manual":
            _handle_clear_manual(self)
        else:
            self.send_error(404)


def main():
    parser = argparse.ArgumentParser(description="Demo viewer web server")
    parser.add_argument("base_dir", help="Directory to scan for demonstrations")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    parser.add_argument("--lightweight", action="store_true", help="Skip video players (faster page loads)")
    parser.add_argument("--no-autoplay", action="store_true", help="Disable video autoplay")
    args = parser.parse_args()

    base_dir = os.path.abspath(args.base_dir)
    if not os.path.isdir(base_dir):
        print(f"Error: {base_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {base_dir} …", end=" ", flush=True)
    entries = find_entries(base_dir)
    n_demos = sum(1 for e in entries if e["type"] == "demonstration")
    n_cals = sum(1 for e in entries if e["type"] == "calibration")
    print(f"found {len(entries)} entries ({n_demos} demos, {n_cals} calibrations)")

    Handler.entries = entries
    Handler.base_dir = base_dir
    Handler.lightweight = args.lightweight
    Handler.autoplay = not args.no_autoplay

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    print(f"Serving at http://localhost:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
