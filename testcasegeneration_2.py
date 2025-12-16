aws bedrock create-inference-profile \
  --inference-profile-name claude35-sonnet-profile \
  --model-arn arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0 \
  --region us-east-1 \
  --no-verify-ssl

# # ai_testcase_generator_fixed_for_claude35.py
# import streamlit as st
# import boto3
# from botocore.config import Config
# import botocore
# import json
# import requests
# from requests.auth import HTTPBasicAuth
# import pandas as pd
# import os
# import tempfile
# import urllib3
# import difflib
# import traceback
# from typing import List, Dict, Any

# # =====================================================================
# # PAGE CONFIG
# # =====================================================================
# st.set_page_config(layout="wide", page_title="AI Testcase Generator (Fixed for Claude 3.5)")
# st.title("AI Testcase Generator — Bedrock Model Picker (Claude 3.5 Compatible)")

# # =====================================================================
# # TLS CONFIG HELPERS
# # =====================================================================
# def build_verify_from_sidebar(prefix: str):
#     st.sidebar.write("---")
#     st.sidebar.markdown(f"**{prefix.capitalize()} TLS options**")
#     disable = st.sidebar.checkbox(
#         f"Disable {prefix} SSL verification (insecure)",
#         value=False, key=f"{prefix}_disable"
#     )
#     upload = st.sidebar.file_uploader(
#         f"Upload {prefix} CA certificate (.pem) (optional)",
#         type=["pem", "crt"], key=f"{prefix}_ca"
#     )

#     ca_path = None
#     if upload is not None:
#         tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
#         tmp.write(upload.read())
#         tmp.flush()
#         tmp.close()
#         ca_path = tmp.name
#         st.sidebar.success(f"Uploaded {prefix} CA certificate will be used.")

#     if disable:
#         urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
#         return False, f"{prefix}: verification DISABLED (insecure)"

#     if ca_path:
#         return ca_path, f"{prefix}: using uploaded CA bundle {ca_path}"

#     if prefix == "bedrock" and os.getenv("AWS_CA_BUNDLE"):
#         return os.getenv("AWS_CA_BUNDLE"), f"{prefix}: using AWS_CA_BUNDLE"

#     return True, f"{prefix}: using system trust store"


# st.sidebar.header("Connection & TLS settings")
# bedrock_verify, bedrock_verify_msg = build_verify_from_sidebar("bedrock")
# jira_verify, jira_verify_msg = build_verify_from_sidebar("jira")
# st.sidebar.markdown(f"*Bedrock TLS:* {bedrock_verify_msg}")
# st.sidebar.markdown(f"*Jira TLS:* {jira_verify_msg}")

# # =====================================================================
# # AWS CREDENTIALS
# # =====================================================================
# st.sidebar.write("---")
# st.sidebar.header("AWS Bedrock credentials")

# aws_region = st.sidebar.text_input("AWS Region", value="us-east-1")
# aws_access_key_id = st.sidebar.text_input("AWS Access Key ID", value=os.getenv("AWS_ACCESS_KEY_ID") or "")
# aws_secret_access_key = st.sidebar.text_input("AWS Secret Access Key", value=os.getenv("AWS_SECRET_ACCESS_KEY") or "", type="password")
# aws_session_token = st.sidebar.text_input("AWS Session Token (optional)", value=os.getenv("AWS_SESSION_TOKEN") or "", type="password")

# # =====================================================================
# # JIRA CREDENTIALS
# # =====================================================================
# st.sidebar.write("---")
# st.sidebar.header("Jira credentials")

# jira_base = st.sidebar.text_input("Jira Base URL (e.g. https://yourdomain.atlassian.net)")
# jira_auth_method = st.sidebar.radio(
#     "Jira Auth Method",
#     options=["api_token", "password"],
#     format_func=lambda x: "Email + API Token (Cloud)" if x == "api_token" else "Username + Password (Server)"
# )

# jira_email = st.sidebar.text_input("Jira Email (for API token auth)")
# jira_api_token = st.sidebar.text_input("Jira API Token", type="password")
# jira_username = st.sidebar.text_input("Jira Username (for password auth)")
# jira_password = st.sidebar.text_input("Jira Password", type="password")

