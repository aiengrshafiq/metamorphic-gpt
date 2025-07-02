# scripts/ingest.py

import os
import json
from datetime import datetime
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, UnstructuredWordDocumentLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Qdrant
from dotenv import load_dotenv

# --- CONFIGURATION ---
# Load environment variables from .env file
load_dotenv()

DOCUMENTS_PATH = "documents/"
PROCESSED_FILES_LOG = "data/processed_files.json"
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")

# --- HELPER FUNCTIONS ---

def load_processed_files_log():
    """
    Loads the log of processed files from a JSON file.
    Handles cases where the file doesn't exist, is empty, or is corrupted.
    """
    log_path = Path(PROCESSED_FILES_LOG)
    
    if not log_path.exists():
        # Create the data directory if it doesn't exist
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return {}
        
    # Check if the file is empty
    if log_path.stat().st_size == 0:
        return {}
        
    with open(log_path, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            # If file is corrupted or malformed, treat as empty and let the script rebuild it.
            print(f"Warning: Could not decode {PROCESSED_FILES_LOG}. Treating as empty. A new log will be created.")
            return {}

def save_processed_files_log(log_data):
    """Saves the log of processed files to a JSON file."""
    with open(PROCESSED_FILES_LOG, 'w') as f:
        json.dump(log_data, f, indent=4)

def has_file_changed(filepath, log_data):
    """Checks if a file is new or has been modified since the last processing."""
    last_modified_time = os.path.getmtime(filepath)
    if filepath not in log_data:
        return True  # New file
    if last_modified_time > log_data[filepath]['last_modified']:
        return True  # File has been updated
    return False

# --- CORE INGESTION LOGIC ---

def get_documents_to_process(force_reingest=False):
    """
    Scans the documents directory and identifies files that need to be processed.
    Extracts metadata (department, role) from the folder structure.
    Example path: documents/sales/general/sales_playbook.pdf
    - department: sales
    - role: general
    """
    files_to_process = []
    processed_log = load_processed_files_log()
    
    for root, _, files in os.walk(DOCUMENTS_PATH):
        for filename in files:
            if not filename.endswith(('.pdf', '.docx')):
                continue

            filepath = os.path.join(root, filename)
            
            if force_reingest or has_file_changed(filepath, processed_log):
                try:
                    path_parts = Path(filepath).parts
                    # documents, department, role, filename.docx
                    if len(path_parts) >= 4:
                        department = path_parts[1]
                        role = path_parts[2]
                        metadata = {"department": department, "role": role, "source": filepath}
                        files_to_process.append({"path": filepath, "metadata": metadata})
                    else:
                        print(f"Skipping {filepath}: Does not match expected directory structure 'documents/department/role/file'.")
                except IndexError:
                    print(f"Warning: Could not extract metadata from path: {filepath}")

    return files_to_process

def load_and_split_documents(files_to_process):
    """Loads documents using appropriate loaders and splits them into chunks."""
    all_docs = []
    for file_info in files_to_process:
        filepath = file_info['path']
        metadata = file_info['metadata']
        
        if filepath.endswith(".pdf"):
            loader = PyPDFLoader(filepath)
        elif filepath.endswith(".docx"):
            loader = UnstructuredWordDocumentLoader(filepath)
        else:
            continue
            
        docs = loader.load()
        
        # Add the extracted metadata to each document chunk
        for doc in docs:
            doc.metadata.update(metadata)
            
        all_docs.extend(docs)

    # Split documents into smaller chunks for better retrieval
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    return text_splitter.split_documents(all_docs)

def main(force_reingest=False):
    """Main function to run the entire ingestion pipeline."""
    print("Starting document ingestion process...")
    
    files_to_process = get_documents_to_process(force_reingest)
    
    if not files_to_process:
        print("No new or updated documents to process.")
        return

    print(f"Found {len(files_to_process)} documents to process.")
    
    # 1. Load and Split Documents
    print("Loading and splitting documents...")
    split_docs = load_and_split_documents(files_to_process)
    
    if not split_docs:
        print("No content could be extracted from the documents.")
        return

    print(f"Created {len(split_docs)} text chunks.")

    # 2. Initialize Embeddings and Vector Store
    print("Initializing embeddings model and vector store...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # 3. Embed and Store Documents in Qdrant
    print(f"Embedding documents and storing in Qdrant collection: '{QDRANT_COLLECTION_NAME}'...")
    Qdrant.from_documents(
        documents=split_docs,
        embedding=embeddings,
        url=QDRANT_URL,
        api_key=os.getenv("QDRANT_API_KEY"),
        collection_name=QDRANT_COLLECTION_NAME,
        force_recreate=force_reingest, # Recreate collection if forcing re-ingestion of all docs
    )
    
    # 4. Update the processed files log
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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-ingestion of all documents, even if they haven't changed."
    )
    args = parser.parse_args()
    
    main(force_reingest=args.force)