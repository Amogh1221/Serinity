# -*- coding: utf-8 -*-
"""
built_vectorDB.py — Build the local ChromaDB knowledge base for Serinity.

Changes from cloud version:
  - Pinecone → ChromaDB PersistentClient (fully local, no API key)
  - Embeddings via OllamaEmbeddings (nomic-embed-text, local)
  - Added Phase 4.2 filtering: drops rows where medical_context looks like
    generic wellness content rather than psychiatry. Prints a summary so you
    can sanity-check the filter before trusting it.
  - Three indexing modes preserved exactly (assistant_only / qa_pairs / both_separate)

Run once before starting the app:
    python built_vectorDB.py

IMPORTANT: Ollama must be running and nomic-embed-text must be pulled:
    ollama pull nomic-embed-text
"""

import os
import json
from collections import Counter
from datasets import load_dataset
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration from .env
# ---------------------------------------------------------------------------
OLLAMA_HOST        = os.getenv("OLLAMA_HOST",           "http://localhost:11434")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL",       "nomic-embed-text")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR",    "./chroma_db")
CHROMA_COLLECTION  = os.getenv("CHROMA_COLLECTION_NAME","mhcva-knowledge")
DATASET_NAME       = "Compumacy/Psych_data"
BATCH_SIZE         = 100  # smaller batches = Ollama less likely to crash under sustained load

# ---------------------------------------------------------------------------
# Phase 4.2 — Generic wellness filter
# Rows whose medical_context contains any of these substrings (case-insensitive)
# are flagged as off-topic generic wellness content.
# Adjust this list if the summary shows the filter is too aggressive/loose.
# ---------------------------------------------------------------------------
GENERIC_WELLNESS_MARKERS = [
    "general wellness",
    "lifestyle advice",
    "wellness discussion",
    "healthy habits",
    "nutrition",
    "exercise tips",
    "sleep hygiene tips",  # keep clinical sleep disorder content, drop generic tips
    "mindfulness general",
    "self-care tips",
]


def _is_generic_wellness(medical_context: str) -> bool:
    """Return True if the row looks like off-topic generic wellness content."""
    if not medical_context:
        return False
    lower = medical_context.lower()
    return any(marker in lower for marker in GENERIC_WELLNESS_MARKERS)


def download_dataset():
    print("📥 Downloading dataset from HuggingFace...")
    ds = load_dataset(DATASET_NAME)
    print(f"✅ Downloaded {len(ds['train']):,} rows.")
    return ds


def filter_and_audit(data):
    """
    Phase 4.2 — Sample medical_context values, drop generic wellness rows,
    and print a summary so the human can sanity-check before committing.
    """
    print("\n🔍 Running corpus quality filter (Phase 4.2)...")

    context_counts = Counter()
    dropped_indices = set()
    dropped_samples = []

    for idx, item in enumerate(tqdm(data, desc="Auditing medical_context")):
        metadata = item.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        ctx = metadata.get("medical_context", "") or ""
        context_counts[ctx] += 1
        if _is_generic_wellness(ctx):
            dropped_indices.add(idx)
            if len(dropped_samples) < 10:
                dropped_samples.append(ctx)

    # Print filter summary
    print(f"\n{'='*60}")
    print(f"CORPUS FILTER SUMMARY")
    print(f"{'='*60}")
    print(f"  Total rows:   {len(data):,}")
    print(f"  Rows dropped: {len(dropped_indices):,} ({100*len(dropped_indices)/len(data):.1f}%)")
    print(f"  Rows kept:    {len(data) - len(dropped_indices):,}")
    print(f"\n  Top 15 medical_context values (before filtering):")
    for ctx, count in context_counts.most_common(15):
        label = ctx[:60] + "..." if len(ctx) > 60 else ctx
        flag = " ← DROPPED" if _is_generic_wellness(ctx) else ""
        print(f"    [{count:>6}] {label}{flag}")
    if dropped_samples:
        print(f"\n  Sample dropped contexts:")
        for s in dropped_samples:
            print(f"    • {s[:80]}")
    print(f"{'='*60}\n")

    return dropped_indices


