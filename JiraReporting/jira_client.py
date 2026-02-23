import os
import requests
from requests.auth import HTTPBasicAuth
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import pandas as pd


class JiraClient:
    def __init__(self, base_url, username, password, verify_ssl=True, timeout=120):

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        if verify_ssl is False:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

        if os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY"):
            self.session.proxies = {
                "http": os.getenv("HTTP_PROXY"),
                "https": os.getenv("HTTPS_PROXY")
            }

    def _request(self, method, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(
                method,
                url,
                params=params,
                timeout=self.timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            raise Exception("Connection Timeout: Jira took too long to respond.")

        except requests.exceptions.HTTPError:
            raise Exception(f"HTTP Error {response.status_code}: {response.text}")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Connection Error: {str(e)}")

    def test_connection(self):
        return self._request("GET", "/rest/api/2/myself")

    def get_projects(self):
        data = self._request("GET", "/rest/api/2/project")
        return pd.DataFrame([
            {"id": p["id"], "key": p["key"], "name": p["name"]}
            for p in data
        ])

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
        data = self._request("GET", f"/rest/api/2/issue/{issue_key}/worklog")
        return data.get("worklogs", [])
