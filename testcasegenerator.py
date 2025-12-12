# ai_testcase_generator_full.py
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

# --- Page config ---
st.set_page_config(layout='wide', page_title='AI Testcase Generator (Bedrock + Jira)')
st.title('AI Testcase Generator (AWS Bedrock + Jira)')

# ---------- Helper: TLS / verify helpers ----------
def build_verify_from_sidebar(prefix: str):
    """
    Create a verify value (True | False | path-to-pem) based on sidebar controls.
    prefix is 'bedrock' or 'jira' to differentiate labels.
    Returns (verify_value, display_message)
    """
    st.sidebar.write('---')
    st.sidebar.markdown(f'**{prefix.capitalize()} TLS options**')
    disable = st.sidebar.checkbox(f'Disable {prefix} SSL verification (insecure)', value=False, key=f'{prefix}_disable')
    upload = st.sidebar.file_uploader(f'Upload {prefix} CA certificate (.pem) (optional)', type=['pem', 'crt'], key=f'{prefix}_ca')
    ca_path = None
    if upload is not None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pem')
        tmp.write(upload.read())
        tmp.flush()
        tmp.close()
        ca_path = tmp.name
        st.sidebar.success(f'Uploaded {prefix} CA certificate will be used for TLS verification.')
    if disable:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return False, f'{prefix}: verification DISABLED (insecure)'
    elif ca_path:
        return ca_path, f'{prefix}: using uploaded CA bundle {ca_path}'
    else:
        # use system default; allow AWS_CA_BUNDLE env var for bedrock
        if prefix == 'bedrock' and os.getenv('AWS_CA_BUNDLE'):
            return os.getenv('AWS_CA_BUNDLE'), f'{prefix}: using AWS_CA_BUNDLE={os.getenv("AWS_CA_BUNDLE")}'
        return True, f'{prefix}: using system trust store'

# We'll show bedrock/jira TLS options side-by-side in the sidebar for clarity
st.sidebar.header('Connection & TLS settings')
bedrock_verify, bedrock_verify_msg = build_verify_from_sidebar('bedrock')
jira_verify, jira_verify_msg = build_verify_from_sidebar('jira')

st.sidebar.markdown(f"*Bedrock TLS:* {bedrock_verify_msg}")
st.sidebar.markdown(f"*Jira TLS:* {jira_verify_msg}")

# ---------- AWS / Bedrock inputs ----------
st.sidebar.write('---')
st.sidebar.header('AWS Bedrock credentials')
aws_region = st.sidebar.text_input('AWS Region', value='us-east-1')
aws_access_key_id = st.sidebar.text_input('AWS Access Key ID', value=os.getenv('AWS_ACCESS_KEY_ID') or '')
aws_secret_access_key = st.sidebar.text_input('AWS Secret Access Key', value=os.getenv('AWS_SECRET_ACCESS_KEY') or '', type='password')
aws_session_token = st.sidebar.text_input('AWS Session Token (optional)', value=os.getenv('AWS_SESSION_TOKEN') or '', type='password')
bedrock_model_id = st.sidebar.text_input('Bedrock Model ID', value='anthropic.claude-2')

# ---------- Jira inputs ----------
st.sidebar.write('---')
st.sidebar.header('Jira credentials')
jira_base = st.sidebar.text_input('Jira Base URL (e.g. https://yourdomain.atlassian.net)')
jira_auth_method = st.sidebar.radio('Jira Auth Method', options=['api_token', 'password'],
                                    format_func=lambda x: 'Email + API Token (Cloud)' if x == 'api_token' else 'Username + Password (Server)')
jira_email = st.sidebar.text_input('Jira Email (for API token auth)')
jira_api_token = st.sidebar.text_input('Jira API Token', type='password')
jira_username = st.sidebar.text_input('Jira Username (for password auth)')
jira_password = st.sidebar.text_input('Jira Password', type='password')

# ---------- Utility: STS test for AWS creds ----------
def test_aws_credentials(region, access_key, secret_key, session_token, verify=True):
    """
    Return (ok:bool, message:str, details:dict|None)
    """
    session_kwargs = {}
    if access_key and secret_key:
        session_kwargs['aws_access_key_id'] = access_key
        session_kwargs['aws_secret_access_key'] = secret_key
    if session_token:
        session_kwargs['aws_session_token'] = session_token

    try:
        session = boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()
        # STS client - use provided region (some endpoints require region)
        sts = session.client('sts', region_name=region, verify=verify)
        resp = sts.get_caller_identity()
        return True, 'STS success (caller identity returned)', resp
    except botocore.exceptions.ClientError as e:
        err = e.response.get('Error', {})
        return False, f"AWS ClientError: {err.get('Code')}: {err.get('Message')}", None
    except botocore.exceptions.NoRegionError as e:
        return False, f'NoRegionError: {e}', None
    except botocore.exceptions.SSLError as e:
        return False, f'SSLError: {e}', None
    except Exception as e:
        return False, f'Unexpected error: {e}', None

