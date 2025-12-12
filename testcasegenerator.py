# ai_testcase_generator_with_model_list.py
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
import difflib
import traceback
from typing import List, Dict, Any

# ---------- Page config ----------
st.set_page_config(layout='wide', page_title='AI Testcase Generator (Bedrock Model Picker)')
st.title('AI Testcase Generator — Bedrock Model Picker')

st.markdown("""
This app discovers Bedrock models visible to your account/region, lets you pick one,
validates the selection, then invokes the model to generate test cases from a Jira issue.
""")

# ---------- TLS helpers ----------
def build_verify_from_sidebar(prefix: str):
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
        if prefix == 'bedrock' and os.getenv('AWS_CA_BUNDLE'):
            return os.getenv('AWS_CA_BUNDLE'), f'{prefix}: using AWS_CA_BUNDLE={os.getenv("AWS_CA_BUNDLE")}'
        return True, f'{prefix}: using system trust store'

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

# ---------- Utility: STS test ----------
def test_aws_credentials(region, access_key, secret_key, session_token, verify=True):
    kwargs = {}
    if access_key and secret_key:
        kwargs['aws_access_key_id'] = access_key
        kwargs['aws_secret_access_key'] = secret_key
    if session_token:
        kwargs['aws_session_token'] = session_token
    try:
        session = boto3.Session(**kwargs) if kwargs else boto3.Session()
        sts = session.client('sts', region_name=region, verify=verify)
        resp = sts.get_caller_identity()
        return True, 'STS OK', resp
    except botocore.exceptions.ClientError as e:
        err = e.response.get('Error', {})
        return False, f"AWS ClientError: {err.get('Code')}: {err.get('Message')}", None
    except botocore.exceptions.SSLError as e:
        return False, f"SSLError: {e}", None
    except Exception as e:
        return False, f"Unexpected error: {e}", None

if st.sidebar.button('Test AWS Credentials / STS'):
    ok, msg, details = test_aws_credentials(aws_region, aws_access_key_id, aws_secret_access_key, aws_session_token, verify=bedrock_verify)
    if ok:
        st.sidebar.success(msg)
        st.sidebar.json(details)
    else:
        st.sidebar.error(msg)

# ---------- Bedrock client ----------
def make_bedrock_client(aws_region: str,
                        aws_access_key_id: str = None,
                        aws_secret_access_key: str = None,
                        aws_session_token: str = None,
                        verify=True):
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
    except botocore.exceptions.ClientError as e:
        err = e.response.get('Error', {})
        raise RuntimeError(f'Bedrock ClientError: {err.get("Code")}: {err.get("Message")}')
    except botocore.exceptions.SSLError as e:
        raise RuntimeError(f'Bedrock SSL error: {e}')
    except Exception as e:
        raise RuntimeError(f'Error creating Bedrock client: {e}')

# ---------- Model listing & validation ----------
def list_bedrock_models_safe(bclient):
    try:
        resp = bclient.list_models()
        models = []
        if isinstance(resp, dict):
            for m in resp.get('models', []) or []:
                mid = None
                if isinstance(m, dict):
                    mid = m.get('modelId') or m.get('id') or m.get('model_id') or m.get('name')
                else:
                    mid = str(m)
                if mid:
                    models.append(str(mid))
        else:
            models = [str(resp)]
        return True, sorted(set(models)), ''
    except botocore.exceptions.ClientError as e:
        err = e.response.get('Error', {})
        tb = traceback.format_exc()
        return False, [], f'ClientError: {err.get("Code")}: {err.get("Message")}\\n{tb}'
    except Exception as e:
        tb = traceback.format_exc()
        return False, [], f'Error calling list_models(): {e}\\n{tb}'

def validate_model_id(bclient, model_id: str):
    ok, models, msg = list_bedrock_models_safe(bclient)
    if not ok:
        return False, f'Could not list models: {msg}', []
    if model_id in models:
        return True, f'Model \"{model_id}\" is available', []
    # case-insensitive
    lower_to_orig = {m.lower(): m for m in models}
    if model_id.lower() in lower_to_orig:
        corr = lower_to_orig[model_id.lower()]
        return True, f'Model id matched case-insensitively. Use \"{corr}\" instead.', [corr]
    suggestions = difflib.get_close_matches(model_id, models, n=8, cutoff=0.35)
    if suggestions:
        return False, f'Model \"{model_id}\" not found. Suggestions: {suggestions}', suggestions
    sample = models[:20]
    more = len(models) - len(sample)
    more_msg = f' (+{more} more)' if more > 0 else ''
    return False, f'Model \"{model_id}\" not found. Found {len(models)} models; sample: {sample}{more_msg}', []

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
            modelId=model_id.strip(),
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

