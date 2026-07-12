# Serinity - Mental Healthcare Voice Assistant (On-Device Edition)

An intelligent, **production-ready** psychiatric assessment system powered by Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG). Dr. Aiden conducts empathetic clinical interviews, analyzes conversation patterns, and provides evidence-based psychological insights grounded in clinical psychopathology literature.

This project has been fully migrated to a **local, on-device architecture** to prioritize patient privacy, eliminate cloud latency, and remove API dependencies.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Local%20Vector%20DB-orange.svg)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20Inference-black.svg)](https://ollama.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Amogh1221/Mental_HealthCare_VoiceAssistant/blob/main/LICENSE)

## Overview

**Serinity** is built with cutting-edge AI technology, running entirely on your local machine:

- **Dual-LLM Architecture (via Ollama)**: Two specialized language models working together.
  - **LLM1 (Conversational)**: `phi4-mini` acts as an empathetic psychiatric interviewer with therapeutic rapport-building.
  - **LLM2 (Analyst)**: `qwen2.5:7b-instruct` acts as the advanced pattern recognition engine across multiple psychological domains.
  
- **Local RAG (Retrieval-Augmented Generation)**: Semantic search over 122k+ psychiatric Q&A pairs via a local **ChromaDB** instance.
  
- **Advanced Voice Processing**:
  - **STT (Speech-to-Text)**: **SenseVoice-Small** (via FunASR) for real-time audio transcription and emotion detection.
  - **TTS (Text-to-Speech)**: Browser-native Web Speech API for natural voice output with zero latency.

- **Patient Dashboard**: Persistent SQLite-backed patient memory allowing you to track previous session summaries and risk assessments.

This system is designed for **educational and research purposes** to demonstrate enterprise-grade AI in healthcare.

---

## Key Features

### Advanced Voice Interface
- **Real-time Speech Recognition**: Powered by SenseVoice-Small, providing transcription and emotion tagging directly from the audio signal.
- **Natural Voice Output**: Browser-native TTS with zero server-side latency.
- **Cross-platform**: Works on Chrome, Edge, Safari.

### Intelligent Dual-LLM System
- **LLM1 (phi4-mini)**: Fluid conversational model running locally.
- **LLM2 (qwen2.5:7b-instruct)**: Clinical reasoning and pattern extraction running locally.
- **Decision Logic**: Intelligent CONTINUE/ANALYZE intent routing.
- **Context Awareness**: Full conversation history with intelligent trimming and rolling summaries.

### Clinical Knowledge Integration
- **122k+ Q&A Pairs**: From clinical texts like "Sims' Symptoms in the Mind".
- **Semantic Search**: ChromaDB for instant local retrieval using `nomic-embed-text` embeddings.
- **Local Vector DB**: Fully offline, no internet connection required to query clinical knowledge.

### Multi-Domain Pattern Analysis
When analysis is triggered, LLM2 identifies patterns across:
- Emotional Themes: Mood states, anhedonia, emotional regulation
- Thinking Patterns: Rumination, catastrophizing, intrusive thoughts
- Behavioral Patterns: Sleep, appetite, social withdrawal, self-care
- Interpersonal Dynamics: Relationship patterns, social functioning
- Stressors: Identified triggers and life challenges
- Unclear Areas: Information gaps for targeted exploration
- **Risk Assessment**: Continuous safety monitoring and flagging.
- Protective Factors: Patient strengths and resources.

### Session Management & Patient Profiles
- **Patient Dashboard**: Create and select patient profiles.
- **Persistent Memory**: SQLite backing tracks past session summaries and integrates them into future contexts.
- **Risk Flagging**: Proactive keyword and NLU-based safety guardrails.

### Production-Grade UI
- Tailwind CSS Styling: Modern, responsive design.
- Real-time Feedback: Typing indicators, recording animations.
- Accessibility: WCAG-compliant with keyboard navigation.

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                       Frontend (Browser)                           │
│  - HTML5 Tailwind UI (Dashboard + Chat)                            │
│  - Web Audio API (Microphone)                                      │
│  - Web Speech API (TTS)                                            │
└────────────────────┬───────────────────────────────────────────────┘
                     │ HTTP/WebSocket
                     ▼
┌────────────────────────────────────────────────────────────────────┐
│              FastAPI Backend (0.0.0.0:7860)                        │
│  - Session Management (SQLite memory_store)                        │
│  - Request/Response Routing                                        │
└──────┬──────────────────────────────────────────────────────┬──────┘
       │                                                      │
       ▼                                                      ▼
  ┌─────────────┐                                  ┌──────────────────┐
  │  FunASR     │                                  │     Ollama       │
  │   (Local)   │                                  │   (Local LLM)    │
  │ SenseVoice  │                                  │                  │
  │ STT+Emotion │                                  │  • LLM1          │
  └─────────────┘                                  │  • LLM2          │
                                                   └────────┬─────────┘
                                                            │
                                                   ┌────────▼───────────┐
                                                   │      ChromaDB      │
                                                   │    (Local Vector)  │
                                                   │  • 122k+ embeddings│
                                                   │  • nomic-embed-text│
                                                   └────────────────────┘
```

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend Framework** | FastAPI | RESTful API, async processing |
| **LLM Inference** | Ollama | Local LLM hosting |
| **LLM Models** | phi4-mini & qwen2.5:7b-instruct | Language understanding & generation |
| **Vector Database** | ChromaDB | Local semantic search |
| **Embeddings** | nomic-embed-text | Local text vectorization |
| **Speech Recognition** | SenseVoice-Small (FunASR) | Audio transcription and emotion detection |
| **Frontend Framework** | HTML5 + Tailwind CSS + Vanilla JS | Responsive UI |
| **Storage** | SQLite | Persistent session and patient profiles |

---

## Prerequisites

### Required
- **Python 3.11+**
- **Ollama** installed on your machine.
- **FFmpeg** (for audio processing).

### Ollama Setup
Before running the application, ensure Ollama is running and pull the necessary models:
```bash
ollama run phi4-mini
ollama run qwen2.5:7b-instruct
ollama run nomic-embed-text
```

### Environment Configuration
Configure your local environment using a `.env` file based on your machine's capabilities.
```env
OLLAMA_HOST=http://localhost:11434
LLM1_MODEL=phi4-mini
LLM2_MODEL=qwen2.5:7b-instruct
EMBEDDING_MODEL=nomic-embed-text
MEMORY_DB_PATH=./data/serinity.db
```

---

## Getting Started

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Amogh1221/Mental_HealthCare_VoiceAssistant.git
   cd Mental_HealthCare_VoiceAssistant
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r Requirements.txt
   ```

4. **Initialize the Vector Database:**
   (Ensure you run this once before starting the server to populate ChromaDB)
   ```bash
   python built_vectorDB.py
   ```

5. **Start the FastAPI server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 7860
   ```

6. **Access the application:**
   Open your browser and navigate to `http://localhost:7860`.

---

## Disclaimer
This application is for educational and research purposes only. It is not intended to be a substitute for professional medical advice, diagnosis, or treatment. Always seek the advice of a qualified health provider with any questions you may have regarding a medical condition.
