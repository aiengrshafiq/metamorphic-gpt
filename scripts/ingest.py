# scripts/ingest.py

import os
import json
from datetime import datetime
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, UnstructuredWordDocumentLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import Qdrant
from qdrant_client import QdrantClient, models
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()

DOCUMENTS_PATH = "documents/"
PROCESSED_FILES_LOG = "data/processed_files.json"
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")

# --- HELPER FUNCTIONS ---

def load_processed_files_log():
    log_path = Path(PROCESSED_FILES_LOG)
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return {}
    if log_path.stat().st_size == 0:
        return {}
    with open(log_path, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode {PROCESSED_FILES_LOG}. Rebuilding log.")
            return {}

def save_processed_files_log(log_data):
    with open(PROCESSED_FILES_LOG, 'w') as f:
        json.dump(log_data, f, indent=4)

def has_file_changed(filepath, log_data):
    last_modified_time = os.path.getmtime(filepath)
    if filepath not in log_data:
        return True
    if last_modified_time > log_data[filepath]['last_modified']:
        return True
    return False

# --- CORE INGESTION LOGIC ---

def get_documents_to_process(force_reingest=False):
    files_to_process = []
    processed_log = load_processed_files_log()
    for root, _, files in os.walk(DOCUMENTS_PATH):
        for filename in files:
            if not filename.endswith(('.pdf', '.docx')):
                continue
            # Normalize path separators for consistency
            filepath = os.path.join(root, filename).replace("\\", "/")
            if force_reingest or has_file_changed(filepath, processed_log):
                try:
                    path_parts = Path(filepath).parts
                    if len(path_parts) >= 4:
                        department = path_parts[1]
                        role = path_parts[2]
                        metadata = {"department": department, "role": role, "source": filepath}
                        files_to_process.append({"path": filepath, "metadata": metadata})
                    else:
                        print(f"Skipping {filepath}: Incorrect directory structure.")
                except IndexError:
                    print(f"Warning: Could not extract metadata from path: {filepath}")
    return files_to_process

def load_and_split_documents(files_to_process):
    all_docs = []
    for file_info in files_to_process:
        filepath = file_info['path']
        metadata = file_info['metadata']
        loader = PyPDFLoader(filepath) if filepath.endswith(".pdf") else UnstructuredWordDocumentLoader(filepath)
        docs = loader.load()
        for doc in docs:
            doc.metadata.update(metadata)
        all_docs.extend(docs)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    return text_splitter.split_documents(all_docs)

def main(force_reingest=False):
    print("Starting document ingestion process...")
    files_to_process = get_documents_to_process(force_reingest)
    
    if not files_to_process:
        print("No new or updated documents to process.")
        return

    print(f"Found {len(files_to_process)} documents to process.")
    print("Loading and splitting documents...")
    split_docs = load_and_split_documents(files_to_process)
    
    if not split_docs:
        print("No content could be extracted.")
        return

    print(f"Created {len(split_docs)} text chunks.")
    print("Initializing embeddings model...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    print(f"Embedding documents and storing in Qdrant collection: '{QDRANT_COLLECTION_NAME}'...")
    Qdrant.from_documents(
        documents=split_docs,
        embedding=embeddings,
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
        collection_name=QDRANT_COLLECTION_NAME,
        force_recreate=force_reingest,
    )
    
    # --- CREATE PAYLOAD INDEX ---
    print("Creating payload index for 'metadata.role'...")
    try:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        client.create_payload_index(
            collection_name=QDRANT_COLLECTION_NAME,
            field_name="metadata.role",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        print("Payload index created successfully.")
    except Exception as e:
        # This might fail if the index already exists, which is okay.
        print(f"Could not create payload index (it may already exist): {e}")

    print("Updating processed files log...")
    processed_log = load_processed_files_log()
    for file_info in files_to_process:
        filepath = file_info['path']
        processed_log[filepath] = {
            'last_modified': os.path.getmtime(filepath),
            'processed_at': datetime.now().isoformat()
        }
    save_processed_files_log(processed_log)
    print("Ingestion process completed successfully!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest documents into the vector store.")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion of all documents.")
    args = parser.parse_args()
    main(force_reingest=args.force)