# ResumeML

ResumeML is a resume screening assistant. You paste a job description, upload many resumes, and it ranks the candidates by how closely each resume matches the job. It shows matched and missing skills, experience and email, lets you open each original resume, export a CSV, and download your shortlisted resumes as one ZIP file.

The score (0–100) is a match indicator to support screening. It is not a hiring decision and not a probability of being hired.

The project is a Python FastAPI application. The same server also serves the web interface, so there is only **one program to start**.

## Project layout

```
resumeml/
├── backend/
│   ├── app/            FastAPI application (main.py is the entry point)
│   │   └── data/skills.json   skills the matcher knows (you can add more)
│   ├── tests/          automated tests
│   └── preload.py      optional: downloads the AI model ahead of time
├── frontend/           web interface (plain HTML, CSS, JavaScript)
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── render.yaml         Render deployment settings
```

---

## Part 1 — Run it on your Windows computer

### 1. Install the prerequisites

1. **Python 3.10, 3.11 or 3.12** from https://www.python.org/downloads/windows/. In the installer, tick **“Add python.exe to PATH”** before clicking Install.
2. **Visual Studio Code** from https://code.visualstudio.com/.
3. (Optional) **Git** from https://git-scm.com/download/win, only if you want to clone the project.
4. (Optional, for scanned resumes) **Tesseract OCR**, see step 9.

Check Python is installed by opening PowerShell and running:

```powershell
python --version
```

### 2. Get the project

- **Download:** on the GitHub page click **Code → Download ZIP**, then right-click the ZIP and **Extract All**.
- **Or clone:**

```powershell
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
```

### 3. Open the project in VS Code

In VS Code choose **File → Open Folder** and select the folder that **directly contains** `backend`, `frontend` and `requirements.txt`. If you extracted a ZIP you may have a folder inside a folder; open the inner one.

### 4. Open the terminal

In VS Code choose **Terminal → New Terminal**. A PowerShell prompt opens at the bottom, already inside your project folder.

### 5. Create a virtual environment

A virtual environment keeps this project's Python packages separate from the rest of your computer. Run each command **one at a time**, pressing Enter and waiting for it to finish before the next one.

```powershell
python -m venv .venv
```

### 6. Activate it

```powershell
.venv\Scripts\Activate.ps1
```

You should now see `(.venv)` at the start of the prompt. If PowerShell says scripts are disabled, run this once, then repeat the activate command:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

If VS Code asks whether to use the new environment for this folder, click **Yes**.

### 7. Install the dependencies

```powershell
python -m pip install --upgrade pip
```

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

```powershell
python -m pip install -r requirements.txt
```

The second command installs the smaller CPU-only version of PyTorch (the AI engine). The third can take several minutes.

### 8. Create your `.env` file

```powershell
copy .env.example .env
```

Open `.env` in VS Code if you want to change settings. The defaults work for most people. Never upload `.env` to GitHub (it is already listed in `.gitignore`).

### 9. Set up Tesseract OCR (only needed for scanned resumes)

**What it is for:** Tesseract reads text from images. ResumeML uses it only for scanned PDFs and image resumes (PNG, JPG, WEBP). Normal PDFs, DOCX and TXT resumes work without it.

1. Open https://github.com/UB-Mannheim/tesseract/wiki (the Windows installers recommended by the Tesseract project) and download the latest 64-bit installer.
2. Run it and keep the default install folder, `C:\Program Files\Tesseract-OCR`.
3. Check it installed. Close and reopen the VS Code terminal, then run:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

4. In `.env` make sure this line points to the installed file:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

If Tesseract is installed in the default folder or added to PATH, ResumeML finds it even without this line. **Restart the backend after changing `.env`.**

If Tesseract is missing, ResumeML still runs. Text-based PDFs, DOCX and TXT files are screened normally, scanned files are reported as failed with a clear message, and the Screening page shows “OCR unavailable”.

### 10. Start the backend

**Uvicorn** is the small web server that runs the application. Start it with:

```powershell
python -m uvicorn backend.app.main:app --reload
```

(`backend.app.main:app` means: in the folder `backend`, in `app`, in `main.py`, the object named `app`.) Run this from the project folder.

The first start downloads the AI model (about 90 MB, once). Wait until you see `Application startup complete`. A warning about `HF_TOKEN` is harmless.

**Keep this terminal open and running while you use the application.** Press **Ctrl+C** in it to stop the server.

### 11. Open the application

There is nothing separate to start for the frontend. The backend serves it. Open your browser at:

