"""
AI Testcase Generator Streamlit App
- Fetches Jira issue by issue key (user inputs Jira base url + email + API token OR username+password)
- Sends description/summary/labels/comments to Amazon Bedrock to generate structured test cases
- Displays editable test cases in UI
- Allows export to CSV
- After review, uploads CSV in Jira and/or creates sub-tasks for each test case

Pre-requisites:
- Python 3.9+
- pip install streamlit boto3 requests pandas python-dotenv
- Set AWS credentials (aws_access_key_id, aws_secret_access_key, aws_session_token) via environment variables OR paste in UI

Notes:
- Jira Cloud (yourdomain.atlassian.net) requires Email + API Token. Username+password works only for Jira Server/Data Center (on-prem), if basic auth is enabled.
"""

import streamlit as st
import boto3
import json
import requests
import pandas as pd
import os
from typing import List, Dict, Any

# ---------- Helper: Bedrock client ----------
def make_bedrock_client(aws_region: str, aws_access_key_id: str = None,
                        aws_secret_access_key: str = None, aws_session_token: str = None):
    # Allow passing creds explicitly or rely on environment/AWS config
    session_kwargs = {}
    if aws_access_key_id and aws_secret_access_key:
        session_kwargs.update({
            'aws_access_key_id': aws_access_key_id,
            'aws_secret_access_key': aws_secret_access_key,
        })
    if aws_session_token:
        session_kwargs['aws_session_token'] = aws_session_token

    session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()
    return session.client('bedrock-runtime', region_name=aws_region)

# ---------- Generate testcases via Bedrock ----------
PROMPT_TEMPLATE = (
    "You are a software QA engineer. Given the Jira issue details below, generate a list of test cases "
    "as a JSON array. Each test case must include: id, title, priority (Low/Medium/High), type (Functional/Regression/Smoke), preconditions, "
    "steps (array of step descriptions), expected_result. Keep output strictly as JSON.\n\n"
    "JIRA SUMMARY:\n{summary}\n\nJIRA DESCRIPTION:\n{description}\n\nLABELS:\n{labels}\n\nCOMMENTS:\n{comments}\n\nRespond only with the JSON array of test cases."
)


def generate_testcases_bedrock(bedrock_client, model_id: str, summary: str, description: str,
                               labels: List[str], comments: List[str], max_tokens: int = 1500) -> List[Dict[str, Any]]:
    # Build prompt
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

    resp = bedrock_client.invoke_model(
        modelId=model_id,
        contentType='application/json',
        accept='application/json',
        body=body
    )

    # Decode response body
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
    if start != -1 and end != -1 and end > start:
        json_text = text[start:end+1]
    else:
        json_text = text

    try:
        testcases = json.loads(json_text)
    except Exception:
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

# ---------- Jira helpers (supports API token and password) ----------
from requests.auth import HTTPBasicAuth

def fetch_jira_issue(jira_base: str, issue_key: str, auth_method: str = 'api_token', email: str = None, api_token: str = None, username: str = None, password: str = None):
    """
    Fetch a Jira issue supporting two auth methods:
    - auth_method='api_token': use HTTPBasicAuth(email, api_token) (Jira Cloud)
    - auth_method='password': use HTTPBasicAuth(username, password) (Jira Server/Data Center)
    Raises RuntimeError with Jira's response body on non-200 responses for easier debugging.
    """
    url = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment'
    headers = {'Accept': 'application/json'}

    # Choose credentials based on selected method
    auth = None
    if auth_method == 'api_token':
        if not (email and api_token):
            raise RuntimeError('Missing email or API token for API token authentication.')
        auth = HTTPBasicAuth(email, api_token)
    elif auth_method == 'password':
        if not (username and password):
            raise RuntimeError('Missing username or password for password authentication.')
        auth = HTTPBasicAuth(username, password)
    else:
        raise RuntimeError(f'Unknown auth method: {auth_method}')

    try:
        resp = requests.get(url, auth=auth, headers=headers, timeout=15)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Network error when connecting to Jira: {e}')

    if resp.status_code == 200:
        return resp.json()
    else:
        body_text = resp.text
        raise RuntimeError(f'Error fetching issue: HTTP {resp.status_code} - {body_text}')


