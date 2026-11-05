"""
Pull the SYS2 document-release Stories and their BL sub-tasks from Jira Cloud.

Step 1: every issue in the saved filter (JIRA_JQL, default filter=11923).
Step 2: every sub-task of the Stories that have at least one sub-task whose
        summary contains SUBTASK_KEYWORD (default "BL"), with the fields the
        dashboard needs (dates and attachments are not on the parent's
        `subtasks` stub, so they have to be fetched separately).

Writes raw_stories.json and raw_subtasks.json (raw Jira v3 issue objects).

Required environment variables:
  JIRA_EMAIL, JIRA_API_TOKEN
Optional:
  JIRA_SITE        default mobiledrivetech.atlassian.net
  JIRA_JQL         default filter=11923
  SUBTASK_KEYWORD  default BL (case-sensitive substring of the sub-task summary)
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

JIRA_SITE = os.environ.get("JIRA_SITE", "mobiledrivetech.atlassian.net")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JQL = os.environ.get("JIRA_JQL", "filter=11923")
KEYWORD = os.environ.get("SUBTASK_KEYWORD", "BL")

STORY_FIELDS = ["summary", "status", "issuetype", "assignee", "created", "updated",
                "duedate", "parent", "subtasks"]
SUBTASK_FIELDS = ["summary", "status", "assignee", "created", "updated",
                  "resolutiondate", "parent", "attachment"]
CHUNK = 50  # parent keys per JQL query; keeps the JQL well under the length limit

_auth = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
_HEADERS = {"Authorization": f"Basic {_auth}", "Content-Type": "application/json",
            "Accept": "application/json"}


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Jira API error {e.code} for {url}:\n{e.read().decode(errors='replace')}") from e


def search(jql, fields):
    url = f"https://{JIRA_SITE}/rest/api/3/search/jql"
    issues, token = [], None
    while True:
        body = {"jql": jql, "maxResults": 100, "fields": fields}
        if token:
            body["nextPageToken"] = token
        data = _post(url, body)
        page = data.get("issues", [])
        issues.extend(page)
        token = data.get("nextPageToken")
        if not token or not page:
            return issues


def main():
    if not JIRA_EMAIL or not JIRA_API_TOKEN:
        sys.exit("JIRA_EMAIL / JIRA_API_TOKEN are empty. Add both under "
                 "Settings > Secrets and variables > Actions, then re-run.")
    stories = search(JQL, STORY_FIELDS)
    print(f"Filter '{JQL}': {len(stories)} issues")
    if not stories:
        # Jira answers an unauthorised search with 200 and no issues, so an empty
        # result almost always means the account cannot see the filter. Stop here
        # rather than publish an empty dashboard over the last good one.
        sys.exit(f"Filter '{JQL}' returned 0 issues. Check that the secrets belong to an "
                 "account that can open the filter.")

    parents = [s["key"] for s in stories
               if any(KEYWORD in (st.get("fields", {}).get("summary") or "")
                      for st in (s.get("fields", {}).get("subtasks") or []))]
    print(f"Stories with a '{KEYWORD}' sub-task: {len(parents)}")

    subtasks = {}
    for i in range(0, len(parents), CHUNK):
        keys = ",".join(parents[i:i + CHUNK])
        for issue in search(f"parent in ({keys})", SUBTASK_FIELDS):
            subtasks[issue["key"]] = issue
    print(f"Sub-tasks fetched: {len(subtasks)}")

    with open("raw_stories.json", "w", encoding="utf-8") as f:
        json.dump(stories, f, ensure_ascii=False)
    with open("raw_subtasks.json", "w", encoding="utf-8") as f:
        json.dump(list(subtasks.values()), f, ensure_ascii=False)


if __name__ == "__main__":
    main()
