"""
AI Testcase Generator (Insecure TLS: verify=False)

WARNING:
  This app disables TLS certificate verification (verify=False) for all network calls.
  THIS IS INSECURE and should only be used for local/dev debugging when you trust the
  network and understand the risk. Do NOT use in production.

Features:
- Fetch Jira issue by key (supports Email+API Token for Cloud or Username+Password for Server)
- Call AWS Bedrock via boto3 to generate testcases (invoke_model)
- Show editable testcases, download CSV, attach CSV to Jira, create subtasks
- All network calls use verify=False
"""

import streamlit as st
import boto3
from botocore.config import Config
import botocore
import json
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import os
from typing import List, Dict, Any
import urllib3

# Disable warnings about insecure requests (since we're forcing verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Streamlit page config ---
st.set_page_config(layout='wide', page_title='AI Testcase Generator (verify=False)')
st.title('AI Testcase Generator — INSECURE TLS: verify=False')
st.markdown(
    """
    **Security warning:** This app sets `verify=False` for all HTTPS calls (Jira & AWS Bedrock).
    Use only for local testing. Do not run this against production or public networks.
    """
)
st.warning('TLS verification is DISABLED (verify=False). This is insecure.')

# ---------- Helper: Bedrock client (verify=False) ----------
def make_bedrock_client_insecure(aws_region: str,
                                 aws_access_key_id: str = None,
                                 aws_secret_access_key: str = None,
                                 aws_session_token: str = None):
    """
    Create a boto3 Bedrock client with verify=False.
    """
    session_kwargs = {}
    if aws_access_key_id and aws_secret_access_key:
        session_kwargs.update({
            'aws_access_key_id': aws_access_key_id,
            'aws_secret_access_key': aws_secret_access_key,
        })
    if aws_session_token:
        session_kwargs['aws_session_token'] = aws_session_token

    session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()
    cfg = Config(retries={'max_attempts': 3, 'mode': 'standard'})

    try:
        # Pass verify=False here to botocore (insecure)
        client = session.client('bedrock-runtime', region_name=aws_region, config=cfg, verify=False)
        return client
    except botocore.exceptions.SSLError as e:
        raise RuntimeError(f'Bedrock SSL error (insecure mode attempted): {e}')
    except Exception as e:
        raise RuntimeError(f'Error creating Bedrock client: {e}')


# ---------- Prompt & generator ----------
PROMPT_TEMPLATE = (
    "You are a software QA engineer. Given the Jira issue details below, generate a list of test cases "
    "as a JSON array. Each test case must include: id, title, priority (Low/Medium/High), type (Functional/Regression/Smoke), preconditions, "
    "steps (array of step descriptions), expected_result. Keep output strictly as JSON.\n\n"
    "JIRA SUMMARY:\n{summary}\n\nJIRA DESCRIPTION:\n{description}\n\nLABELS:\n{labels}\n\nCOMMENTS:\n{comments}\n\nRespond only with the JSON array of test cases."
)


def generate_testcases_bedrock_insecure(bedrock_client, model_id: str, summary: str, description: str,
                                        labels: List[str], comments: List[str], max_tokens: int = 1500) -> List[Dict[str, Any]]:
    prompt = PROMPT_TEMPLATE.format(
        summary=summary or "",
        description=description or "",
        labels=", ".join(labels) if labels else "",
        comments="\n".join(comments) if comments else ""
    )

    body = json.dumps({
        'prompt': prompt,
        'max_tokens_to_sample': max_tokens
    })

    try:
        resp = bedrock_client.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=body
        )
    except botocore.exceptions.SSLError as e:
        raise RuntimeError(f'Bedrock SSL error during invoke_model: {e}')
    except botocore.exceptions.ClientError as e:
        raise RuntimeError(f'Bedrock client error: {e}')
    except Exception as e:
        raise RuntimeError(f'Unexpected error calling Bedrock: {e}')

    # decode streaming body
    if isinstance(resp.get('body'), (bytes, bytearray)):
        text = resp['body'].decode('utf-8')
    else:
        try:
            text = resp['body'].read().decode('utf-8')
        except Exception:
            text = str(resp.get('body'))

    text = text.strip()
    start = text.find('[')
    end = text.rfind(']')
    json_text = text[start:end+1] if (start != -1 and end != -1 and end > start) else text

    try:
        testcases = json.loads(json_text)
    except Exception:
        # fallback single item with raw output
        testcases = [{
            'id': 'GEN-ERR-1',
            'title': 'Model output parse error',
            'priority': 'Medium',
            'type': 'Manual',
            'preconditions': '',
            'steps': [text],
            'expected_result': ''
        }]

    normalized = []
    for i, tc in enumerate(testcases, start=1):
        normalized.append({
            'id': tc.get('id') or f'G-{i}',
            'title': tc.get('title') or tc.get('name') or (tc.get('summary')[:80] if tc.get('summary') else 'Untitled'),
            'priority': tc.get('priority') or 'Medium',
            'type': tc.get('type') or 'Functional',
            'preconditions': tc.get('preconditions') or tc.get('precondition') or '',
            'steps': tc.get('steps') or tc.get('steps_list') or ([] if not tc.get('steps') else tc.get('steps')),
            'expected_result': tc.get('expected_result') or tc.get('expected') or ''
        })
    return normalized


