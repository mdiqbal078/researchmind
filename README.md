# ResearchMind ⚡🔬

**ResearchMind** is an autonomous, dual-mode multi-agent system designed for deep research and fast answers. Instead of relying on a single Large Language Model to guess answers, ResearchMind orchestrates a pipeline of specialized agents to plan searches, fetch full webpage content, extract facts, fact-check claims against each other, and write a fully cited, comprehensive Markdown report. 

It features a beautiful dark-mode UI with live streaming (via Server-Sent Events) so you can watch the agents "think" and type in real-time.

![ResearchMind UI](https://img.shields.io/badge/UI-Dark_Mode-090d16?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688?style=flat-square&logo=fastapi)
![Celery](https://img.shields.io/badge/Celery-5.4.0-37814A?style=flat-square&logo=celery)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis)

---

## 🌟 Key Features

*   **Multi-Agent Architecture:** Separates concerns into specific tasks (`Orchestrator`, `Retrieval`, `Extraction`, `Critique`, `Report`) to prevent LLM hallucinations.
*   **Dual-Mode Capability:** Choose between `Quick Answer` for immediate responses or `Deep Research` for an intense, multi-source fact-finding mission.
*   **Live Streaming UI:** Real-time visual tracking of which agent is currently running, followed by a live typewriter effect as the Markdown report is generated.
*   **Rich Frontend:** Built-in syntax highlighting (highlight.js), auto-expanding inputs, and starter prompt cards.
*   **Asynchronous & Resilient:** Powered by Celery for background processing and Redis for Pub/Sub event streaming.

---

## 🏗️ How it Works

When you submit a deep research query:
1.  **Orchestrator Agent:** Analyzes the prompt and generates highly specific search queries.
2.  **Retrieval Agent:** Scrapes the web (via Tavily or DuckDuckGo) and truncates text to fit within token limits.
3.  **Extraction Agent:** Reads the raw text and extracts strictly factual claims into JSON.
4.  **Critique Agent:** Cross-references the claims against each other to find contradictions and mark them as `VERIFIED` or `CONTRADICTED`.
5.  **Report Agent:** Synthesizes only the verified facts into a beautifully structured Markdown report, streaming it back to your browser.

---

## 🚀 Getting Started (Localhost)

Follow these steps to run the ResearchMind stack locally.

### 1. Prerequisites
Ensure you have the following installed:
*   Python 3.10+
*   Docker & Docker Compose (for PostgreSQL & Redis)

### 2. Environment Variables
Create a `.env` file in the root directory based on your API keys:
```env
# Example .env file
GROQ_API_KEY=your_groq_api_key_here
# Add Tavily API key if using Tavily instead of DuckDuckGo
# TAVILY_API_KEY=your_tavily_key
```

### 3. Install Dependencies
Set up your virtual environment and install the required Python packages:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Start Infrastructure (DB & Redis)
Use the provided `docker-compose.yml` (or Makefile) to spin up PostgreSQL and Redis:
```bash
make run
# OR
docker-compose up -d
```

### 5. Initialize the Database
Create the necessary PostgreSQL tables:
```bash
python -m db.init_db
```

### 6. Start the Celery Worker
In a **new terminal window** (with your venv activated), start the background worker that processes the multi-agent pipeline:
```bash
celery -A worker.celery_app worker --pool=solo --loglevel=info
```
*(Note: `--pool=solo` is recommended on some OS environments to prevent asyncio event loop conflicts).*

### 7. Start the FastAPI Server
In your **main terminal window**, start the web server:
```bash
uvicorn api.main:app --reload
```

### 🎉 8. Open the App
Visit [http://localhost:8000](http://localhost:8000) in your browser!

---

## 🛠️ Tech Stack
*   **Backend:** FastAPI, Python `asyncio`
*   **Task Queue:** Celery
*   **Broker/PubSub:** Redis
*   **Database:** PostgreSQL (with `asyncpg` and SQLAlchemy)
*   **LLM Provider:** Groq (LPU architecture for ultra-fast generation)
*   **Frontend:** Vanilla JS/HTML/CSS, marked.js, highlight.js

---

## 🧹 Cleaning Up
To stop the Docker containers and clean up Python cache files, simply run:
```bash
make stop
make clean
```
