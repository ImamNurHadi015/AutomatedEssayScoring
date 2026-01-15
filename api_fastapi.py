#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FastAPI untuk Automated Essay Scoring System
Migrasi dari Flask ke FastAPI dengan Pydantic validation dan async support
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import certifi
from bson.objectid import ObjectId

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AES-API-FastAPI")

# Import modul AES
current_dir = Path(__file__).parent.absolute()
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from aes_system_full import (
    DocumentProcessor, BM25Retriever, LlamaModelCpp, 
    AnswerEvaluator, DenseRetriever, HybridRetriever, CachedEvaluator
)

# Inisialisasi FastAPI app
app = FastAPI(
    title="Automated Essay Scoring System API",
    description="API untuk sistem penilaian otomatis jawaban siswa menggunakan LLM dan RAG",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Dalam production, ganti dengan domain spesifik
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== PYDANTIC MODELS ====================

class StudentBase(BaseModel):
    name: str = Field(..., min_length=1, description="Nama siswa")
    nis: str = Field(..., min_length=1, description="Nomor Induk Siswa")
    kelas: Optional[str] = Field(None, description="Kelas siswa")

class StudentCreate(StudentBase):
    pass

class StudentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    nis: Optional[str] = Field(None, min_length=1)
    kelas: Optional[str] = None

class StudentResponse(StudentBase):
    id: str = Field(..., description="ID siswa")
    created_at: str = Field(..., description="Timestamp pembuatan")

    class Config:
        schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Ahmad Fauzi",
                "nis": "1001",
                "kelas": "X-A",
                "created_at": "2024-01-01T10:00:00"
            }
        }

class ExamBase(BaseModel):
    title: str = Field(..., min_length=1, description="Judul ujian")
    description: Optional[str] = Field("", description="Deskripsi ujian")

class ExamCreate(ExamBase):
    pass

class ExamUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None

class ExamResponse(ExamBase):
    id: str = Field(..., description="ID ujian")
    created_at: str = Field(..., description="Timestamp pembuatan")
    question_count: Optional[int] = Field(0, description="Jumlah pertanyaan")

class QuestionBase(BaseModel):
    question_text: str = Field(..., min_length=1, description="Teks pertanyaan")
    question_type: Optional[str] = Field("panjang", description="Tipe soal: 'singkat' atau 'panjang'")

class QuestionCreate(QuestionBase):
    pass

class QuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=1)
    question_type: Optional[str] = None

class QuestionResponse(QuestionBase):
    id: str = Field(..., description="ID pertanyaan")
    exam_id: str = Field(..., description="ID ujian")
    created_at: str = Field(..., description="Timestamp pembuatan")
    max_score: int = Field(..., description="Skor maksimal")
    allowed_scores: List[int] = Field(..., description="Daftar skor yang diperbolehkan")
    answer_count: Optional[int] = Field(0, description="Jumlah jawaban")

class AnswerBase(BaseModel):
    question_id: str = Field(..., description="ID pertanyaan")
    answer_text: str = Field(..., min_length=1, description="Teks jawaban siswa")
    student_name: Optional[str] = Field(None, description="Nama siswa")
    student_id: Optional[str] = Field(None, description="ID siswa")
    session_id: Optional[str] = Field(None, description="ID sesi ujian")

class AnswerCreate(AnswerBase):
    pass

class AnswerResponse(BaseModel):
    id: str = Field(..., description="ID jawaban")
    question_id: str = Field(..., description="ID pertanyaan")
    student_name: str = Field(..., description="Nama siswa")
    answer_text: str = Field(..., description="Teks jawaban")
    score: Optional[int] = Field(None, description="Skor yang diberikan")
    evaluation: Optional[str] = Field(None, description="Evaluasi dari sistem")
    references: Optional[List[str]] = Field([], description="Referensi yang digunakan")
    created_at: str = Field(..., description="Timestamp pembuatan")
    evaluated_at: Optional[str] = Field(None, description="Timestamp evaluasi")
    question_type: str = Field(..., description="Tipe soal")
    max_score: int = Field(..., description="Skor maksimal")
    allowed_scores: List[int] = Field(..., description="Daftar skor yang diperbolehkan")

class SessionCreate(BaseModel):
    exam_id: Optional[str] = Field(None, description="ID ujian utama")
    exam_ids: Optional[List[str]] = Field([], description="Daftar ID ujian")
    student_ids: Optional[List[str]] = Field([], description="Daftar ID siswa")
    total_students: Optional[int] = Field(0, description="Jumlah siswa")

class SessionResponse(BaseModel):
    id: str
    session_code: str
    exam_id: str
    exam_title: str
    exams: List[Dict[str, Any]]
    students: List[Dict[str, Any]]
    total_students: int
    current_student: Optional[Dict[str, Any]]
    current_student_index: int
    current_exam_index: int
    is_completed: bool
    created_at: str

class CompareRAGRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Pertanyaan untuk dibandingkan")

class HealthResponse(BaseModel):
    status: str = Field("ok", description="Status kesehatan API")
    message: str = Field("API berjalan dengan baik", description="Pesan status")

# ==================== MONGODB CONNECTION ====================

try:
    mongo_uri = "mongodb+srv://adigaming015:1qGGJATMGcnSgygS@cluster0.wzzqu4l.mongodb.net/?retryWrites=true&w=majority"
    
    ssl_configs = [
        {
            "name": "Server API v1 dengan CA bundle",
            "config": {
                "server_api": ServerApi('1'),
                "tls": True,
                "tlsCAFile": certifi.where(),
                "retryWrites": True,
                "serverSelectionTimeoutMS": 15000,
                "connectTimeoutMS": 30000,
                "socketTimeoutMS": 30000,
            }
        },
        {
            "name": "Tanpa Server API, SSL permisif",
            "config": {
                "tls": True,
                "tlsAllowInvalidCertificates": True,
                "tlsAllowInvalidHostnames": True,
                "retryWrites": True,
                "serverSelectionTimeoutMS": 20000,
                "connectTimeoutMS": 30000,
                "socketTimeoutMS": 30000,
            }
        },
        {
            "name": "Tanpa SSL (fallback)",
            "config": {
                "tls": False,
                "retryWrites": True,
                "serverSelectionTimeoutMS": 20000,
                "connectTimeoutMS": 30000,
                "socketTimeoutMS": 30000,
            }
        }
    ]
    
    client = None
    for config in ssl_configs:
        try:
            logger.info(f"Mencoba konfigurasi: {config['name']}")
            client = MongoClient(mongo_uri, **config['config'])
            client.admin.command({"ping": 1})
            logger.info(f"Koneksi MongoDB Atlas berhasil dengan konfigurasi: {config['name']}")
            break
        except Exception as e:
            logger.warning(f"Konfigurasi {config['name']} gagal: {e}")
            if client:
                client.close()
            continue
    
    if not client:
        raise Exception("Semua konfigurasi SSL gagal")
    
    db = client["aes_database"]
    logger.info("Menggunakan database MongoDB Atlas: aes_database")
    
    collection_names = db.list_collection_names()
    logger.info(f"Koleksi yang tersedia di MongoDB Atlas: {collection_names}")
    
    try:
        exams_count = db.exams.count_documents({})
        questions_count = db.questions.count_documents({})
        students_count = db.students.count_documents({})
        logger.info(f"MongoDB Atlas - Jumlah dokumen: Exams: {exams_count}, Questions: {questions_count}, Students: {students_count}")
    except Exception as e:
        logger.warning(f"Gagal mendapatkan jumlah dokumen: {e}")
    
    exams_collection = db["exams"]
    questions_collection = db["questions"]
    sessions_collection = db["sessions"]
    answers_collection = db["answers"]
    students_collection = db["students"]
    
