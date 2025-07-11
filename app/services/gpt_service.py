# app/services/gpt_service.py
from operator import itemgetter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import Qdrant
from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.core.config import settings

class GPTService:
    def __init__(self):
        """Initializes the GPT service with all necessary components."""
        self.model = ChatOpenAI(
            model="gpt-4o",
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=0.1
        )
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        self.qdrant_client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        self.vector_store = Qdrant(
            client=self.qdrant_client,
            collection_name=settings.QDRANT_COLLECTION_NAME,
            embeddings=self.embeddings
        )
        
        self.prompt_template = self._create_prompt_template()
        self.rag_chain = self._create_rag_chain()

    def _create_prompt_template(self):
        template = """
You are the Metamorphic GPT, a highly specialized AI assistant for Metamorphic LLC employees.
Your purpose is to provide clear, accurate, and compliant answers based *only* on the provided official company documents.
You must adhere to the company's core values in your tone and responses.

**Core Values:**
{core_values}

**Instructions:**
1. Analyze the user's question and the provided context (SOPs).
2. Formulate a direct and helpful answer using *only* the information from the context.
3. If the context does not contain the answer, you MUST state: "I could not find information on this topic in the available company documents. Please consult your manager or the relevant department."
4. DO NOT invent information or use external knowledge.
5. At the end of your answer, cite the source document(s) from the context metadata.

---
**Context (Relevant SOPs):**
{context}
---

**User's Question:**
{question}

**Compliant Answer:**
"""
        return PromptTemplate(
            template=template,
            input_variables=["context", "question", "core_values"]
        )

    def _get_retriever(self, user_role: str):
        role_filter = Filter(
            should=[
                FieldCondition(key="metadata.role", match=MatchValue(value=user_role)),
                FieldCondition(key="metadata.role", match=MatchValue(value="general"))
            ]
        )
        return self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={'k': 4, 'filter': role_filter}
        )

    def _create_rag_chain(self):
        
        def format_docs(docs):
            """
            This robust version handles both Document objects and dictionaries.
            """
            formatted_strings = []
            for doc in docs:
                # Check if the item is a Document object
                if isinstance(doc, Document):
                    metadata = doc.metadata
                    page_content = doc.page_content
                # Check if the item is a dictionary
                elif isinstance(doc, dict):
                    metadata = doc.get('metadata', {})
                    page_content = doc.get('page_content', '')
                else:
                    # Skip any other unexpected types
                    continue
                
                source = metadata.get('source', 'N/A')
                formatted_strings.append(f"Source: {source}\n\nContent: {page_content}")
            
            return "\n\n---\n\n".join(formatted_strings)

        def get_retrieved_docs(input_dict):
            retriever = self._get_retriever(input_dict["user_role"])
            return retriever.invoke(input_dict["question"])

        chain = (
            {
                "context": RunnableLambda(get_retrieved_docs) | RunnableLambda(format_docs),
                "question": itemgetter("question"),
                "core_values": itemgetter("core_values"),
            }
            | self.prompt_template
            | self.model
            | StrOutputParser()
        )
        return chain

    def get_answer(self, query: str, user_role: str = "general"):
        print(f"[GPTService] RAG chain input → role={user_role}, query={query}")
        response = self.rag_chain.invoke({
            "question": query,
            "user_role": user_role,
            "core_values": settings.METAMORPHIC_CORE_VALUES
        })
        return response

gpt_service = GPTService()