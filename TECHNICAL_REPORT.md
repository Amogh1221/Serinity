# Serinity Technical & Evaluation Report

This report outlines the technical specifications, evaluation methodologies, privacy protocols, and attributions for the Serinity AI system.

## 1. Technical Specifications & Hardware

Serinity is heavily optimized to run on consumer hardware without relying on cloud APIs.

- **Core LLM**: Qwen2.5 (7B parameters, Instruct fine-tune)
- **Quantization**: 4-bit quantization (via Ollama Q4_K_M) to reduce VRAM requirements while maintaining conversational coherence.
- **Embedding Model**: Nomic-Embed-Text (nomic-ai/nomic-embed-text-v1.5)
- **Speech-to-Text**: SenseVoice (Small/Fast variant for real-time transcription)
- **Runtime Environment**: Ollama (LLM/Embeddings) and Python/FastAPI (Orchestration)
- **Peak Memory Usage**: ~5.5 GB VRAM (allowing it to run on standard 8GB consumer GPUs or unified Apple Silicon memory).
- **Inference Latency**: Average time-to-first-token (TTFT) is < 1.5 seconds on a standard M-series Mac or Nvidia RTX 3060.

## 2. Local AI Verification & Privacy

The core value proposition of Serinity is absolute data sovereignty.

- **What runs locally?** 100% of the core pipeline runs on-device. This includes Speech-to-Text (SenseVoice), all 3 Agentic LLMs (Qwen2.5 via Ollama), and the Vector Database (ChromaDB). 
- **What requires the internet?** The system operates fully offline. Internet is only required during the initial installation to pull the Docker-like model weights via Ollama and `pip install` dependencies.
- **Where is data stored?** All patient profiles, chat transcripts, and audio blobs are stored locally in the `/data` and `/logs` directories on the user's hard drive. No telemetry, logs, or analytics are sent externally.

## 3. Scientific Evaluation & Quality Results

Evaluating empathetic AI requires more than standard factual benchmarks (like MMLU). We built a custom evaluation pipeline using the **Ragas** framework to score the bot against two highly specific clinical criteria:

### Evaluation Metrics
1. **Therapeutic Alliance (Empathy)**: Does the bot validate the user's emotions *before* offering unsolicited advice? 
2. **Clinical Safety (Harm Avoidance)**: Does the bot strictly avoid medical diagnoses and prescription advice?

### Results & Known Failure Cases
During our baseline evaluation of a highly distressed user (Raj), the initial system prompt resulted in a **0.0 Therapeutic Alliance score**. The model exhibited a known failure case: **Premature Problem Solving**. Because LLMs are trained via RLHF to be "helpful assistants," the bot immediately offered study advice instead of listening to the user's feelings of loneliness.

**The Fix:** We instituted a rigid "NO UNSOLICITED ADVICE" guardrail in the System Prompt. Subsequent evaluations proved that overriding the base RLHF training allows the local model to successfully establish a therapeutic bond (Score: 1.0) while maintaining 100% Clinical Safety.

## 4. Safety & Limitations

- **Limitations**: Serinity is a supportive conversational tool, not a licensed medical professional. It does not possess AGI and cannot replace human psychiatric intervention for severe mental illness.
- **Safety Protocol**: The Agent 1 prompt contains a **Critical Safety Rule**. If passive or active suicidal ideation is detected, the bot bypasses normal conversation flow, sets a `risk_flag`, and outputs immediate crisis intervention questions, halting all open-ended exploration.

## 5. Attributions & Open Source

This project would not be possible without the incredible work of the open-source community:

- **Ollama**: For providing the frictionless local LLM runtime.
- **Qwen Team (Alibaba Cloud)**: For the highly capable Qwen2.5 7B model.
- **Nomic AI**: For the `nomic-embed-text` embeddings.
- **SenseVoice / FunASR**: For the rapid, on-device Speech-to-Text capabilities.
- **Ragas**: For the evaluation framework used to test our multi-agent prompts.
- **ChromaDB**: For the local vector storage.
- **LangChain**: For the underlying RAG orchestration utilities.
- **Vanilla JS & HTML**: For the fast, lightweight frontend user interface.
