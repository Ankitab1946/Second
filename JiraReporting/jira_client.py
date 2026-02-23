import requests
import pandas as pd
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class JiraClient:
    def __init__(self, base_url, username, password, verify_ssl=True, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )

        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    # ---------------- Generic Request ----------------
    def _request(self, method, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"

        response = self.session.request(
            method,
            url,
            params=params,
            timeout=self.timeout,
            verify=self.verify_ssl
        )

        response.raise_for_status()
        return response.json()

    # ---------------- Basic APIs ----------------

    def test_connection(self):
        return self._request("GET", "/rest/api/2/myself")

    def get_projects(self):
        data = self._request("GET", "/rest/api/2/project")
        return pd.DataFrame(data)

    def get_boards(self):
        data = self._request("GET", "/rest/agile/1.0/board")
        boards_df = pd.DataFrame(data.get("values", []))

        # 🔥 Keep only Scrum boards
        if not boards_df.empty and "type" in boards_df.columns:
            boards_df = boards_df[boards_df["type"] == "scrum"]

        return boards_df

    def get_sprints(self, board_id):
        try:
            data = self._request(
                "GET",
                f"/rest/agile/1.0/board/{board_id}/sprint"
            )
            return pd.DataFrame(data.get("values", []))
        except requests.exceptions.HTTPError:
            return pd.DataFrame()

    def search_issues(self, jql, fields, batch_size=100):
        start_at = 0
        all_issues = []

        while True:
            data = self._request(
                "GET",
                "/rest/api/2/search",
                params={
                    "jql": jql,
                    "fields": fields,
                    "startAt": start_at,
                    "maxResults": batch_size
                }
            )

            issues = data.get("issues", [])
            total = data.get("total", 0)

            all_issues.extend(issues)

            if start_at + batch_size >= total:
                break

            start_at += batch_size

        return all_issues

    def get_worklogs(self, issue_key):
        data = self._request(
            "GET",
            f"/rest/api/2/issue/{issue_key}/worklog"
        )
        return data.get("worklogs", [])
