# server.py
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os, tempfile
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional
import jwt

load_dotenv()

# LangSmith tracing (optional - for monitoring)
LANGCHAIN_TRACING = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
if LANGCHAIN_TRACING:
    print("✅ LangSmith tracing enabled")
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "PadhAI-RAG")
else:
    print("⚠️  LangSmith tracing disabled (set LANGCHAIN_TRACING_V2=true to enable)")

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "https://padh-ai-pro.vercel.app",  # Production
        "https://*.vercel.app"  # All Vercel preview deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase setup
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Service role key bypasses RLS
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

# Validate required environment variables
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL must be set in .env file")

# Use service role key for backend operations (bypasses RLS)
# This is safe because we validate user_id from JWT token
SUPABASE_KEY = SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY

if not SUPABASE_KEY:
    raise ValueError("Either SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY must be set")

if not SUPABASE_JWT_SECRET:
    print("WARNING: SUPABASE_JWT_SECRET not set. Using anon key for development.")
    SUPABASE_JWT_SECRET = SUPABASE_ANON_KEY

if SUPABASE_SERVICE_KEY:
    print("✅ Using Supabase Service Role Key (RLS bypassed)")
else:
    print("⚠️  Using Supabase Anon Key (RLS policies apply)")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

INDEX_DIR = "./data/indexes"  # Local storage for FAISS indexes

# Pydantic models
class IndexRequest(BaseModel):
    folder_name: str

class ChatRequest(BaseModel):
    folder_name: str
    query: str

# Authentication dependency
def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """Extract user_id from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    
    token = authorization.split(" ")[1]
    
    try:
        # Decode JWT token
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(500, "Server configuration error: JWT secret not configured")
        
        payload = jwt.decode(
            token, 
            str(SUPABASE_JWT_SECRET),  # Ensure it's a string
            algorithms=["HS256"], 
            audience="authenticated"
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token: no user ID")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Authentication error: {str(e)}")

# ----------------- Index Folder from Supabase -----------------
@app.post("/index_folder")
def index_folder(request: IndexRequest, user_id: str = Depends(get_current_user)):
    """
    Download PDFs from Supabase Storage and create FAISS index
    Path in Supabase: {user_id}/{folder_name}/files.pdf
    """
    folder_name = request.folder_name
    
    try:
        # List all files in the user's folder from Supabase Storage
        # Path format: user_id/folder_name
        folder_path = f"{user_id}/{folder_name}"
        
        # List files - Supabase Python SDK requires path parameter
        try:
            files_list = supabase.storage.from_("folders").list(path=folder_path)
        except Exception as list_error:
            print(f"Error listing files: {list_error}")
            # Try alternative method
            files_list = supabase.storage.from_("folders").list(folder_path)
        
        # Debug logging
        print(f"User ID: {user_id}")
        print(f"Folder name: {folder_name}")
        print(f"Looking for files in path: {folder_path}")
        print(f"Files found: {files_list}")
        print(f"Number of files: {len(files_list) if files_list else 0}")
        
        if not files_list or len(files_list) == 0:
            raise HTTPException(404, f"No files found in folder '{folder_name}'. Path checked: {folder_path}. Make sure files are uploaded to the correct location.")
        
        # Filter PDF files only
        pdf_files = [f for f in files_list if f.get("name", "").lower().endswith(".pdf")]
        
        if not pdf_files:
            raise HTTPException(404, f"No PDF files found in folder '{folder_name}'")
        
        docs = []
        
        # Download and process each PDF
        for file_obj in pdf_files:
            file_name = file_obj.get("name")
            if file_name == ".placeholder":
                continue
                
            file_path = f"{folder_path}/{file_name}"
            
            # Download file from Supabase Storage
            file_data = supabase.storage.from_("folders").download(file_path)
            
            # Save temporarily to process with PyPDFLoader
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            
            try:
                # Load PDF
                loader = PyPDFLoader(tmp_path)
                docs += loader.load()
            finally:
                # Clean up temp file
                os.unlink(tmp_path)
        
        if not docs:
            raise HTTPException(400, "No content extracted from PDFs")
        
        # Split documents into chunks
        # Larger chunks = more context but less precise
        # Smaller chunks = more precise but may miss context
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,  # Increased for better context
            chunk_overlap=300,  # Increased overlap to maintain continuity
            separators=["\n\n", "\n", ". ", " ", ""]  # Split on natural boundaries
        )
        chunks = splitter.split_documents(docs)
        
        # Create embeddings and FAISS index
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        vectorstore = FAISS.from_documents(chunks, embeddings)
        
        # Save FAISS index locally
        index_path = os.path.join(INDEX_DIR, user_id)
        os.makedirs(index_path, exist_ok=True)
        vectorstore.save_local(os.path.join(index_path, f"{folder_name}_faiss"))
        
        return {
            "status": "indexed",
            "folder": folder_name,
            "files_processed": len(pdf_files),
            "chunks_created": len(chunks)
        }
        
    except Exception as e:
        raise HTTPException(500, f"Error indexing folder: {str(e)}")

# ----------------- Chat with Folder Documents -----------------
@app.post("/chat")
def chat(request: ChatRequest, user_id: str = Depends(get_current_user)):
    """
    Chat with documents in a specific folder using RAG
    """
    folder_name = request.folder_name
    query_text = request.query
    
    if not query_text:
        raise HTTPException(400, "Query text is required")
    
    # Check if folder is indexed
    index_path = os.path.join(INDEX_DIR, user_id, f"{folder_name}_faiss")
    if not os.path.exists(index_path):
        raise HTTPException(404, f"Folder '{folder_name}' not indexed yet. Please index it first.")
    
    try:
        # Load FAISS index
        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        vectorstore = FAISS.load_local(
            index_path, 
            embeddings,
            allow_dangerous_deserialization=True  # ⚠ Only safe for your own files
        )
        # Retrieve more chunks for better context
        # k=10 means top 10 most relevant chunks will be used
        retriever = vectorstore.as_retriever(
            search_type="similarity",  # or "mmr" for diversity
            search_kwargs={
                "k": 10,  # Increased from 6 to 10 for more context
                "fetch_k": 20  # Fetch 20, then filter to top 10
            }
        )
        
        # Initialize LLM
        llm = ChatGroq(
            model="deepseek-r1-distill-llama-70b",
            temperature=0,  # 0 for factual, 0.7 for creative
            max_tokens=None,
            reasoning_format="parsed",
            timeout=None,
            max_retries=2,
        )
        
        # Custom prompt template for better accuracy
        prompt_template = """You are an expert AI tutor helping students understand their study materials. 