**http://localhost:8000**

The API documentation is at http://localhost:8000/docs.

### 12. Use the application

1. Click **Screening** in the top menu. Wait for the green “model ready” pill.
2. Paste a job description. Name the skills and the years of experience you want.
3. Under it, click **Select Files** or **Select Folder** (or drag resumes in).
4. Choose **Top Candidates** if you want to limit the list, then click **Start Resume Screening**.
5. In the results you can sort, filter, search, change **Show: Top 10 / 20 / 50 / 100 / All**, click **Open** to view an original resume, export a **CSV**, and click **Download Selected Resumes (.zip)** at the bottom. The ZIP contains exactly the resumes shown in the table.
6. **Edit inputs** brings back the form with your job description and files; **New screening** starts fresh.

Word (.docx) files cannot be shown directly by browsers. **Open** shows a readable view of the document with a link to download the original `.docx`.

Uploaded resumes are kept in a temporary folder for `RESUME_TTL_MINUTES` (default 120) and then deleted.

### 13. Run the tests

```powershell
python -m pip install -r requirements-dev.txt
```

```powershell
python -m pytest
```

The tests use a lightweight stand-in for the AI model, so they run quickly and do not download anything. The OCR tests need Tesseract installed.

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `python` is not recognized | Reinstall Python and tick “Add python.exe to PATH”, then reopen VS Code. |
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, then activate again. |
| `No module named 'backend'` | You are not in the project folder. The folder you open must directly contain `backend` and `requirements.txt`. |
| `No module named 'fastapi'` (or similar) | The environment is not active (no `(.venv)` in the prompt) or step 7 did not finish. Activate it and run step 7 again. |
| `Address already in use` | Another program uses port 8000. Run `python -m uvicorn backend.app.main:app --reload --port 8001` and open http://localhost:8001. |
| Pill says “Backend unreachable” | The backend terminal is closed or crashed. Start it again (step 10). |
| Pill says “loading ML model” for a long time | The first start is downloading the model. Check your internet connection and wait. |
| Pill says “OCR unavailable” | Install Tesseract (step 9) and restart the backend. Only scanned and image resumes are affected. |
| A resume is listed under “could not be screened” | Read the reason shown. Common causes: password-protected or corrupted file, unsupported type, or a scanned file without OCR. |

---

## Part 2 — Deploy to Render

Render runs the app as a native Python web service. The repository already contains `render.yaml` with everything below.

### What the configuration uses

| Setting | Value |
| --- | --- |
| Runtime | Python |
| Build command | `pip install --upgrade pip && pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt && python -m backend.preload` |
| Start command | `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/api/health` |
| Environment variables | `PYTHON_VERSION=3.11.9`, `MODEL_CACHE_DIR=/opt/render/project/src/.model_cache`, `CORS_ORIGINS=*` |

The backend and the interface are one service, so the frontend automatically talks to the same address and no URL needs to be configured. The AI model needs roughly 1 GB of memory; the blueprint selects the 2 GB plan.

### Steps

1. Push the project to GitHub (`.env` is ignored automatically).
2. In Render choose **New → Blueprint**, connect GitHub and select the repository. Render reads `render.yaml`.
   - Prefer manual setup? Choose **New → Web Service**, pick the repo, runtime **Python 3**, paste the build and start commands from the table, and add the environment variables.
3. Click **Apply / Create**. The first build takes several minutes.
4. When the status is **Live**, open your `https://….onrender.com` address.

### Verify the deployment

- Open `https://YOUR-SERVICE.onrender.com/api/health`. It should show `"status":"ok"` and, after a short warm-up, `"model_loaded":true`.
- Open the site, go to **Screening**, and run a screening with a few resumes.
- Open the **Open** link and the ZIP download to confirm they work.

### CORS and a separate frontend

With the default one-service setup, leave `CORS_ORIGINS=*` or set it to your Render address. Only if you host the `frontend` folder somewhere else, set `window.RESUMEML_API_BASE` in `frontend/config.js` to your Render address and set `CORS_ORIGINS` on Render to the address of that frontend.

### Limits on Render

- **Scanned and image resumes will not work**, because Render’s native Python environment does not include the Tesseract program. The app reports “OCR unavailable” and still screens PDF, DOCX and TXT files. Tesseract works on your own computer (step 9).
- Uploaded resumes are stored on temporary disk and removed after `RESUME_TTL_MINUTES`, or whenever the service restarts. Download the ZIP while your results are on screen.
- Free and small plans have too little memory for the AI model.
