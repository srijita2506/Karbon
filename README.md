# SplitMint — Your Gateway to Karbon

SplitMint is a full‑stack expense sharing app with groups, participants, smart splitting, balance settlement, and an optional MintSense (NL → expense draft) helper.

## Features
- Email‑based registration + JWT login
- Groups (max 3 participants + primary user)
- Participants with optional color/avatar
- Expenses with equal / custom amount / percentage splits
- Automatic balance & settlement suggestions
- Search + filters (text, participant, date, amount)
- CSV export
- MintSense draft generator

## Tech Stack
- Backend: Django + DRF + SimpleJWT
- Frontend: Vite + React
- DB (dev): SQLite

## Run Locally
### Backend
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend
```powershell
cd SplitMint_Frontend
npm install
npm run dev
```

Frontend: http://127.0.0.1:5173
Backend: http://127.0.0.1:8000

## API Quickstart
- Auth: `/api/auth/register/`, `/api/auth/login/`, `/api/auth/me/`
- Groups: `/api/groups/`
- Expenses: `/api/expenses/`
- MintSense: `/api/mintsense/`
- Export CSV: `/api/groups/<id>/export/`

## Notes
- Uses SQLite by default (`D:\Karbon\db.sqlite3`).
- To reset dev DB: stop server, delete `db.sqlite3`, run migrations.

---
Built with care for the SplitMint journey.