# # =====================================================================
# # STS TEST
# # =====================================================================
# def test_aws_credentials(region, access_key, secret_key, session_token, verify=True):
#     kwargs = {}
#     if access_key and secret_key:
#         kwargs["aws_access_key_id"] = access_key
#         kwargs["aws_secret_access_key"] = secret_key
#     if session_token:
#         kwargs["aws_session_token"] = session_token

#     try:
#         session = boto3.Session(**kwargs) if kwargs else boto3.Session()
#         sts = session.client("sts", region_name=region, verify=verify)
#         identity = sts.get_caller_identity()
#         return True, "STS OK", identity
#     except Exception as e:
#         return False, str(e), None


# if st.sidebar.button("Test AWS Credentials / STS"):
#     ok, msg, details = test_aws_credentials(
#         aws_region, aws_access_key_id, aws_secret_access_key, aws_session_token, verify=bedrock_verify
#     )
#     if ok:
#         st.sidebar.success(msg)
#         st.sidebar.json(details)
#     else:
#         st.sidebar.error(msg)

# # =====================================================================
# # CREATE BEDROCK CLIENTS
# # =====================================================================
# def make_clients():
#     session_kwargs = {}

#     if aws_access_key_id and aws_secret_access_key:
#         session_kwargs["aws_access_key_id"] = aws_access_key_id
#         session_kwargs["aws_secret_access_key"] = aws_secret_access_key
#     if aws_session_token:
#         session_kwargs["aws_session_token"] = aws_session_token

#     session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()

#     cfg = Config(retries={"max_attempts": 3, "mode": "standard"})

#     mgmt = session.client("bedrock", region_name=aws_region, config=cfg, verify=bedrock_verify)
#     runtime = session.client("bedrock-runtime", region_name=aws_region, config=cfg, verify=bedrock_verify)

#     return mgmt, runtime


# # =====================================================================
# # LIST MODELS
# # =====================================================================
# def list_bedrock_models(mgmt):
#     try:
#         # resp = mgmt.list_models()
#         resp = mgmt.list_foundation_models()
#         models = [m["modelId"] for m in resp.get("modelSummaries", [])]
#         return True, sorted(models), ""
#     except Exception as e:
#         return False, [], str(e)

# # =====================================================================
# # MODEL-FAMILY DETECTION
# # =====================================================================
# def detect_model_family(model_id: str):
#     mid = model_id.lower()
#     if "claude-3" in mid:
#         return "claude3"
#     if "claude" in mid:
#         return "claude-legacy"
#     if "llama" in mid:
#         return "llama"
#     if "titan" in mid:
#         return "titan"
#     return "unknown"

# # =====================================================================
# # FIXED PROMPT TEMPLATE
# # =====================================================================
# PROMPT_TEMPLATE = (
#     "You are a software QA engineer. Given the Jira issue details below, generate a list of test cases "
#     "as a JSON array. Each test case must include: id, title, priority (Low/Medium/High), type "
#     "(Functional/Regression/Smoke), preconditions, steps (array of step descriptions), expected_result. "
#     "Output strictly JSON.\n\n"
#     "JIRA SUMMARY:\n{summary}\n\n"
#     "JIRA DESCRIPTION:\n{description}\n\n"
#     "LABELS:\n{labels}\n\n"
#     "COMMENTS:\n{comments}"
# )

# # =====================================================================
# # INVOCATION FIXED FOR CLAUDE 3.5
# # =====================================================================
# def generate_testcases(runtime, model_id, summary, description, labels, comments, max_tokens):

#     user_prompt = PROMPT_TEMPLATE.format(
#         summary=summary or "",
#         description=description or "",
#         labels=", ".join(labels) if labels else "",
#         comments="\n".join(comments) if comments else ""
#     )

#     body = json.dumps({
#         "messages": [
#             {"role": "user", "content": user_prompt}
#         ],
#         "max_tokens": max_tokens,
#         "temperature": 0.2
#     })

#     try:
#         resp = runtime.invoke_model(
#             modelId=model_id,
#             contentType="application/json",
#             accept="application/json",
#             body=body
#         )
#     except Exception as e:
#         raise RuntimeError(f"Bedrock invoke error: {e}")

#     raw = resp["body"].read().decode("utf-8")
#     data = json.loads(raw)

#     # Extract assistant message
#     content = data["output"]["message"]["content"][0]["text"]

#     # Extract JSON array from free-text output
#     start = content.find("[")
#     end = content.rfind("]")
#     json_text = content[start:end+1]