def create_documents(data, dropped_indices: set, mode: str = "assistant_only"):
    """
    Build Document objects from the dataset.
    Modes: assistant_only | qa_pairs | both_separate
    """
    print(f"📄 Creating documents (mode: {mode}, skipping {len(dropped_indices):,} filtered rows)...")
    documents = []

    for idx, item in enumerate(tqdm(data, desc="Building documents")):
        if idx in dropped_indices:
            continue

        user_msg      = item.get("user_message",    "") or ""
        assistant_msg = item.get("assistant_message","") or ""
        metadata      = item.get("metadata",        {}) or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        doc_metadata = {
            "chunk_id":        idx,
            "source_pdf":      metadata.get("source_pdf",      "unknown"),
            "page_number":     metadata.get("page_number",     -1),
            "confidence_score":metadata.get("confidence_score", 0.0),
            "medical_context": metadata.get("medical_context", ""),
        }

        if mode == "assistant_only":
            if assistant_msg.strip():
                documents.append(Document(page_content=assistant_msg.strip(), metadata=doc_metadata))

        elif mode == "qa_pairs":
            if user_msg and assistant_msg:
                combined = f"Question: {user_msg.strip()}\n\nAnswer: {assistant_msg.strip()}"
                documents.append(Document(page_content=combined, metadata=doc_metadata))

        elif mode == "both_separate":
            if user_msg.strip():
                q_meta = {**doc_metadata, "type": "question"}
                documents.append(Document(page_content=f"Question: {user_msg.strip()}", metadata=q_meta))
            if assistant_msg.strip():
                a_meta = {**doc_metadata, "type": "answer"}
                documents.append(Document(page_content=assistant_msg.strip(), metadata=a_meta))

    print(f"✅ Created {len(documents):,} document objects.")
    return documents


def build_chroma_db(documents: list):
    """
    Push documents to local ChromaDB using Ollama embeddings.
    Resume-capable: checks how many docs are already stored and skips
    those batches so a crashed run can continue where it left off.
    """
    if not documents:
        raise ValueError("No documents to index — check your filter settings.")

    print(f"\n🔧 Initializing OllamaEmbeddings ({EMBEDDING_MODEL})...")
    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_HOST,
        keep_alive=-1,   # keep model loaded for the full run, don't let it time out
    )

    # Verify Ollama is reachable by embedding a test string
    print("🔗 Verifying Ollama connection...")
    test_vec = embeddings.embed_query("test")
    print(f"✅ Embedding model ready (dimension: {len(test_vec)}).")

    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

    # Open (or create) the persistent collection
    vectorstore = Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
    )

    # Resume support: figure out how many docs are already stored
    already_stored = vectorstore._collection.count()
    start_batch    = (already_stored // BATCH_SIZE)
    start_doc      = start_batch * BATCH_SIZE

    if already_stored > 0:
        print(f"\n⏩ Resuming from batch {start_batch} ({already_stored:,} docs already stored).")
        print(f"   Skipping first {start_doc:,} documents.")
    else:
        print(f"\n📦 Pushing to ChromaDB at {CHROMA_PERSIST_DIR} ...")

    print(f"   Collection:     {CHROMA_COLLECTION}")
    print(f"   Total docs:     {len(documents):,}")
    print(f"   Remaining docs: {len(documents) - start_doc:,}")
    print(f"   Batch size:     {BATCH_SIZE}")
    print("   This will take a while (embedding locally)...\n")

    remaining_docs = documents[start_doc:]
    total_batches  = (len(remaining_docs) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in tqdm(range(0, len(remaining_docs), BATCH_SIZE),
                  total=total_batches, desc="Embedding batches"):
        batch = remaining_docs[i : i + BATCH_SIZE]
        vectorstore.add_documents(batch)

    final_count = vectorstore._collection.count()
    print(f"\n✅ ChromaDB build complete! {final_count:,} vectors stored.")
    return vectorstore


def main():
    import sys
    resuming = "--resume" in sys.argv

    print("=" * 60)
    print("  Serinity — LOCAL KNOWLEDGE BASE BUILDER")
    print("  Target: ChromaDB + nomic-embed-text (Ollama)")
    if resuming:
        print("  MODE: RESUME (skipping already-embedded batches)")
    print("=" * 60)

    print("\nChoose indexing mode:")
    print("  1. Assistant messages only (default — cleanest clinical answers)")
    print("  2. Q&A pairs (combined question + answer)")
    print("  3. Both separate (individual question and answer docs)")
    choice = input("\nEnter choice (1/2/3) [1]: ").strip() or "1"
    mode_map = {"1": "assistant_only", "2": "qa_pairs", "3": "both_separate"}
    mode = mode_map.get(choice, "assistant_only")

    try:
        dataset     = download_dataset()
        data        = dataset["train"]
        dropped_idx = filter_and_audit(data)

        if not resuming:
            print("\nProceed with the filter above? (Ctrl+C to abort, Enter to continue)")
            input()
        else:
            print("\n(Resume mode — skipping filter confirmation, using same filter as before.)")

        documents = create_documents(data, dropped_idx, mode=mode)
        build_chroma_db(documents)
        print("\n✅ Knowledge base is ready. Start the app with: uvicorn main:app --reload")
    except KeyboardInterrupt:
        print("\n⚠️  Aborted by user. Run with --resume to continue from where you stopped.")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    main()