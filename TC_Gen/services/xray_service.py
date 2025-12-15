
import json
from .jira_service import JiraService


class XrayService:
    """
    Handles Xray-specific logic:
    - Auto-detecting Xray Steps field
    - Auto-detecting Test Set association field
    - Creating Xray Test issues
    - Creating/Selecting Test Sets
    - Adding test steps in Xray format
    - Linking Tests ↔ Story, Test Set ↔ Story
    """

    def __init__(self, jira: JiraService, project_key: str,
                 xray_test_issue_type="Xray Test",
                 xray_testset_issue_type="Test Set"):
        self.jira = jira
        self.project_key = project_key
        self.xray_test_issue_type = xray_test_issue_type
        self.xray_testset_issue_type = xray_testset_issue_type

        # Auto-detected fields
        self.steps_field = None
        self.testset_tests_field = None

    # ----------------------------------------------------------------------
    # Auto-detect Xray Test Steps custom field
    # ----------------------------------------------------------------------
    def detect_steps_field(self):
        """
        Detects the customfield ID used for Xray Test Steps.
        This field exists only on issue type "Xray Test".
        """

        metadata = self.jira.get_issue_metadata(self.project_key, self.xray_test_issue_type)

        try:
            issue_type_def = metadata["projects"][0]["issuetypes"][0]["fields"]
        except (KeyError, IndexError):
            raise RuntimeError("Failed to fetch Jira metadata for Xray Test issue type.")

        for field_id, field_info in issue_type_def.items():
            schema = field_info.get("schema", {})
            if "com.xpand-addons.xray:test-steps" in str(schema.get("custom")):
                self.steps_field = field_id
                return self.steps_field

        raise RuntimeError("Cannot detect Xray Steps field. Check Xray installation or permissions.")

    # ----------------------------------------------------------------------
    # Auto-detect Test Set association field
    # ----------------------------------------------------------------------
    def detect_testset_tests_field(self):
        """
        Detects the customfield ID used to store the list of Tests inside a Test Set.
        """

        metadata = self.jira.get_issue_metadata(self.project_key, self.xray_testset_issue_type)

        try:
            fields = metadata["projects"][0]["issuetypes"][0]["fields"]
        except (KeyError, IndexError):
            raise RuntimeError("Failed to fetch metadata for Test Set issue type.")

        for field_id, field_info in fields.items():
            name = field_info.get("name", "").lower()
            type_hint = str(field_info.get("schema", {}))

            if "test" in name and "set" in name and "array" in type_hint:
                # This is most likely the association field
                self.testset_tests_field = field_id
                return self.testset_tests_field

            # Backup heuristic for Xray
            if "tests" in name and field_info.get("schema", {}).get("type") == "array":
                self.testset_tests_field = field_id
                return self.testset_tests_field

        raise RuntimeError("Unable to detect Xray Test Set association field.")

    # ----------------------------------------------------------------------
    # Create Xray Test Issue
    # ----------------------------------------------------------------------
    def create_xray_test(self, summary: str, description: str = None):
        """
        Create a new Xray Test issue.
        Steps will be added separately.
        """

        issue = self.jira.create_issue(
            project_key=self.project_key,
            issue_type=self.xray_test_issue_type,
            summary=summary,
            description=description
        )

        return issue["key"]

    # ----------------------------------------------------------------------
    # Add Xray Test Steps
    # ----------------------------------------------------------------------
    def add_test_steps(self, test_key: str, steps: list):
        """
        Saves step list in Xray format:
        [
            {"action": "Step 1", "data": null, "result": "Expected 1"},
            ...
        ]
        """

        if not self.steps_field:
            self.detect_steps_field()

        xray_steps_format = []
        for step in steps:
            xray_steps_format.append({
                "action": step.get("action") or step.get("step") or "",
                "data": step.get("data") or None,
                "result": step.get("expected") or step.get("expected_result") or ""
            })

        payload = {
            "fields": {
                self.steps_field: xray_steps_format
            }
        }

        return self.jira._put(f"/rest/api/3/issue/{test_key}", payload)

    # ----------------------------------------------------------------------
    # Create Test Set
    # ----------------------------------------------------------------------
    def create_testset(self, name: str, description: str = ""):
        issue = self.jira.create_issue(
            project_key=self.project_key,
            issue_type=self.xray_testset_issue_type,
            summary=name,
            description=description
        )
        return issue["key"]

    # ----------------------------------------------------------------------
    # Add test keys to a Test Set
    # ----------------------------------------------------------------------
    def add_tests_to_testset(self, testset_key: str, test_keys: list):
        if not self.testset_tests_field:
            self.detect_testset_tests_field()

        update_payload = {
            "update": {
                self.testset_tests_field: [
                    {"add": {"key": t}} for t in test_keys
                ]
            }
        }

        return self.jira._put(f"/rest/api/3/issue/{testset_key}", update_payload)

    # ----------------------------------------------------------------------
    # Link issues (Story ↔ Test, Story ↔ Test Set)
    # ----------------------------------------------------------------------
    def link_test_to_story(self, test_key: str, story_key: str):
        return self.jira.link_issues(inward_key=test_key, outward_key=story_key, link_type="Tests")

    def link_testset_to_story(self, testset_key: str, story_key: str):
        return self.jira.link_issues(inward_key=testset_key, outward_key=story_key, link_type="Tests")
