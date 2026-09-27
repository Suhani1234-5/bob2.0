# ProofPR

> Evidence-Backed Multi-Agent PR Verification powered by IBM Bob.
> *Don't just review AI-generated code. Prove the review.*

---

## Project Structure

```
.
├── backend/            # FastAPI Python backend
│   ├── main.py         # Entry point & API routes (/api/health)
│   └── requirements.txt
├── frontend/           # Vite + React + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── App.tsx     # Main dashboard placeholder
│   │   └── ...
│   └── package.json
└── README.md
```

---

## Running Locally

### 1. Backend (FastAPI on port 8000)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The backend health-check route will be live at:
`http://localhost:8000/api/health`

---

### 2. Frontend (Vite on port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open your browser at:
`http://localhost:5173`
