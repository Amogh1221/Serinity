---
title: Serinity
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Serinity: Local-First AI Psychiatrist

**Serinity** is an offline-first, highly empathetic Conversational AI system designed to conduct rigorous clinical interviews, track mental health trajectories over time, and provide emotional support—all while ensuring 100% data privacy by running entirely on-device.

Unlike general-purpose AIs that suffer from "Helpful Assistant Syndrome" (offering premature advice or toxic positivity), Serinity acts as a professional, empathetic listener. 

## Features

- **100% Private (Local-First)**: Audio processing, Vector Database (RAG), and LLM inference happen entirely on your local hardware or your private cloud deployment. No user data is sent to public AI APIs.
- **Clinically Grounded**: Powered by a Retrieval-Augmented Generation (RAG) pipeline loaded with psychiatric literature, allowing the bot to conduct structured clinical interviews.
- **Agentic Memory**: Uses a background agent to continually update a structured "Clinical Profile" across 8 domains (Emotional Themes, Behavioral Patterns, Risk Assessment) to track patient trajectories over multiple sessions.
- **Multi-Modal Support**: Asynchronous voice-to-text processing built-in.

---

## Installation

### Prerequisites
1. **Python 3.10+**
2. **Ollama**: Must be installed locally and running (if running locally).
   ```bash
   ollama pull nomic-embed-text:latest
   ollama pull qwen2.5:7b-instruct
   ```
3. **FFmpeg**: Required for audio processing.

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Amogh1221/Serinity.git
   cd Serinity
   ```

2. **Backend Setup (FastAPI):**
   ```bash
   python -m venv .venv
   
   # Activate it (Windows)
   .venv\Scripts\activate
   # Or on Linux/Mac: source .venv/bin/activate
   
   # Install dependencies
   pip install -r Requirements.txt
   ```

3. **Environment Variables:**
   Create a `.env` file in the root directory using `.env.example` as a template.
   ```env
   # Ollama local inference
   OLLAMA_HOST=http://localhost:11434
   LLM1_MODEL=phi4-mini
   LLM2_MODEL=qwen2.5:7b-instruct
   EMBEDDING_MODEL=nomic-embed-text
   
   # HuggingFace model cache 
   HF_HOME=./models
   
   # ChromaDB local vector store
   CHROMA_PERSIST_DIR=./chroma_db
   CHROMA_COLLECTION_NAME=mhcva-knowledge
   
   # SQLite memory store
   MEMORY_DB_PATH=./data/serinity.db
   
   # Debug logs directory
   LOG_DIR=./logs
   
   # Working memory window
   WORKING_MEMORY_TURNS=20
   ```

---

## Usage

To start the application locally, run the FastAPI backend server:

```bash
.venv\Scripts\activate
uvicorn main:app --reload
```
*The full application will be available at `http://localhost:8000`*

---

## Testing & Development

Serinity includes a comprehensive test suite for both local logic and cloud integrations, using `pytest`.

To run the full test suite (unit + integration tests) locally:
```bash
python -m pytest -v tests/
```

---

## Documentation

For a deeper dive into the system design, please see the following documents:
- [ARCHITECTURE.md](ARCHITECTURE.md) - System diagrams and data flow.
- [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) - Specs, metrics, safety protocols, and attribution.

## License
MIT License
