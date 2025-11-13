#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
API untuk Automated Essay Scoring System
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import certifi
from bson.objectid import ObjectId
from datetime import datetime
import logging

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AES-API")

# Import modul AES
current_dir = Path(__file__).parent.absolute()
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

from aes_system import DocumentProcessor, BM25Retriever, LlamaModelCpp, AnswerEvaluator, DenseRetriever, HybridRetriever

# Inisialisasi Flask app
app = Flask(__name__)
CORS(app)

# Konfigurasi MongoDB Atlas
try:
    # MongoDB Atlas connection string
    mongo_uri = "mongodb+srv://adigaming015:1qGGJATMGcnSgygS@cluster0.wzzqu4l.mongodb.net/?retryWrites=true&w=majority"
    
    # Coba beberapa konfigurasi SSL yang berbeda
    ssl_configs = [
        # Konfigurasi 1: Server API v1 dengan CA bundle
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
        # Konfigurasi 2: Tanpa Server API, dengan SSL yang lebih permisif
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
        # Konfigurasi 3: Tanpa SSL (tidak direkomendasikan untuk production)
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
            
            # Tes koneksi
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
    
    # Gunakan database aes_database
    db = client["aes_database"]
    logger.info("Menggunakan database MongoDB Atlas: aes_database")
    
    # Verifikasi koleksi yang tersedia
    collection_names = db.list_collection_names()
    logger.info(f"Koleksi yang tersedia di MongoDB Atlas: {collection_names}")
    
    # Cek koneksi ke setiap koleksi
    try:
        exams_count = db.exams.count_documents({})
        questions_count = db.questions.count_documents({})
        students_count = db.students.count_documents({})
        logger.info(f"MongoDB Atlas - Jumlah dokumen: Exams: {exams_count}, Questions: {questions_count}, Students: {students_count}")
    except Exception as e:
        logger.warning(f"Gagal mendapatkan jumlah dokumen: {e}")
        
    # Koleksi MongoDB Atlas
    exams_collection = db["exams"]
    questions_collection = db["questions"]
    sessions_collection = db["sessions"]
    answers_collection = db["answers"]
    students_collection = db["students"]
    
except Exception as e:
    logger.error(f"Koneksi MongoDB Atlas gagal: {e}")
    logger.info("Mencoba fallback ke database lokal...")
    
    try:
        # Fallback ke MongoDB lokal
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        logger.info("Koneksi MongoDB lokal berhasil")
        db = client["aes_database_local"]
        
        # Koleksi MongoDB lokal
        exams_collection = db["exams"]
        questions_collection = db["questions"]
        sessions_collection = db["sessions"]
        answers_collection = db["answers"]
        students_collection = db["students"]
        
    except Exception as local_error:
        logger.error(f"Koneksi MongoDB lokal juga gagal: {local_error}")
        logger.error("Aplikasi membutuhkan koneksi database untuk berjalan")
        sys.exit(1)

# Helper function untuk konversi ObjectId menjadi string
def object_id_to_str(obj):
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

# Helper function untuk mendapatkan timestamp saat ini
def get_timestamp():
    return datetime.utcnow().isoformat()

def normalize_question_type(question_type: Optional[str]) -> str:
    """
    Normalisasi tipe soal ke nilai standar ('singkat' atau 'panjang').
    """
    if not question_type:
        return "panjang"
    normalized = str(question_type).strip().lower()
    if normalized in {"singkat", "short", "isian", "isian singkat"}:
        return "singkat"
    return "panjang"

def get_scoring_defaults(question_type: Optional[str]) -> Dict[str, Any]:
    """
    Dapatkan konfigurasi skor default berdasarkan tipe soal.
    """
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

def load_question_document(question_id: str) -> Optional[Dict[str, Any]]:
    """Ambil dokumen pertanyaan dari database berdasarkan ID string atau ObjectId."""
    try:
        question_obj_id = ObjectId(question_id)
        question = questions_collection.find_one({"_id": question_obj_id})
        if question:
            return question
    except Exception:
        pass
    return questions_collection.find_one({"_id": question_id})

def serialize_question_response(question: Dict[str, Any], include_answers: bool = True) -> Dict[str, Any]:
    """Bangun payload JSON untuk satu pertanyaan, opsional menyertakan daftar jawaban."""
    question_type = normalize_question_type(question.get("question_type"))
    question_scoring = get_scoring_defaults(question_type)
    max_score = question.get("max_score", question_scoring["max_score"])
    allowed_scores = question.get("allowed_scores", question_scoring["allowed_scores"])

    response = {
        "id": str(question["_id"]),
        "exam_id": question["exam_id"],
        "question_text": question["question_text"],
        "created_at": question.get("created_at", get_timestamp()),
        "question_type": question_type,
        "max_score": max_score,
        "allowed_scores": allowed_scores
    }

    if include_answers:
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
        response["answers"] = answers

    return response

def update_question_and_answers(question: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Terapkan perubahan pada pertanyaan dan lakukan re-evaluasi jawaban jika diperlukan.
    Mengembalikan dict hasil serialisasi ditambah field 'answers_updated'.
    """
    update_fields: Dict[str, Any] = {}
    normalized_type_override = None
    question_text_new = question.get("question_text", "")

    if "question_text" in data:
        question_text_candidate = str(data["question_text"]).strip()
        if not question_text_candidate:
            raise ValueError("Parameter 'question_text' tidak boleh kosong")
        update_fields["question_text"] = question_text_candidate
        question_text_new = question_text_candidate

    if "question_type" in data:
        normalized_type_override = normalize_question_type(data["question_type"])
        scoring_defaults_override = get_scoring_defaults(normalized_type_override)
        update_fields["question_type"] = normalized_type_override
        update_fields["max_score"] = scoring_defaults_override["max_score"]
        update_fields["allowed_scores"] = scoring_defaults_override["allowed_scores"]

    if not update_fields:
        raise ValueError("Tidak ada field yang diperbarui")

    questions_collection.update_one({"_id": question["_id"]}, {"$set": update_fields})
    question = questions_collection.find_one({"_id": question["_id"]})

    question_type = normalize_question_type(
        question.get("question_type") or normalized_type_override
    )
    scoring_defaults = get_scoring_defaults(question_type)
    question_text_new = question.get("question_text", question_text_new)

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

    response = serialize_question_response(question, include_answers=False)
    response["answers_updated"] = len(affected_answers)
    return response

# Fungsi untuk menginisialisasi data template
def initialize_template_data():
    """Inisialisasi data template untuk soal dan siswa jika koleksi kosong"""
    try:
        # Data siswa template
        students_data = [
            {"name": "Siswa 1", "nis": "1001", "kelas": "X-A", "created_at": get_timestamp()},
            {"name": "Siswa 2", "nis": "1002", "kelas": "X-A", "created_at": get_timestamp()},
            {"name": "Siswa 3", "nis": "1003", "kelas": "X-B", "created_at": get_timestamp()},
            {"name": "Siswa 4", "nis": "1004", "kelas": "X-B", "created_at": get_timestamp()},
            {"name": "Siswa 5", "nis": "1005", "kelas": "X-C", "created_at": get_timestamp()},
        ]
        
        # Data ujian template
        exam_data = {
            "title": "Ujian IPA Kelas X",
            "description": "Ujian tentang materi dasar IPA untuk kelas X",
            "created_at": get_timestamp()
        }
        
        # Cek apakah koleksi students kosong
        if students_collection.count_documents({}) == 0:
            logger.info("Menginisialisasi data siswa template...")
            students_collection.insert_many(students_data)
            logger.info(f"Berhasil menambahkan {len(students_data)} data siswa template")
        
        # Cek apakah koleksi exams kosong
        if exams_collection.count_documents({}) == 0:
            logger.info("Menginisialisasi data ujian template...")
            
            # Buat ujian template
            exam_id = exams_collection.insert_one(exam_data).inserted_id
            
            # Buat pertanyaan template untuk ujian tersebut
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

# Variabel global untuk menyimpan instance AES
aes_processor = None
aes_retriever = None
aes_sparse_retriever = None  # BM25 retriever untuk compare
aes_dpr_retriever = None
aes_model = None
aes_evaluator = None

def initialize_aes():
    """Inisialisasi komponen AES"""
    global aes_processor, aes_retriever, aes_sparse_retriever, aes_dpr_retriever, aes_model, aes_evaluator
    
    try:
        # Path ke file PDF dan model
        pdf_path = os.path.join(current_dir, "BUKU_IPA.pdf")
        model_path = os.path.join(current_dir, "models", "gemma-3-12b-it-q4_0.gguf")
        
        # Cek apakah file ada dan berikan pesan error yang lebih detail
        if not os.path.exists(pdf_path):
            logger.error(f"File PDF tidak ditemukan: {pdf_path}")
            logger.error(f"Direktori saat ini: {current_dir}")
            logger.error(f"Daftar file di direktori saat ini: {os.listdir(current_dir)}")
            return False
            
        if not os.path.exists(model_path):
            logger.error(f"File model tidak ditemukan: {model_path}")
            models_dir = os.path.join(current_dir, "models")
            if os.path.exists(models_dir):
                logger.error(f"Daftar file di direktori models: {os.listdir(models_dir)}")
            else:
                logger.error(f"Direktori models tidak ditemukan: {models_dir}")
            return False
        
        # Inisialisasi komponen
        logger.info(f"Memproses dokumen: {pdf_path}")
        aes_processor = DocumentProcessor(pdf_path)
        chunks = aes_processor.chunk_text(chunk_size=500, overlap=50)
        logger.info(f"Dokumen berhasil dibagi menjadi {len(chunks)} chunk")
        
        logger.info("Menginisialisasi BM25 retriever...")
        aes_sparse_retriever = BM25Retriever(chunks)
        
        # Inisialisasi DPR retriever
        logger.info("Menginisialisasi DPR retriever...")
        cache_dir = os.path.join(current_dir, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        try:
            # Coba memuat dari cache jika ada
            rag_model_path = os.path.join(current_dir, "rag_model.pkl")
            
            # Periksa apakah file cache ada dan valid
            if os.path.exists(rag_model_path):
                try:
                    logger.info(f"Memuat DPR retriever dari {rag_model_path}...")
                    aes_dpr_retriever = DenseRetriever.load(rag_model_path)
                    
                    if not aes_dpr_retriever:
                        logger.warning("Gagal memuat DPR dari cache, membuat baru...")
                        # Hapus file cache yang rusak
                        try:
                            os.remove(rag_model_path)
                            logger.info(f"File cache yang rusak telah dihapus: {rag_model_path}")
                        except:
                            pass
                        # Buat model baru
                        aes_dpr_retriever = DenseRetriever(chunks, cache_dir=cache_dir)
                        # Simpan model baru
                        aes_dpr_retriever.save(rag_model_path)
                except Exception as cache_err:
                    logger.warning(f"Error saat memuat dari cache: {cache_err}")
                    # Hapus file cache yang rusak
                    try:
                        os.remove(rag_model_path)
                        logger.info(f"File cache yang rusak telah dihapus: {rag_model_path}")
                    except:
                        pass
                    # Buat model baru
                    logger.info("Membuat model DPR baru...")
                    aes_dpr_retriever = DenseRetriever(chunks, cache_dir=cache_dir)
                    # Simpan model baru
                    aes_dpr_retriever.save(rag_model_path)
            else:
                logger.info("Model DPR tidak ditemukan, membuat baru...")
                aes_dpr_retriever = DenseRetriever(chunks, cache_dir=cache_dir)
                # Simpan model untuk penggunaan berikutnya
                aes_dpr_retriever.save(rag_model_path)
        except Exception as e:
            logger.error(f"Error saat inisialisasi DPR: {e}")
            logger.info("Melanjutkan tanpa DPR retriever...")
            aes_dpr_retriever = None
        
        # Inisialisasi Hybrid Retriever dengan adaptive alpha jika DPR tersedia
        if aes_dpr_retriever:
            logger.info("Menginisialisasi Hybrid Retriever dengan adaptive alpha...")
            aes_retriever = HybridRetriever(
                sparse_retriever=aes_sparse_retriever,
                dense_retriever=aes_dpr_retriever,
                alpha=0.5,  # Default alpha
                use_adaptive=True,  # Aktifkan adaptive alpha
                adaptive_method="confidence"  # Metode: confidence, score_distribution, atau overlap
            )
            logger.info("Hybrid Retriever dengan adaptive alpha berhasil diinisialisasi")
        else:
            # Fallback ke sparse retriever jika DPR tidak tersedia
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
        
        aes_evaluator = AnswerEvaluator(aes_model, aes_retriever)
        logger.info("AES system berhasil diinisialisasi")
        return True
        
    except Exception as e:
        logger.error(f"Error saat inisialisasi AES: {e}")
        return False

# API Routes
@app.route('/api/students', methods=['GET'])
def get_students():
    """Mendapatkan daftar semua siswa"""
    try:
        students_cursor = students_collection.find().sort("name", 1)  # Urutkan berdasarkan nama
        students = []
        
        for student in students_cursor:
            students.append({
                "id": str(student["_id"]),
                "name": student.get("name", ""),
                "nis": student.get("nis", ""),
                "created_at": student.get("created_at", get_timestamp())
            })
            
        return jsonify(students)
    except Exception as e:
        logger.error(f"Error saat mendapatkan daftar siswa: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/students', methods=['POST'])
def create_student():
    """Membuat siswa baru"""
    try:
        data = request.json
        name = data.get('name')
        nis = data.get('nis')
        
        if not name:
            return jsonify({"error": "Parameter 'name' diperlukan"}), 400
        if not nis:
            return jsonify({"error": "Parameter 'nis' diperlukan"}), 400
            
        # Cek apakah NIS sudah digunakan
        existing = students_collection.find_one({"nis": nis})
        if existing:
            return jsonify({"error": f"NIS '{nis}' sudah digunakan oleh siswa lain"}), 400
            
        # Buat siswa baru
        new_student = {
            "name": name,
            "nis": nis,
            "created_at": get_timestamp()
        }
        
        result = students_collection.insert_one(new_student)
        new_student_id = result.inserted_id
        
        return jsonify({
            "id": str(new_student_id),
            "name": name,
            "nis": nis,
            "created_at": new_student["created_at"]
        }), 201
    except Exception as e:
        logger.error(f"Error saat membuat siswa: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/students/<student_id>', methods=['GET'])
def get_student(student_id):
    """Mendapatkan detail siswa"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            student_obj_id = ObjectId(student_id)
            student = students_collection.find_one({"_id": student_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            student = students_collection.find_one({"_id": student_id})
            
        if not student:
            return jsonify({"error": f"Siswa dengan ID {student_id} tidak ditemukan"}), 404
            
        return jsonify({
            "id": str(student["_id"]),
            "name": student.get("name", ""),
            "nis": student.get("nis", ""),
            "created_at": student.get("created_at", get_timestamp())
        })
    except Exception as e:
        logger.error(f"Error saat mendapatkan detail siswa: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/students/<student_id>', methods=['PUT', 'PATCH'])
def update_student(student_id):
    """Memperbarui data siswa"""
    try:
        data = request.json
        
        # Validasi data
        if not data:
            return jsonify({"error": "Tidak ada data yang diberikan"}), 400
            
        # Coba konversi ke ObjectId jika valid
        try:
            student_obj_id = ObjectId(student_id)
            student = students_collection.find_one({"_id": student_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            student = students_collection.find_one({"_id": student_id})
            
        if not student:
            return jsonify({"error": f"Siswa dengan ID {student_id} tidak ditemukan"}), 404
            
        # Perbarui data
        update_data = {}
        
        if 'name' in data:
            update_data["name"] = data["name"]
            
        if 'nis' in data:
            # Cek apakah NIS sudah digunakan oleh siswa lain
            if data["nis"] != student.get("nis"):
                existing = students_collection.find_one({"nis": data["nis"], "_id": {"$ne": student["_id"]}})
                if existing:
                    return jsonify({"error": f"NIS '{data['nis']}' sudah digunakan oleh siswa lain"}), 400
            update_data["nis"] = data["nis"]
            
        if not update_data:
            return jsonify({"error": "Tidak ada data yang diperbarui"}), 400
            
        # Update di database
        students_collection.update_one({"_id": student["_id"]}, {"$set": update_data})
        
        # Ambil data terbaru
        updated_student = students_collection.find_one({"_id": student["_id"]})
        
        return jsonify({
            "id": str(updated_student["_id"]),
            "name": updated_student.get("name", ""),
            "nis": updated_student.get("nis", ""),
            "created_at": updated_student.get("created_at", get_timestamp())
        })
    except Exception as e:
        logger.error(f"Error saat memperbarui siswa: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    """Menghapus siswa"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            student_obj_id = ObjectId(student_id)
            student = students_collection.find_one({"_id": student_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            student = students_collection.find_one({"_id": student_id})
            
        if not student:
            return jsonify({"error": f"Siswa dengan ID {student_id} tidak ditemukan"}), 404
            
        # Cek apakah siswa memiliki jawaban
        answer_count = answers_collection.count_documents({"student_id": str(student["_id"])})
        if answer_count > 0:
            return jsonify({"error": f"Tidak dapat menghapus siswa karena memiliki {answer_count} jawaban terkait"}), 400
            
        # Hapus siswa
        students_collection.delete_one({"_id": student["_id"]})
        
        return jsonify({"message": "Siswa berhasil dihapus"})
    except Exception as e:
        logger.error(f"Error saat menghapus siswa: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint untuk cek kesehatan API"""
    return jsonify({"status": "ok", "message": "API berjalan dengan baik"})

@app.route('/api/sessions', methods=['POST'])
def create_session():
    """Membuat sesi ujian baru"""
    try:
        data = request.json
        exam_id = data.get('exam_id')
        exam_ids = data.get('exam_ids', [])
        student_ids = data.get('student_ids', [])
        total_students = data.get('total_students', 0)
        
        # Mendukung baik exam_id tunggal maupun array exam_ids
        if not exam_id and not exam_ids:
            return jsonify({"error": "Parameter 'exam_id' atau 'exam_ids' diperlukan"}), 400
            
        # Jika exam_ids disediakan, gunakan yang pertama sebagai exam_id utama
        if exam_ids and isinstance(exam_ids, list) and len(exam_ids) > 0:
            exam_id = exam_ids[0]
        
        # Jika student_ids disediakan, gunakan itu
        # Jika tidak, ambil dari database berdasarkan total_students
        if not student_ids or not isinstance(student_ids, list) or len(student_ids) == 0:
            if total_students and total_students > 0:
                # Ambil siswa dari database
                students_cursor = students_collection.find().limit(total_students)
                student_ids = [str(student["_id"]) for student in students_cursor]
                logger.info(f"Mengambil {len(student_ids)} siswa dari database untuk sesi")
            else:
                return jsonify({"error": "Parameter 'student_ids' atau 'total_students' diperlukan"}), 400
            
        # Validasi exam_id dan exam_ids
        primary_exam = None
        exams_list = []
        
        # Validasi exam_id utama
        try:
            exam_obj_id = ObjectId(exam_id)
            primary_exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            primary_exam = exams_collection.find_one({"_id": exam_id})
            
        if not primary_exam:
            return jsonify({"error": f"Ujian utama dengan ID {exam_id} tidak ditemukan"}), 404
            
        exams_list.append({
            "id": str(primary_exam["_id"]),
            "title": primary_exam["title"]
        })
        
        # Validasi exam_ids tambahan jika ada
        if exam_ids and isinstance(exam_ids, list) and len(exam_ids) > 1:
            for additional_exam_id in exam_ids[1:]:  # Skip yang pertama karena sudah divalidasi
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
                # Jika ID tidak valid, lanjutkan ke ID berikutnya
                continue
                
        if len(valid_students) == 0:
            return jsonify({"error": "Tidak ada siswa yang valid dalam daftar"}), 400
            
        # Generate session code
        import random
        import string
        session_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Buat session baru
        new_session = {
            "session_code": session_code,
            "exam_id": str(primary_exam["_id"]),  # Untuk kompatibilitas dengan kode lama
            "exams": exams_list,                 # Daftar semua ujian yang dipilih
            "students": valid_students,
            "total_students": len(valid_students),
            "current_student_index": 0,
            "current_student": valid_students[0] if valid_students else None,
            "current_exam_index": 0,             # Indeks ujian saat ini
            "is_completed": False,
            "created_at": get_timestamp()
        }
        
        # Simpan session
        result = sessions_collection.insert_one(new_session)
        new_session_id = result.inserted_id
        
        return jsonify({
            "id": str(new_session_id),
            "session_code": new_session["session_code"],
            "exam_id": new_session["exam_id"],
            "exam_title": primary_exam["title"],
            "exams": new_session["exams"],
            "students": new_session["students"],
            "total_students": new_session["total_students"],
            "current_student": new_session["current_student"],
            "current_student_index": new_session["current_student_index"],
            "current_exam_index": new_session["current_exam_index"],
            "is_completed": new_session["is_completed"],
            "created_at": new_session["created_at"]
        })
    except Exception as e:
        logger.error(f"Error saat membuat sesi: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """Mendapatkan detail sesi"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            return jsonify({"error": f"Sesi dengan ID {session_id} tidak ditemukan"}), 404
            
        # Ambil ujian
        try:
            exam_obj_id = ObjectId(session["exam_id"])
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": session["exam_id"]})
            
        exam_title = exam["title"] if exam else "Unknown Exam"
        
        # Ambil pertanyaan untuk ujian ini
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
            
        # Tambahkan daftar exams jika ada
        exams_list = session.get("exams", [])
        
        return jsonify({
            "id": str(session["_id"]),
            "session_code": session.get("session_code", ""),
            "exam_id": session["exam_id"],
            "exam_title": exam_title,
            "exams": exams_list,  # Tambahkan daftar ujian
            "students": session.get("students", []),
            "total_students": session.get("total_students", 0),
            "current_student": session.get("current_student", {}),
            "current_student_index": session.get("current_student_index", 0),
            "current_exam_index": session.get("current_exam_index", 0),  # Tambahkan indeks ujian saat ini
            "is_completed": session.get("is_completed", False),
            "created_at": session.get("created_at", get_timestamp()),
            "questions": questions
        })
    except Exception as e:
        logger.error(f"Error saat mendapatkan sesi: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions', methods=['GET'])
def get_sessions():
    """Mendapatkan daftar semua sesi ujian"""
    try:
        sessions_cursor = sessions_collection.find().sort("created_at", -1)  # Urutkan dari yang terbaru
        sessions = []
        
        for session in sessions_cursor:
            # Ambil ujian
            exam_title = "Unknown Exam"
            try:
                exam_obj_id = ObjectId(session["exam_id"])
                exam = exams_collection.find_one({"_id": exam_obj_id})
                if exam:
                    exam_title = exam["title"]
            except:
                pass
            
            # Tambahkan ke hasil
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
            
        return jsonify(sessions)
    except Exception as e:
        logger.error(f"Error saat mendapatkan daftar sesi: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/next-student', methods=['POST'])
def next_student(session_id):
    """Pindah ke siswa berikutnya dalam sesi"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            return jsonify({"error": f"Sesi dengan ID {session_id} tidak ditemukan"}), 404
            
        if session.get("is_completed", False):
            return jsonify({"error": "Sesi sudah selesai"}), 400
            
        # Ambil data siswa
        students = session.get("students", [])
        current_index = session.get("current_student_index", 0)
        
        # Periksa apakah sudah siswa terakhir
        if current_index >= len(students) - 1:
            # Update status sesi menjadi selesai
            sessions_collection.update_one(
                {"_id": session["_id"]},
                {"$set": {"is_completed": True}}
            )
            return jsonify({
                "message": "Sesi telah selesai",
                "session_id": str(session["_id"]),
                "is_completed": True
            })
            
        # Increment current_student_index
        new_index = current_index + 1
        next_student = students[new_index] if new_index < len(students) else None
        
        # Update session
        sessions_collection.update_one(
            {"_id": session["_id"]},
            {"$set": {
                "current_student_index": new_index,
                "current_student": next_student
            }}
        )
        
        # Ambil sesi yang sudah diupdate
        updated_session = sessions_collection.find_one({"_id": session["_id"]})
        
        return jsonify({
            "id": str(updated_session["_id"]),
            "session_code": updated_session.get("session_code", ""),
            "exam_id": updated_session["exam_id"],
            "current_student": updated_session.get("current_student"),
            "current_student_index": updated_session.get("current_student_index", 0),
            "total_students": len(students),
            "is_completed": updated_session.get("is_completed", False)
        })
    except Exception as e:
        logger.error(f"Error saat pindah ke siswa berikutnya: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/answers', methods=['GET'])
def get_session_answers(session_id):
    """Mendapatkan semua jawaban dalam sesi"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            return jsonify({"error": f"Sesi dengan ID {session_id} tidak ditemukan"}), 404
            
        # Ambil jawaban untuk sesi ini
        answers_cursor = answers_collection.find({"session_id": str(session["_id"])})
        
        result = []
        for answer in answers_cursor:
            # Ambil pertanyaan
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
            
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error saat mendapatkan jawaban sesi: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/answers', methods=['POST'])
def create_answer():
    """Membuat jawaban baru"""
    try:
        data = request.json
        question_id = data.get('question_id')
        answer_text = data.get('answer_text')
        session_id = data.get('session_id')  # Optional, untuk sesi ujian
        
        # Jika ada sesi, gunakan siswa saat ini dari sesi
        # Jika tidak, gunakan student_name dari request
        student_name = data.get('student_name')
        student_id = data.get('student_id')
        student_info = None
        
        if not question_id or not answer_text:
            return jsonify({"error": "Parameter 'question_id' dan 'answer_text' diperlukan"}), 400
            
        # Validasi question_id
        try:
            question_obj_id = ObjectId(question_id)
            question = questions_collection.find_one({"_id": question_obj_id})
        except:
            question = questions_collection.find_one({"_id": question_id})
            
        if not question:
            return jsonify({"error": f"Pertanyaan dengan ID {question_id} tidak ditemukan"}), 404
            
        # Validasi session_id jika ada
        if session_id:
            try:
                session_obj_id = ObjectId(session_id)
                session = sessions_collection.find_one({"_id": session_obj_id})
            except:
                session = sessions_collection.find_one({"_id": session_id})
                
            if not session:
                return jsonify({"error": f"Sesi dengan ID {session_id} tidak ditemukan"}), 404
                
            # Validasi bahwa sesi belum selesai
            if session.get("is_completed", False):
                return jsonify({"error": "Sesi sudah selesai, tidak dapat menambahkan jawaban baru"}), 400
                
            # Ambil informasi siswa saat ini dari sesi
            current_student = session.get("current_student")
            if current_student:
                student_info = current_student
                student_name = current_student.get("name")
                student_id = current_student.get("id")
        else:
            # Jika tidak ada sesi, harus ada student_name
            if not student_name:
                return jsonify({"error": "Parameter 'student_name' diperlukan jika tidak ada sesi"}), 400
                
            # Jika ada student_id, validasi
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
                    # Jika ID tidak valid, gunakan student_name saja
                    pass
        
        # Tentukan tipe soal dan konfigurasi skor dasar
        question_type = normalize_question_type(question.get("question_type"))
        scoring_defaults = get_scoring_defaults(question_type)

        # Buat jawaban baru
        new_answer = {
            "question_id": str(question["_id"]),
            "student_name": student_name,
            "answer_text": answer_text,
            "created_at": get_timestamp(),
            "question_type": question_type,
            "max_score": scoring_defaults["max_score"],
            "allowed_scores": scoring_defaults["allowed_scores"]
        }
        
        # Tambahkan student_info jika ada
        if student_info:
            new_answer["student"] = student_info
            
        # Tambahkan student_id jika ada
        if student_id:
            new_answer["student_id"] = student_id
        
        # Tambahkan session_id jika ada
        if session_id:
            new_answer["session_id"] = str(session["_id"])
        
        # Simpan jawaban
        result = answers_collection.insert_one(new_answer)
        new_answer_id = result.inserted_id
        
        # Jika ini adalah bagian dari sesi, tambahkan informasi sesi
        session_info = None
        if session_id:
            session_info = {
                "session_id": str(session["_id"]),
                "session_code": session.get("session_code", ""),
                "current_student": session.get("current_student"),
                "current_student_index": session.get("current_student_index", 0),
                "total_students": session.get("total_students", 0)
            }
        
        # Evaluasi jawaban jika AES tersedia
        if aes_evaluator:
            try:
                evaluation_result = aes_evaluator.evaluate_answer(
                    question["question_text"], 
                    answer_text, 
                    top_k=3,
                    question_type=question_type
                )
                
                updated_question_type = evaluation_result.get("question_type", question_type)
                updated_scoring = get_scoring_defaults(updated_question_type)
                
                # Update jawaban dengan hasil evaluasi
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
                
                # Ambil jawaban yang sudah diupdate
                updated_answer = answers_collection.find_one({"_id": new_answer_id})
                
                return jsonify({
                    "id": str(updated_answer["_id"]),
                    "question_id": str(question["_id"]),
                    "student": updated_answer.get("student"),
                    "student_name": updated_answer["student_name"],
                    "answer_text": updated_answer["answer_text"],
                    "score": updated_answer.get("score"),
                    "evaluation": updated_answer.get("evaluation"),
                    "references": updated_answer.get("references"),
                    "created_at": updated_answer.get("created_at"),
                    "evaluated_at": updated_answer.get("evaluated_at"),
                    "question_type": updated_answer.get("question_type", updated_question_type),
                    "max_score": updated_answer.get("max_score", updated_scoring["max_score"]),
                    "allowed_scores": updated_answer.get("allowed_scores", updated_scoring["allowed_scores"]),
                    "session": session_info
                }), 201
            except Exception as e:
                logger.error(f"Error saat evaluasi jawaban: {e}")
        
        return jsonify({
            "id": str(new_answer_id),
            "question_id": str(question["_id"]),
            "student": new_answer.get("student"),
            "student_name": student_name,
            "answer_text": answer_text,
            "created_at": new_answer["created_at"],
            "question_type": question_type,
            "max_score": scoring_defaults["max_score"],
            "allowed_scores": scoring_defaults["allowed_scores"],
            "session": session_info
        }), 201
    except Exception as e:
        logger.error(f"Error saat membuat jawaban: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/summary', methods=['GET'])
def get_session_summary(session_id):
    """Mendapatkan ringkasan hasil sesi"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            session_obj_id = ObjectId(session_id)
            session = sessions_collection.find_one({"_id": session_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            session = sessions_collection.find_one({"_id": session_id})
            
        if not session:
            return jsonify({"error": f"Sesi dengan ID {session_id} tidak ditemukan"}), 404
            
        # Ambil semua jawaban dalam sesi
        answers_cursor = answers_collection.find({"session_id": str(session["_id"])})
        
        # Kelompokkan jawaban berdasarkan student_name
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
            
            # Ambil pertanyaan
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
            allowed_scores = answer.get("allowed_scores", scoring_defaults["allowed_scores"])
            score_value = answer.get("score")
            evaluation_text = answer.get("evaluation", "")
            
            student_results[student_name]["answers"].append({
                "question_id": answer["question_id"],
                "question_text": question_text,
                "answer_text": answer["answer_text"],
                "score": score_value,
                "max_score": max_score,
                "question_type": answer_type,
                "allowed_scores": allowed_scores,
                "evaluation": evaluation_text
            })
            
            if score_value is not None:
                student_results[student_name]["total_score"] += score_value
                student_results[student_name]["total_max_score"] += max_score
                student_results[student_name]["question_count"] += 1
        
        # Hitung rata-rata skor untuk setiap siswa
        for data in student_results.values():
            if data["question_count"] > 0:
                data["average_score"] = data["total_score"] / data["question_count"]
            if data["total_max_score"] > 0:
                data["average_percentage"] = data["total_score"] / data["total_max_score"]
                
        # Ambil ujian
        try:
            exam_obj_id = ObjectId(session["exam_id"])
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": session["exam_id"]})
            
        exam_title = exam["title"] if exam else "Unknown Exam"
        
        return jsonify({
            "session_id": str(session["_id"]),
            "session_code": session.get("session_code", ""),
            "exam_id": session["exam_id"],
            "exam_title": exam_title,
            "total_students": session.get("total_students", 1),
            "is_completed": session.get("is_completed", False),
            "student_results": list(student_results.values())
        })
    except Exception as e:
        logger.error(f"Error saat mendapatkan ringkasan sesi: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/questions', methods=['GET'])
def get_all_questions():
    """Mendapatkan semua pertanyaan dari semua ujian"""
    try:
        questions = []
        exams_cursor = exams_collection.find()
        
        for exam in exams_cursor:
            # Ambil pertanyaan untuk ujian ini
            questions_cursor = questions_collection.find({"exam_id": str(exam["_id"])})
            
            for question in questions_cursor:
                question_type = normalize_question_type(question.get("question_type"))
                scoring_defaults = get_scoring_defaults(question_type)
                questions.append({
                    "id": str(question["_id"]),
                    "question_text": question["question_text"],
                    "exam_id": str(exam["_id"]),
                    "exam_title": exam["title"],
                    "question_type": question_type,
                    "max_score": question.get("max_score", scoring_defaults["max_score"]),
                    "allowed_scores": question.get("allowed_scores", scoring_defaults["allowed_scores"])
                })
        
        return jsonify(questions)
    except Exception as e:
        logger.error(f"Error saat mengambil semua pertanyaan: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams', methods=['GET'])
def get_exams():
    """Mendapatkan daftar semua ujian"""
    try:
        exams = list(exams_collection.find())
        result = []
        
        for exam in exams:
            # Hitung jumlah pertanyaan
            question_count = questions_collection.count_documents({"exam_id": str(exam["_id"])})
            
            result.append({
                "id": str(exam["_id"]),
                "title": exam["title"],
                "description": exam.get("description", ""),
                "created_at": exam.get("created_at", get_timestamp()),
                "question_count": question_count
            })
            
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error saat mengambil daftar ujian: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams', methods=['POST'])
def create_exam():
    """Membuat ujian baru"""
    try:
        data = request.json
        
        if not data.get('title'):
            return jsonify({"error": "Parameter 'title' diperlukan"}), 400
            
        new_exam = {
            "title": data['title'],
            "description": data.get('description', ''),
            "created_at": get_timestamp()
        }
        
        result = exams_collection.insert_one(new_exam)
        
        return jsonify({
            "id": str(result.inserted_id),
            "title": new_exam["title"],
            "description": new_exam["description"],
            "created_at": new_exam["created_at"]
        }), 201
    except Exception as e:
        logger.error(f"Error saat membuat ujian: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams/<exam_id>', methods=['PATCH'])
def update_exam(exam_id):
    """Memperbarui detail ujian (judul / deskripsi)."""
    try:
        data = request.json or {}
        update_fields = {}

        if "title" in data:
            title = str(data["title"]).strip()
            if not title:
                return jsonify({"error": "Parameter 'title' tidak boleh kosong"}), 400
            update_fields["title"] = title

        if "description" in data:
            update_fields["description"] = str(data["description"]).strip()

        if not update_fields:
            return jsonify({"error": "Tidak ada field yang diperbarui"}), 400

        # Temukan ujian
        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            exam = exams_collection.find_one({"_id": exam_id})

        if not exam:
            return jsonify({"error": f"Ujian dengan ID {exam_id} tidak ditemukan"}), 404

        # Update ujian
        exams_collection.update_one({"_id": exam["_id"]}, {"$set": update_fields})
        updated_exam = exams_collection.find_one({"_id": exam["_id"]})

        return jsonify({
            "id": str(updated_exam["_id"]),
            "title": updated_exam["title"],
            "description": updated_exam.get("description", ""),
            "created_at": updated_exam.get("created_at", get_timestamp())
        })
    except Exception as e:
        logger.error(f"Error saat memperbarui ujian: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams/<exam_id>', methods=['GET'])
def get_exam(exam_id):
    """Mendapatkan detail ujian"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            exam = exams_collection.find_one({"_id": exam_id})
            
        if not exam:
            return jsonify({"error": f"Ujian dengan ID {exam_id} tidak ditemukan"}), 404
            
        # Ambil pertanyaan untuk ujian ini
        questions_cursor = questions_collection.find({"exam_id": str(exam["_id"])})
        questions = []
        
        for question in questions_cursor:
            # Hitung jumlah jawaban
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
            
        return jsonify({
            "id": str(exam["_id"]),
            "title": exam["title"],
            "description": exam.get("description", ""),
            "created_at": exam.get("created_at", get_timestamp()),
            "questions": questions
        })
    except Exception as e:
        logger.error(f"Error saat mengambil detail ujian: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams/<exam_id>/questions', methods=['GET'])
def get_exam_questions(exam_id):
    """Mendapatkan semua pertanyaan untuk ujian tertentu"""
    logger.info(f"Mendapatkan pertanyaan untuk ujian dengan ID: {exam_id}")
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            exam = exams_collection.find_one({"_id": exam_id})
            
        if not exam:
            return jsonify({"error": f"Ujian dengan ID {exam_id} tidak ditemukan"}), 404
            
        # Ambil pertanyaan untuk ujian ini
        questions_cursor = questions_collection.find({"exam_id": str(exam["_id"])})
        questions = []
        
        for question in questions_cursor:
            question_type = normalize_question_type(question.get("question_type"))
            scoring_defaults = get_scoring_defaults(question_type)
            questions.append({
                "id": str(question["_id"]),
                "question_text": question["question_text"],
                "created_at": question.get("created_at", get_timestamp()),
                "question_type": question_type,
                "max_score": question.get("max_score", scoring_defaults["max_score"]),
                "allowed_scores": question.get("allowed_scores", scoring_defaults["allowed_scores"]),
                "exam_id": str(exam["_id"]),
                "exam_title": exam["title"]
            })
                
        logger.info(f"Ditemukan {len(questions)} pertanyaan untuk ujian {exam_id}")
        return jsonify(questions)
    except Exception as e:
        logger.error(f"Error saat mengambil pertanyaan ujian: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams/<exam_id>/questions', methods=['POST'])
def create_question(exam_id):
    """Membuat pertanyaan baru untuk ujian"""
    logger.info(f"Mencoba membuat pertanyaan baru untuk ujian dengan ID: {exam_id}")
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            logger.info(f"Mencoba konversi {exam_id} ke ObjectId")
            exam_obj_id = ObjectId(exam_id)
            exam = exams_collection.find_one({"_id": exam_obj_id})
            logger.info(f"Hasil pencarian dengan ObjectId: {exam is not None}")
        except Exception as e:
            logger.info(f"Konversi ke ObjectId gagal: {e}, mencoba dengan string ID")
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            exam = exams_collection.find_one({"_id": exam_id})
            logger.info(f"Hasil pencarian dengan string ID: {exam is not None}")
            
        if not exam:
            logger.warning(f"Ujian dengan ID {exam_id} tidak ditemukan")
            return jsonify({"error": f"Ujian dengan ID {exam_id} tidak ditemukan"}), 404
            
        data = request.json
        logger.info(f"Data request: {data}")
        question_text = data.get('question_text')
        question_type = normalize_question_type(data.get('question_type'))
        scoring_defaults = get_scoring_defaults(question_type)
        
        if not question_text:
            logger.warning("Parameter 'question_text' tidak ditemukan dalam request")
            return jsonify({"error": "Parameter 'question_text' diperlukan"}), 400
        
        # Untuk MongoDB
        logger.info("Menggunakan MongoDB Atlas untuk menyimpan pertanyaan")
        question = {
            "exam_id": str(exam["_id"]),
            "question_text": question_text,
            "created_at": get_timestamp(),
            "question_type": question_type,
            "max_score": scoring_defaults["max_score"],
            "allowed_scores": scoring_defaults["allowed_scores"]
        }
        
        # Tambahkan informasi database dan koleksi
        if hasattr(db, 'name'):
            logger.info(f"Database: {db.name}, Koleksi: questions")
        
        logger.info(f"Mencoba insert_one dengan data: {question}")
        result = questions_collection.insert_one(question)
        logger.info(f"Pertanyaan berhasil disimpan dengan ID: {result.inserted_id}")
        
        # Verifikasi bahwa data berhasil disimpan
        try:
            saved_question = questions_collection.find_one({"_id": result.inserted_id})
            if saved_question:
                logger.info(f"Verifikasi: Data berhasil disimpan dan dapat diambil kembali dengan ID: {result.inserted_id}")
            else:
                logger.warning(f"Verifikasi gagal: Data tidak ditemukan setelah disimpan dengan ID: {result.inserted_id}")
        except Exception as e:
            logger.warning(f"Gagal memverifikasi penyimpanan data: {e}")
        
        return jsonify({
            "id": str(result.inserted_id),
            "exam_id": question["exam_id"],
            "question_text": question["question_text"],
            "created_at": question["created_at"],
            "question_type": question["question_type"],
            "max_score": question["max_score"],
            "allowed_scores": question["allowed_scores"]
        }), 201
    except Exception as e:
        logger.error(f"Error saat membuat pertanyaan: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/questions/<question_id>', methods=['GET', 'PATCH'])
def handle_question(question_id):
    """Mendapatkan atau memperbarui pertanyaan beserta penilaian terkait."""
    try:
        question = load_question_document(question_id)
        if not question:
            return jsonify({"error": f"Pertanyaan dengan ID {question_id} tidak ditemukan"}), 404

        if request.method == 'PATCH':
            data = request.json or {}
            try:
                update_result = update_question_and_answers(question, data)
            except ValueError as validation_err:
                return jsonify({"error": str(validation_err)}), 400

            return jsonify(update_result)

        return jsonify(serialize_question_response(question, include_answers=True))
    except Exception as e:
        logger.error(f"Error saat memproses permintaan pertanyaan: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/questions/<question_id>/answers', methods=['POST'])
def submit_answer(question_id):
    """Mengirimkan jawaban untuk pertanyaan"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            question_obj_id = ObjectId(question_id)
            question = questions_collection.find_one({"_id": question_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            question = questions_collection.find_one({"_id": question_id})
            
        if not question:
            return jsonify({"error": f"Pertanyaan dengan ID {question_id} tidak ditemukan"}), 404
            
        data = request.json
        student_name = data.get('student_name')
        answer_text = data.get('answer_text')
        session_id = data.get('session_id')
        
        if not student_name or not answer_text:
            return jsonify({"error": "Parameter 'student_name' dan 'answer_text' diperlukan"}), 400
        
        question_type = normalize_question_type(question.get("question_type"))
        scoring_defaults = get_scoring_defaults(question_type)

        # Buat jawaban baru
        new_answer = {
            "question_id": str(question["_id"]),
            "student_name": student_name,
            "answer_text": answer_text,
            "created_at": get_timestamp(),
            "question_type": question_type,
            "max_score": scoring_defaults["max_score"],
            "allowed_scores": scoring_defaults["allowed_scores"]
        }
        
        # Tambahkan session_id jika ada
        if session_id:
            new_answer["session_id"] = session_id
        
        # Simpan jawaban
        result = answers_collection.insert_one(new_answer)
        new_answer_id = result.inserted_id
        
        # Evaluasi jawaban secara asinkron (dalam kasus nyata gunakan task queue)
        # Untuk sekarang, kita evaluasi langsung
        if aes_evaluator:
            try:
                evaluation_result = aes_evaluator.evaluate_answer(
                    question["question_text"], 
                    answer_text, 
                    top_k=3,
                    question_type=question_type
                )
                
                updated_question_type = evaluation_result.get("question_type", question_type)
                updated_scoring = get_scoring_defaults(updated_question_type)
                
                # Update jawaban dengan hasil evaluasi
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
                
                # Ambil jawaban yang sudah diupdate
                updated_answer = answers_collection.find_one({"_id": new_answer_id})
                
                return jsonify({
                    "id": str(updated_answer["_id"]),
                    "question_id": updated_answer["question_id"],
                    "student_name": updated_answer["student_name"],
                    "answer_text": updated_answer["answer_text"],
                    "score": updated_answer.get("score"),
                    "evaluation": updated_answer.get("evaluation"),
                    "references": updated_answer.get("references"),
                    "created_at": updated_answer.get("created_at"),
                    "evaluated_at": updated_answer.get("evaluated_at"),
                    "question_type": updated_answer.get("question_type", updated_question_type),
                    "max_score": updated_answer.get("max_score", updated_scoring["max_score"]),
                    "allowed_scores": updated_answer.get("allowed_scores", updated_scoring["allowed_scores"])
                }), 201
            except Exception as e:
                logger.error(f"Error saat evaluasi jawaban: {e}")
                # Tetap kembalikan jawaban meski evaluasi gagal
                return jsonify({
                    "id": str(new_answer_id),
                    "question_id": str(question["_id"]),
                    "student_name": student_name,
                    "answer_text": answer_text,
                    "score": None,
                    "evaluation": "Evaluasi gagal: " + str(e),
                    "references": [],
                    "created_at": new_answer["created_at"],
                    "evaluated_at": None,
                    "question_type": question_type,
                    "max_score": scoring_defaults["max_score"],
                    "allowed_scores": scoring_defaults["allowed_scores"]
                }), 201
        else:
            return jsonify({
                "id": str(new_answer_id),
                "question_id": str(question["_id"]),
                "student_name": student_name,
                "answer_text": answer_text,
                "score": None,
                "evaluation": "Sistem AES belum diinisialisasi",
                "references": [],
                "created_at": new_answer["created_at"],
                "evaluated_at": None,
                "question_type": question_type,
                "max_score": scoring_defaults["max_score"],
                "allowed_scores": scoring_defaults["allowed_scores"]
            }), 201
    except Exception as e:
        logger.error(f"Error saat mengirim jawaban: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/answers/<answer_id>', methods=['GET'])
def get_answer(answer_id):
    """Mendapatkan detail jawaban"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            answer_obj_id = ObjectId(answer_id)
            answer = answers_collection.find_one({"_id": answer_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            answer = answers_collection.find_one({"_id": answer_id})
            
        if not answer:
            return jsonify({"error": f"Jawaban dengan ID {answer_id} tidak ditemukan"}), 404
            
        # Ambil references jika ada
        references = answer.get("references", [])
        question_type = normalize_question_type(answer.get("question_type"))
        scoring_defaults = get_scoring_defaults(question_type)
        
        # Konversi ObjectId ke string
        answer_data = {
            "id": str(answer["_id"]),
            "question_id": answer["question_id"],
            "student_name": answer["student_name"],
            "answer_text": answer["answer_text"],
            "score": answer.get("score"),
            "evaluation": answer.get("evaluation"),
            "references": references,
            "created_at": answer.get("created_at"),
            "evaluated_at": answer.get("evaluated_at"),
            "question_type": question_type,
            "max_score": answer.get("max_score", scoring_defaults["max_score"]),
            "allowed_scores": answer.get("allowed_scores", scoring_defaults["allowed_scores"])
        }
        
        # Tambahkan session_id jika ada
        if "session_id" in answer:
            answer_data["session_id"] = answer["session_id"]
        
        return jsonify(answer_data)
    except Exception as e:
        logger.error(f"Error saat mengambil detail jawaban: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/answers/<answer_id>/evaluate', methods=['POST'])
def evaluate_answer(answer_id):
    """Mengevaluasi atau mengevaluasi ulang jawaban"""
    try:
        # Coba konversi ke ObjectId jika valid
        try:
            answer_obj_id = ObjectId(answer_id)
            answer = answers_collection.find_one({"_id": answer_obj_id})
        except:
            # Jika bukan ObjectId yang valid, cari berdasarkan string ID
            answer = answers_collection.find_one({"_id": answer_id})
            
        if not answer:
            return jsonify({"error": f"Jawaban dengan ID {answer_id} tidak ditemukan"}), 404
            
        # Ambil pertanyaan
        try:
            question_obj_id = ObjectId(answer["question_id"])
            question = questions_collection.find_one({"_id": question_obj_id})
        except:
            question = questions_collection.find_one({"_id": answer["question_id"]})
            
        if not question:
            return jsonify({"error": f"Pertanyaan dengan ID {answer['question_id']} tidak ditemukan"}), 404
        
        if not aes_evaluator:
            return jsonify({"error": "Sistem AES belum diinisialisasi"}), 500
        
        question_type_source = normalize_question_type(
            answer.get("question_type") or question.get("question_type")
        )
        scoring_defaults = get_scoring_defaults(question_type_source)

        evaluation_result = aes_evaluator.evaluate_answer(
            question["question_text"], 
            answer["answer_text"], 
            top_k=3,
            question_type=question_type_source
        )
        
        updated_question_type = evaluation_result.get("question_type", question_type_source)
        updated_scoring = get_scoring_defaults(updated_question_type)
        
        # Update jawaban dengan hasil evaluasi
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
        
        # Ambil jawaban yang sudah diupdate
        updated_answer = answers_collection.find_one({"_id": answer["_id"]})
        
        return jsonify({
            "id": str(updated_answer["_id"]),
            "question_id": updated_answer["question_id"],
            "student_name": updated_answer["student_name"],
            "answer_text": updated_answer["answer_text"],
            "score": updated_answer.get("score"),
            "evaluation": updated_answer.get("evaluation"),
            "references": updated_answer.get("references"),
            "created_at": updated_answer.get("created_at"),
            "evaluated_at": updated_answer.get("evaluated_at"),
            "question_type": updated_answer.get("question_type", updated_question_type),
            "max_score": updated_answer.get("max_score", updated_scoring["max_score"]),
            "allowed_scores": updated_answer.get("allowed_scores", updated_scoring["allowed_scores"])
        })
    except Exception as e:
        logger.error(f"Error saat evaluasi jawaban: {e}")
        return jsonify({"error": str(e)}), 500

def compare_retrievers(query: str, sparse_retriever, dense_retriever, top_k: int = 5, normalize_scores: bool = True) -> Dict[str, Any]:
    """
    Membandingkan hasil retrieval dari sparse (BM25) dan dense (DPR) retriever
    
    Args:
        query: Query pencarian
        sparse_retriever: Instance BM25Retriever atau sparse retriever lainnya
        dense_retriever: Instance DenseRetriever
        top_k: Jumlah dokumen teratas yang akan dikembalikan
        normalize_scores: Apakah skor perlu dinormalisasi
        
    Returns:
        Dictionary berisi hasil perbandingan
    """
    import time
    
    # Retrieve dengan BM25
    start_time = time.time()
    bm25_results = sparse_retriever.retrieve(query, top_k=top_k, min_score=0.5)
    bm25_time = time.time() - start_time
    
    # Retrieve dengan DPR
    start_time = time.time()
    dpr_results = dense_retriever.retrieve(query, top_k=top_k)
    dpr_time = time.time() - start_time
    
    # Hitung overlap
    bm25_indices = set(r.get("index", -1) for r in bm25_results)
    dpr_indices = set(r.get("index", -1) for r in dpr_results)
    overlap = len(bm25_indices & dpr_indices)
    overlap_percentage = (overlap / top_k * 100) if top_k > 0 else 0.0
    
    return {
        "query": query,
        "bm25_results": bm25_results,
        "dpr_results": dpr_results,
        "bm25_time": bm25_time,
        "dpr_time": dpr_time,
        "overlap": overlap,
        "overlap_percentage": overlap_percentage
    }

@app.route('/api/compare-rag', methods=['POST'])
def compare_rag_api():
    """Membandingkan hasil RAG (BM25 vs DPR)"""
    try:
        logger.info("Memproses permintaan compare-rag")
        data = request.json
        question = data.get('question')
        
        logger.info(f"Pertanyaan yang diterima: {question}")
        
        if not question:
            logger.warning("Parameter 'question' tidak ditemukan dalam request")
            return jsonify({"error": "Parameter 'question' diperlukan"}), 400
            
        if not aes_retriever:
            logger.error("Sistem AES belum diinisialisasi (aes_retriever tidak tersedia)")
            # Coba inisialisasi ulang
            logger.info("Mencoba inisialisasi ulang sistem AES...")
            success = initialize_aes()
            if not success or not aes_retriever:
                return jsonify({
                    "error": "Sistem AES belum diinisialisasi",
                    "detail": "Gagal menginisialisasi sistem AES. Pastikan file PDF dan model tersedia."
                }), 500
        
        # Pastikan aes_retriever tersedia
        if not aes_retriever:
            logger.error("BM25 retriever tidak tersedia, tidak dapat melanjutkan")
            return jsonify({
                "error": "Sistem AES tidak diinisialisasi dengan benar",
                "detail": "BM25 retriever tidak tersedia"
            }), 500
        
        # Jika DPR retriever tersedia, gunakan untuk perbandingan
        if aes_dpr_retriever and aes_sparse_retriever:
            logger.info("Menggunakan DPR retriever untuk perbandingan")
            # Gunakan fungsi compare_retrievers untuk mendapatkan hasil perbandingan
            try:
                comparison = compare_retrievers(question, aes_sparse_retriever, aes_dpr_retriever, top_k=5, normalize_scores=True)
                logger.info(f"Perbandingan berhasil: {len(comparison['bm25_results'])} hasil BM25, {len(comparison['dpr_results'])} hasil DPR")
                
                return jsonify({
                    "query": comparison["query"],
                    "bm25_results": comparison["bm25_results"],
                    "dpr_results": comparison["dpr_results"],
                    "bm25_time": comparison["bm25_time"],
                    "dpr_time": comparison["dpr_time"],
                    "overlap": comparison["overlap"],
                    "overlap_percentage": comparison["overlap_percentage"]
                })
            except Exception as comp_err:
                logger.error(f"Error saat membandingkan dengan DPR: {comp_err}")
                logger.info("Mencoba fallback ke BM25 saja...")
                # Fallback ke BM25 jika perbandingan gagal
                try:
                    bm25_results = aes_retriever.retrieve(question, top_k=5, min_score=0.5)
                    logger.info(f"BM25 retrieval berhasil: {len(bm25_results)} hasil")
                    
                    # Dummy hasil untuk DPR dengan pesan error
                    dpr_results = [
                        {
                            "chunk": f"Error saat menggunakan DPR: {str(comp_err)}. Instal dependensi dengan 'pip install -r requirements_dpr.txt'",
                            "score": 0.0,
                            "index": -1
                        }
                    ]
                    
                    return jsonify({
                        "query": question,
                        "bm25_results": bm25_results,
                        "dpr_results": dpr_results,
                        "bm25_time": 0.0,
                        "dpr_time": 0.0,
                        "overlap": 0,
                        "overlap_percentage": 0.0,
                        "warning": "Gagal menggunakan DPR, hanya menggunakan BM25"
                    })
                except Exception as fallback_err:
                    logger.error(f"Error saat fallback ke BM25: {fallback_err}")
                    raise fallback_err
        else:
            logger.info("DPR retriever tidak tersedia, menggunakan hanya BM25")
            # Jika DPR tidak tersedia, gunakan hanya BM25
            try:
                bm25_results = aes_retriever.retrieve(question, top_k=5, min_score=0.5)
                logger.info(f"BM25 retrieval berhasil: {len(bm25_results)} hasil")
                
                # Dummy hasil untuk DPR
                dpr_results = [
                    {
                        "chunk": "DPR retriever tidak tersedia. Instal dependensi dengan 'pip install -r requirements_dpr.txt'",
                        "score": 0.0,
                        "index": -1
                    }
                ]
                
                return jsonify({
                    "query": question,
                    "bm25_results": bm25_results,
                    "dpr_results": dpr_results,
                    "bm25_time": 0.0,
                    "dpr_time": 0.0,
                    "overlap": 0,
                    "overlap_percentage": 0.0
                })
            except Exception as bm25_err:
                logger.error(f"Error saat melakukan BM25 retrieval: {bm25_err}")
                raise bm25_err
    except Exception as e:
        logger.error(f"Error saat membandingkan RAG: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/initialize-aes', methods=['POST'])
def init_aes():
    """Endpoint untuk menginisialisasi sistem AES"""
    try:
        logger.info("Mencoba menginisialisasi sistem AES dari API endpoint...")
        
        # Reset variabel global
        global aes_processor, aes_retriever, aes_dpr_retriever, aes_model, aes_evaluator
        aes_processor = None
        aes_retriever = None
        aes_dpr_retriever = None
        aes_model = None
        aes_evaluator = None
        
        # Inisialisasi ulang
        success = initialize_aes()
        
        if success:
            logger.info("Sistem AES berhasil diinisialisasi dari API endpoint")
            return jsonify({
                "status": "success", 
                "message": "Sistem AES berhasil diinisialisasi",
                "details": {
                    "processor": aes_processor is not None,
                    "retriever": aes_retriever is not None,
                    "dpr_retriever": aes_dpr_retriever is not None,
                    "model": aes_model is not None,
                    "evaluator": aes_evaluator is not None
                }
            })
        else:
            logger.error("Gagal menginisialisasi sistem AES dari API endpoint")
            return jsonify({
                "status": "error", 
                "message": "Gagal menginisialisasi sistem AES",
                "details": "Periksa log server untuk informasi lebih lanjut"
            }), 500
    except Exception as e:
        logger.error(f"Error saat menginisialisasi AES dari API endpoint: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint untuk mendapatkan daftar siswa sudah didefinisikan di atas
# Kode di bawah ini dinonaktifkan untuk menghindari duplikasi
# @app.route('/api/students', methods=['GET'])
# def get_students_legacy():
#     """Mendapatkan daftar semua siswa (versi lama)"""
#     try:
#         students = list(students_collection.find())
#         result = []
#         
#         for student in students:
#             result.append({
#                 "id": str(student["_id"]),
#                 "name": student["name"],
#                 "nis": student["nis"],
#                 "kelas": student["kelas"],
#                 "created_at": student.get("created_at", get_timestamp())
#             })
#             
#         return jsonify(result)
#     except Exception as e:
#         logger.error(f"Error saat mengambil daftar siswa: {e}")
#         return jsonify({"error": str(e)}), 500

# Fungsi yang dijalankan saat request pertama
@app.before_request
def before_request():
    # Jalankan hanya sekali saat request pertama
    if not getattr(app, '_got_first_request', False):
        app._got_first_request = True
        # Coba inisialisasi AES
        initialize_aes()
        # Inisialisasi data template
        initialize_template_data()

if __name__ == '__main__':
    # Inisialisasi AES system sebelum server dimulai
    logger.info("Menginisialisasi sistem AES sebelum server dimulai...")
    success = initialize_aes()
    if success:
        logger.info("Sistem AES berhasil diinisialisasi")
    else:
        logger.warning("Gagal menginisialisasi sistem AES, beberapa fitur mungkin tidak berfungsi")
    
    # Inisialisasi data template
    logger.info("Menginisialisasi data template...")
    template_success = initialize_template_data()
    if template_success:
        logger.info("Data template berhasil diinisialisasi")
    else:
        logger.warning("Gagal menginisialisasi data template")
        
    # Jalankan server dengan konfigurasi yang lebih stabil
    # Matikan hot-reloading untuk menghindari error socket di Windows
    app.run(
        debug=True,                # Mode debug tetap aktif
        port=5000,                 # Port server
        use_reloader=False,        # Matikan hot-reloading untuk mencegah error socket
        threaded=True,             # Gunakan threading untuk menangani request secara paralel
        host='0.0.0.0'             # Terima koneksi dari semua interface
    )