# ---------- Jira helpers ----------
def fetch_jira_issue(jira_base: str, issue_key: str, auth_method: str = 'api_token',
                     email: str = None, api_token: str = None, username: str = None, password: str = None,
                     verify=True):
    url = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment'
    headers = {'Accept': 'application/json'}
    if auth_method == 'api_token':
        if not (email and api_token):
            raise RuntimeError('Missing email or API token.')
        auth = HTTPBasicAuth(email, api_token)
    else:
        if not (username and password):
            raise RuntimeError('Missing username or password.')
        auth = HTTPBasicAuth(username, password)
    try:
        resp = requests.get(url, auth=auth, headers=headers, timeout=20, verify=verify)
    except requests.exceptions.SSLError as e:
        raise RuntimeError(f'Jira SSL error: {e}')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Network error contacting Jira: {e}')
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
        raise RuntimeError(f'Attachment SSL error: {e}')
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
        raise RuntimeError(f'Subtask SSL error: {e}')
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f'Subtask creation failed: {e}')

# ---------- UI flow ----------
st.markdown('Enter Jira issue key → Fetch issue → Pick Bedrock model → Generate testcases → Review → Upload.')

# Fetch issue
left, right = st.columns([2,1])
with left:
    issue_key = st.text_input('Jira Issue Key (e.g. PROJ-123)')
with right:
    if st.button('Fetch Jira Issue'):
        if not issue_key or not jira_base:
            st.error('Provide Jira base URL and issue key.')
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

# If issue in session, preview and allow model listing / selection
if 'issue' in st.session_state:
    issue = st.session_state['issue']
    fields = issue.get('fields', {})
    st.subheader('Jira Issue Preview')
    st.markdown(f"**{issue_key} - {fields.get('summary')}**")
    st.markdown('**Description**')
    st.write(fields.get('description') or '')
    st.markdown('**Labels**: ' + ', '.join(fields.get('labels') or []))
    comments = [c.get('body') for c in (fields.get('comment') or {}).get('comments', [])]
    if comments:
        st.markdown('**Recent comments**:')
        for c in comments[:5]:
            st.write('- ' + (c[:200] + '...' if len(c) > 200 else c))

    st.write('---')
    st.subheader('Bedrock Model Selection')

    # Create bedrock client and list models (show errors if occur)
    try:
        bclient = make_bedrock_client(aws_region,
                                      aws_access_key_id or None,
                                      aws_secret_access_key or None,
                                      aws_session_token or None,
                                      verify=bedrock_verify)
    except Exception as e:
        st.error('Error creating Bedrock client: ' + str(e))
        bclient = None

    available_models = []
    if bclient:
        ok, models, msg = list_bedrock_models_safe(bclient)
        if not ok:
            st.error('Could not list Bedrock models: ' + str(msg))
        else:
            available_models = models
            st.success(f'Found {len(models)} models (showing up to 200).')
            # small dropdown (show top 50 for ergonomics)
            sample = models[:200]
            selected_model = st.selectbox('Pick a model (or paste a model id below)', options=['-- choose --'] + sample, index=0)
            custom_model = st.text_input('Or enter custom model id (paste exact id if not in dropdown)')
            chosen_model = (custom_model.strip() if custom_model.strip() else (selected_model if selected_model != '-- choose --' else ''))
            st.markdown(f'**Chosen model:** `{chosen_model}`')

            # Validate model id on demand
            if st.button('Validate chosen model'):
                if not chosen_model:
                    st.error('Please choose or enter a model id.')
                else:
                    valid, msg, suggestions = validate_model_id(bclient, chosen_model)
                    if valid:
                        st.success(msg)
                    else:
                        st.error(msg)
                        if suggestions:
                            st.info('Suggestions: ' + ', '.join(suggestions))

            # Generate testcases button
            st.write('---')
            st.subheader('Generate Testcases')
            gen_cols = st.columns(3)
            with gen_cols[0]:
                max_tokens = st.number_input('Max tokens', value=1500)
            with gen_cols[1]:
                model_to_use = st.text_input('Model id to use for invocation', value=chosen_model)
            with gen_cols[2]:
                if st.button('Generate Testcases (invoke)'):
                    if not model_to_use or not model_to_use.strip():
                        st.error('Provide a model id (select or paste).')
                    else:
                        # validate before invoking
                        if bclient:
                            valid, msg, suggestions = validate_model_id(bclient, model_to_use.strip())
                            if not valid:
                                st.error('Model validation failed: ' + msg)
                                if suggestions:
                                    st.info('Suggestions: ' + ', '.join(suggestions))
                            else:
                                st.info('Model validated: ' + msg)
                                # proceed to invoke
                                summary = fields.get('summary') or ''
                                description = fields.get('description') or ''
                                labels = fields.get('labels') or []
                                comments = [c.get('body') for c in (fields.get('comment') or {}).get('comments', [])]
                                try:
                                    tcs = generate_testcases_bedrock(bclient, model_to_use.strip(), summary, description, labels, comments, max_tokens=max_tokens)
                                    st.session_state['testcases'] = tcs
                                    st.success(f'Generated {len(tcs)} testcases')
                                except Exception as e:
                                    st.error('Generation error: ' + str(e))

# show testcases and upload flow
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

st.markdown('---')
st.markdown('**Notes & Troubleshooting**')
st.markdown('- If `validate_model_id` fails, ensure the Bedrock region is correct and your IAM principal has `bedrock:ListModels` permission.')
st.markdown('- If Bedrock `invoke_model` returns `ValidationException: provided model identifier is invalid`, use the model id exactly as listed by `list_models()`.')
st.markdown('- Use the STS test (sidebar) to check invalid/expired AWS credentials.')