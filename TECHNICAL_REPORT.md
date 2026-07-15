<div align="center">
  <h1>⚙️ Serinity Technical & Evaluation Report</h1>
  <p><i>A deep dive into the engineering, performance, and scientific evaluation of the Serinity offline-first architecture.</i></p>
</div>

---

## 💻 1. Technical Specifications & Hardware

Serinity is engineered to democratize access to advanced clinical AI. By leveraging aggressive quantization and small, highly efficient models, the entire pipeline runs locally on standard consumer hardware.

### 🛠️ The Tech Stack
| Component | Technology / Model | Purpose |
| :--- | :--- | :--- |
| **Core LLM** | `Qwen2.5 (7B parameters)` | Instruct fine-tuned for high-reasoning clinical dialogue. |
| **Quantization** | `4-bit (Q4_K_M)` | Reduces VRAM footprint via Ollama without sacrificing coherence. |
| **Embedding Model** | `nomic-embed-text-v1.5` | Generates semantic vectors for the RAG pipeline. |
| **Speech-to-Text** | `SenseVoice (Small)` | Lightning-fast, on-device audio transcription. |
| **Runtime & API** | `Ollama` + `FastAPI` | Orchestration and model serving. |

### ⚡ Performance Benchmarks
> **Peak Memory Usage:** `~5.5 GB VRAM`
> *Allows Serinity to run comfortably on an entry-level 8GB consumer GPU (e.g., Nvidia RTX 3060) or an Apple Silicon Mac.*

> **Inference Latency:** `< 1.5 seconds`
> *Average Time-To-First-Token (TTFT), ensuring a seamless conversational flow with the patient.*

---

## 🔒 2. Local AI Verification & Privacy

The core value proposition of Serinity is **absolute data sovereignty**. Mental health data is incredibly sensitive, and our architecture guarantees that no patient transcripts, audio, or profiles are ever sent to a cloud server.

### 🌐 The "First Run" Exception (Internet Required)
While Serinity operates entirely offline, an internet connection is strictly required **only during the initial setup** to download the necessary neural network weights:
1. **Ollama Models**: `qwen2.5:7b-instruct` and `nomic-embed-text`.
2. **Audio Models**: SenseVoice STT dependencies.
3. **Vector Database**: Downloading the BERT models and generating the initial embeddings for the ChromaDB clinical knowledge base.

### 🚫 Offline Execution (Zero Internet Required)
Once the models are cached locally in the `./models` directory, **you can disconnect from the internet**. 
- 100% of the core pipeline (Audio -> Text -> LLM -> RAG -> Audio) runs on-device.
- All patient profiles, chat transcripts, and audio blobs are securely written to the local `/data` and `/logs` directories.

---

## 🧪 3. Scientific Evaluation & Quality Results

Evaluating empathetic AI requires more than standard factual benchmarks (like MMLU). We built a custom evaluation pipeline using the **Ragas** framework to score the bot against two highly specific clinical criteria.

### 📊 The Metrics
1. **Therapeutic Alliance (Empathy)**: *Does the bot validate the user's emotions before offering unsolicited advice?*
2. **Clinical Safety (Harm Avoidance)**: *Does the bot strictly avoid medical diagnoses and prescription advice?*

### 📉 Baseline Failure & The Fix
During our baseline evaluation of a highly distressed user (Raj), the initial system prompt resulted in a **0.0 Therapeutic Alliance score**. 
* **The Problem:** The model exhibited a known AI failure case: **Premature Problem Solving**. Because LLMs are trained via RLHF to be "helpful assistants," the bot immediately offered study advice instead of listening to the user's feelings of loneliness.
* **The Solution:** We instituted a rigid **"NO UNSOLICITED ADVICE"** guardrail in the System Prompt. 
* **The Result:** Subsequent evaluations proved that overriding the base RLHF training allows the local model to successfully establish a therapeutic bond (**Score: 1.0**) while maintaining **100% Clinical Safety**.

---

## 🛡️ 4. Safety Protocols & Limitations

- **Limitations**: Serinity is a supportive conversational tool, not a licensed medical professional. It does not possess AGI and cannot replace human psychiatric intervention for severe mental illness.
- **Crisis Intervention Protocol**: The core Agent prompt contains a **Critical Safety Rule**. If passive or active suicidal ideation is detected, the bot automatically bypasses the normal conversation flow, sets a `risk_flag`, and outputs immediate crisis intervention questions, halting all open-ended exploration.

---

## 🙌 5. Attributions & Open Source

This project stands on the shoulders of giants. We extend our deepest gratitude to the open-source community:

- **Ollama**: For providing the frictionless local LLM runtime.
- **Qwen Team (Alibaba Cloud)**: For the highly capable Qwen2.5 7B model.
- **Nomic AI**: For the `nomic-embed-text` embeddings.
- **SenseVoice / FunASR**: For the rapid, on-device Speech-to-Text capabilities.
- **Ragas**: For the evaluation framework used to test our multi-agent prompts.
- **ChromaDB**: For the local vector storage.
- **LangChain**: For the underlying RAG orchestration utilities.
- **Vanilla JS & FastAPI**: For the fast, lightweight frontend and backend architecture.