def create_jira_subtask(jira_base: str, parent_key: str, summary: str, description: str, issue_type: str, project_key: str, auth_method: str, email: str = None, api_token: str = None, username: str = None, password: str = None):
    api = jira_base.rstrip('/') + '/rest/api/3/issue'
    # choose auth
    if auth_method == 'api_token':
        auth = HTTPBasicAuth(email, api_token)
    else:
        auth = HTTPBasicAuth(username, password)

    payload = {
        'fields': {
            'project': {'key': project_key},
            'parent': {'key': parent_key},
            'summary': summary,
            'description': description,
            'issuetype': {'name': issue_type}
        }
    }
    resp = requests.post(api, auth=auth, headers={'Content-Type': 'application/json'}, json=payload)
    resp.raise_for_status()
    return resp.json()


def attach_file_to_issue(jira_base: str, issue_key: str, file_bytes: bytes, filename: str, auth_method: str, email: str = None, api_token: str = None, username: str = None, password: str = None):
    api = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}/attachments'
    headers = {'X-Atlassian-Token': 'no-check'}
    if auth_method == 'api_token':
        auth = HTTPBasicAuth(email, api_token)
    else:
        auth = HTTPBasicAuth(username, password)
    files = {'file': (filename, file_bytes)}
    resp = requests.post(api, auth=auth, headers=headers, files=files)
    resp.raise_for_status()
    return resp.json()

# ---------- Streamlit UI ----------

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

st.set_page_config(layout='wide', page_title='AI Testcase Generator')
st.title('AI Testcase Generator (AWS Bedrock + Jira)')

st.sidebar.header('Connection settings')
aws_region = st.sidebar.text_input('AWS Region', value='us-east-1')
aws_access_key_id = st.sidebar.text_input('AWS Access Key ID', value=os.getenv('AWS_ACCESS_KEY_ID') or '', type='password')
aws_secret_access_key = st.sidebar.text_input('AWS Secret Access Key', value=os.getenv('AWS_SECRET_ACCESS_KEY') or '', type='password')
aws_session_token = st.sidebar.text_input('AWS Session Token (optional)', value=os.getenv('AWS_SESSION_TOKEN') or '', type='password')
model_id = st.sidebar.text_input('Bedrock Model ID', value='anthropic.claude-2', help='Use a model id available in your region (e.g. "anthropic.claude-2")')

st.sidebar.write('---')
st.sidebar.header('Jira Settings')
jira_base = st.sidebar.text_input('Jira Base URL (e.g. https://yourdomain.atlassian.net)')

# Auth method selection
jira_auth_method = st.sidebar.radio('Jira Auth Method', options=['api_token', 'password'], index=0, format_func=lambda x: 'Email + API Token (Cloud)' if x=='api_token' else 'Username + Password (Server)')

# API token fields
jira_email = st.sidebar.text_input('Jira Email (for API token auth)')
jira_api_token = st.sidebar.text_input('Jira API Token', type='password')

# Password fields
jira_username = st.sidebar.text_input('Jira Username (for password auth)')
jira_password = st.sidebar.text_input('Jira Password', type='password')

st.markdown('Enter a Jira issue key below, press Fetch to load details. Then click Generate to create test cases.')

col1, col2 = st.columns([2, 1])
with col1:
    issue_key = st.text_input('Jira Issue Key (e.g. PROJ-123)')
with col2:
    if st.button('Fetch Jira Issue'):
        # Validate inputs based on selected auth method
        if not issue_key or not jira_base:
            st.error('Provide Jira base URL and issue key in the sidebar or fields.')
        else:
            try:
                auth_method = jira_auth_method
                if auth_method == 'api_token':
                    if not jira_email or not jira_api_token:
                        st.error('Provide Jira Email and API Token for API token authentication.')
                    else:
                        issue = fetch_jira_issue(jira_base, issue_key, auth_method='api_token', email=jira_email, api_token=jira_api_token)
                        st.session_state['issue'] = issue
                        st.success('Fetched issue ' + issue_key)
                else:
                    if not jira_username or not jira_password:
                        st.error('Provide Jira username and password for password authentication.')
                    else:
                        issue = fetch_jira_issue(jira_base, issue_key, auth_method='password', username=jira_username, password=jira_password)
                        st.session_state['issue'] = issue
                        st.success('Fetched issue ' + issue_key)
            except Exception as e:
                st.error('Error fetching issue: ' + str(e))

