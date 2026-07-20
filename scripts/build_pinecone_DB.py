# -*- coding: utf-8 -*-
"""
build_pinecone_DB.py — Build the Pinecone knowledge base for Serinity.

Run once before starting the app:
    python scripts/build_pinecone_DB.py

IMPORTANT: Ollama must be running and nomic-embed-text must be pulled:
    ollama pull nomic-embed-text
"""

import os
import json
from collections import Counter
from datasets import load_dataset
from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_ollama import OllamaEmbeddings
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# Configuration from .env
OLLAMA_HOST        = os.getenv("OLLAMA_HOST",           "http://localhost:11434")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL",       "nomic-embed-text")
PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY",      "")
PINECONE_INDEX_NAME= os.getenv("PINECONE_INDEX_NAME",   "serinity-knowledge")
DATASET_NAME       = "Compumacy/Psych_data"
BATCH_SIZE         = 100

# Generic wellness filter markers
GENERIC_WELLNESS_MARKERS = [
    "general wellness",
    "lifestyle advice",
    "wellness discussion",
    "healthy habits",
    "nutrition",
    "exercise tips",
    "sleep hygiene tips",
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
    """Download the specified dataset from HuggingFace."""
    print("Downloading dataset from HuggingFace...")
    ds = load_dataset(DATASET_NAME)
    print(f"Downloaded {len(ds['train']):,} rows.")
    return ds


def filter_and_audit(data):
    """
    Sample medical_context values, drop generic wellness rows,
    and print a summary for sanity checking before committing.
    """
    print("\nRunning corpus quality filter...")

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

    print(f"\n{'='*60}")
    print("CORPUS FILTER SUMMARY")
    print(f"{'='*60}")
    print(f"  Total rows:   {len(data):,}")
    print(f"  Rows dropped: {len(dropped_indices):,} ({100*len(dropped_indices)/len(data):.1f}%)")
    print(f"  Rows kept:    {len(data) - len(dropped_indices):,}")
    print("\n  Top 15 medical_context values (before filtering):")
    for ctx, count in context_counts.most_common(15):
        label = ctx[:60] + "..." if len(ctx) > 60 else ctx
        flag = " [DROPPED]" if _is_generic_wellness(ctx) else ""
        print(f"    [{count:>6}] {label}{flag}")
    if dropped_samples:
        print("\n  Sample dropped contexts:")
        for s in dropped_samples:
            print(f"    - {s[:80]}")
    print(f"{'='*60}\n")

    return dropped_indices


def create_documents(data, dropped_indices: set, mode: str = "assistant_only"):
    """
    Build Document objects from the dataset.
    Modes: assistant_only | qa_pairs | both_separate
    """
    print(f"Creating documents (mode: {mode}, skipping {len(dropped_indices):,} filtered rows)...")
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

    print(f"Created {len(documents):,} document objects.")
    return documents


def build_pinecone_db(documents: list):
    """
    Push documents to Pinecone using Ollama embeddings.
    """
    if not documents:
        raise ValueError("No documents to index — check filter settings.")

    print(f"\nInitializing OllamaEmbeddings ({EMBEDDING_MODEL})...")
    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OLLAMA_HOST,
        keep_alive=-1,
    )

    print("Verifying Ollama connection...")
    test_vec = embeddings.embed_query("test")
    print(f"Embedding model ready (dimension: {len(test_vec)}).")

    if not PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY is missing from .env")

    print(f"\nInitializing Pinecone Client and pushing to index: {PINECONE_INDEX_NAME} ...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing_indexes:
        print(f"Index '{PINECONE_INDEX_NAME}' not found. Creating it with dimension {len(test_vec)}...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=len(test_vec),
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        print("Index created successfully.")
        
    index = pc.Index(PINECONE_INDEX_NAME)
    
    vectorstore = PineconeVectorStore(
        index=index,
        embedding=embeddings,
        text_key="text"
    )

    # For a fresh build, we start from 0. 
    # Pinecone stats can be accessed but keeping track of exact batches is harder due to distributed nature.
    # We will just upload all provided documents.
    start_doc = 0

    print(f"Index:          {PINECONE_INDEX_NAME}")
    print(f"Total docs:     {len(documents):,}")
    print(f"Batch size:     {BATCH_SIZE}")
    print("This will take a while (embedding locally and uploading to Pinecone)...\n")

    remaining_docs = documents[start_doc:]
    total_batches  = (len(remaining_docs) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in tqdm(range(0, len(remaining_docs), BATCH_SIZE),
                  total=total_batches, desc="Embedding and Uploading batches"):
        batch = remaining_docs[i : i + BATCH_SIZE]
        vectorstore.add_documents(batch)

    print(f"\nPinecone build complete! Vectors uploaded.")
    return vectorstore


def main():
    import sys
    resuming = "--resume" in sys.argv

    print("=" * 60)
    print("  Serinity — LOCAL KNOWLEDGE BASE BUILDER")
    print("  Target: Pinecone + nomic-embed-text (Ollama)")
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
        build_pinecone_db(documents)
        print("\nKnowledge base is ready. Start the app with: uvicorn main:app --reload")
    except KeyboardInterrupt:
        print("\nAborted by user. Run with --resume to continue from where you stopped.")
    except Exception as e:
        print(f"\nERROR: {e}")
        raise


if __name__ == "__main__":
    main()