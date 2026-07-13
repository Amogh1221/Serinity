# Serinity - Mental Healthcare Assistant

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Local%20Vector%20DB-orange.svg)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20Inference-black.svg)](https://ollama.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Amogh1221/Serinity/blob/main/LICENSE)

> **OSDHack 2026 Submission:** This project has been explicitly engineered for the **On Device AI** theme.

---

##  What We Built
**Serinity** is an intelligent, production-ready psychiatric assessment system powered by Large Language Models (LLMs) and Retrieval Augmented Generation (RAG). It features a conversational AI that conducts empathetic clinical interviews via a natural voice interface. Behind the scenes, the system analyzes conversation patterns in real-time and provides evidence-based psychological insights grounded in clinical psychopathology literature.

##  Why It Matters
Mental healthcare is heavily stigmatized, expensive, and largely inaccessible for millions. While AI has the potential to bridge this gap, putting highly sensitive mental health and conversational data into the cloud raises massive privacy concerns. 

**Serinity matters because it provides enterprise-grade, intelligent psychiatric assessment completely offline.** By running locally on the user's device, we guarantee absolute data privacy. Users can speak freely about their mental state without fear of their data being harvested, leaked, or used for model training by third-party cloud providers. Furthermore, an offline-first approach eliminates cloud API latency, providing a seamless, real-time voice experience.

##  How It Works
Serinity utilizes an "Intent-Driven Synchronous 3-Pipeline" architecture combining specialized LLM behaviors and local semantic search:

1. **Tri-Pipeline LLM Architecture (via Ollama)**: 
   - **LLM1 (Conversational/Query)**: `phi4-mini` handles real-time dialogue, acting as an empathetic interviewer. If the user asks for advice, it triggers a synchronous RAG pipeline to provide immediate, evidence-based answers.
   - **LLM2 (Analyst)**: `qwen2.5:7b-instruct` runs synchronous, heavy pattern-recognition across multiple psychological domains during the session.
   - **LLM3 (Profile Manager)**: `qwen2.5:7b-instruct` runs at the end of the session to generate concise clinical summaries and intelligently merge/deduplicate long-term patient profiles.
2. **Local RAG Pipeline**: Uses a local **ChromaDB** instance to perform semantic searches over 122k+ psychiatric Q&A pairs (using `nomic-embed-text` embeddings with HyDE optimization), providing clinical context to the LLMs.
3. **Voice Processing**: Uses **SenseVoice-Small** via FunASR for Speech-to-Text and emotional tone detection, while utilizing the Browser-native Web Speech API for zero-latency Text-to-Speech.
4. **Session Management**: Persistent SQLite-backed patient memory tracks previous session summaries and continuously evaluates safety risk flags.

##  How It Uses On Device AI
This project strictly adheres to the **On Device AI** theme. **The entire AI stack runs 100% locally on the device.** No cloud AI APIs are used.
* **Local Inference:** LLMs are hosted entirely on the local machine using Ollama.
* **Local Vector DB:** ChromaDB stores and retrieves all clinical embeddings locally.
* **Local Speech AI:** SenseVoice processes audio on-device without sending voice bytes to external servers.

---

##  Demo Video & Screenshots
> **Note to evaluator:** 
* [Link to Demo Video](#) *(Insert YouTube/Vimeo link here)*

### Screenshots

#### 1. Conversational Interface (phi4-mini)
![Chat UI](icons/conversation.png)

#### 2. Clinical History & Patient Profile (qwen2.5:7b-instruct)
![Patient Profile](icons/profile.png)

#### 3. Local Inference Logs (100% On-Device)
![Terminal Logs](icons/terminal.png)

---

##  How Others Can Run or Try It (Setup Instructions)

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
Copy the contents of .env.example file on it

### 4. Initialize Database & Run
```bash
# Populate the ChromaDB vector database (Run this once)
python scripts/build_vector_db.py

# Start the FastAPI server
uvicorn main:app --host 0.0.0.0 --port 7860
```
Open your browser and navigate to `http://localhost:7860` to access the application.

---

##  License
This project is licensed under the [MIT License](LICENSE).

## Disclaimer
This application is for educational and hackathon demonstration purposes only. It is not intended to be a substitute for professional medical advice, diagnosis, or treatment.