# Optional: test credentials button
st.sidebar.write('---')
if st.sidebar.button('Test Jira Credentials'):
    try:
        if jira_auth_method == 'api_token':
            if not jira_email or not jira_api_token:
                st.sidebar.error('Provide email and API token')
            else:
                # call a lightweight endpoint: my permissions
                url = jira_base.rstrip('/') + '/rest/api/3/myself'
                resp = requests.get(url, auth=HTTPBasicAuth(jira_email, jira_api_token), headers={'Accept': 'application/json'}, timeout=10)
                if resp.status_code == 200:
                    st.sidebar.success('API token credentials valid')
                else:
                    st.sidebar.error(f'Auth test failed: {resp.status_code} - {resp.text}')
        else:
            if not jira_username or not jira_password:
                st.sidebar.error('Provide username and password')
            else:
                url = jira_base.rstrip('/') + '/rest/api/3/myself'
                resp = requests.get(url, auth=HTTPBasicAuth(jira_username, jira_password), headers={'Accept': 'application/json'}, timeout=10)
                if resp.status_code == 200:
                    st.sidebar.success('Username/password valid')
                else:
                    st.sidebar.error(f'Auth test failed: {resp.status_code} - {resp.text}')
    except Exception as e:
        st.sidebar.error('Network or other error: ' + str(e))

if 'issue' in st.session_state:
    issue = st.session_state['issue']
    fields = issue.get('fields', {})
    st.subheader('Jira Issue Preview')
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

    st.subheader('Generate Testcases')
    gen_cols = st.columns(3)
    with gen_cols[0]:
        override_model = st.text_input('Model ID (override)', value=model_id)
    with gen_cols[1]:
        max_tokens = st.number_input('Max tokens', value=1500)
    with gen_cols[2]:
        if st.button('Generate Testcases'):
            try:
                bclient = make_bedrock_client(aws_region, aws_access_key_id or None, aws_secret_access_key or None, aws_session_token or None)
            except Exception as e:
                st.error('Error creating Bedrock client: ' + str(e))
                bclient = None

            if bclient:
                summary = fields.get('summary') or ''
                description = fields.get('description') or ''
                labels = fields.get('labels') or []
                comments = [c.get('body') for c in (fields.get('comment') or {}).get('comments', [])]

                with st.spinner('Generating...'):
                    try:
                        tcs = generate_testcases_bedrock(bclient, override_model or model_id, summary, description, labels, comments, max_tokens=max_tokens)
                        st.session_state['testcases'] = tcs
                        st.success(f'Generated {len(tcs)} testcases')
                    except Exception as e:
                        st.error('Generation error: ' + str(e))

if 'testcases' in st.session_state:
    st.subheader('Review & Edit Testcases')
    df = tc_list_to_df(st.session_state['testcases'])

    edited_df = st.experimental_data_editor(df, num_rows='dynamic')

    st.download_button('Download CSV', edited_df.to_csv(index=False).encode('utf-8'), file_name=f'{issue_key}_testcases.csv', mime='text/csv')

    st.write('---')
    st.subheader('Upload to Jira')
    st.write('You can either attach the CSV to the issue or create subtasks (one per testcase).')

    col_attach, col_subtask = st.columns(2)
    with col_attach:
        if st.button('Attach CSV to Jira Issue'):
            if not jira_base:
                st.error('Enter Jira base URL in sidebar')
            else:
                csv_bytes = edited_df.to_csv(index=False).encode('utf-8')
                try:
                    res = attach_file_to_issue(jira_base, issue_key, csv_bytes, f'{issue_key}_testcases.csv', jira_auth_method, email=jira_email, api_token=jira_api_token, username=jira_username, password=jira_password)
                    st.success('CSV attached to issue')
                    st.write(res)
                except Exception as e:
                    st.error('Attachment failed: ' + str(e))

    with col_subtask:
        project_key = st.text_input('Project Key for Sub-tasks (e.g. PROJ)')
        issue_type = st.selectbox('Sub-task Issue Type Name', options=['Sub-task', 'Task', 'Bug'])
        if st.button('Create Sub-tasks for Each Testcase'):
            if not (jira_base and project_key):
                st.error('Provide Jira base URL and project key')
            else:
                created = []
                for _, row in edited_df.iterrows():
                    summ = f"TC - {row['id']} - {row['title'][:80]}"
                    desc = f"Preconditions:\n{row['preconditions']}\n\nSteps:\n{row['steps']}\n\nExpected:\n{row['expected_result']}"
                    try:
                        res = create_jira_subtask(jira_base, issue_key, summ, desc, issue_type, project_key, jira_auth_method, email=jira_email, api_token=jira_api_token, username=jira_username, password=jira_password)
                        created.append(res.get('key'))
                    except Exception as e:
                        st.error('Failed creating subtask: ' + str(e))
                if created:
                    st.success('Created sub-tasks: ' + ', '.join(created))

st.markdown('\n---\n**Notes & Tips:**')
st.markdown('- Tune the prompt template in the source to change how the model formats testcases.\n- Validate generated testcases carefully: LLMs may hallucinate details or miss edge cases.\n- For production, use prompt management, logging, and human-in-the-loop review.')