Use the following context from the student's documents to answer their question accurately and comprehensively.

Context from documents:
{context}

Student's Question: {question}

Instructions:
1. Answer based ONLY on the provided context
2. If the answer isn't in the context, say "I don't have enough information in your documents to answer this question."
3. Cite specific details from the context when possible
4. Explain concepts clearly and break down complex topics
5. Use examples from the documents if available
6. If relevant, mention which part of the document the information comes from

Answer:"""

        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )
        
        # Create QA chain with custom prompt
        qa = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",  # "stuff" puts all context in one prompt
            retriever=retriever,
            return_source_documents=False,
            chain_type_kwargs={"prompt": PROMPT}
        )
        
        answer = qa.run(query_text)
        
        return {
            "answer": answer,
            "folder": folder_name,
            "user_id": user_id
        }
        
    except Exception as e:
        raise HTTPException(500, f"Error processing chat: {str(e)}")

# ----------------- Get User's Folders -----------------
@app.get("/folders")
def get_folders(user_id: str = Depends(get_current_user)):
    """
    Get list of folders for the current user from Supabase Storage
    """
    try:
        files_list = supabase.storage.from_("folders").list(user_id)
        
        # Filter out files, keep only folders (items with id=None)
        folders = [f.get("name") for f in files_list if f.get("id") is None]
        
        return {"folders": folders, "user_id": user_id}
        
    except Exception as e:
        raise HTTPException(500, f"Error fetching folders: {str(e)}")

# ----------------- Health Check -----------------
@app.get("/")
def health_check():
    return {"status": "ok", "service": "PadhAI RAG API"}

# ----------------- Debug: List All Files -----------------
@app.get("/debug/list_storage/{user_folder}")
def debug_list_storage(user_folder: str, user_id: str = Depends(get_current_user)):
    """Debug endpoint to see what's in storage"""
    try:
        # Try listing at root
        root_files = supabase.storage.from_("folders").list()
        
        # Try listing user folder
        user_files = supabase.storage.from_("folders").list(user_id)
        
        # Try listing specific folder
        folder_files = supabase.storage.from_("folders").list(f"{user_id}/{user_folder}")
        
        return {
            "user_id": user_id,
            "folder": user_folder,
            "root_files": root_files,
            "user_files": user_files,
            "folder_files": folder_files
        }
    except Exception as e:
        return {"error": str(e)}