except Exception as e:
    logger.error(f"Koneksi MongoDB Atlas gagal: {e}")
    logger.info("Mencoba fallback ke database lokal...")
    
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        logger.info("Koneksi MongoDB lokal berhasil")
        db = client["aes_database_local"]
        
        exams_collection = db["exams"]
        questions_collection = db["questions"]
        sessions_collection = db["sessions"]
        answers_collection = db["answers"]
        students_collection = db["students"]
        
    except Exception as local_error:
        logger.error(f"Koneksi MongoDB lokal juga gagal: {local_error}")
        logger.error("Aplikasi membutuhkan koneksi database untuk berjalan")
        sys.exit(1)

# ==================== HELPER FUNCTIONS ====================

def get_timestamp() -> str:
    """Mendapatkan timestamp saat ini dalam format ISO"""
    return datetime.utcnow().isoformat()

def normalize_question_type(question_type: Optional[str]) -> str:
    """Normalisasi tipe soal ke nilai standar ('singkat' atau 'panjang')"""
    if not question_type:
        return "panjang"
    normalized = str(question_type).strip().lower()
    if normalized in {"singkat", "short", "isian", "isian singkat"}:
        return "singkat"
    return "panjang"

def get_scoring_defaults(question_type: Optional[str]) -> Dict[str, Any]:
    """Dapatkan konfigurasi skor default berdasarkan tipe soal"""
    normalized = normalize_question_type(question_type)
    if normalized == "singkat":
        return {
            "question_type": "singkat",
            "allowed_scores": [0, 2],
            "max_score": 2
        }
    return {
        "question_type": "panjang",
        "allowed_scores": [1, 2, 3, 4],
        "max_score": 4
    }

def object_id_to_str(obj):
    """Konversi ObjectId menjadi string secara rekursif"""
    if isinstance(obj, dict):
        for key in obj:
            if isinstance(obj[key], ObjectId):
                obj[key] = str(obj[key])
            elif isinstance(obj[key], dict) or isinstance(obj[key], list):
                obj[key] = object_id_to_str(obj[key])
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, ObjectId):
                obj[i] = str(item)
            elif isinstance(item, dict) or isinstance(item, list):
                obj[i] = object_id_to_str(item)
    return obj

def load_question_document(question_id: str) -> Optional[Dict[str, Any]]:
    """Ambil dokumen pertanyaan dari database berdasarkan ID"""
    try:
        question_obj_id = ObjectId(question_id)
        question = questions_collection.find_one({"_id": question_obj_id})
        if question:
            return question
    except Exception:
        pass
    return questions_collection.find_one({"_id": question_id})

# ==================== AES SYSTEM ====================

aes_processor = None
aes_retriever = None
aes_sparse_retriever = None
aes_dpr_retriever = None
aes_model = None
aes_evaluator = None