#     try:
#         tcs = json.loads(json_text)
#     except Exception:
#         tcs = [{
#             "id": "ERR",
#             "title": "Parse Error",
#             "priority": "Medium",
#             "type": "Functional",
#             "preconditions": "",
#             "steps": [content],
#             "expected_result": ""
#         }]

#     return tcs

# # =====================================================================
# # JIRA HELPERS
# # =====================================================================
# # (unchanged – skipped for brevity, same as your version)
# # If needed, I will paste them again.

# # (… truncated in this message due to space — I will deliver the remaining JIRA + UI code in the next message.)

# # =====================================================================
# # JIRA HELPERS
# # =====================================================================

# def fetch_jira_issue(jira_base: str, issue_key: str, auth_method: str,
#                      email: str = None, api_token: str = None,
#                      username: str = None, password: str = None,
#                      verify=True):

#     url = jira_base.rstrip("/") + f"/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment"
#     headers = {"Accept": "application/json"}

#     if auth_method == "api_token":
#         auth = HTTPBasicAuth(email, api_token)
#     else:
#         auth = HTTPBasicAuth(username, password)

#     try:
#         resp = requests.get(url, auth=auth, headers=headers, verify=verify)
#     except requests.exceptions.SSLError as e:
#         raise RuntimeError(f"Jira SSL error: {e}")

#     if resp.status_code != 200:
#         raise RuntimeError(f"Error fetching issue: {resp.status_code} - {resp.text}")

#     return resp.json()


# def attach_file_to_issue(jira_base: str, issue_key: str, file_bytes: bytes, filename: str,
#                          auth_method: str, email: str = None, api_token: str = None,
#                          username: str = None, password: str = None, verify=True):

#     url = jira_base.rstrip("/") + f"/rest/api/3/issue/{issue_key}/attachments"
#     headers = {"X-Atlassian-Token": "no-check"}

#     auth = HTTPBasicAuth(email, api_token) if auth_method == "api_token" else HTTPBasicAuth(username, password)

#     files = {"file": (filename, file_bytes)}

#     try:
#         resp = requests.post(url, auth=auth, headers=headers, files=files, verify=verify)
#         resp.raise_for_status()
#         return resp.json()
#     except Exception as e:
#         raise RuntimeError(f"Attachment failed: {e}")


# def create_jira_subtask(jira_base: str, parent_key: str, summary: str, description: str,
#                         issue_type: str, project_key: str, auth_method: str,
#                         email: str = None, api_token: str = None,
#                         username: str = None, password: str = None,
#                         verify=True):

#     url = jira_base.rstrip("/") + "/rest/api/3/issue"

#     auth = HTTPBasicAuth(email, api_token) if auth_method == "api_token" else HTTPBasicAuth(username, password)

#     payload = {
#         "fields": {
#             "project": {"key": project_key},
#             "parent": {"key": parent_key},
#             "summary": summary,
#             "description": description,
#             "issuetype": {"name": issue_type}
#         }
#     }

#     try:
#         resp = requests.post(url, auth=auth, json=payload,
#                              headers={"Content-Type": "application/json"}, verify=verify)
#         resp.raise_for_status()
#         return resp.json()
#     except Exception as e:
#         raise RuntimeError(f"Subtask creation failed: {e}")


# # =====================================================================
# # UI — FETCH JIRA ISSUE
# # =====================================================================

# st.markdown("Enter Jira issue → Fetch → Choose Model → Generate → Review → Upload.")

# left, right = st.columns([2, 1])
# with left:
#     issue_key = st.text_input("Jira Issue Key (e.g., PROJ-123)")

# with right:
#     if st.button("Fetch Jira Issue"):
#         if not issue_key or not jira_base:
#             st.error("Please enter Jira base URL & issue key.")
#         else:
#             try:
#                 issue = fetch_jira_issue(
#                     jira_base, issue_key,
#                     auth_method=jira_auth_method,
#                     email=jira_email,
#                     api_token=jira_api_token,
#                     username=jira_username,
#                     password=jira_password,
#                     verify=jira_verify
#                 )

#                 st.session_state["issue"] = issue
#                 st.success(f"Issue {issue_key} fetched.")
#             except Exception as e:
#                 st.error(f"Error: {e}")


# # =====================================================================
# # ISSUE PREVIEW + MODEL LISTING
# # =====================================================================

# if "issue" in st.session_state:
#     issue = st.session_state["issue"]
#     fields = issue["fields"]

