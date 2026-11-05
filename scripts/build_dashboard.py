"""
raw_stories.json + raw_subtasks.json  ->  site/index.html (+ site/data.json)

Rules
- A Story is shown only if it has at least one sub-task whose summary contains
  SUBTASK_KEYWORD (default "BL", case-sensitive). Other sub-tasks are ignored.
- The BL number is read from the summary (BL1, _BL12, "BL 3", BL4.1 -> 4.1).
- "Finished" statuses are listed in DONE_STATUSES; DROP_STATUSES are shown greyed out.
- Every date is converted to Asia/Taipei.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

JIRA_SITE = os.environ.get("JIRA_SITE", "mobiledrivetech.atlassian.net")
JQL = os.environ.get("JIRA_JQL", "filter=11923")
KEYWORD = os.environ.get("SUBTASK_KEYWORD", "BL")
TPE = timezone(timedelta(hours=8))

DONE_STATUSES = {"Done", "Released", "Closed", "Resolved"}
DROP_STATUSES = {"DROP", "Dropped", "Cancelled", "Canceled", "Rejected"}
BL_RE = re.compile(r"BL\s*(\d+(?:\.\d+)?)")
CFTS_RE = re.compile(r"CFTS[\s_]*(\d+)", re.I)
VF_RE = re.compile(r"VF(\d+)(?:[_-]?V(\d+))?")
PART_RE = re.compile(r"part\s*(\d+)", re.I)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")


def tpe(ts):
    """Jira timestamp ('2026-11-04T20:08:59.280+0800') -> ISO string in Taipei time."""
    if not ts:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(ts, fmt).astimezone(TPE).isoformat(timespec="minutes")
        except ValueError:
            pass
    return ts


def state(status):
    if status in DROP_STATUSES:
        return "drop"
    if status in DONE_STATUSES:
        return "done"
    return "open"


def doc_id(summary):
    """Document family and number from the Story summary, used for the CFTS / VF
    filter and for sorting: CFTS by number then part, VF by number then version."""
    part = PART_RE.search(summary)
    part = int(part.group(1)) if part else 0
    m = CFTS_RE.search(summary)
    if m:
        n = int(m.group(1))
        return {"type": "CFTS", "no": n, "ver": 0, "part": part, "label": f"CFTS {n:03d}"}
    m = VF_RE.search(summary)
    if m:
        n, v = int(m.group(1)), int(m.group(2) or 0)
        return {"type": "VF", "no": n, "ver": v, "part": part,
                "label": f"VF{n:03d}" + (f" V{v}" if v else "")}
    return {"type": "其他", "no": 0, "ver": 0, "part": part, "label": ""}


def name(user):
    return (user or {}).get("displayName", "")


def main():
    stories = json.load(open("raw_stories.json", encoding="utf-8"))
    subtasks = {s["key"]: s for s in json.load(open("raw_subtasks.json", encoding="utf-8"))}

    out = []
    for s in stories:
        f = s["fields"]
        bls = []
        for stub in f.get("subtasks") or []:
            summ = stub.get("fields", {}).get("summary") or ""
            if KEYWORD not in summ:
                continue
            full = subtasks.get(stub["key"], stub)
            sf = full.get("fields", {})
            m = BL_RE.search(summ)
            status = (sf.get("status") or {}).get("name", "")
            bls.append({
                "key": stub["key"],
                "summary": summ.replace("\t", " "),
                "bl": float(m.group(1)) if m else None,
                "status": status,
                "state": state(status),
                "assignee": name(sf.get("assignee")),
                "created": tpe(sf.get("created")),
                "updated": tpe(sf.get("updated")),
                "files": sorted(
                    [{"name": a.get("filename", ""), "created": tpe(a.get("created")),
                      "author": name(a.get("author")), "size": a.get("size", 0)}
                     for a in sf.get("attachment") or []],
                    key=lambda a: a["created"], reverse=True),
            })
        if not bls:
            continue
        # BL number order; a sub-task without a readable number goes last, and two
        # sub-tasks with the same number keep their creation order
        bls.sort(key=lambda b: (b["bl"] is None, b["bl"] or 0, b["created"]))
        parent = (f.get("parent") or {}).get("fields", {})
        out.append({
            "key": s["key"],
            "summary": (f.get("summary") or "").replace("\t", " "),
            "status": (f.get("status") or {}).get("name", ""),
            "assignee": name(f.get("assignee")),
            "release": parent.get("summary", "(no parent)"),
            "updated": tpe(f.get("updated")),
            "doc": doc_id(f.get("summary") or ""),
            "bls": bls,
        })

    data = {
        "generated": datetime.now(TPE).isoformat(timespec="minutes"),
        "site": JIRA_SITE,
        "jql": JQL,
        "keyword": KEYWORD,
        "filterStories": len(stories),
        "stories": out,
    }
    os.makedirs("site", exist_ok=True)
    with open("site/data.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    html = open(TEMPLATE, encoding="utf-8").read()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    with open("site/index.html", "w", encoding="utf-8") as fh:
        fh.write(html.replace("/*__DATA__*/null", payload))
    print(f"{len(out)} of {len(stories)} stories have a '{KEYWORD}' sub-task; "
          f"{sum(len(s['bls']) for s in out)} {KEYWORD} sub-tasks -> site/index.html")


if __name__ == "__main__":
    main()
