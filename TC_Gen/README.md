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