#     st.subheader("Jira Issue Preview")

#     st.markdown(f"### **{issue_key} — {fields.get('summary', '')}**")

#     st.markdown("**Description**")
#     st.write(fields.get("description") or "")

#     st.markdown("**Labels:** " + ", ".join(fields.get("labels") or []))

#     comments = [c.get("body") for c in (fields.get("comment") or {}).get("comments", [])]
#     if comments:
#         st.markdown("**Recent comments:**")
#         for c in comments[:5]:
#             st.write("- " + (c[:200] + "..." if len(c) > 200 else c))

#     st.write("---")
#     st.subheader("Bedrock Model Selection")

#     try:
#         mgmt, runtime = make_clients()
#     except Exception as e:
#         st.error("Could not create Bedrock clients: " + str(e))
#         mgmt = runtime = None

#     models = []
#     if mgmt:
#         ok, models, msg = list_bedrock_models(mgmt)
#         if not ok:
#             st.error(f"Model listing failed: {msg}")
#         else:
#             st.success(f"Found {len(models)} models")

#             sample = models[:200]
#             selected_model = st.selectbox(
#                 "Pick model",
#                 options=["-- choose --"] + sample
#             )
#             custom_id = st.text_input("Or paste custom model id")

#             chosen_model = custom_id.strip() if custom_id.strip() else (
#                 selected_model if selected_model != "-- choose --" else ""
#             )

#             if chosen_model:
#                 st.info(f"Using: `{chosen_model}`")
#             else:
#                 st.warning("No model selected yet.")

#             # Model validation
#             if st.button("Validate Model"):
#                 if chosen_model in models:
#                     st.success("Model found and valid.")
#                 else:
#                     st.error("Model not in list — ensure correct region & permissions.")

#             # ---------------------------------------------------------------------
#             # GENERATE TESTCASES BUTTON
#             # ---------------------------------------------------------------------
#             st.write("---")
#             st.subheader("Generate Testcases")

#             max_tokens = st.number_input("Max tokens", value=1500)

#             if st.button("Generate Testcases (Claude 3.5)"):
#                 if not chosen_model:
#                     st.error("Select or enter a model ID.")
#                 else:
#                     try:
#                         tcs = generate_testcases(
#                             runtime, chosen_model,
#                             fields.get("summary", ""),
#                             fields.get("description", ""),
#                             fields.get("labels") or [],
#                             comments or [],
#                             max_tokens=max_tokens
#                         )
#                         st.session_state["testcases"] = tcs
#                         st.success(f"Generated {len(tcs)} testcases.")
#                     except Exception as e:
#                         st.error(f"Generation Error: {e}")

# # =====================================================================
# # DISPLAY & EDIT TESTCASES
# # =====================================================================

# def tc_list_to_df(tcs: List[Dict[str, Any]]) -> pd.DataFrame:
#     rows = []
#     for tc in tcs:
#         rows.append({
#             "id": tc.get("id"),
#             "title": tc.get("title"),
#             "priority": tc.get("priority"),
#             "type": tc.get("type"),
#             "preconditions": tc.get("preconditions"),
#             "steps": "\n".join(tc.get("steps")) if isinstance(tc.get("steps"), list) else str(tc.get("steps")),
#             "expected_result": tc.get("expected_result")
#         })
#     return pd.DataFrame(rows)


# if "testcases" in st.session_state:
#     st.subheader("Review & Edit Testcases")

#     df = tc_list_to_df(st.session_state["testcases"])

#     edited_df = st.experimental_data_editor(df, num_rows="dynamic")

#     # ----------------------------------------------------
#     # DOWNLOAD CSV
#     # ----------------------------------------------------
#     st.download_button(
#         "Download CSV",
#         edited_df.to_csv(index=False).encode("utf-8"),
#         file_name=f"{issue_key}_testcases.csv",
#         mime="text/csv"
#     )

#     st.write("---")
#     st.subheader("Upload to Jira")

#     # ====================================================
#     # ATTACHMENT
#     # ====================================================
#     col_attach, col_subtask = st.columns(2)

#     with col_attach:
#         if st.button("Attach CSV to Jira Issue"):
#             try:
#                 csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
#                 resp = attach_file_to_issue(
#                     jira_base,
#                     issue_key,
#                     csv_bytes,
#                     f"{issue_key}_testcases.csv",
#                     jira_auth_method,
#                     email=jira_email,
#                     api_token=jira_api_token,
#                     username=jira_username,
#                     password=jira_password,
#                     verify=jira_verify
#                 )
#                 st.success("CSV attached successfully.")
#                 st.json(resp)
#             except Exception as e:
#                 st.error(f"Attachment failed: {e}")

