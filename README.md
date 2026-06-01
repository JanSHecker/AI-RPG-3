# AI RPG World Data Generator

Local React + FastAPI app for generating regional text RPG world data. Structured records are stored in SQLite; prose lore is stored as Markdown sidecars under `worlds/`.

## Run

```powershell
npm install
npm --prefix frontend install
cd backend
py -3.10 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
npm run dev
```

Open `http://localhost:5173`.

The backend now targets Python 3.10+ because the world-generation workflow uses Microsoft Agent Framework.

## Providers

The default model is `lmstudio:local-model`. OpenRouter and LM Studio entries are available in `backend/models.json`.

To use OpenRouter, create `backend/.env` from `backend/.env.example` and set `OPENROUTER_API_KEY`.

To use LM Studio, start its OpenAI-compatible server and keep the default `LM_STUDIO_BASE_URL=http://localhost:1234/v1`, or change it in `backend/.env`.

## Checks

```powershell
npm run test:backend
npm run frontend:build
```