# ---------- Jira helpers (all requests use verify=False) ----------
def fetch_jira_issue_insecure(jira_base: str, issue_key: str, auth_method: str = 'api_token',
                              email: str = None, api_token: str = None, username: str = None, password: str = None):
    """
    Fetch a Jira issue using verify=False (insecure).
    """
    url = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment'
    headers = {'Accept': 'application/json'}
    auth = None
    if auth_method == 'api_token':
        if not (email and api_token):
            raise RuntimeError('Missing email or API token.')
        auth = HTTPBasicAuth(email, api_token)
    elif auth_method == 'password':
        if not (username and password):
            raise RuntimeError('Missing username or password.')
        auth = HTTPBasicAuth(username, password)
    else:
        raise RuntimeError(f'Unknown auth method: {auth_method}')

    try:
        resp = requests.get(url, auth=auth, headers=headers, timeout=20, verify=False)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Network error when connecting to Jira (insecure): {e}')

    if resp.status_code == 200:
        return resp.json()
    else:
        raise RuntimeError(f'Error fetching issue: HTTP {resp.status_code} - {resp.text}')


def attach_file_to_issue_insecure(jira_base: str, issue_key: str, file_bytes: bytes, filename: str,
                                  auth_method: str, email: str = None, api_token: str = None,
                                  username: str = None, password: str = None):
    api = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}/attachments'
    headers = {'X-Atlassian-Token': 'no-check'}
    auth = HTTPBasicAuth(email, api_token) if auth_method == 'api_token' else HTTPBasicAuth(username, password)
    files = {'file': (filename, file_bytes)}
    try:
        resp = requests.post(api, auth=auth, headers=headers, files=files, verify=False)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Attachment failed (insecure): {e}')


def create_jira_subtask_insecure(jira_base: str, parent_key: str, summary: str, description: str,
                                 issue_type: str, project_key: str, auth_method: str,
                                 email: str = None, api_token: str = None, username: str = None, password: str = None):
    api = jira_base.rstrip('/') + '/rest/api/3/issue'
    auth = HTTPBasicAuth(email, api_token) if auth_method == 'api_token' else HTTPBasicAuth(username, password)
    payload = {
        'fields': {
            'project': {'key': project_key},
            'parent': {'key': parent_key},
            'summary': summary,
            'description': description,
            'issuetype': {'name': issue_type}
        }
    }
    try:
        resp = requests.post(api, auth=auth, headers={'Content-Type': 'application/json'}, json=payload, verify=False)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Subtask creation failed (insecure): {e}')