#     # ====================================================
#     # SUBTASK CREATION
#     # ====================================================
#     with col_subtask:
#         project_key = st.text_input("Project Key for Subtasks (ex: PROJ)")
#         issue_type = st.selectbox("Issue Type", options=["Sub-task", "Task", "Bug"])

#         if st.button("Create Subtasks for Each Testcase"):
#             if not project_key:
#                 st.error("Enter project key.")
#             else:
#                 created = []
#                 for _, row in edited_df.iterrows():
#                     summary = f"TC - {row['id']} - {row['title'][:80]}"
#                     desc = (
#                         f"Preconditions:\n{row['preconditions']}\n\n"
#                         f"Steps:\n{row['steps']}\n\n"
#                         f"Expected:\n{row['expected_result']}"
#                     )

#                     try:
#                         res = create_jira_subtask(
#                             jira_base,
#                             issue_key,
#                             summary,
#                             desc,
#                             issue_type,
#                             project_key,
#                             jira_auth_method,
#                             email=jira_email,
#                             api_token=jira_api_token,
#                             username=jira_username,
#                             password=jira_password,
#                             verify=jira_verify
#                         )
#                         created.append(res.get("key"))
#                     except Exception as e:
#                         st.error(f"Subtask creation failed: {e}")

#                 if created:
#                     st.success("Created: " + ", ".join(created))


# # =====================================================================
# # TROUBLESHOOTING NOTES
# # =====================================================================

# st.markdown("---")
# st.markdown("### **Notes & Troubleshooting**")
# st.markdown("""
# - **Claude 3.5 requires `messages[]` format**, not `"prompt"` or `"Human:"`.
# - If you see **ValidationException**, your model ID is wrong for your region.
# - If `list_models()` fails:
#   - Make sure IAM has:  
#     `bedrock:ListModels`, `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`
# - If SSL issues occur, use **sidebar TLS disable** or upload a CA bundle.
# - STS test helps diagnose **invalid or expired AWS credentials**.
# """)

# ai_testcase_generator_claude35_profiles_full.py
import streamlit as st
import boto3
from botocore.config import Config
import botocore
import json
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import os
import tempfile
import urllib3
from typing import List, Dict, Any


# =====================================================================
# PAGE CONFIG
# =====================================================================
st.set_page_config(layout="wide", page_title="AI Testcase Generator (Claude 3.5 + Profiles)")
st.title("AI Testcase Generator — Claude 3.5 Sonnet (Inference Profiles Enabled)")


# =====================================================================
# TLS CONFIG BLOCK
# =====================================================================
def build_verify_from_sidebar(prefix: str):
    st.sidebar.write("---")
    st.sidebar.markdown(f"**{prefix.upper()} TLS Options**")

    disable = st.sidebar.checkbox(
        f"Disable {prefix} SSL verification (insecure)",
        value=False,
        key=f"{prefix}_disable"
    )

    upload = st.sidebar.file_uploader(
        f"Upload {prefix} CA (.pem)",
        type=["pem", "crt"],
        key=f"{prefix}_ca"
    )

    ca_path = None
    if upload:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        tmp.write(upload.read())
        tmp.close()
        ca_path = tmp.name

    if disable:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return False, "(SSL Verification Disabled)"

    if ca_path:
        return ca_path, f"(Custom CA: {ca_path})"

    return True, "(System Trust Store)"


st.sidebar.header("TLS Settings")
bedrock_verify, msg_bedrock = build_verify_from_sidebar("bedrock")
jira_verify, msg_jira = build_verify_from_sidebar("jira")
st.sidebar.write("Bedrock TLS:", msg_bedrock)
st.sidebar.write("Jira TLS:", msg_jira)


# =====================================================================
# AWS CREDENTIALS
# =====================================================================
st.sidebar.write("---")
st.sidebar.header("AWS Credentials")

aws_region = st.sidebar.text_input("AWS Region", value="us-east-1")
aws_access_key_id = st.sidebar.text_input("AWS Access Key ID", value=os.getenv("AWS_ACCESS_KEY_ID") or "")
aws_secret_access_key = st.sidebar.text_input("AWS Secret Access Key", type="password",
                                              value=os.getenv("AWS_SECRET_ACCESS_KEY") or "")
