# import requests
# from requests.auth import HTTPBasicAuth


# class XrayService:
#     def __init__(self, jira, project_key):
#         self.jira = jira
#         self.project_key = project_key
#         self.base_url = jira.base_url
#         self.auth = HTTPBasicAuth(jira.username, jira.password)
#         self.headers = {"Content-Type": "application/json"}

#     # ---------------------------------------------------
#     # Create Xray Test Issue
#     # ---------------------------------------------------
#     def create_xray_test(self, title, preconditions):
#         payload = {
#             "fields": {
#                 "project": {"key": self.project_key},
#                 "summary": title,
#                 "description": preconditions,
#                 "issuetype": {"name": "Xray Test"}
#             }
#         }

#         r = requests.post(
#             f"{self.base_url}/rest/api/2/issue",
#             json=payload,
#             auth=self.auth,
#             headers=self.headers,
#             verify=False
#         )
#         r.raise_for_status()
#         return r.json()["key"]

#     # ---------------------------------------------------
#     # Add Test Steps (ONE BY ONE – XRAY SAFE)
#     # ---------------------------------------------------
#     def add_test_steps(self, test_key, steps):
#         for s in steps:
#             payload = {
#                 "step": {
#                     "action": s.get("action", ""),
#                     "data": "",
#                     "result": s.get("expected", "")
#                 }
#             }

#             r = requests.post(
#                 f"{self.base_url}/rest/raven/1.0/api/test/{test_key}/step",
#                 json=payload,
#                 auth=self.auth,
#                 headers=self.headers,
#                 verify=False
#             )
#             r.raise_for_status()

#     # ---------------------------------------------------
#     # Create Test Set
#     # ---------------------------------------------------
#     def create_testset(self, name):
#         payload = {
#             "fields": {
#                 "project": {"key": self.project_key},
#                 "summary": name,
#                 "issuetype": {"name": "Test Set"}
#             }
#         }

#         r = requests.post(
#             f"{self.base_url}/rest/api/2/issue",
#             json=payload,
#             auth=self.auth,
#             headers=self.headers,
#             verify=False
#         )
#         r.raise_for_status()
#         return r.json()["key"]

#     # ---------------------------------------------------
#     # Link Test Set → Story
#     # (Shows as "Tested By" in Story, "Tests" in Test Set)
#     # ---------------------------------------------------
#     def link_testset_to_story(self, testset_key, story_key):
#         payload = {
#             "type": {"name": "Tests"},
#             "inwardIssue": {"key": testset_key},
#             "outwardIssue": {"key": story_key}
#         }

#         r = requests.post(
#             f"{self.base_url}/rest/api/2/issueLink",
#             json=payload,
#             auth=self.auth,
#             headers=self.headers,
#             verify=False
#         )
#         r.raise_for_status()

#     # ---------------------------------------------------
#     # Add Tests → Test Set
#     # ---------------------------------------------------
#     def add_tests_to_testset(self, testset_key, test_keys):
#         payload = {"add": test_keys}

#         r = requests.post(
#             f"{self.base_url}/rest/raven/1.0/api/testset/{testset_key}/test",
#             json=payload,
#             auth=self.auth,
#             headers=self.headers,
#             verify=False
#         )
#         r.raise_for_status()


import requests
from requests.auth import HTTPBasicAuth


class XrayService:
    """
    Production-safe Xray integration.

    Supports:
    - Create Xray Test
    - Add Test Steps (ALL Xray variants)
    - Create Test Set
    - Link Test Set -> Story (Tested By)
    - Add Tests -> Test Set

    Handles:
    - Xray Cloud (new / old)
    - Xray Data Center
    - PUT /steps, PUT /step, POST /step differences
    """

    def __init__(self, jira, project_key):
        self.jira = jira
        self.project_key = project_key

        # Normalize base URL to avoid //rest errors
        self.base_url = jira.base_url.rstrip("/")

        self.auth = HTTPBasicAuth(jira.username, jira.password)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    # ---------------------------------------------------------
    # Create Xray Test
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Add Test Steps (UNIVERSAL IMPLEMENTATION)
    # ---------------------------------------------------------
    def add_test_steps(self, test_key, steps):
        """
        Adds steps to an Xray Test.

        Tries in this order:
        1) PUT  /steps   (Xray Cloud – bulk replace, most common)
        2) PUT  /step    (Xray Data Center)
        3) POST /step    (Legacy Xray Cloud)

        This covers ALL known Xray versions.
        """

        if not steps:
            return

        normalized_steps = [
            {
                "action": s.get("action", ""),
                "data": "",
                "result": s.get("expected", "")
            }
            for s in steps
        ]

        # =====================================================
        # 1️⃣ TRY PUT /steps (Bulk replace – Cloud)
        # =====================================================
        bulk_url = f"{self.base_url}/rest/raven/1.0/api/test/{test_key}/steps"
        bulk_payload = {"steps": normalized_steps}

        r = requests.put(
            bulk_url,
            json=bulk_payload,
            auth=self.auth,
            headers=self.headers,
            verify=False
        )

        if r.status_code in (200, 201, 204):
            return  # SUCCESS

        # =====================================================
        # 2️⃣ TRY PUT /step (DC)
        # =====================================================
        step_url = f"{self.base_url}/rest/raven/1.0/api/test/{test_key}/step"

        put_success = True
        for step in normalized_steps:
            payload = {"step": step}

            r = requests.put(
                step_url,
                json=payload,
                auth=self.auth,
                headers=self.headers,
                verify=False
            )

            if r.status_code not in (200, 201, 204):
                put_success = False
                break

        if put_success:
            return  # SUCCESS

        # =====================================================
        # 3️⃣ FALLBACK POST /step (Legacy Cloud)
        # =====================================================
        for step in normalized_steps:
            payload = {"step": step}

            r = requests.post(
                step_url,
                json=payload,
                auth=self.auth,
                headers=self.headers,
                verify=False
            )

            if r.status_code not in (200, 201, 204):
                raise RuntimeError(
                    f"Failed to add steps to {test_key}. "
                    f"Status: {r.status_code}, Response: {r.text}"
                )

    # ---------------------------------------------------------
    # Create Test Set
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Link Test Set -> Story
    # Appears as:
    # Story  -> Tested By -> Test Set
    # TestSet -> Tests    -> Story
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Add Tests -> Test Set
    # ---------------------------------------------------------
    def add_tests_to_testset(self, testset_key, test_keys):
        if not test_keys:
            return

        payload = {"add": test_keys}

        r = requests.post(
            f"{self.base_url}/rest/raven/1.0/api/testset/{testset_key}/test",
            json=payload,
            auth=self.auth,
            headers=self.headers,
            verify=False
        )

        r.raise_for_status()