# ---------- Utility to transform testcases to DataFrame ----------
def tc_list_to_df(tcs: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for tc in tcs:
        rows.append({
            'id': tc.get('id'),
            'title': tc.get('title'),
            'priority': tc.get('priority'),
            'type': tc.get('type'),
            'preconditions': tc.get('preconditions'),
            'steps': '\n'.join(tc.get('steps')) if isinstance(tc.get('steps'), list) else str(tc.get('steps')),
            'expected_result': tc.get('expected_result')
        })
    return pd.DataFrame(rows)


# ---------- Sidebar: Credentials & settings ----------
st.sidebar.header('AWS Bedrock (insecure TLS)')
aws_region = st.sidebar.text_input('AWS Region', value='us-east-1')
aws_access_key_id = st.sidebar.text_input('AWS Access Key ID', type='password')
aws_secret_access_key = st.sidebar.text_input('AWS Secret Access Key', type='password')
aws_session_token = st.sidebar.text_input('AWS Session Token (optional)', type='password')
bedrock_model_id = st.sidebar.text_input('Bedrock Model ID', value='anthropic.claude-2')

st.sidebar.write('---')
st.sidebar.header('Jira Settings (insecure TLS)')
jira_base = st.sidebar.text_input('Jira Base URL (e.g. https://yourdomain.atlassian.net)')
jira_auth_method = st.sidebar.radio('Jira Auth Method', options=['api_token', 'password'],
                                    format_func=lambda x: 'Email + API Token (Cloud)' if x == 'api_token' else 'Username + Password (Server)')
# API token fields
jira_email = st.sidebar.text_input('Jira Email (for API token auth)')
jira_api_token = st.sidebar.text_input('Jira API Token', type='password')
# Password fields
jira_username = st.sidebar.text_input('Jira Username (for password auth)')
jira_password = st.sidebar.text_input('Jira Password', type='password')

# Credential test (insecure)
if st.sidebar.button('Test Jira Credentials (insecure)'):
    try:
        if jira_auth_method == 'api_token':
            if not jira_email or not jira_api_token:
                st.sidebar.error('Provide email and API token')
            else:
                url = jira_base.rstrip('/') + '/rest/api/3/myself'
                resp = requests.get(url, auth=HTTPBasicAuth(jira_email, jira_api_token),
                                    headers={'Accept': 'application/json'}, timeout=10, verify=False)
                if resp.status_code == 200:
                    st.sidebar.success('API token credentials valid (insecure)')
                else:
                    st.sidebar.error(f'Auth test failed: {resp.status_code} - {resp.text}')
        else:
            if not jira_username or not jira_password:
                st.sidebar.error('Provide username and password')
            else:
                url = jira_base.rstrip('/') + '/rest/api/3/myself'
                resp = requests.get(url, auth=HTTPBasicAuth(jira_username, jira_password),
                                    headers={'Accept': 'application/json'}, timeout=10, verify=False)
                if resp.status_code == 200:
                    st.sidebar.success('Username/password valid (insecure)')
                else:
                    st.sidebar.error(f'Auth test failed: {resp.status_code} - {resp.text}')
    except Exception as e:
        st.sidebar.error('Network or other error (insecure): ' + str(e))


# ---------- Main UI: Fetch / Generate / Review ----------
st.markdown('Enter a Jira issue key, fetch the issue, generate testcases (Bedrock), review and upload.')

col1, col2 = st.columns([2, 1])
with col1:
    issue_key = st.text_input('Jira Issue Key (e.g. PROJ-123)')
with col2:
    if st.button('Fetch Jira Issue (insecure)'):
        if not issue_key or not jira_base:
            st.error('Provide Jira base URL and issue key.')
        else:
            try:
                issue = fetch_jira_issue_insecure(jira_base, issue_key,
                                                  auth_method=jira_auth_method,
                                                  email=jira_email, api_token=jira_api_token,
                                                  username=jira_username, password=jira_password)
                st.session_state['issue'] = issue
                st.success('Fetched issue ' + issue_key)
            except Exception as e:
                st.error('Error fetching issue (insecure): ' + str(e))

if 'issue' in st.session_state:
    issue = st.session_state['issue']
    fields = issue.get('fields', {})
    st.subheader('Jira Issue Preview (insecure)')
    st.markdown(f"**{issue_key} - {fields.get('summary')}**")
    st.markdown('**Description:**')
    st.write(fields.get('description') or '')
    st.markdown('**Labels:** ' + ', '.join(fields.get('labels') or []))
    comments = [c.get('body') for c in (fields.get('comment') or {}).get('comments', [])]
    if comments:
        st.markdown('**Recent comments:**')
        for c in comments[:5]:
            st.write('- ' + (c[:100] + '...' if len(c) > 120 else c))

    st.write('---')

    st.subheader('Generate Testcases (invoke Bedrock, insecure TLS)')
    gen_cols = st.columns(3)
    with gen_cols[0]:
        override_model = st.text_input('Model ID (override)', value=bedrock_model_id)
    with gen_cols[1]:
        max_tokens = st.number_input('Max tokens', value=1500)
    with gen_cols[2]:
        if st.button('Generate Testcases (insecure)'):
            # create bedrock client with verify=False
            try:
                bclient = make_bedrock_client_insecure(aws_region,
                                                       aws_access_key_id or None,
                                                       aws_secret_access_key or None,
                                                       aws_session_token or None)
            except Exception as e:
                st.error('Error creating Bedrock client (insecure): ' + str(e))
                bclient = None

            if bclient:
                summary = fields.get('summary') or ''
                description = fields.get('description') or ''
                labels = fields.get('labels') or []
                comments = [c.get('body') for c in (fields.get('comment') or {}).get('comments', [])]

                with st.spinner('Generating...'):
                    try:
                        tcs = generate_testcases_bedrock_insecure(bclient, override_model or bedrock_model_id,
                                                                  summary, description, labels, comments, max_tokens=max_tokens)
                        st.session_state['testcases'] = tcs
                        st.success(f'Generated {len(tcs)} testcases (insecure)')
                    except Exception as e:
                        st.error('Generation error (insecure): ' + str(e))

if 'testcases' in st.session_state:
    st.subheader('Review & Edit Testcases (insecure)')
    df = tc_list_to_df(st.session_state['testcases'])
    edited_df = st.experimental_data_editor(df, num_rows='dynamic')
    st.download_button('Download CSV', edited_df.to_csv(index=False).encode('utf-8'),
                       file_name=f'{issue_key}_testcases.csv', mime='text/csv')

    st.write('---')
    st.subheader('Upload to Jira (insecure)')
    col_attach, col_subtask = st.columns(2)
    with col_attach:
        if st.button('Attach CSV to Jira Issue (insecure)'):
            if not jira_base:
                st.error('Enter Jira base URL in sidebar')
            else:
                csv_bytes = edited_df.to_csv(index=False).encode('utf-8')
                try:
                    res = attach_file_to_issue_insecure(jira_base, issue_key, csv_bytes, f'{issue_key}_testcases.csv',
                                                        jira_auth_method, email=jira_email, api_token=jira_api_token,
                                                        username=jira_username, password=jira_password)
                    st.success('CSV attached to issue (insecure)')
                    st.write(res)
                except Exception as e:
                    st.error('Attachment failed (insecure): ' + str(e))

    with col_subtask:
        project_key = st.text_input('Project Key for Sub-tasks (e.g. PROJ)')
        issue_type = st.selectbox('Sub-task Issue Type Name', options=['Sub-task', 'Task', 'Bug'])
        if st.button('Create Sub-tasks for Each Testcase (insecure)'):
            if not (jira_base and project_key):
                st.error('Provide Jira base URL and project key')
            else:
                created = []
                for _, row in edited_df.iterrows():
                    summ = f"TC - {row['id']} - {row['title'][:80]}"
                    desc = f"Preconditions:\n{row['preconditions']}\n\nSteps:\n{row['steps']}\n\nExpected:\n{row['expected_result']}"
                    try:
                        res = create_jira_subtask_insecure(jira_base, issue_key, summ, desc, issue_type, project_key,
                                                           jira_auth_method, email=jira_email, api_token=jira_api_token,
                                                           username=jira_username, password=jira_password)
                        created.append(res.get('key'))
                    except Exception as e:
                        st.error('Failed creating subtask (insecure): ' + str(e))
                if created:
                    st.success('Created sub-tasks (insecure): ' + ', '.join(created))

st.markdown('\n---\n**Notes:**\n- This app uses verify=False for all HTTPS connections. Use only for testing.\n- For production, restore TLS verification and use a CA bundle or system trusts for corporate certs.')