aws_session_token = st.sidebar.text_input("AWS Session Token (optional)", type="password",
                                          value=os.getenv("AWS_SESSION_TOKEN") or "")


# =====================================================================
# STS TEST FUNCTION + BUTTON
# =====================================================================
def test_aws_credentials(region, access_key, secret_key, session_token, verify=True):
    try:
        kwargs = {}
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

        session = boto3.Session(**kwargs) if kwargs else boto3.Session()
        sts = session.client("sts", region_name=region, verify=verify)
        resp = sts.get_caller_identity()

        return True, "STS test successful!", resp

    except botocore.exceptions.ClientError as e:
        err = e.response.get("Error", {})
        return False, f"{err.get('Code')}: {err.get('Message')}", None
    except Exception as e:
        return False, f"Unexpected error: {e}", None


if st.sidebar.button("Test AWS Credentials / STS"):
    ok, msg, details = test_aws_credentials(
        aws_region,
        aws_access_key_id,
        aws_secret_access_key,
        aws_session_token,
        verify=bedrock_verify
    )
    if ok:
        st.sidebar.success(msg)
        st.sidebar.json(details)
    else:
        st.sidebar.error(msg)


# =====================================================================
# JIRA CREDENTIALS
# =====================================================================
st.sidebar.write("---")
st.sidebar.header("Jira Credentials")

jira_base = st.sidebar.text_input("Jira Base URL (e.g. https://company.atlassian.net)")

jira_auth_method = st.sidebar.radio(
    "Jira Authentication Method",
    ["api_token", "password"],
    format_func=lambda x: "Email + API Token (Cloud)" if x == "api_token" else "Username + Password (Server)"
)

jira_email = st.sidebar.text_input("Jira Email (Cloud)")
jira_api_token = st.sidebar.text_input("Jira API Token", type="password")
jira_username = st.sidebar.text_input("Jira Username (Server)")
jira_password = st.sidebar.text_input("Jira Password (Server)", type="password")


# =====================================================================
# CREATE BEDROCK CLIENTS (mgmt + runtime)
# =====================================================================
def make_clients():
    session_kwargs = {}
    if aws_access_key_id:
        session_kwargs["aws_access_key_id"] = aws_access_key_id
        session_kwargs["aws_secret_access_key"] = aws_secret_access_key
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token

    session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()
    cfg = Config(retries={"max_attempts": 3, "mode": "standard"})

    mgmt = session.client("bedrock", region_name=aws_region, config=cfg, verify=bedrock_verify)
    runtime = session.client("bedrock-runtime", region_name=aws_region, config=cfg, verify=bedrock_verify)

    return mgmt, runtime


# =====================================================================
# LIST FOUNDATION MODELS
# =====================================================================
def list_foundation_models(mgmt):
    try:
        resp = mgmt.list_foundation_models()
        return True, [m["modelId"] for m in resp.get("modelSummaries", [])], ""
    except Exception as e:
        return False, [], str(e)


# =====================================================================
# LIST INFERENCE PROFILES (REQUIRED FOR CLAUDE 3.5)
# =====================================================================
def list_inference_profiles(mgmt):
    try:
        resp = mgmt.list_inference_profiles()
        profiles = [
            {"name": p.get("inferenceProfileName"), "arn": p.get("inferenceProfileArn")}
            for p in resp.get("inferenceProfiles", [])
        ]
        return True, profiles, ""
    except Exception as e:
        return False, [], str(e)


# =====================================================================
# JIRA HELPERS
# =====================================================================
def fetch_jira_issue(jira_base, issue_key, auth_method,
                     email=None, api_token=None, username=None, password=None,
                     verify=True):

    url = jira_base.rstrip("/") + f"/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment"

    auth = HTTPBasicAuth(email, api_token) if auth_method == "api_token" else HTTPBasicAuth(username, password)

    resp = requests.get(url, auth=auth, headers={"Accept": "application/json"}, verify=verify)

    if resp.status_code != 200:
        raise RuntimeError(f"Jira Error {resp.status_code}: {resp.text}")

    return resp.json()


