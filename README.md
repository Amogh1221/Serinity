# Serinity - Mental Healthcare Voice Assistant (On-Device Edition)

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Local%20Vector%20DB-orange.svg)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20Inference-black.svg)](https://ollama.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Amogh1221/Serinity/blob/main/LICENSE)

> **OSDHack 2026 Submission:** This project has been explicitly engineered for the **On Device AI** theme.

---

## 🚀 What We Built
**Serinity** is an intelligent, production-ready psychiatric assessment system powered by Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG). It features a conversational AI (Dr. Aiden) that conducts empathetic clinical interviews via a natural voice interface. Behind the scenes, the system analyzes conversation patterns in real-time and provides evidence-based psychological insights grounded in clinical psychopathology literature.

## 💡 Why It Matters
Mental healthcare is heavily stigmatized, expensive, and largely inaccessible for millions. While AI has the potential to bridge this gap, putting highly sensitive mental health and conversational data into the cloud raises massive privacy concerns. 

**Serinity matters because it provides enterprise-grade, intelligent psychiatric assessment completely offline.** By running locally on the user's device, we guarantee absolute data privacy. Users can speak freely about their mental state without fear of their data being harvested, leaked, or used for model training by third-party cloud providers. Furthermore, an offline-first approach eliminates cloud API latency, providing a seamless, real-time voice experience.

## ⚙️ How It Works
Serinity utilizes a "Sync Fast-Path, Async Slow-Path" architecture combining two specialized models and local semantic search:

1. **Dual-LLM Architecture (via Ollama)**: 
   - **LLM1 (Conversational)**: `phi4-mini` handles real-time dialogue, acting as an empathetic interviewer with therapeutic rapport-building capabilities.
   - **LLM2 (Analyst)**: `qwen2.5:7b-instruct` runs asynchronous, heavy pattern-recognition across multiple psychological domains (Emotional Themes, Behavioral Patterns, Risk Assessment, etc.).
2. **Local RAG Pipeline**: Uses a local **ChromaDB** instance to perform semantic searches over 122k+ psychiatric Q&A pairs (using `nomic-embed-text` embeddings), providing clinical context to the LLMs.
3. **Voice Processing**: Uses **SenseVoice-Small** via FunASR for Speech-to-Text and emotional tone detection, while utilizing the Browser-native Web Speech API for zero-latency Text-to-Speech.
4. **Session Management**: Persistent SQLite-backed patient memory tracks previous session summaries and continuously evaluates safety risk flags.

## 📱 How It Uses On Device AI
This project strictly adheres to the **On Device AI** theme. **The entire AI stack runs 100% locally on the device.** No cloud AI APIs are used.
* **Local Inference:** LLMs are hosted entirely on the local machine using Ollama.
* **Local Vector DB:** ChromaDB stores and retrieves all clinical embeddings locally.
* **Local Speech AI:** SenseVoice processes audio on-device without sending voice bytes to external servers.

---

## 🎥 Demo Video & Screenshots
> **Note to evaluator:** 
* [Link to Demo Video](#) *(Insert YouTube/Vimeo link here)*

### Screenshots
*(Insert screenshots here showcasing the UI, dashboard, and terminal logs)*

---

## 🛠️ How Others Can Run or Try It (Setup Instructions)

### Prerequisites
- **Python 3.11+**
- **Ollama** installed on your machine.
- **FFmpeg** (for audio processing).

### 1. Ollama Setup
Before running the application, ensure Ollama is running and pull the necessary models:
```bash
ollama run phi4-mini
ollama run qwen2.5:7b-instruct
ollama run nomic-embed-text
```

### 2. Installation
Clone the repository and set up the environment:
```bash
git clone https://github.com/Amogh1221/Serinity.git
cd Serinity

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r Requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory:
```env
OLLAMA_HOST=http://localhost:11434
LLM1_MODEL=phi4-mini
LLM2_MODEL=qwen2.5:7b-instruct
EMBEDDING_MODEL=nomic-embed-text
MEMORY_DB_PATH=./data/serinity.db
```

### 4. Initialize Database & Run
```bash
# Populate the ChromaDB vector database (Run this once)
python scripts/build_vector_db.py

# Start the FastAPI server
uvicorn main:app --host 0.0.0.0 --port 7860
```
Open your browser and navigate to `http://localhost:7860` to access the application.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

## Disclaimer
This application is for educational and hackathon demonstration purposes only. It is not intended to be a substitute for professional medical advice, diagnosis, or treatment.
