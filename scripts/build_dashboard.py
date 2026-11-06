"""
raw_stories.json + raw_subtasks.json  ->  site/index.html (+ site/data.json)

Rules
- A Story is shown only if it has at least one sub-task whose summary contains
  SUBTASK_KEYWORD (default "BL", case-sensitive). Other sub-tasks are ignored.
- The BL number is read from the summary (BL1, _BL12, "BL 3", BL4.1 -> 4.1).
- A sub-task counts as finished when its status is in Jira's "Done" category;
  DROP_STATUSES are shown greyed out instead.
- "Polarion checked": the time a sub-task (any sub-task of the Story, BL or not)
  became done for Polarion, i.e. moved into Polarion checked, Polarion in progress
  or Polarion in review (COMPLETE_STATUSES), read from the changelog.
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

POLARION_STATUS = os.environ.get("POLARION_STATUS", "Polarion checked")
POLARION_JQL = os.environ.get("POLARION_JQL", "filter=12786")
# the two tags on the Polarion tab, in this order; any other status in that filter
# still shows up after them
QUEUE_STATUSES = ["Polarion in progress", "Polarion in review"]
# a sub-task in any of these statuses counts as done for Polarion
COMPLETE_STATUSES = [POLARION_STATUS] + QUEUE_STATUSES
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


def state(status_obj):
    name_ = (status_obj or {}).get("name", "")
    if name_ in DROP_STATUSES:
        return "drop"
    if ((status_obj or {}).get("statusCategory") or {}).get("key") == "done":
        return "done"
    return "open"


def polarion_checked(issue, status_ids):
    """When this sub-task (last) became done for Polarion, or ''.

    Done means one of COMPLETE_STATUSES. The time is taken from the changelog: the
    latest move into one of them from a status outside them, so a later move between
    them (Polarion checked -> Polarion in progress) keeps the original date. Without a
    changelog entry, the resolution date of a sub-task currently in one of them."""
    f = issue.get("fields", {})

    def inside(sid, sname):
        return sid in status_ids or sname in COMPLETE_STATUSES

    start = ""
    histories = sorted((issue.get("changelog") or {}).get("histories") or [],
                       key=lambda h: h.get("created") or "")
    for h in histories:
        for it in h.get("items") or []:
            if it.get("field") != "status":
                continue
            if inside(it.get("to"), it.get("toString")) and not inside(it.get("from"), it.get("fromString")):
                start = h.get("created") or start
    if start:
        return tpe(start)
    if (f.get("status") or {}).get("name") in COMPLETE_STATUSES:
        return tpe(f.get("resolutiondate") or f.get("statuscategorychangedate"))
    return ""


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
    # the status may have been renamed, so match old changelog entries by status id
    status_ids = {(t["fields"].get("status") or {}).get("id") for t in subtasks.values()
                  if (t["fields"].get("status") or {}).get("name") in COMPLETE_STATUSES} - {None}

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
                "checked": polarion_checked(full, status_ids),
                "key": stub["key"],
                "summary": summ.replace("\t", " "),
                "bl": float(m.group(1)) if m else None,
                "status": status,
                "state": state(sf.get("status")),
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
        checks = []
        for stub in f.get("subtasks") or []:
            full = subtasks.get(stub["key"])
            when = polarion_checked(full, status_ids) if full else ""
            if when:
                checks.append({"key": stub["key"], "when": when,
                               "summary": (stub.get("fields", {}).get("summary") or "").replace("\t", " ")})
        checks.sort(key=lambda c: c["when"], reverse=True)
        parent = (f.get("parent") or {}).get("fields", {})
        out.append({
            "key": s["key"],
            "summary": (f.get("summary") or "").replace("\t", " "),
            "status": (f.get("status") or {}).get("name", ""),
            "assignee": name(f.get("assignee")),
            "release": parent.get("summary", "(no parent)"),
            "updated": tpe(f.get("updated")),
            "doc": doc_id(f.get("summary") or ""),
            "checks": checks,
            "bls": bls,
        })

    queue = []
    if os.path.exists("raw_polarion.json"):
        for q in json.load(open("raw_polarion.json", encoding="utf-8")):
            f = q["fields"]
            st = f.get("status") or {}
            since = ""   # when the issue entered its current status
            for h in (q.get("changelog") or {}).get("histories") or []:
                for it in h.get("items") or []:
                    if it.get("field") == "status" and it.get("to") == st.get("id"):
                        since = max(since, h.get("created") or "")
            parent = f.get("parent") or {}
            psum = (parent.get("fields") or {}).get("summary") or ""
            queue.append({
                "key": q["key"],
                "summary": (f.get("summary") or "").replace("\t", " "),
                "type": (f.get("issuetype") or {}).get("name", ""),
                "status": st.get("name", ""),
                "assignee": name(f.get("assignee")),
                "created": tpe(f.get("created")),
                "updated": tpe(f.get("updated")),
                "due": f.get("duedate") or "",
                "since": tpe(since),
                "parent": parent.get("key", ""),
                "parentSummary": psum.replace("\t", " "),
                "doc": doc_id(psum or f.get("summary") or ""),
            })

    data = {
        "generated": datetime.now(TPE).isoformat(timespec="minutes"),
        "site": JIRA_SITE,
        "jql": JQL,
        "keyword": KEYWORD,
        "polarion": " / ".join(COMPLETE_STATUSES),
        "filterStories": len(stories),
        "stories": out,
        "queueJql": POLARION_JQL,
        "queueStatuses": QUEUE_STATUSES,
        "queue": queue,
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