def attach_file_to_issue(jira_base, issue_key, file_bytes, filename,
                         auth_method, email=None, api_token=None, username=None, password=None,
                         verify=True):

    url = jira_base.rstrip("/") + f"/rest/api/3/issue/{issue_key}/attachments"
    headers = {"X-Atlassian-Token": "no-check"}

    auth = HTTPBasicAuth(email, api_token) if auth_method == "api_token" else HTTPBasicAuth(username, password)

    resp = requests.post(url, auth=auth, headers=headers,
                         files={"file": (filename, file_bytes)}, verify=verify)
    resp.raise_for_status()

    return resp.json()


def create_jira_subtask(jira_base, parent_key, summary, description,
                        issue_type, project_key, auth_method,
                        email=None, api_token=None, username=None, password=None,
                        verify=True):

    url = jira_base.rstrip("/") + "/rest/api/3/issue"
    auth = HTTPBasicAuth(email, api_token) if auth_method == "api_token" else HTTPBasicAuth(username, password)

    payload = {
        "fields": {
            "project": {"key": project_key},
            "parent": {"key": parent_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type}
        }
    }

    resp = requests.post(url, auth=auth,
                         headers={"Content-Type": "application/json"},
                         json=payload, verify=verify)

    resp.raise_for_status()
    return resp.json()


# =====================================================================
# CLAUDE 3.5 SONNET TESTCASE GENERATION (MUST USE PROFILE ARN)
# =====================================================================
PROMPT_TEMPLATE = (
    "You are a senior QA engineer. Generate a JSON array of test cases. "
    "Each object MUST contain: id, title, priority, type, preconditions, steps, expected_result.\n\n"
    "SUMMARY:\n{summary}\n\nDESCRIPTION:\n{description}\n\nLABELS:\n{labels}\n\nCOMMENTS:\n{comments}\n\n"
    "Return ONLY a valid JSON array."
)


def generate_testcases(runtime, profile_arn, summary, description, labels, comments, max_tokens):

    prompt = PROMPT_TEMPLATE.format(
        summary=summary,
        description=description,
        labels=", ".join(labels),
        comments="\n".join(comments)
    )

    request_body = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }

    try:
        resp = runtime.invoke_model(
            modelId=profile_arn,     # <-- Using inference profile ARN
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body)
        )
    except Exception as e:
        raise RuntimeError(f"Bedrock invoke error: {e}")

    raw = resp["body"].read().decode("utf-8")
    data = json.loads(raw)

    assistant_msg = data["output"]["message"]["content"][0]["text"]

    # Extract JSON array safely
    start = assistant_msg.find("[")
    end = assistant_msg.rfind("]")

    try:
        return json.loads(assistant_msg[start:end+1])
    except:
        return [{
            "id": "ERR",
            "title": "Parse Error",
            "priority": "Medium",
            "type": "Functional",
            "preconditions": "",
            "steps": [assistant_msg],
            "expected_result": ""
        }]


# =====================================================================
# UI — FETCH JIRA ISSUE
# =====================================================================
st.write("---")
st.subheader("Step 1 — Fetch Jira Issue")

left, right = st.columns([2,1])
with left:
    issue_key = st.text_input("Jira Issue Key (e.g., PROJ-101)")

with right:
    if st.button("Fetch Jira Issue"):
        try:
            issue = fetch_jira_issue(
                jira_base, issue_key,
                jira_auth_method,
                email=jira_email, api_token=jira_api_token,
                username=jira_username, password=jira_password,
                verify=jira_verify
            )
            st.session_state["issue"] = issue
            st.success("Issue fetched successfully!")
        except Exception as e:
            st.error(str(e))


