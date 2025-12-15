# 🧪 AI Test Case Generator  
### Jira + Xray + AWS Bedrock Claude 3.7 Sonnet (EU)  
A complete enterprise AI-driven Test Case Generator using:

- AWS Bedrock (Claude Sonnet 3.7 EU Model)
- Jira Cloud or Jira Data Center
- Xray Test Management
- Streamlit Web Application
- Predefined Test Case Templates

---

## 🚀 Features

### ✔ AI Test Case Generation
- Uses Claude 3.7 Sonnet (EU)
- Generates functional, negative, and edge test cases
- JSON structured output
- Integrates keywords + predefined templates

### ✔ Jira + Xray Integration
- Supports Jira Cloud & Data Center
- Story selection:
  - Manual entry (`ABC-123`)
  - Search by Project / Text / JQL
- Creates:
  - Xray Test issues (`issuetype = Xray Test`)
  - Test Steps inside Xray
  - Xray Test Set (`issuetype = Test Set`)
- Adds Tests to Test Set
- Links Test ↔ Story and Test Set ↔ Story

### ✔ Templates
- Upload CSV/Excel predefined test case library
- Keywords mapped automatically

### ✔ Downloads
- Export as Excel
- Export as JSON

---

## 🏗 Project Structure
│
├── app.py
│
├── services/
│ ├── bedrock_service.py
│ ├── jira_service.py
│ ├── xray_service.py
│ ├── utils.py
│
└── prompts/
└── testcase_prompt.txt


---

## 🔧 Installation

### 1️⃣ Clone Repository

```bash
git clone <repo-url>
cd ai-testcase-generator

#**##2️⃣ Install Dependencies**
pip install -r requirements.txt

**###🔐 AWS Setup**
Set your AWS credentials as environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=eu-west-3


**###Bedrock model used:**

eu.anthropic.claude-3-7-sonnet-20250219-v1:0

###🔐 Jira Setup

Jira Cloud

Username = Email
Password = API Token
Base URL = https://company.atlassian.net

Jira Data Center

Username = Username
Password = REAL password
Base URL = https://jira.company.com

###▶️ Run the App
streamlit run app.py
App starts at:
http://localhost:8501


###🐳 Running via Docker
**Build**
docker build -t ai-testcase-generator .

**Run**
docker run -p 8501:8501 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e AWS_REGION=eu-west-3 \
  ai-testcase-generator


**Predefined Template Format**

Upload CSV/Excel with columns:

FeatureKeyword	TestCaseTitle	Preconditions	Steps	ExpectedResult	Priority	Type

