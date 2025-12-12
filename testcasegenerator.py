"""
AI Testcase Generator Streamlit App
- Fetches Jira issue by issue key (user inputs Jira base url + email + API token)
- Sends description/summary/labels/comments to Amazon Bedrock to generate structured test cases
- Displays editable test cases in UI
- Allows export to CSV
- After review, uploads CSV as attachment to Jira and/or creates sub-tasks for each test case

Pre-requisites:
- Python 3.9+
- pip install streamlit boto3 requests pandas python-dotenv
- Set AWS credentials (aws_access_key_id, aws_secret_access_key, aws_session_token) via environment variables OR paste in UI

References: Amazon Bedrock SDK (boto3) and Jira REST API.
"""

import streamlit as st
import boto3
import json
import requests
import pandas as pd
import os
from typing import List, Dict, Any
from base64 import b64encode

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

    # Bedrock expects a bytes or JSON body depending on API variant. We use invoke_model (text mode)
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

    # Response body may be bytes; decode
    if isinstance(resp.get('body'), (bytes, bytearray)):  # sometimes Streaming
        text = resp['body'].decode('utf-8')
    else:
        # boto3 may return a StreamingBody object
        try:
            text = resp['body'].read().decode('utf-8')
        except Exception:
            text = str(resp.get('body'))

    # The model may return extra tokens; try to extract first JSON array
    text = text.strip()

    # Attempt to find JSON array start
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        json_text = text[start:end+1]
    else:
        # fallback: try full text
        json_text = text

    try:
        testcases = json.loads(json_text)
    except Exception as e:
        # If parsing fails, provide raw text in one test case so user can correct prompt
        testcases = [{
            'id': 'GEN-ERR-1',
            'title': 'Model output parse error',
            'priority': 'Medium',
            'type': 'Manual',
            'preconditions': '',
            'steps': [text],
            'expected_result': ''
        }]

    # Normalize testcases: ensure fields exist
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

def fetch_jira_issue(jira_base: str, issue_key: str, email: str, api_token: str):
    api = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}?fields=summary,description,labels,comment'
    resp = requests.get(api, auth=(email, api_token), headers={'Accept': 'application/json'})
    resp.raise_for_status()
    return resp.json()


def create_jira_subtask(jira_base: str, parent_key: str, summary: str, description: str, issue_type: str, project_key: str, email: str, api_token: str):
    api = jira_base.rstrip('/') + '/rest/api/3/issue'
    payload = {
        'fields': {
            'project': {'key': project_key},
            'parent': {'key': parent_key},
            'summary': summary,
            'description': description,
            'issuetype': {'name': issue_type}
        }
    }
    resp = requests.post(api, auth=(email, api_token), headers={'Content-Type': 'application/json'}, json=payload)
    resp.raise_for_status()
    return resp.json()


def attach_file_to_issue(jira_base: str, issue_key: str, file_bytes: bytes, filename: str, email: str, api_token: str):
    api = jira_base.rstrip('/') + f'/rest/api/3/issue/{issue_key}/attachments'
    headers = {
        'X-Atlassian-Token': 'no-check'
    }
    files = {'file': (filename, file_bytes)}
    resp = requests.post(api, auth=(email, api_token), headers=headers, files=files)
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
jira_email = st.sidebar.text_input('Jira Email (for API auth)')
jira_api_token = st.sidebar.text_input('Jira API Token', type='password')

st.markdown('Enter a Jira issue key below, press Fetch to load details. Then click Generate to create test cases.')

col1, col2 = st.columns([2, 1])
with col1:
    issue_key = st.text_input('Jira Issue Key (e.g. PROJ-123)')
with col2:
    if st.button('Fetch Jira Issue'):
        if not (jira_base and jira_email and jira_api_token and issue_key):
            st.error('Provide Jira base URL, email, API token and issue key in the sidebar or fields.')
        else:
            try:
                issue = fetch_jira_issue(jira_base, issue_key, jira_email, jira_api_token)
                st.session_state['issue'] = issue
                st.success('Fetched issue ' + issue_key)
            except Exception as e:
                st.error('Error fetching issue: ' + str(e))

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
            # create bedrock client
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
            if not (jira_base and jira_email and jira_api_token):
                st.error('Enter Jira credentials in sidebar')
            else:
                csv_bytes = edited_df.to_csv(index=False).encode('utf-8')
                try:
                    res = attach_file_to_issue(jira_base, issue_key, csv_bytes, f'{issue_key}_testcases.csv', jira_email, jira_api_token)
                    st.success('CSV attached to issue')
                    st.write(res)
                except Exception as e:
                    st.error('Attachment failed: ' + str(e))

    with col_subtask:
        project_key = st.text_input('Project Key for Sub-tasks (e.g. PROJ)')
        issue_type = st.selectbox('Sub-task Issue Type Name', options=['Sub-task', 'Task', 'Bug'])
        if st.button('Create Sub-tasks for Each Testcase'):
            if not (jira_base and jira_email and jira_api_token and project_key):
                st.error('Provide Jira credentials and project key')
            else:
                created = []
                for _, row in edited_df.iterrows():
                    summ = f"TC - {row['id']} - {row['title'][:80]}"
                    desc = f"Preconditions:\n{row['preconditions']}\n\nSteps:\n{row['steps']}\n\nExpected:\n{row['expected_result']}"
                    try:
                        res = create_jira_subtask(jira_base, issue_key, summ, desc, issue_type, project_key, jira_email, jira_api_token)
                        created.append(res.get('key'))
                    except Exception as e:
                        st.error('Failed creating subtask: ' + str(e))
                if created:
                    st.success('Created sub-tasks: ' + ', '.join(created))


st.markdown('\n---\n**Notes & Tips:**')
st.markdown('- Tune the prompt template in the source to change how the model formats testcases.\n- Validate generated testcases carefully: LLMs may hallucinate details or miss edge cases.\n- For production, use prompt management, logging, and human-in-the-loop review.')