# =====================================================================
# ISSUE PREVIEW + PROFILE SELECTION
# =====================================================================
if "issue" in st.session_state:

    fields = st.session_state["issue"].get("fields", {})

    st.write("---")
    st.subheader("Step 2 — Jira Issue Preview")

    st.write(f"### {issue_key}: {fields.get('summary','')}")
    st.write(fields.get("description", ""))

    labels = fields.get("labels", [])
    comments = [c["body"] for c in (fields.get("comment") or {}).get("comments", [])]

    st.write("Labels:", ", ".join(labels))

    mgmt, runtime = make_clients()

    st.write("---")
    st.subheader("Step 3 — Select Inference Profile for Claude 3.5")

    ok, profiles, msg = list_inference_profiles(mgmt)
    if not ok:
        st.error(msg)
        profiles = []

    profile_names = [f"{p['name']} — {p['arn']}" for p in profiles]
    profile_arns = [p["arn"] for p in profiles]

    chosen_profile = st.selectbox("Choose Inference Profile", ["-- Select --"] + profile_names)

    profile_arn = ""
    if chosen_profile != "-- Select --":
        idx = profile_names.index(chosen_profile)
        profile_arn = profile_arns[idx]
        st.info(f"Using profile ARN:\n`{profile_arn}`")


    # =================================================================
    # GENERATE TESTCASES
    # =================================================================
    st.write("---")
    st.subheader("Step 4 — Generate Testcases")

    max_tokens = st.number_input("Max Tokens", value=1500)

    if st.button("Generate with Claude 3.5 Sonnet"):
        if not profile_arn:
            st.error("Please select an inference profile.")
        else:
            try:
                tcs = generate_testcases(
                    runtime, profile_arn,
                    fields.get("summary",""),
                    fields.get("description",""),
                    labels,
                    comments,
                    max_tokens
                )
                st.session_state["testcases"] = tcs
                st.success(f"Generated {len(tcs)} testcases!")
            except Exception as e:
                st.error(str(e))


# =====================================================================
# TESTCASE EDITOR
# =====================================================================
if "testcases" in st.session_state:

    st.write("---")
    st.subheader("Step 5 — Review & Edit Testcases")

    def build_df(tcs):
        return pd.DataFrame([
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "priority": t.get("priority"),
                "type": t.get("type"),
                "preconditions": t.get("preconditions"),
                "steps": "\n".join(t.get("steps")) if isinstance(t.get("steps"), list) else "",
                "expected_result": t.get("expected_result")
            }
            for t in tcs
        ])

    df = build_df(st.session_state["testcases"])
    edited_df = st.experimental_data_editor(df, num_rows="dynamic")

    st.download_button(
        "Download CSV",
        edited_df.to_csv(index=False).encode("utf-8"),
        f"{issue_key}_testcases.csv",
        "text/csv"
    )


    # =================================================================
    # JIRA UPLOAD + SUBTASK CREATION
    # =================================================================
    st.write("---")
    st.subheader("Step 6 — Upload to Jira")

    colA, colB = st.columns(2)

    # Attach CSV
    with colA:
        if st.button("Attach CSV to Jira Issue"):
            try:
                csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
                resp = attach_file_to_issue(
                    jira_base, issue_key,
                    csv_bytes, f"{issue_key}_testcases.csv",
                    jira_auth_method,
                    email=jira_email, api_token=jira_api_token,
                    username=jira_username, password=jira_password,
                    verify=jira_verify
                )
                st.success("CSV attached successfully!")
                st.json(resp)
            except Exception as e:
                st.error(str(e))

    # Create subtasks
    with colB:
        project_key = st.text_input("Project Key (e.g. PROJ)")
        issue_type = st.selectbox("Subtask Issue Type", ["Sub-task", "Task", "Bug"])

        if st.button("Create Subtasks"):
            if not project_key:
                st.error("Enter project key.")
            else:
                created = []
                for _, row in edited_df.iterrows():
                    summary = f"TC-{row['id']}: {row['title'][:80]}"
                    description = (
                        f"*Preconditions:*\n{row['preconditions']}\n\n"
                        f"*Steps:*\n{row['steps']}\n\n"
                        f"*Expected:*\n{row['expected_result']}"
                    )

                    try:
                        res = create_jira_subtask(
                            jira_base,
                            issue_key,
                            summary,
                            description,
                            issue_type,
                            project_key,
                            jira_auth_method,
                            email=jira_email, api_token=jira_api_token,
                            username=jira_username, password=jira_password,
                            verify=jira_verify
                        )
                        created.append(res.get("key"))
                    except Exception as e:
                        st.error(str(e))

                if created:
                    st.success("Created subtasks: " + ", ".join(created))


# =====================================================================
# TROUBLESHOOTING FOOTER
# =====================================================================
st.write("---")
st.markdown("""
### Troubleshooting Notes

- **Claude 3.5 Sonnet cannot be invoked with a `modelId`.  
  You *must* use an Inference Profile ARN.  
  This script handles that automatically.**

- If inference profiles do not appear →  
  Ensure IAM permissions include:  
  `bedrock:ListInferenceProfiles`, `bedrock:InvokeModel`.

- TLS errors → use sidebar SSL options.

- Parse errors → model sometimes adds prose; script extracts JSON automatically.

- Use the STS button to verify AWS credentials.
""")
