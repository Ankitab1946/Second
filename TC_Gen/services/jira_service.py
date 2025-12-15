
import requests
from requests.auth import HTTPBasicAuth
import json
import urllib.parse


class JiraService:
    """
    Jira Service supporting both:
    - Jira Cloud (email + API token)
    - Jira Data Center (username + password)
    """

    def __init__(self, base_url: str, username: str, password: str, jira_type: str = "cloud"):
        """
        :param base_url: Jira base URL (cloud or datacenter)
        :param username: Jira username or email (cloud)
        :param password: API token (cloud) or password (datacenter)
        :param jira_type: "cloud" or "datacenter"
        """

        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.jira_type = jira_type.lower()

        # Build auth object
        self.auth = HTTPBasicAuth(self.username, self.password)

        # Common headers
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    # ----------------------------------------------------------------------
    # Internal HTTP wrapper
    # ----------------------------------------------------------------------
    def _get(self, path: str, params=None):
        url = f"{self.base_url}{path}"
        res = requests.get(url, headers=self.headers, auth=self.auth, params=params)
        self._check_error(res, url)
        return res.json()

    def _post(self, path: str, payload: dict):
        url = f"{self.base_url}{path}"
        res = requests.post(url, headers=self.headers, auth=self.auth, data=json.dumps(payload))
        self._check_error(res, url, payload)
        return res.json()

    def _put(self, path: str, payload: dict):
        url = f"{self.base_url}{path}"
        res = requests.put(url, headers=self.headers, auth=self.auth, data=json.dumps(payload))
        self._check_error(res, url, payload)
        return res.json()

    def _check_error(self, response, url, payload=None):
        if not response.ok:
            msg = f"Jira API Error {response.status_code} at {url}\n{response.text}"
            if payload:
                msg += f"\nPayload: {json.dumps(payload, indent=2)}"
            raise RuntimeError(msg)

    # ----------------------------------------------------------------------
    # Issue metadata
    # ----------------------------------------------------------------------
    def get_issue_metadata(self, project_key: str, issue_type: str):
        """
        Retrieves metadata for creating issues, including field definitions.
        Used to detect Xray Steps custom field.
        """
        path = f"/rest/api/3/issue/createmeta?projectKeys={project_key}&issuetypeNames={urllib.parse.quote(issue_type)}&expand=projects.issuetypes.fields"
        return self._get(path)

    # ----------------------------------------------------------------------
    # Issue search methods
    # ----------------------------------------------------------------------
    def search_issues_jql(self, jql: str, max_results: int = 50):
        path = "/rest/api/3/search"
        params = {"jql": jql, "maxResults": max_results}
        return self._get(path, params)

    def search_issues_by_summary(self, project_key: str, text: str, max_results: int = 50):
        jql = f'project = "{project_key}" AND summary ~ "{text}" order by created desc'
        return self.search_issues_jql(jql, max_results)

    def search_issues_by_project(self, project_key: str, issue_type: str = None, max_results: int = 50):
        if issue_type:
            jql = f'project = "{project_key}" AND issuetype = "{issue_type}" order by created desc'
        else:
            jql = f'project = "{project_key}" order by created desc'
        return self.search_issues_jql(jql, max_results)

    # ----------------------------------------------------------------------
    # Retrieve issue data
    # ----------------------------------------------------------------------
    def get_issue(self, issue_key: str):
        path = f"/rest/api/3/issue/{issue_key}"
        return self._get(path)

    def get_issue_transitions(self, issue_key: str):
        path = f"/rest/api/3/issue/{issue_key}/transitions"
        return self._get(path)

    # ----------------------------------------------------------------------
    # Issue creation
    # ----------------------------------------------------------------------
    def create_issue(self, project_key: str, issue_type: str, summary: str, description: str = None, fields: dict = None):
        """
        Generic issue creation — used for Test, Test Set, etc.
        """
        payload_fields = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }

        if description:
            payload_fields["description"] = description

        if fields:
            payload_fields.update(fields)

        payload = {"fields": payload_fields}
        return self._post("/rest/api/3/issue", payload)

    # ----------------------------------------------------------------------
    # Linking issues
    # ----------------------------------------------------------------------
    def link_issues(self, inward_key: str, outward_key: str, link_type: str = "Tests"):
        """
        Link issues using a Jira issue link type.
        Example: link Test → Story, or Test Set → Story
        """
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key}
        }
        return self._post("/rest/api/3/issueLink", payload)

    # ----------------------------------------------------------------------
    # Add issues to Test Set
    # ----------------------------------------------------------------------
    def add_tests_to_testset(self, testset_key: str, test_keys: list):
        """
        Adds a list of Xray Test keys to a Test Set.
        """
        path = f"/rest/api/3/issue/{testset_key}"

        update_block = {
            "update": {
                "customfield_testset_tests": [
                    {"add": {"key": t}} for t in test_keys
                ]
            }
        }

        return self._put(path, update_block)
