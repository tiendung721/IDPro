
# Excel AI Agent – Response API

A production-style **FastAPI backend** that enables users to upload Excel/CSV files, automatically detect and confirm table sections, generate structured outputs, and perform **natural-language Q&A over spreadsheet data using an LLM (OpenAI)**.

The project is designed with **real-world backend practices**: session-based workflows, JWT authentication, clean separation of concerns, and environment-based configuration.

---

## Key Features

- **Excel / CSV Upload**
  - Supports `.xlsx`, `.xls`, `.csv`
  - Session-based processing with unique `session_id`

- **Automatic Table Section Detection**
  - Detects logical table regions from spreadsheets
  - Allows users to confirm or adjust detected sections

- **Section Confirmation Pipeline**
  - Validates row/column indices
  - Persists a structured manifest for downstream processing

- **LLM-Powered Data Understanding**
  - Ask natural-language questions about uploaded data
  - Uses OpenAI API for contextual reasoning

- **Final Output Generation**
  - Produces structured artifacts after confirmation
  - Outputs are stored and served as static files

- **Authentication & Authorization**
  - JWT-based authentication
  - Admin and user roles
  - Session ownership enforcement

- **Optional Streamlit UI**
  - End-to-end demo UI for non-technical users

---

## Tech Stack

- **Backend**: FastAPI, Uvicorn
- **Data Processing**: Pandas
- **Authentication**: JWT (python-jose), Passlib (bcrypt)
- **LLM Integration**: OpenAI Python SDK
- **Optional UI**: Streamlit
- **Config Management**: Environment variables (`.env`)

---

## Project Structure

```text
.
├── main.py                      # FastAPI application entry point
├── controllers/                 # API routers (upload, preview, confirm, final, qa, auth)
├── services/                    # OpenAI and artifact services
├── data_processing/             # Section detection & validation logic
├── common/                      # Shared models, auth, session store
├── streamlit_app/               # Optional Streamlit UI
├── output/                      # Generated artifacts (served as static files)
├── requirements.txt
└── README.md
```

---

 ## Environment Configuration

This project uses a single .env file to manage all runtime configuration, following 12-Factor App principles.
⚠️ Important
- Do NOT commit .env to GitHub
- Always commit .env.example instead

```text

OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-mini

JWT_SECRET_KEY=CHANGE_THIS_TO_A_LONG_RANDOM_STRING
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=720

UPLOAD_DIR=uploaded_files
SESSIONS_ARTIFACTS_DIR=sessions_artifacts
OUTPUT_DIR=output

APP_ENV=development
DEBUG=true
```

---

## How to Run Locally

Follow the steps below to run the project on your local machine.

1. Create environment file

- Windows
```text
copy .env.example .env
```

- macOS / Linux
```text
cp .env.example .env
```

2. Create virtual environment

```text
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate     # macOS / Linux
```

3. Install dependencies

```text
pip install -r requirements.txt
```

4. Start FastAPI server
```text
uvicorn main:app --reload
```

---

## API Documentation

- Swagger UI: http://127.0.0.1:8000/docs

- Health Check: GET /health

- Optional: Streamlit Demo UI
```text
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

Open in browser:
```text
http://127.0.0.1:8501
```

---

## API Workflow (High-Level)
1. Upload file
POST /upload
→ returns session_id

2. Preview & detect table sections
POST /preview

3. Confirm detected sections
POST /confirm_sections

4. Generate final structured output
POST /final

5. Ask questions about uploaded data
POST /qa

---

## Authentication & Authorization
- Admin login
POST /auth/login

- User login
POST /auth/user_login

- Admin endpoints
GET    /admin/users
POST   /admin/users
PATCH  /admin/users/{user_id}

### Authorization header for protected endpoints:
```text
Authorization: Bearer <JWT_TOKEN>
```
---

## Security Notes
- Secrets are loaded from environment variables
- No API keys are hard-coded
- Session ownership is enforced
- Sensitive data is excluded via .gitignore

## Recommended .gitignore:
```text
.env
__pycache__/
*.sqlite3
uploaded_files/
sessions_artifacts/
output/
.vscode/
```

---

## Roadmap
- Add unit & integration tests (pytest)
- Add CI pipeline (GitHub Actions)
- Dockerize the application
- Improve API schemas & validation
- Add request/response examples

---

## License
MIT License