if st.sidebar.button('Test AWS Credentials / STS'):
    ok, msg, details = test_aws_credentials(aws_region, aws_access_key_id, aws_secret_access_key, aws_session_token, verify=bedrock_verify)
    if ok:
        st.sidebar.success(msg)
        st.sidebar.json(details)
    else:
        st.sidebar.error(msg)

# ---------- Bedrock client creation (honoring verify) ----------
def make_bedrock_client(aws_region: str,
                        aws_access_key_id: str = None,
                        aws_secret_access_key: str = None,
                        aws_session_token: str = None,
                        verify=True):
    """
    Create a Bedrock runtime client; verify can be True/False/path-to-pem.
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
        client = session.client('bedrock-runtime', region_name=aws_region, config=cfg, verify=verify)
        return client
    except botocore.exceptions.SSLError as e:
        raise RuntimeError(f'Bedrock SSL error when creating client: {e}')
    except botocore.exceptions.ClientError as e:
        # include AWS error code/message
        err = e.response.get('Error', {})
        raise RuntimeError(f'Bedrock ClientError: {err.get("Code")}: {err.get("Message")}')
    except Exception as e:
        raise RuntimeError(f'Error creating Bedrock client: {e}')

# ---------- Bedrock invocation wrapper ----------
PROMPT_TEMPLATE = (
    "You are a software QA engineer. Given the Jira issue details below, generate a list of test cases "
    "as a JSON array. Each test case must include: id, title, priority (Low/Medium/High), type (Functional/Regression/Smoke), preconditions, "
    "steps (array of step descriptions), expected_result. Keep output strictly as JSON.\n\n"
    "JIRA SUMMARY:\n{summary}\n\nJIRA DESCRIPTION:\n{description}\n\nLABELS:\n{labels}\n\nCOMMENTS:\n{comments}\n\nRespond only with the JSON array of test cases."
)

def generate_testcases_bedrock(bclient, model_id: str, summary: str, description: str,
                               labels: List[str], comments: List[str], max_tokens: int = 1500):
    body = json.dumps({'prompt': PROMPT_TEMPLATE.format(
        summary=summary or "",
        description=description or "",
        labels=", ".join(labels) if labels else "",
        comments="\n".join(comments) if comments else ""
    ), 'max_tokens_to_sample': max_tokens})

    try:
        resp = bclient.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=body
        )
    except botocore.exceptions.ClientError as e:
        err = e.response.get('Error', {})
        raise RuntimeError(f'Bedrock ClientError during invoke_model: {err.get("Code")}: {err.get("Message")}')
    except botocore.exceptions.SSLError as e:
        raise RuntimeError(f'Bedrock SSL error during invoke_model: {e}')
    except Exception as e:
        raise RuntimeError(f'Unexpected error calling Bedrock: {e}')

    # decode response body (boto3 may return StreamingBody)
    if isinstance(resp.get('body'), (bytes, bytearray)):
        text = resp['body'].decode('utf-8')
    else:
        try:
            text = resp['body'].read().decode('utf-8')
        except Exception:
            text = str(resp.get('body'))

    # extract first JSON array in output
    text = text.strip()
    start = text.find('[')
    end = text.rfind(']')
    json_text = text[start:end+1] if (start != -1 and end != -1 and end > start) else text

    try:
        testcases = json.loads(json_text)
    except Exception:
        # fallback: return single item containing raw output for inspection
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

# ---------- Jira helpers (supporting verify param) ----------
def fetch_jira_issue(jira_base: str, issue_key: str, auth_method: str = 'api_token',
                     email: str = None, api_token: str = None, username: str = None, password: str = None,
                     verify=True):
    url = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment'
    headers = {'Accept': 'application/json'}
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
        resp = requests.get(url, auth=auth, headers=headers, timeout=20, verify=verify)
    except requests.exceptions.SSLError as e:
        raise RuntimeError(f'SSL verification failed when contacting Jira: {e}')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Network error when connecting to Jira: {e}')

    if resp.status_code == 200:
        return resp.json()
    else:
        raise RuntimeError(f'Error fetching issue: HTTP {resp.status_code} - {resp.text}')

def attach_file_to_issue(jira_base: str, issue_key: str, file_bytes: bytes, filename: str,
                         auth_method: str, email: str = None, api_token: str = None, username: str = None, password: str = None,
                         verify=True):
    api = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}/attachments'
    headers = {'X-Atlassian-Token': 'no-check'}
    auth = HTTPBasicAuth(email, api_token) if auth_method == 'api_token' else HTTPBasicAuth(username, password)
    files = {'file': (filename, file_bytes)}
    try:
        resp = requests.post(api, auth=auth, headers=headers, files=files, verify=verify)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.SSLError as e:
        raise RuntimeError(f'SSL verification failed during attachment upload: {e}')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Attachment failed: {e}')

def create_jira_subtask(jira_base: str, parent_key: str, summary: str, description: str,
                        issue_type: str, project_key: str, auth_method: str,
                        email: str = None, api_token: str = None, username: str = None, password: str = None,
                        verify=True):
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
        resp = requests.post(api, auth=auth, headers={'Content-Type': 'application/json'}, json=payload, verify=verify)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.SSLError as e:
        raise RuntimeError(f'SSL verification failed during subtask creation: {e}')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Subtask creation failed: {e}')

# ---------- UI: Main flow ----------
st.markdown('Enter a Jira issue key, fetch the issue, generate testcases (Bedrock), review and upload.')

# Left: issue input / fetch
col1, col2 = st.columns([2, 1])
with col1:
    issue_key = st.text_input('Jira Issue Key (e.g. PROJ-123)')
with col2:
    if st.button('Fetch Jira Issue'):
        if not issue_key or not jira_base:
            st.error('Provide Jira base URL and issue key in the sidebar or fields.')
        else:
            try:
                issue = fetch_jira_issue(jira_base, issue_key, auth_method=jira_auth_method,
                                        email=jira_email, api_token=jira_api_token,
                                        username=jira_username, password=jira_password,
                                        verify=jira_verify)
                st.session_state['issue'] = issue
                st.success('Fetched issue ' + issue_key)
            except Exception as e:
                st.error('Error fetching issue: ' + str(e))

# If issue fetched, preview
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
            st.write('- ' + (c[:120] + '...' if len(c) > 120 else c))

    st.write('---')
    st.subheader('Generate Testcases')

    gen_cols = st.columns(3)
    with gen_cols[0]:
        override_model = st.text_input('Model ID (override)', value=bedrock_model_id)
    with gen_cols[1]:
        max_tokens = st.number_input('Max tokens', value=1500)
    with gen_cols[2]:
        if st.button('Generate Testcases'):
            # create bedrock client (honoring verify and aws_session_token)
            try:
                bclient = make_bedrock_client(aws_region,
                                              aws_access_key_id or None,
                                              aws_secret_access_key or None,
                                              aws_session_token or None,
                                              verify=bedrock_verify)
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
                        tcs = generate_testcases_bedrock(bclient, override_model or bedrock_model_id, summary, description, labels, comments, max_tokens=max_tokens)
                        st.session_state['testcases'] = tcs
                        st.success(f'Generated {len(tcs)} testcases')
                    except Exception as e:
                        # Most likely causes: invalid AWS token, wrong region, permissions, or SSL issues
                        st.error('Generation error: ' + str(e))

# Show testcases for review
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

if 'testcases' in st.session_state:
    st.subheader('Review & Edit Testcases')
    df = tc_list_to_df(st.session_state['testcases'])
    edited_df = st.experimental_data_editor(df, num_rows='dynamic')
    st.download_button('Download CSV', edited_df.to_csv(index=False).encode('utf-8'), file_name=f'{issue_key}_testcases.csv', mime='text/csv')

    st.write('---')
    st.subheader('Upload to Jira')
    st.write('You can attach the CSV to the issue or create subtasks (one per testcase).')

    col_attach, col_subtask = st.columns(2)
    with col_attach:
        if st.button('Attach CSV to Jira Issue'):
            if not jira_base:
                st.error('Enter Jira base URL in sidebar')
            else:
                csv_bytes = edited_df.to_csv(index=False).encode('utf-8')
                try:
                    res = attach_file_to_issue(jira_base, issue_key, csv_bytes, f'{issue_key}_testcases.csv', jira_auth_method, email=jira_email, api_token=jira_api_token, username=jira_username, password=jira_password, verify=jira_verify)
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
                        res = create_jira_subtask(jira_base, issue_key, summ, desc, issue_type, project_key, jira_auth_method, email=jira_email, api_token=jira_api_token, username=jira_username, password=jira_password, verify=jira_verify)
                        created.append(res.get('key'))
                    except Exception as e:
                        st.error('Failed creating subtask: ' + str(e))
                if created:
                    st.success('Created sub-tasks: ' + ', '.join(created))

st.markdown('\n---\n**Notes & Troubleshooting:**')
st.markdown('- If you see **\"The security token included in the request is invalid\"**, your `aws_session_token` is probably missing/expired or the access key/secret are incorrect. Use **Test AWS Credentials / STS** (sidebar) to diagnose. ')
st.markdown('- If you see SSL errors, try uploading your CA bundle in the sidebar or temporarily disable verification (insecure).')
st.markdown('- Ensure Bedrock is available in the specified AWS region and your IAM principal has permissions like `bedrock:InvokeModel`.')