def initialize_aes() -> bool:
    """Inisialisasi komponen AES"""
    global aes_processor, aes_retriever, aes_sparse_retriever, aes_dpr_retriever, aes_model, aes_evaluator
    
    try:
        pdf_path = os.path.join(current_dir, "BUKU_IPA.pdf")
        model_path = os.path.join(current_dir, "output_classification", "Qwen3-4B-Instruct-Q8_0_finetuned_best.gguf")
        
        if not os.path.exists(pdf_path):
            logger.error(f"File PDF tidak ditemukan: {pdf_path}")
            return False
            
        if not os.path.exists(model_path):
            logger.error(f"File model tidak ditemukan: {model_path}")
            return False
        
        logger.info(f"Memproses dokumen: {pdf_path}")
        aes_processor = DocumentProcessor(pdf_path)
        chunks = aes_processor.chunk_text(chunk_size=500, overlap=50)
        logger.info(f"Dokumen berhasil dibagi menjadi {len(chunks)} chunk")
        
        logger.info("Menginisialisasi BM25 retriever...")
        aes_sparse_retriever = BM25Retriever(chunks)
        
        logger.info("Menginisialisasi DPR retriever...")
        cache_dir = os.path.join(current_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        try:
            rag_model_path = os.path.join(current_dir, "rag_model.pkl")
            
            if os.path.exists(rag_model_path):
                try:
                    logger.info(f"Memuat DPR retriever dari {rag_model_path}...")
                    aes_dpr_retriever = DenseRetriever.load(rag_model_path)
                    
                    if not aes_dpr_retriever:
                        logger.warning("Gagal memuat DPR dari cache, membuat baru...")
                        try:
                            os.remove(rag_model_path)
                        except:
                            pass
                        aes_dpr_retriever = DenseRetriever(chunks, cache_dir=cache_dir)
                        aes_dpr_retriever.save(rag_model_path)
                except Exception as cache_err:
                    logger.warning(f"Error saat memuat dari cache: {cache_err}")
                    try:
                        os.remove(rag_model_path)
                    except:
                        pass
                    aes_dpr_retriever = DenseRetriever(chunks, cache_dir=cache_dir)
                    aes_dpr_retriever.save(rag_model_path)
            else:
                logger.info("Model DPR tidak ditemukan, membuat baru...")
                aes_dpr_retriever = DenseRetriever(chunks, cache_dir=cache_dir)
                aes_dpr_retriever.save(rag_model_path)
        except Exception as e:
            logger.error(f"Error saat inisialisasi DPR: {e}")
            aes_dpr_retriever = None
        
        if aes_dpr_retriever:
            logger.info("Menginisialisasi Hybrid Retriever dengan adaptive alpha...")
            aes_retriever = HybridRetriever(
                sparse_retriever=aes_sparse_retriever,
                dense_retriever=aes_dpr_retriever,
                alpha=0.5,
                use_adaptive=True,
                adaptive_method="confidence"
            )
            logger.info("Hybrid Retriever berhasil diinisialisasi")
        else:
            logger.info("Menggunakan BM25 Retriever (sparse) saja...")
            aes_retriever = aes_sparse_retriever
        
        logger.info(f"Memuat model LLM: {model_path}")
        try:
            aes_model = LlamaModelCpp(
                model_path=model_path,
                n_gpu_layers=999,
                ctx_size=16384
            )
            logger.info("Model LLM berhasil dimuat")
        except Exception as model_err:
            logger.error(f"Error saat memuat model LLM: {model_err}")
            return False
        
        aes_evaluator = CachedEvaluator(aes_model, aes_retriever)
        logger.info("AES system berhasil diinisialisasi dengan CachedEvaluator")
        return True
        
    except Exception as e:
        logger.error(f"Error saat inisialisasi AES: {e}")
        return False

def initialize_template_data():
    """Inisialisasi data template untuk soal dan siswa jika koleksi kosong"""
    try:
        students_data = [
            {"name": "Siswa 1", "nis": "1001", "kelas": "X-A", "created_at": get_timestamp()},
            {"name": "Siswa 2", "nis": "1002", "kelas": "X-A", "created_at": get_timestamp()},
            {"name": "Siswa 3", "nis": "1003", "kelas": "X-B", "created_at": get_timestamp()},
            {"name": "Siswa 4", "nis": "1004", "kelas": "X-B", "created_at": get_timestamp()},
            {"name": "Siswa 5", "nis": "1005", "kelas": "X-C", "created_at": get_timestamp()},
        ]
        
        exam_data = {
            "title": "Ujian IPA Kelas X",
            "description": "Ujian tentang materi dasar IPA untuk kelas X",
            "created_at": get_timestamp()
        }
        
        if students_collection.count_documents({}) == 0:
            logger.info("Menginisialisasi data siswa template...")
            students_collection.insert_many(students_data)
            logger.info(f"Berhasil menambahkan {len(students_data)} data siswa template")
        
        if exams_collection.count_documents({}) == 0:
            logger.info("Menginisialisasi data ujian template...")
            exam_id = exams_collection.insert_one(exam_data).inserted_id
            
            long_defaults = get_scoring_defaults("panjang")
            questions_data = [
                {
                    "exam_id": str(exam_id),
                    "question_text": "Jelaskan proses fotosintesis dan mengapa proses ini penting bagi kehidupan di bumi.",
                    "created_at": get_timestamp(),
                    "question_type": "panjang",
                    "max_score": long_defaults["max_score"],
                    "allowed_scores": long_defaults["allowed_scores"]
                },
                {
                    "exam_id": str(exam_id),
                    "question_text": "Jelaskan perbedaan antara sel hewan dan sel tumbuhan.",
                    "created_at": get_timestamp(),
                    "question_type": "panjang",
                    "max_score": long_defaults["max_score"],
                    "allowed_scores": long_defaults["allowed_scores"]
                },
                {
                    "exam_id": str(exam_id),
                    "question_text": "Jelaskan hukum Newton tentang gerak dan berikan contoh penerapannya dalam kehidupan sehari-hari.",
                    "created_at": get_timestamp(),
                    "question_type": "panjang",
                    "max_score": long_defaults["max_score"],
                    "allowed_scores": long_defaults["allowed_scores"]
                }
            ]
            questions_collection.insert_many(questions_data)
            logger.info(f"Berhasil menambahkan 1 ujian template dengan {len(questions_data)} pertanyaan")
            
        return True
    except Exception as e:
        logger.error(f"Error saat menginisialisasi data template: {e}")
        return False

# ==================== STARTUP & SHUTDOWN ====================

@app.on_event("startup")
async def startup_event():
    """Event yang dijalankan saat aplikasi dimulai"""
    logger.info("🚀 Menginisialisasi sistem AES...")
    success = initialize_aes()
    if success:
        logger.info("✅ Sistem AES berhasil diinisialisasi")
    else:
        logger.warning("⚠️ Gagal menginisialisasi sistem AES")
    
    logger.info("📊 Menginisialisasi data template...")
    template_success = initialize_template_data()
    if template_success:
        logger.info("✅ Data template berhasil diinisialisasi")
    else:
        logger.warning("⚠️ Gagal menginisialisasi data template")

@app.on_event("shutdown")
async def shutdown_event():
    """Event yang dijalankan saat aplikasi dihentikan"""
    logger.info("🛑 Menutup koneksi database...")
    if client:
        client.close()
    logger.info("✅ Koneksi database ditutup")

# ==================== API ENDPOINTS ====================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": "Automated Essay Scoring System API with FastAPI",
        "version": "2.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Endpoint untuk cek kesehatan API"""
    return HealthResponse(status="ok", message="API berjalan dengan baik")

# ==================== STUDENTS ENDPOINTS ====================

@app.get("/api/students", response_model=List[StudentResponse], tags=["Students"])
async def get_students():
    """Mendapatkan daftar semua siswa"""
    try:
        students_cursor = students_collection.find().sort("name", 1)
        students = []
        
        for student in students_cursor:
            students.append(StudentResponse(
                id=str(student["_id"]),
                name=student.get("name", ""),
                nis=student.get("nis", ""),
                kelas=student.get("kelas"),
                created_at=student.get("created_at", get_timestamp())
            ))
            
        return students
    except Exception as e:
        logger.error(f"Error saat mendapatkan daftar siswa: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED, tags=["Students"])
async def create_student(student: StudentCreate):
    """Membuat siswa baru"""
    try:
        # Cek apakah NIS sudah digunakan
        existing = students_collection.find_one({"nis": student.nis})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"NIS '{student.nis}' sudah digunakan oleh siswa lain"
            )
        
        new_student = {
            "name": student.name,
            "nis": student.nis,
            "kelas": student.kelas,
            "created_at": get_timestamp()
        }
        
        result = students_collection.insert_one(new_student)
        
        return StudentResponse(
            id=str(result.inserted_id),
            name=student.name,
            nis=student.nis,
            kelas=student.kelas,
            created_at=new_student["created_at"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat membuat siswa: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/students/{student_id}", response_model=StudentResponse, tags=["Students"])
async def get_student(student_id: str):
    """Mendapatkan detail siswa"""
    try:
        try:
            student_obj_id = ObjectId(student_id)
            student = students_collection.find_one({"_id": student_obj_id})
        except:
            student = students_collection.find_one({"_id": student_id})
            
        if not student:
            raise HTTPException(
                status_code=404,
                detail=f"Siswa dengan ID {student_id} tidak ditemukan"
            )
            
        return StudentResponse(
            id=str(student["_id"]),
            name=student.get("name", ""),
            nis=student.get("nis", ""),
            kelas=student.get("kelas"),
            created_at=student.get("created_at", get_timestamp())
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mendapatkan detail siswa: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/students/{student_id}", response_model=StudentResponse, tags=["Students"])
@app.patch("/api/students/{student_id}", response_model=StudentResponse, tags=["Students"])
async def update_student(student_id: str, student_update: StudentUpdate):
    """Memperbarui data siswa"""
    try:
        try:
            student_obj_id = ObjectId(student_id)
            student = students_collection.find_one({"_id": student_obj_id})
        except:
            student = students_collection.find_one({"_id": student_id})
            
        if not student:
            raise HTTPException(
                status_code=404,
                detail=f"Siswa dengan ID {student_id} tidak ditemukan"
            )
        
        update_data = {}
        
        if student_update.name is not None:
            update_data["name"] = student_update.name
            
        if student_update.nis is not None:
            if student_update.nis != student.get("nis"):
                existing = students_collection.find_one({
                    "nis": student_update.nis,
                    "_id": {"$ne": student["_id"]}
                })
                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail=f"NIS '{student_update.nis}' sudah digunakan oleh siswa lain"
                    )
            update_data["nis"] = student_update.nis
        
        if student_update.kelas is not None:
            update_data["kelas"] = student_update.kelas
            
        if not update_data:
            raise HTTPException(status_code=400, detail="Tidak ada data yang diperbarui")
            
        students_collection.update_one({"_id": student["_id"]}, {"$set": update_data})
        updated_student = students_collection.find_one({"_id": student["_id"]})
        
        return StudentResponse(
            id=str(updated_student["_id"]),
            name=updated_student.get("name", ""),
            nis=updated_student.get("nis", ""),
            kelas=updated_student.get("kelas"),
            created_at=updated_student.get("created_at", get_timestamp())
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat memperbarui siswa: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/students/{student_id}", tags=["Students"])
async def delete_student(student_id: str):
    """Menghapus siswa"""
    try:
        try:
            student_obj_id = ObjectId(student_id)
            student = students_collection.find_one({"_id": student_obj_id})
        except:
            student = students_collection.find_one({"_id": student_id})
            
        if not student:
            raise HTTPException(
                status_code=404,
                detail=f"Siswa dengan ID {student_id} tidak ditemukan"
            )
            
        answer_count = answers_collection.count_documents({"student_id": str(student["_id"])})
        if answer_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Tidak dapat menghapus siswa karena memiliki {answer_count} jawaban terkait"
            )
            
        students_collection.delete_one({"_id": student["_id"]})
        
        return {"message": "Siswa berhasil dihapus"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat menghapus siswa: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== EXAMS ENDPOINTS ====================

@app.get("/api/exams", response_model=List[ExamResponse], tags=["Exams"])
async def get_exams():
    """Mendapatkan daftar semua ujian"""
    try:
        exams = list(exams_collection.find())
        result = []
        
        for exam in exams:
            question_count = questions_collection.count_documents({"exam_id": str(exam["_id"])})
            
            result.append(ExamResponse(
                id=str(exam["_id"]),
                title=exam["title"],
                description=exam.get("description", ""),
                created_at=exam.get("created_at", get_timestamp()),
                question_count=question_count
            ))
            
        return result
    except Exception as e:
        logger.error(f"Error saat mengambil daftar ujian: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/exams", response_model=ExamResponse, status_code=status.HTTP_201_CREATED, tags=["Exams"])
async def create_exam(exam: ExamCreate):
    """Membuat ujian baru"""
    try:
        new_exam = {
            "title": exam.title,
            "description": exam.description,
            "created_at": get_timestamp()
        }
        
        result = exams_collection.insert_one(new_exam)
        
        return ExamResponse(
            id=str(result.inserted_id),
            title=new_exam["title"],
            description=new_exam["description"],
            created_at=new_exam["created_at"],
            question_count=0
        )
    except Exception as e:
        logger.error(f"Error saat membuat ujian: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/exams/{exam_id}", response_model=Dict[str, Any], tags=["Exams"])
async def get_exam(exam_id: str):
    """Mendapatkan detail ujian beserta pertanyaannya"""
    try:
        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": exam_id})
            
        if not exam:
            raise HTTPException(
                status_code=404,
                detail=f"Ujian dengan ID {exam_id} tidak ditemukan"
            )
            
        questions_cursor = questions_collection.find({"exam_id": str(exam["_id"])})
        questions = []
        
        for question in questions_cursor:
            answer_count = answers_collection.count_documents({"question_id": str(question["_id"])})
            question_type = normalize_question_type(question.get("question_type"))
            scoring_defaults = get_scoring_defaults(question_type)
            
            questions.append({
                "id": str(question["_id"]),
                "question_text": question["question_text"],
                "created_at": question.get("created_at", get_timestamp()),
                "answer_count": answer_count,
                "question_type": question_type,
                "max_score": question.get("max_score", scoring_defaults["max_score"]),
                "allowed_scores": question.get("allowed_scores", scoring_defaults["allowed_scores"])
            })
            
        return {
            "id": str(exam["_id"]),
            "title": exam["title"],
            "description": exam.get("description", ""),
            "created_at": exam.get("created_at", get_timestamp()),
            "questions": questions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mengambil detail ujian: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/exams/{exam_id}", response_model=ExamResponse, tags=["Exams"])
async def update_exam(exam_id: str, exam_update: ExamUpdate):
    """Memperbarui detail ujian"""
    try:
        update_fields = {}

        if exam_update.title is not None:
            if not exam_update.title.strip():
                raise HTTPException(status_code=400, detail="Parameter 'title' tidak boleh kosong")
            update_fields["title"] = exam_update.title.strip()

        if exam_update.description is not None:
            update_fields["description"] = exam_update.description.strip()

        if not update_fields:
            raise HTTPException(status_code=400, detail="Tidak ada field yang diperbarui")

        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": exam_id})

        if not exam:
            raise HTTPException(
                status_code=404,
                detail=f"Ujian dengan ID {exam_id} tidak ditemukan"
            )

        exams_collection.update_one({"_id": exam["_id"]}, {"$set": update_fields})
        updated_exam = exams_collection.find_one({"_id": exam["_id"]})
        
        question_count = questions_collection.count_documents({"exam_id": str(exam["_id"])})

        return ExamResponse(
            id=str(updated_exam["_id"]),
            title=updated_exam["title"],
            description=updated_exam.get("description", ""),
            created_at=updated_exam.get("created_at", get_timestamp()),
            question_count=question_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat memperbarui ujian: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== QUESTIONS ENDPOINTS ====================

@app.get("/api/exams/{exam_id}/questions", response_model=List[QuestionResponse], tags=["Questions"])
async def get_exam_questions(exam_id: str):
    """Mendapatkan semua pertanyaan untuk ujian tertentu"""
    try:
        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": exam_id})
            
        if not exam:
            raise HTTPException(
                status_code=404,
                detail=f"Ujian dengan ID {exam_id} tidak ditemukan"
            )
            
        questions_cursor = questions_collection.find({"exam_id": str(exam["_id"])})
        questions = []
        
        for question in questions_cursor:
            question_type = normalize_question_type(question.get("question_type"))
            scoring_defaults = get_scoring_defaults(question_type)
            answer_count = answers_collection.count_documents({"question_id": str(question["_id"])})
            
            questions.append(QuestionResponse(
                id=str(question["_id"]),
                exam_id=str(exam["_id"]),
                question_text=question["question_text"],
                created_at=question.get("created_at", get_timestamp()),
                question_type=question_type,
                max_score=question.get("max_score", scoring_defaults["max_score"]),
                allowed_scores=question.get("allowed_scores", scoring_defaults["allowed_scores"]),
                answer_count=answer_count
            ))
                
        return questions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mengambil pertanyaan ujian: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/exams/{exam_id}/questions", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED, tags=["Questions"])
async def create_question(exam_id: str, question: QuestionCreate):
    """Membuat pertanyaan baru untuk ujian"""
    try:
        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": exam_id})
            
        if not exam:
            raise HTTPException(
                status_code=404,
                detail=f"Ujian dengan ID {exam_id} tidak ditemukan"
            )
        
        question_type = normalize_question_type(question.question_type)
        scoring_defaults = get_scoring_defaults(question_type)
        
        new_question = {
            "exam_id": str(exam["_id"]),
            "question_text": question.question_text,
            "created_at": get_timestamp(),
            "question_type": question_type,
            "max_score": scoring_defaults["max_score"],
            "allowed_scores": scoring_defaults["allowed_scores"]
        }
        
        result = questions_collection.insert_one(new_question)
        
        return QuestionResponse(
            id=str(result.inserted_id),
            exam_id=new_question["exam_id"],
            question_text=new_question["question_text"],
            created_at=new_question["created_at"],
            question_type=new_question["question_type"],
            max_score=new_question["max_score"],
            allowed_scores=new_question["allowed_scores"],
            answer_count=0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat membuat pertanyaan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/questions/{question_id}", response_model=Dict[str, Any], tags=["Questions"])
async def get_question(question_id: str):
    """Mendapatkan detail pertanyaan beserta jawabannya"""
    try:
        question = load_question_document(question_id)
        if not question:
            raise HTTPException(
                status_code=404,
                detail=f"Pertanyaan dengan ID {question_id} tidak ditemukan"
            )
        
        question_type = normalize_question_type(question.get("question_type"))
        scoring_defaults = get_scoring_defaults(question_type)
        
        # Ambil jawaban
        answers_cursor = answers_collection.find({"question_id": str(question["_id"])})
        answers = []
        for answer in answers_cursor:
            answer_type = normalize_question_type(answer.get("question_type") or question_type)
            answer_scoring = get_scoring_defaults(answer_type)
            answers.append({
                "id": str(answer["_id"]),
                "student_name": answer["student_name"],
                "answer_text": answer["answer_text"],
                "score": answer.get("score"),
                "created_at": answer.get("created_at", get_timestamp()),
                "evaluated_at": answer.get("evaluated_at"),
                "question_type": answer_type,
                "max_score": answer.get("max_score", answer_scoring["max_score"]),
                "allowed_scores": answer.get("allowed_scores", answer_scoring["allowed_scores"])
            })
        
        return {
            "id": str(question["_id"]),
            "exam_id": question["exam_id"],
            "question_text": question["question_text"],
            "created_at": question.get("created_at", get_timestamp()),
            "question_type": question_type,
            "max_score": question.get("max_score", scoring_defaults["max_score"]),
            "allowed_scores": question.get("allowed_scores", scoring_defaults["allowed_scores"]),
            "answers": answers
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mendapatkan detail pertanyaan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/questions/{question_id}", response_model=Dict[str, Any], tags=["Questions"])
async def update_question(question_id: str, question_update: QuestionUpdate):
    """Memperbarui pertanyaan dan re-evaluasi jawaban terkait"""
    try:
        question = load_question_document(question_id)
        if not question:
            raise HTTPException(
                status_code=404,
                detail=f"Pertanyaan dengan ID {question_id} tidak ditemukan"
            )
        
        update_fields = {}
        normalized_type_override = None
        question_text_new = question.get("question_text", "")

        if question_update.question_text is not None:
            if not question_update.question_text.strip():
                raise HTTPException(status_code=400, detail="Parameter 'question_text' tidak boleh kosong")
            update_fields["question_text"] = question_update.question_text.strip()
            question_text_new = question_update.question_text.strip()

        if question_update.question_type is not None:
            normalized_type_override = normalize_question_type(question_update.question_type)
            scoring_defaults_override = get_scoring_defaults(normalized_type_override)
            update_fields["question_type"] = normalized_type_override
            update_fields["max_score"] = scoring_defaults_override["max_score"]
            update_fields["allowed_scores"] = scoring_defaults_override["allowed_scores"]

        if not update_fields:
            raise HTTPException(status_code=400, detail="Tidak ada field yang diperbarui")

        questions_collection.update_one({"_id": question["_id"]}, {"$set": update_fields})
        question = questions_collection.find_one({"_id": question["_id"]})

        question_type = normalize_question_type(
            question.get("question_type") or normalized_type_override
        )
        scoring_defaults = get_scoring_defaults(question_type)
        question_text_new = question.get("question_text", question_text_new)

        # Re-evaluasi jawaban terkait
        answers_cursor = answers_collection.find({"question_id": str(question["_id"])})
        affected_answers = list(answers_cursor)

        for answer in affected_answers:
            base_update = {
                "question_type": question_type,
                "max_score": scoring_defaults["max_score"],
                "allowed_scores": scoring_defaults["allowed_scores"]
            }

            if aes_evaluator:
                try:
                    if hasattr(aes_evaluator, 'evaluate_answer_cached'):
                        eval_result = aes_evaluator.evaluate_answer_cached(
                            question_text_new,
                            answer.get("answer_text", ""),
                            question_type=question_type,
                            top_k=3
                        )
                    else:
                        eval_result = aes_evaluator.evaluate_answer(
                            question_text_new,
                            answer.get("answer_text", ""),
                            top_k=3,
                            question_type=question_type
                        )
                    base_update.update({
                        "score": eval_result["score"],
                        "evaluation": eval_result["evaluation"],
                        "references": eval_result["references"],
                        "evaluated_at": get_timestamp(),
                        "max_score": eval_result.get("max_score", scoring_defaults["max_score"]),
                        "allowed_scores": eval_result.get("allowed_scores", scoring_defaults["allowed_scores"]),
                        "question_type": eval_result.get("question_type", question_type)
                    })
                except Exception as eval_err:
                    logger.error(f"Gagal mengevaluasi ulang jawaban {answer['_id']}: {eval_err}")

            answers_collection.update_one({"_id": answer["_id"]}, {"$set": base_update})

        return {
            "id": str(question["_id"]),
            "exam_id": question["exam_id"],
            "question_text": question["question_text"],
            "created_at": question.get("created_at", get_timestamp()),
            "question_type": question_type,
            "max_score": question.get("max_score", scoring_defaults["max_score"]),
            "allowed_scores": question.get("allowed_scores", scoring_defaults["allowed_scores"]),
            "answers_updated": len(affected_answers)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat memperbarui pertanyaan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ANSWERS ENDPOINTS ====================

@app.post("/api/answers", response_model=AnswerResponse, status_code=status.HTTP_201_CREATED, tags=["Answers"])
async def create_answer(answer: AnswerCreate):
    """Membuat jawaban baru dan evaluasi otomatis"""
    try:
        # Validasi question_id
        try:
            question_obj_id = ObjectId(answer.question_id)
            question = questions_collection.find_one({"_id": question_obj_id})
        except:
            question = questions_collection.find_one({"_id": answer.question_id})
            
        if not question:
            raise HTTPException(
                status_code=404,
                detail=f"Pertanyaan dengan ID {answer.question_id} tidak ditemukan"
            )
        
        # Tentukan student_name
        student_name = answer.student_name
        student_id = answer.student_id
        student_info = None
        
        # Jika ada session_id, ambil info siswa dari sesi
        if answer.session_id:
            try:
                session_obj_id = ObjectId(answer.session_id)
                session = sessions_collection.find_one({"_id": session_obj_id})
            except:
                session = sessions_collection.find_one({"_id": answer.session_id})
                
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sesi dengan ID {answer.session_id} tidak ditemukan"
                )
                
            if session.get("is_completed", False):
                raise HTTPException(
                    status_code=400,
                    detail="Sesi sudah selesai, tidak dapat menambahkan jawaban baru"
                )
                
            current_student = session.get("current_student")
            if current_student:
                student_info = current_student
                student_name = current_student.get("name")
                student_id = current_student.get("id")
        else:
            if not student_name:
                raise HTTPException(
                    status_code=400,
                    detail="Parameter 'student_name' diperlukan jika tidak ada sesi"
                )
                
            if student_id:
                try:
                    student_obj_id = ObjectId(student_id)
                    student = students_collection.find_one({"_id": student_obj_id})
                    if student:
                        student_info = {
                            "id": str(student["_id"]),
                            "name": student["name"],
                            "nis": student["nis"]
                        }
                        student_name = student["name"]
                except:
                    pass
        
        question_type = normalize_question_type(question.get("question_type"))
        scoring_defaults = get_scoring_defaults(question_type)

        new_answer = {
            "question_id": str(question["_id"]),
            "student_name": student_name,
            "answer_text": answer.answer_text,
            "created_at": get_timestamp(),
            "question_type": question_type,
            "max_score": scoring_defaults["max_score"],
            "allowed_scores": scoring_defaults["allowed_scores"]
        }
        
        if student_info:
            new_answer["student"] = student_info
            
        if student_id:
            new_answer["student_id"] = student_id
        
        if answer.session_id:
            new_answer["session_id"] = answer.session_id
        
        result = answers_collection.insert_one(new_answer)
        new_answer_id = result.inserted_id
        
        # Evaluasi jawaban jika AES tersedia
        if aes_evaluator:
            try:
                if hasattr(aes_evaluator, 'evaluate_answer_cached'):
                    evaluation_result = aes_evaluator.evaluate_answer_cached(
                        question["question_text"], 
                        answer.answer_text, 
                        question_type=question_type,
                        top_k=3
                    )
                else:
                    evaluation_result = aes_evaluator.evaluate_answer(
                        question["question_text"], 
                        answer.answer_text, 
                        top_k=3,
                        question_type=question_type
                    )
                
                updated_question_type = evaluation_result.get("question_type", question_type)
                updated_scoring = get_scoring_defaults(updated_question_type)
                
                answers_collection.update_one(
                    {"_id": new_answer_id},
                    {"$set": {
                        "score": evaluation_result["score"],
                        "evaluation": evaluation_result["evaluation"],
                        "references": evaluation_result["references"],
                        "evaluated_at": get_timestamp(),
                        "question_type": updated_question_type,
                        "max_score": evaluation_result.get("max_score", updated_scoring["max_score"]),
                        "allowed_scores": evaluation_result.get("allowed_scores", updated_scoring["allowed_scores"])
                    }}
                )
                
                updated_answer = answers_collection.find_one({"_id": new_answer_id})
                
                return AnswerResponse(
                    id=str(updated_answer["_id"]),
                    question_id=str(question["_id"]),
                    student_name=updated_answer["student_name"],
                    answer_text=updated_answer["answer_text"],
                    score=updated_answer.get("score"),
                    evaluation=updated_answer.get("evaluation"),
                    references=updated_answer.get("references", []),
                    created_at=updated_answer.get("created_at"),
                    evaluated_at=updated_answer.get("evaluated_at"),
                    question_type=updated_answer.get("question_type", updated_question_type),
                    max_score=updated_answer.get("max_score", updated_scoring["max_score"]),
                    allowed_scores=updated_answer.get("allowed_scores", updated_scoring["allowed_scores"])
                )
            except Exception as e:
                logger.error(f"Error saat evaluasi jawaban: {e}")
        
        return AnswerResponse(
            id=str(new_answer_id),
            question_id=str(question["_id"]),
            student_name=student_name,
            answer_text=answer.answer_text,
            score=None,
            evaluation=None,
            references=[],
            created_at=new_answer["created_at"],
            evaluated_at=None,
            question_type=question_type,
            max_score=scoring_defaults["max_score"],
            allowed_scores=scoring_defaults["allowed_scores"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat membuat jawaban: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/answers/{answer_id}", response_model=Dict[str, Any], tags=["Answers"])
async def get_answer(answer_id: str):
    """Mendapatkan detail jawaban"""
    try:
        try:
            answer_obj_id = ObjectId(answer_id)
            answer = answers_collection.find_one({"_id": answer_obj_id})
        except:
            answer = answers_collection.find_one({"_id": answer_id})
            
        if not answer:
            raise HTTPException(
                status_code=404,
                detail=f"Jawaban dengan ID {answer_id} tidak ditemukan"
            )
            
        question_type = normalize_question_type(answer.get("question_type"))
        scoring_defaults = get_scoring_defaults(question_type)
        
        answer_data = {
            "id": str(answer["_id"]),
            "question_id": answer["question_id"],
            "student_name": answer["student_name"],
            "answer_text": answer["answer_text"],
            "score": answer.get("score"),
            "evaluation": answer.get("evaluation"),
            "references": answer.get("references", []),
            "created_at": answer.get("created_at"),
            "evaluated_at": answer.get("evaluated_at"),
            "question_type": question_type,
            "max_score": answer.get("max_score", scoring_defaults["max_score"]),
            "allowed_scores": answer.get("allowed_scores", scoring_defaults["allowed_scores"])
        }
        
        if "session_id" in answer:
            answer_data["session_id"] = answer["session_id"]
        
        return answer_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mengambil detail jawaban: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/answers/{answer_id}/evaluate", response_model=AnswerResponse, tags=["Answers"])
async def evaluate_answer_endpoint(answer_id: str):
    """Mengevaluasi atau mengevaluasi ulang jawaban"""
    try:
        try:
            answer_obj_id = ObjectId(answer_id)
            answer = answers_collection.find_one({"_id": answer_obj_id})
        except:
            answer = answers_collection.find_one({"_id": answer_id})
            
        if not answer:
            raise HTTPException(
                status_code=404,
                detail=f"Jawaban dengan ID {answer_id} tidak ditemukan"
            )
            
        try:
            question_obj_id = ObjectId(answer["question_id"])
            question = questions_collection.find_one({"_id": question_obj_id})
        except:
            question = questions_collection.find_one({"_id": answer["question_id"]})
            
        if not question:
            raise HTTPException(
                status_code=404,
                detail=f"Pertanyaan dengan ID {answer['question_id']} tidak ditemukan"
            )
        
        if not aes_evaluator:
            raise HTTPException(status_code=500, detail="Sistem AES belum diinisialisasi")
        
        question_type_source = normalize_question_type(
            answer.get("question_type") or question.get("question_type")
        )
        scoring_defaults = get_scoring_defaults(question_type_source)

        if hasattr(aes_evaluator, 'evaluate_answer_cached'):
            evaluation_result = aes_evaluator.evaluate_answer_cached(
                question["question_text"], 
                answer["answer_text"], 
                question_type=question_type_source,
                top_k=3
            )
        else:
            evaluation_result = aes_evaluator.evaluate_answer(
                question["question_text"], 
                answer["answer_text"], 
                top_k=3,
                question_type=question_type_source
            )
        
        updated_question_type = evaluation_result.get("question_type", question_type_source)
        updated_scoring = get_scoring_defaults(updated_question_type)
        
        answers_collection.update_one(
            {"_id": answer["_id"]},
            {"$set": {
                "score": evaluation_result["score"],
                "evaluation": evaluation_result["evaluation"],
                "references": evaluation_result["references"],
                "evaluated_at": get_timestamp(),
                "question_type": updated_question_type,
                "max_score": evaluation_result.get("max_score", updated_scoring["max_score"]),
                "allowed_scores": evaluation_result.get("allowed_scores", updated_scoring["allowed_scores"])
            }}
        )
        
        updated_answer = answers_collection.find_one({"_id": answer["_id"]})
        
        return AnswerResponse(
            id=str(updated_answer["_id"]),
            question_id=updated_answer["question_id"],
            student_name=updated_answer["student_name"],
            answer_text=updated_answer["answer_text"],
            score=updated_answer.get("score"),
            evaluation=updated_answer.get("evaluation"),
            references=updated_answer.get("references", []),
            created_at=updated_answer.get("created_at"),
            evaluated_at=updated_answer.get("evaluated_at"),
            question_type=updated_answer.get("question_type", updated_question_type),
            max_score=updated_answer.get("max_score", updated_scoring["max_score"]),
            allowed_scores=updated_answer.get("allowed_scores", updated_scoring["allowed_scores"])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat evaluasi jawaban: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SESSIONS ENDPOINTS ====================

@app.post("/api/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED, tags=["Sessions"])
async def create_session(session: SessionCreate):
    """Membuat sesi ujian baru"""
    try:
        exam_id = session.exam_id
        exam_ids = session.exam_ids or []
        student_ids = session.student_ids or []
        total_students = session.total_students or 0
        
        if not exam_id and not exam_ids:
            raise HTTPException(
                status_code=400,
                detail="Parameter 'exam_id' atau 'exam_ids' diperlukan"
            )
            
        if exam_ids and isinstance(exam_ids, list) and len(exam_ids) > 0:
            exam_id = exam_ids[0]
        
        if not student_ids or not isinstance(student_ids, list) or len(student_ids) == 0:
            if total_students and total_students > 0:
                students_cursor = students_collection.find().limit(total_students)
                student_ids = [str(student["_id"]) for student in students_cursor]
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Parameter 'student_ids' atau 'total_students' diperlukan"
                )
            
        # Validasi exam_id
        primary_exam = None
        exams_list = []
        
        try:
            exam_obj_id = ObjectId(exam_id)
            primary_exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            primary_exam = exams_collection.find_one({"_id": exam_id})
            
        if not primary_exam:
            raise HTTPException(
                status_code=404,
                detail=f"Ujian utama dengan ID {exam_id} tidak ditemukan"
            )
            
        exams_list.append({
            "id": str(primary_exam["_id"]),
            "title": primary_exam["title"]
        })
        
        # Validasi exam_ids tambahan
        if exam_ids and isinstance(exam_ids, list) and len(exam_ids) > 1:
            for additional_exam_id in exam_ids[1:]:
                try:
                    add_exam_obj_id = ObjectId(additional_exam_id)
                    additional_exam = exams_collection.find_one({"_id": add_exam_obj_id})
                except:
                    additional_exam = exams_collection.find_one({"_id": additional_exam_id})
                
                if additional_exam:
                    exams_list.append({
                        "id": str(additional_exam["_id"]),
                        "title": additional_exam["title"]
                    })
            
        # Validasi student_ids
        valid_students = []
        for student_id in student_ids:
            try:
                student_obj_id = ObjectId(student_id)
                student = students_collection.find_one({"_id": student_obj_id})
                if student:
                    valid_students.append({
                        "id": str(student["_id"]),
                        "name": student["name"],
                        "nis": student["nis"]
                    })
            except:
                continue
                
        if len(valid_students) == 0:
            raise HTTPException(
                status_code=400,
                detail="Tidak ada siswa yang valid dalam daftar"
            )
            
        # Generate session code
        import random
        import string
        session_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        new_session = {
            "session_code": session_code,
            "exam_id": str(primary_exam["_id"]),
            "exams": exams_list,
            "students": valid_students,
            "total_students": len(valid_students),
            "current_student_index": 0,
            "current_student": valid_students[0] if valid_students else None,
            "current_exam_index": 0,
            "is_completed": False,
            "created_at": get_timestamp()
        }
        
        result = sessions_collection.insert_one(new_session)
        
        return SessionResponse(
            id=str(result.inserted_id),
            session_code=new_session["session_code"],
            exam_id=new_session["exam_id"],
            exam_title=primary_exam["title"],
            exams=new_session["exams"],
            students=new_session["students"],
            total_students=new_session["total_students"],
            current_student=new_session["current_student"],
            current_student_index=new_session["current_student_index"],
            current_exam_index=new_session["current_exam_index"],
            is_completed=new_session["is_completed"],
            created_at=new_session["created_at"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat membuat sesi: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions", response_model=List[Dict[str, Any]], tags=["Sessions"])
async def get_sessions():
    """Mendapatkan daftar semua sesi ujian"""
    try:
        sessions_cursor = sessions_collection.find().sort("created_at", -1)
        sessions = []
        
        for session in sessions_cursor:
            exam_title = "Unknown Exam"
            try:
                exam_obj_id = ObjectId(session["exam_id"])
                exam = exams_collection.find_one({"_id": exam_obj_id})
                if exam:
                    exam_title = exam["title"]
            except:
                pass
            
            sessions.append({
                "id": str(session["_id"]),
                "session_code": session.get("session_code", ""),
                "exam_id": session["exam_id"],
                "exam_title": exam_title,
                "exams": session.get("exams", []),
                "total_students": session.get("total_students", 0),
                "is_completed": session.get("is_completed", False),
                "created_at": session.get("created_at", get_timestamp())
            })
            
        return sessions
    except Exception as e:
        logger.error(f"Error saat mendapatkan daftar sesi: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}", response_model=Dict[str, Any], tags=["Sessions"])
async def get_session(session_id: str):
    """Mendapatkan detail sesi"""
    try:
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Sesi dengan ID {session_id} tidak ditemukan"
            )
            
        try:
            exam_obj_id = ObjectId(session["exam_id"])
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": session["exam_id"]})
            
        exam_title = exam["title"] if exam else "Unknown Exam"
        
        questions = []
        try:
            questions_cursor = questions_collection.find({"exam_id": session["exam_id"]})
            for question in questions_cursor:
                questions.append({
                    "id": str(question["_id"]),
                    "question_text": question["question_text"]
                })
        except Exception as e:
            logger.error(f"Error saat mengambil pertanyaan: {e}")
            
        exams_list = session.get("exams", [])
        
        return {
            "id": str(session["_id"]),
            "session_code": session.get("session_code", ""),
            "exam_id": session["exam_id"],
            "exam_title": exam_title,
            "exams": exams_list,
            "students": session.get("students", []),
            "total_students": session.get("total_students", 0),
            "current_student": session.get("current_student", {}),
            "current_student_index": session.get("current_student_index", 0),
            "current_exam_index": session.get("current_exam_index", 0),
            "is_completed": session.get("is_completed", False),
            "created_at": session.get("created_at", get_timestamp()),
            "questions": questions
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mendapatkan sesi: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sessions/{session_id}/next-student", response_model=Dict[str, Any], tags=["Sessions"])
async def next_student(session_id: str):
    """Pindah ke siswa berikutnya dalam sesi"""
    try:
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Sesi dengan ID {session_id} tidak ditemukan"
            )
            
        if session.get("is_completed", False):
            raise HTTPException(status_code=400, detail="Sesi sudah selesai")
            
        students = session.get("students", [])
        current_index = session.get("current_student_index", 0)
        
        if current_index >= len(students) - 1:
            sessions_collection.update_one(
                {"_id": session["_id"]},
                {"$set": {"is_completed": True}}
            )
            return {
                "message": "Sesi telah selesai",
                "session_id": str(session["_id"]),
                "is_completed": True
            }
            
        new_index = current_index + 1
        next_student_data = students[new_index] if new_index < len(students) else None
        
        sessions_collection.update_one(
            {"_id": session["_id"]},
            {"$set": {
                "current_student_index": new_index,
                "current_student": next_student_data
            }}
        )
        
        updated_session = sessions_collection.find_one({"_id": session["_id"]})
        
        return {
            "id": str(updated_session["_id"]),
            "session_code": updated_session.get("session_code", ""),
            "exam_id": updated_session["exam_id"],
            "current_student": updated_session.get("current_student"),
            "current_student_index": updated_session.get("current_student_index", 0),
            "total_students": len(students),
            "is_completed": updated_session.get("is_completed", False)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat pindah ke siswa berikutnya: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}/answers", response_model=List[Dict[str, Any]], tags=["Sessions"])
async def get_session_answers(session_id: str):
    """Mendapatkan semua jawaban dalam sesi"""
    try:
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Sesi dengan ID {session_id} tidak ditemukan"
            )
            
        answers_cursor = answers_collection.find({"session_id": str(session["_id"])})
        
        result = []
        for answer in answers_cursor:
            try:
                question_obj_id = ObjectId(answer["question_id"])
                question = questions_collection.find_one({"_id": question_obj_id})
            except:
                question = questions_collection.find_one({"_id": answer["question_id"]})
                
            question_text = question["question_text"] if question else "Unknown Question"
            answer_type = normalize_question_type(
                answer.get("question_type") or (question.get("question_type") if question else None)
            )
            scoring_defaults = get_scoring_defaults(answer_type)
            
            result.append({
                "id": str(answer["_id"]),
                "question_id": answer["question_id"],
                "question_text": question_text,
                "student_name": answer["student_name"],
                "answer_text": answer["answer_text"],
                "score": answer.get("score"),
                "evaluation": answer.get("evaluation"),
                "references": answer.get("references", []),
                "created_at": answer.get("created_at"),
                "evaluated_at": answer.get("evaluated_at"),
                "question_type": answer_type,
                "max_score": answer.get("max_score", scoring_defaults["max_score"]),
                "allowed_scores": answer.get("allowed_scores", scoring_defaults["allowed_scores"])
            })
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mendapatkan jawaban sesi: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sessions/{session_id}/summary", response_model=Dict[str, Any], tags=["Sessions"])
async def get_session_summary(session_id: str):
    """Mendapatkan ringkasan hasil sesi"""
    try:
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Sesi dengan ID {session_id} tidak ditemukan"
            )
            
        answers_cursor = answers_collection.find({"session_id": str(session["_id"])})
        
        student_results = {}
        for answer in answers_cursor:
            student_name = answer["student_name"]
            if student_name not in student_results:
                student_results[student_name] = {
                    "name": student_name,
                    "answers": [],
                    "total_score": 0,
                    "total_max_score": 0,
                    "average_score": 0,
                    "average_percentage": 0,
                    "question_count": 0
                }
            
            try:
                question_obj_id = ObjectId(answer["question_id"])
                question = questions_collection.find_one({"_id": question_obj_id})
            except:
                question = questions_collection.find_one({"_id": answer["question_id"]})
                
            question_text = question["question_text"] if question else "Unknown Question"
            answer_type = normalize_question_type(
                answer.get("question_type") or (question.get("question_type") if question else None)
            )
            scoring_defaults = get_scoring_defaults(answer_type)
            max_score = answer.get("max_score", scoring_defaults["max_score"])
            score_value = answer.get("score")
            
            student_results[student_name]["answers"].append({
                "question_id": answer["question_id"],
                "question_text": question_text,
                "answer_text": answer["answer_text"],
                "score": score_value,
                "max_score": max_score,
                "question_type": answer_type,
                "evaluation": answer.get("evaluation", "")
            })
            
            if score_value is not None:
                student_results[student_name]["total_score"] += score_value
                student_results[student_name]["total_max_score"] += max_score
                student_results[student_name]["question_count"] += 1
        
        for data in student_results.values():
            if data["question_count"] > 0:
                data["average_score"] = data["total_score"] / data["question_count"]
            if data["total_max_score"] > 0:
                data["average_percentage"] = data["total_score"] / data["total_max_score"]
                
        try:
            exam_obj_id = ObjectId(session["exam_id"])
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": session["exam_id"]})
            
        exam_title = exam["title"] if exam else "Unknown Exam"
        
        return {
            "session_id": str(session["_id"]),
            "session_code": session.get("session_code", ""),
            "exam_id": session["exam_id"],
            "exam_title": exam_title,
            "total_students": session.get("total_students", 1),
            "is_completed": session.get("is_completed", False),
            "student_results": list(student_results.values())
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mendapatkan ringkasan sesi: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== RAG COMPARISON ENDPOINT ====================

@app.post("/api/compare-rag", response_model=Dict[str, Any], tags=["RAG"])
async def compare_rag(request: CompareRAGRequest):
    """Membandingkan hasil RAG (BM25 vs DPR)"""
    try:
        if not aes_retriever:
            success = initialize_aes()
            if not success or not aes_retriever:
                raise HTTPException(
                    status_code=500,
                    detail="Sistem AES belum diinisialisasi"
                )
        
        if not aes_retriever:
            raise HTTPException(status_code=500, detail="BM25 retriever tidak tersedia")
        
        if aes_dpr_retriever and aes_sparse_retriever:
            try:
                import time
                
                # BM25 retrieval
                start_time = time.time()
                bm25_results = aes_sparse_retriever.retrieve(request.question, top_k=5, min_score=0.5)
                bm25_time = time.time() - start_time
                
                # DPR retrieval
                start_time = time.time()
                dpr_results = aes_dpr_retriever.retrieve(request.question, top_k=5)
                dpr_time = time.time() - start_time
                
                # Calculate overlap
                bm25_indices = set(r.get("index", -1) for r in bm25_results)
                dpr_indices = set(r.get("index", -1) for r in dpr_results)
                overlap = len(bm25_indices & dpr_indices)
                overlap_percentage = (overlap / 5 * 100) if 5 > 0 else 0.0
                
                return {
                    "query": request.question,
                    "bm25_results": bm25_results,
                    "dpr_results": dpr_results,
                    "bm25_time": bm25_time,
                    "dpr_time": dpr_time,
                    "overlap": overlap,
                    "overlap_percentage": overlap_percentage
                }
            except Exception as comp_err:
                logger.error(f"Error saat membandingkan: {comp_err}")
                bm25_results = aes_retriever.retrieve(request.question, top_k=5, min_score=0.5)
                return {
                    "query": request.question,
                    "bm25_results": bm25_results,
                    "dpr_results": [{"chunk": f"Error: {str(comp_err)}", "score": 0.0, "index": -1}],
                    "bm25_time": 0.0,
                    "dpr_time": 0.0,
                    "overlap": 0,
                    "overlap_percentage": 0.0,
                    "warning": "Gagal menggunakan DPR"
                }
        else:
            bm25_results = aes_retriever.retrieve(request.question, top_k=5, min_score=0.5)
            return {
                "query": request.question,
                "bm25_results": bm25_results,
                "dpr_results": [{"chunk": "DPR tidak tersedia", "score": 0.0, "index": -1}],
                "bm25_time": 0.0,
                "dpr_time": 0.0,
                "overlap": 0,
                "overlap_percentage": 0.0
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat membandingkan RAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== AES INITIALIZATION ENDPOINT ====================

@app.post("/api/initialize-aes", tags=["System"])
async def init_aes():
    """Endpoint untuk menginisialisasi sistem AES"""
    try:
        global aes_processor, aes_retriever, aes_dpr_retriever, aes_model, aes_evaluator
        aes_processor = None
        aes_retriever = None
        aes_dpr_retriever = None
        aes_model = None
        aes_evaluator = None
        
        success = initialize_aes()
        
        if success:
            return {
                "status": "success", 
                "message": "Sistem AES berhasil diinisialisasi",
                "details": {
                    "processor": aes_processor is not None,
                    "retriever": aes_retriever is not None,
                    "dpr_retriever": aes_dpr_retriever is not None,
                    "model": aes_model is not None,
                    "evaluator": aes_evaluator is not None
                }
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Gagal menginisialisasi sistem AES"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat menginisialisasi AES: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    
    # Gunakan port 5000 untuk kompatibilitas dengan frontend
    PORT = 5000
    HOST = "0.0.0.0"  # Terima koneksi dari semua interface
    
    logger.info("🚀 Memulai FastAPI server...")
    logger.info(f"📚 Dokumentasi API: http://localhost:{PORT}/docs")
    logger.info(f"📖 ReDoc: http://localhost:{PORT}/redoc")
    logger.info(f"🌐 API Base URL: http://localhost:{PORT}/api")
    
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
        reload=False  # Set False untuk production
    )

