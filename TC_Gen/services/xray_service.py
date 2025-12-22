import requests
from requests.auth import HTTPBasicAuth


class XrayService:
    def __init__(self, jira, project_key):
        self.jira = jira
        self.project_key = project_key
        self.base_url = jira.base_url
        self.auth = HTTPBasicAuth(jira.username, jira.password)
        self.headers = {"Content-Type": "application/json"}

    # ---------------------------------------------------
    # Create Xray Test Issue
    # ---------------------------------------------------
    def create_xray_test(self, title, preconditions):
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": title,
                "description": preconditions,
                "issuetype": {"name": "Xray Test"}
            }
        }

        r = requests.post(
            f"{self.base_url}/rest/api/2/issue",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            verify=False
        )
        r.raise_for_status()
        return r.json()["key"]

    # ---------------------------------------------------
    # Add Test Steps (ONE BY ONE – XRAY SAFE)
    # ---------------------------------------------------
    def add_test_steps(self, test_key, steps):
        for s in steps:
            payload = {
                "step": {
                    "action": s.get("action", ""),
                    "data": "",
                    "result": s.get("expected", "")
                }
            }

            r = requests.post(
                f"{self.base_url}/rest/raven/1.0/api/test/{test_key}/step",
                json=payload,
                auth=self.auth,
                headers=self.headers,
                verify=False
            )
            r.raise_for_status()

    # ---------------------------------------------------
    # Create Test Set
    # ---------------------------------------------------
    def create_testset(self, name):
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": name,
                "issuetype": {"name": "Test Set"}
            }
        }

        r = requests.post(
            f"{self.base_url}/rest/api/2/issue",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            verify=False
        )
        r.raise_for_status()
        return r.json()["key"]

    # ---------------------------------------------------
    # Link Test Set → Story
    # (Shows as "Tested By" in Story, "Tests" in Test Set)
    # ---------------------------------------------------
    def link_testset_to_story(self, testset_key, story_key):
        payload = {
            "type": {"name": "Tests"},
            "inwardIssue": {"key": testset_key},
            "outwardIssue": {"key": story_key}
        }

        r = requests.post(
            f"{self.base_url}/rest/api/2/issueLink",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            verify=False
        )
        r.raise_for_status()

    # ---------------------------------------------------
    # Add Tests → Test Set
    # ---------------------------------------------------
    def add_tests_to_testset(self, testset_key, test_keys):
        payload = {"add": test_keys}

        r = requests.post(
            f"{self.base_url}/rest/raven/1.0/api/testset/{testset_key}/test",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            verify=False
        )
        r.raise_for_status()
