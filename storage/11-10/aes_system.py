#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sistem Penilaian Otomatis Jawaban Siswa (AES)
Menggunakan LLM Llama-3.2 dan RAG dengan BM25
"""

import os
import sys
import json
import argparse
import time
import subprocess
import tempfile
import re
from pathlib import Path
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import logging
import concurrent.futures

from dense_retriever import DenseRetriever

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("AES")

# Pastikan direktori saat ini ada di PYTHONPATH
current_dir = Path(__file__).parent.absolute()
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Kelas untuk mengelola dokumen dan pemrosesan teks
class DocumentProcessor:
    """Kelas untuk memproses dokumen PDF dan mengekstrak teks"""
    
    def __init__(self, pdf_path: str):
        """
        Inisialisasi processor dokumen
        
        Args:
            pdf_path: Path ke file PDF yang akan diproses
        """
        self.pdf_path = pdf_path
        self.raw_text = ""
        self.chunks = []
        
    def extract_text_from_pdf(self) -> str:
        """Ekstrak teks dari file PDF"""
        try:
            import PyPDF2
            with open(self.pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() + "\n"
                self.raw_text = text
                return text
        except ImportError:
            logger.error("PyPDF2 tidak ditemukan. Menginstal dengan 'pip install PyPDF2'")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Gagal mengekstrak teks dari PDF: {e}")
            sys.exit(1)
    
    def chunk_text(self, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        Membagi teks menjadi chunk yang lebih kecil dengan metode yang ditingkatkan
        
        Args:
            chunk_size: Ukuran maksimal setiap chunk
            overlap: Jumlah karakter yang overlap antar chunk
            
        Returns:
            List chunk teks
        """
        if not self.raw_text:
            self.extract_text_from_pdf()
            
        text = self.raw_text
        chunks = []
        
        # Deteksi batas topik berdasarkan judul atau kata kunci
        import re
        
        # Pola untuk mendeteksi judul atau sub-judul
        # Contoh: "BAB I", "1.1 Pendahuluan", "A. Fotosintesis"
        title_patterns = [
            r'\n\s*BAB\s+[IVX]+\s*[\.:)]?\s*\w+',  # BAB I: Pendahuluan
            r'\n\s*\d+\.\d+\s+\w+',            # 1.1 Pendahuluan
            r'\n\s*[A-Z]\.\s+\w+',             # A. Pendahuluan
            r'\n\s*\d+\.\s+\w+',               # 1. Pendahuluan
            r'\n\s*[A-Z]\. \w+'                # A. Pendahuluan (spasi setelah titik)
        ]
        
        # Gabungkan semua pola
        combined_pattern = '|'.join(title_patterns)
        
        # Coba split berdasarkan pola judul
        topic_chunks = re.split(combined_pattern, text)
        titles = re.findall(combined_pattern, text)
        
        # Jika berhasil menemukan judul, gabungkan judul dengan konten
        if len(titles) > 0 and len(topic_chunks) > 1:
            # Chunk pertama mungkin tidak memiliki judul
            if topic_chunks[0].strip():
                chunks.append(topic_chunks[0].strip())
                
            # Gabungkan judul dengan konten untuk chunk berikutnya
            for i in range(len(titles)):
                if i < len(topic_chunks) - 1:
                    topic_text = titles[i] + topic_chunks[i+1]
                    
                    # Jika topik terlalu panjang, bagi lagi
                    if len(topic_text) > chunk_size:
                        sub_chunks = self._chunk_by_paragraphs(topic_text, chunk_size, overlap)
                        chunks.extend(sub_chunks)
                    else:
                        chunks.append(topic_text.strip())
        else:
            # Jika tidak menemukan pola judul, gunakan metode chunking berdasarkan paragraf
            chunks = self._chunk_by_paragraphs(text, chunk_size, overlap)
        
        self.chunks = chunks
        return chunks
    
    def _chunk_by_paragraphs(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        Membagi teks menjadi chunk berdasarkan paragraf
        
        Args:
            text: Teks yang akan dibagi
            chunk_size: Ukuran maksimal setiap chunk
            overlap: Jumlah karakter yang overlap antar chunk
            
        Returns:
            List chunk teks
        """
        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            # Jika paragraf mengandung kata kunci penting, tandai sebagai chunk terpisah
            important_keywords = ['fotosintesis', 'sel hewan', 'sel tumbuhan', 'klorofil', 'kloroplas', 
                                'dinding sel', 'vakuola', 'sentriol', 'mitokondria']
            
            is_important = any(keyword.lower() in para.lower() for keyword in important_keywords)
            
            if is_important and current_chunk and len(para) < chunk_size:
                # Simpan chunk saat ini dan mulai chunk baru dengan paragraf penting
                chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
                continue
                
            if len(current_chunk) + len(para) <= chunk_size:
                current_chunk += para + "\n\n"
            else:
                # Simpan chunk saat ini jika tidak kosong
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # Jika paragraf lebih besar dari chunk_size, bagi lagi
                if len(para) > chunk_size:
                    sentences = para.split('. ')
                    current_chunk = ""
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) <= chunk_size:
                            current_chunk += sentence + ". "
                        else:
                            chunks.append(current_chunk.strip())
                            current_chunk = sentence + ". "
                else:
                    current_chunk = para + "\n\n"
        
        # Tambahkan chunk terakhir jika tidak kosong
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

# Kelas untuk implementasi BM25
class BM25Retriever:
    """Implementasi BM25 untuk retrieval dokumen"""
    
    def __init__(self, chunks: List[str]):
        """
        Inisialisasi retriever BM25
        
        Args:
            chunks: List chunk teks yang akan diindeks
        """
        self.chunks = chunks
        self.tokenized_chunks = [self._tokenize(chunk) for chunk in chunks]
        self.bm25 = None
        self._initialize_bm25()
        
    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenisasi teks menjadi kata-kata
        
        Args:
            text: Teks yang akan ditokenisasi
            
        Returns:
            List token
        """
        # Tokenisasi sederhana - bisa diganti dengan tokenizer yang lebih baik
        return text.lower().split()
    
    def _initialize_bm25(self):
        """Inisialisasi model BM25"""
        try:
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi(self.tokenized_chunks)
        except ImportError:
            logger.error("rank_bm25 tidak ditemukan. Menginstal dengan 'pip install rank-bm25'")
            sys.exit(1)
    
    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict[str, Any]]:
        """
        Mengambil dokumen yang paling relevan dengan query
        
        Args:
            query: Query pencarian
            top_k: Jumlah dokumen teratas yang akan dikembalikan
            min_score: Skor minimum untuk dokumen yang akan dikembalikan
            
        Returns:
            List dokumen yang relevan dengan skor
        """
        # Tokenisasi query langsung tanpa ekstraksi kata kunci manual
        # Biarkan algoritma BM25 yang menentukan relevansi
        tokenized_query = self._tokenize(query)
        
        try:
            scores = self.bm25.get_scores(tokenized_query)
            top_indices = np.argsort(scores)[::-1][:top_k*2]  # Ambil lebih banyak kandidat
            
            results = []
            for idx in top_indices:
                if scores[idx] > min_score:  # Filter berdasarkan skor minimum
                    results.append({
                        "chunk": self.chunks[idx],
                        "score": float(scores[idx]),
                        "index": int(idx)
                    })
            
            # Filter hasil untuk menghilangkan duplikasi konten
            filtered_results = self._filter_similar_chunks(results)
            
            # Batasi jumlah hasil akhir
            return filtered_results[:top_k]
        except Exception as e:
            logger.error(f"Error saat melakukan retrieval: {e}")
            return []
    
    def _filter_similar_chunks(self, chunks: List[Dict[str, Any]], similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Filter chunks yang terlalu mirip untuk menghindari duplikasi
        
        Args:
            chunks: List chunk dengan skor
            similarity_threshold: Ambang batas kesamaan untuk menganggap dua chunk mirip
            
        Returns:
            List chunk yang sudah difilter
        """
        if not chunks:
            return []
            
        # Urutkan berdasarkan skor
        sorted_chunks = sorted(chunks, key=lambda x: x["score"], reverse=True)
        
        filtered = [sorted_chunks[0]]  # Selalu ambil chunk dengan skor tertinggi
        
        for chunk in sorted_chunks[1:]:
            # Cek apakah chunk ini terlalu mirip dengan chunk yang sudah diambil
            is_similar = False
            for selected in filtered:
                # Hitung kesamaan sederhana berdasarkan kata-kata yang sama
                chunk_words = set(self._tokenize(chunk["chunk"]))
                selected_words = set(self._tokenize(selected["chunk"]))
                
                if not chunk_words or not selected_words:  # Hindari division by zero
                    continue
                    
                # Jaccard similarity
                intersection = len(chunk_words.intersection(selected_words))
                union = len(chunk_words.union(selected_words))
                similarity = intersection / union if union > 0 else 0
                
                if similarity > similarity_threshold:
                    is_similar = True
                    break
            
            if not is_similar:
                filtered.append(chunk)
                
        return filtered

class HybridRetriever:
    """Kombinasi sparse (BM25) dan dense retriever dengan penggabungan skor ter-normalisasi."""

    def __init__(self, sparse_retriever: BM25Retriever, dense_retriever: DenseRetriever, alpha: float = 0.5):
        """
        Args:
            sparse_retriever: Instance BM25Retriever.
            dense_retriever: Instance DenseRetriever.
            alpha: Bobot kontribusi skor sparse. (0-1)
        """
        self.sparse_retriever = sparse_retriever
        self.dense_retriever = dense_retriever
        self.alpha = max(0.0, min(1.0, alpha))
        # Gunakan chunk dari retriever sparse jika tersedia, fallback ke dense
        self.chunks = getattr(sparse_retriever, "chunks", None) or getattr(dense_retriever, "chunks", [])

    @staticmethod
    def _normalize_scores(results: List[Dict[str, Any]]) -> Dict[int, float]:
        if not results:
            return {}
        scores = [r["score"] for r in results]
        max_score = max(scores)
        min_score = min(scores)
        denom = max_score - min_score
        normalized = {}
        for item in results:
            idx = item.get("index")
            if idx is None:
                continue
            if denom > 0:
                normalized[idx] = (item["score"] - min_score) / denom
            else:
                normalized[idx] = 1.0
        return normalized

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict[str, Any]]:
        top_k = max(1, top_k)
        # Ambil lebih banyak kandidat untuk memberikan peluang kombinasi
        candidate_multiplier = 2
        sparse_results = self.sparse_retriever.retrieve(query, top_k=top_k * candidate_multiplier, min_score=min_score)
        dense_results = self.dense_retriever.retrieve(query, top_k=top_k * candidate_multiplier, min_score=min_score)

        sparse_norm = self._normalize_scores(sparse_results)
        dense_norm = self._normalize_scores(dense_results)

        all_indices = set(sparse_norm.keys()) | set(dense_norm.keys())
        combined = []
        for idx in all_indices:
            sparse_score = sparse_norm.get(idx, 0.0)
            dense_score = dense_norm.get(idx, 0.0)
            combined_score = self.alpha * sparse_score + (1.0 - self.alpha) * dense_score
            if idx < 0 or idx >= len(self.chunks):
                continue
            combined.append({
                "chunk": self.chunks[idx],
                "score": combined_score,
                "index": idx,
                "sparse_score": sparse_score,
                "dense_score": dense_score
            })

        # Jika tidak ada kombinasi menghasilkan skor, fallback ke sparse
        if not combined:
            combined = sparse_results[:]

        combined_sorted = sorted(combined, key=lambda x: x["score"], reverse=True)
        return combined_sorted[:top_k]

# Kelas untuk mengelola LLM dengan llama.cpp langsung
class LlamaModelCpp:
    """Kelas untuk mengelola model Llama menggunakan llama.cpp"""
    
    def __init__(self, model_path: str, llama_path: str = None, n_gpu_layers: int = 999, ctx_size: int = 16384):
        """
        Inisialisasi model Llama dengan llama.cpp
        
        Args:
            model_path: Path ke file model GGUF
            llama_path: Path ke binary llama-run.exe
            n_gpu_layers: Jumlah layer yang akan dijalankan di GPU
            ctx_size: Ukuran konteks maksimum
        """
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.ctx_size = ctx_size
        
        # Cari llama-run.exe jika tidak disediakan
        if llama_path is None:
            # Coba cari di lokasi default
            default_paths = [
                os.path.join(current_dir, "llama.cpp", "build", "bin", "Release", "llama-run.exe"),
                os.path.join(current_dir, "llama.cpp", "build", "bin", "llama-run.exe"),
                os.path.join(current_dir.parent, "llama.cpp", "build", "bin", "Release", "llama-run.exe")
            ]
            
            for path in default_paths:
                if os.path.exists(path):
                    llama_path = path
                    break
        
        if not llama_path or not os.path.exists(llama_path):
            logger.error("Path ke llama-run.exe tidak ditemukan. Harap tentukan path yang benar.")
            sys.exit(1)
            
        self.llama_path = llama_path
        logger.info(f"Menggunakan llama-run.exe dari: {self.llama_path}")
        logger.info(f"Model path: {self.model_path}")
        logger.info(f"Konfigurasi: GPU Layers={self.n_gpu_layers}, Context Size={self.ctx_size}")
    
    def generate(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        """
        Menghasilkan teks dari model berdasarkan prompt menggunakan llama-run
        
        Args:
            prompt: Prompt untuk model
            max_tokens: Jumlah token maksimum yang akan dihasilkan
            temperature: Parameter temperature untuk sampling
            
        Returns:
            Teks yang dihasilkan
        """
        try:
            # Gunakan prompt langsung seperti di gpu_test.py
            # Perhatikan bahwa llama-run mengharapkan prompt sebagai argumen terakhir
            cmd = [
                self.llama_path,
                "--ngl", str(self.n_gpu_layers),  # offload layer ke GPU
                "-c", str(self.ctx_size),        # context size
                "-n", str(max_tokens),           # max tokens
                "-t", str(temperature),         # temperature
                self.model_path,                # path ke model
                prompt                          # prompt langsung setelah model
            ]
            
            logger.info(f"Menjalankan llama-run dengan {max_tokens} token maksimum...")
            start_time = time.time()
            
            # Jalankan proses dengan timeout yang cukup
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            elapsed = time.time() - start_time
            logger.info(f"Inferensi selesai dalam {elapsed:.2f} detik")
            
            if result.returncode != 0:
                logger.error(f"Error saat menjalankan llama-run: {result.stderr}")
                # Coba cara alternatif jika gagal
                return self._generate_alternative(prompt, max_tokens, temperature)
            
            # Ambil output dari stdout
            output = result.stdout.strip()
            
            # Hapus prompt dari output jika ada
            if output.startswith(prompt):
                output = output[len(prompt):].strip()
            
            # Jika output kosong, coba cara alternatif
            if not output:
                logger.warning("Output kosong, mencoba cara alternatif...")
                return self._generate_alternative(prompt, max_tokens, temperature)
                
            return output
            
        except subprocess.TimeoutExpired:
            logger.error("Timeout saat menjalankan llama-run, mencoba cara alternatif...")
            return self._generate_alternative(prompt, max_tokens, temperature)
        except Exception as e:
            logger.error(f"Error saat menghasilkan teks: {e}")
            return self._generate_alternative(prompt, max_tokens, temperature)
            
    def _generate_alternative(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
        """
        Metode alternatif untuk menghasilkan teks jika cara utama gagal
        """
        try:
            # Simpan prompt ke file sementara
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as temp_file:
                temp_file.write(prompt)
                temp_file_path = temp_file.name
            
            # Gunakan pendekatan dengan file prompt
            cmd = [
                self.llama_path,
                "--ngl", str(self.n_gpu_layers),
                "-c", str(self.ctx_size),
                "-n", str(max_tokens),
                "-t", str(temperature),
                "-f", temp_file_path,
                self.model_path
            ]
            
            logger.info("Mencoba metode alternatif dengan file prompt...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # Hapus file sementara
            try:
                os.unlink(temp_file_path)
            except:
                pass
            
            if result.returncode != 0:
                logger.error(f"Metode alternatif juga gagal: {result.stderr}")
                # Buat respons default
                return self._create_default_response(prompt)
            
            output = result.stdout.strip()
            
            # Jika output kosong, buat respons default
            if not output:
                return self._create_default_response(prompt)
                
            return output
            
        except Exception as e:
            logger.error(f"Error pada metode alternatif: {e}")
            return self._create_default_response(prompt)
    
    def _create_default_response(self, prompt: str) -> str:
        """Buat respons default jika semua metode gagal"""
        logger.warning("Membuat respons default karena semua metode gagal")
        
        # Cek apakah ini adalah prompt evaluasi
        if "PERTANYAAN:" in prompt and "JAWABAN SISWA:" in prompt and "REFERENSI:" in prompt:
            return """
        1. Skor: 0

        2. Kata kunci penting: (tidak tersedia)
        """
        else:
            return "Maaf, tidak dapat menghasilkan respons untuk prompt ini."

# Kelas untuk penilaian jawaban
class AnswerEvaluator:
    """Kelas untuk mengevaluasi jawaban siswa"""
    
    def __init__(self, llm: LlamaModelCpp, retriever: BM25Retriever):
        """
        Inisialisasi evaluator jawaban
        
        Args:
            llm: Instance dari LlamaModel
            retriever: Instance dari BM25Retriever
        """
        self.llm = llm
        self.retriever = retriever
    
    def _get_scoring_config(self, question_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Menentukan konfigurasi penilaian berdasarkan tipe soal.
        
        Args:
            question_type: Tipe soal (misal: 'singkat' atau 'panjang')
        
        Returns:
            Konfigurasi penilaian yang mencakup rubrik, opsi skor, dan informasi terkait.
        """
        normalized_type = (question_type or "panjang").strip().lower()
        if normalized_type in {"singkat", "short", "isian", "isian singkat"}:
            allowed_scores = [0, 2]
            return {
                "type": "singkat",
                "allowed_scores": allowed_scores,
                "max_score": max(allowed_scores),
                "score_options_display": "0 atau 2",
                "top_score_instruction": "Berikan nilai 2 hanya jika jawaban tepat dan sesuai dengan referensi.",
                "rubric": (
                    "2 - Jawaban tepat, relevan, dan secara langsung menjawab pertanyaan sesuai referensi.\n"
                    "0 - Jawaban salah, tidak relevan, mengandung informasi keliru, atau siswa tidak memberikan jawaban."
                )
            }
        
        # Default ke tipe soal panjang/uraian
        allowed_scores = [1, 2, 3, 4]
        return {
            "type": "panjang",
            "allowed_scores": allowed_scores,
            "max_score": max(allowed_scores),
            "score_options_display": "1, 2, 3, atau 4",
            "top_score_instruction": (
                "Berikan nilai 4 jika jawaban sangat sesuai dengan referensi dan mencakup seluruh poin penting tanpa kesalahan konsep."
            ),
            "rubric": (
                "4 - Jawaban benar, lengkap, mencakup seluruh poin penting, dan konsisten dengan referensi.\n"
                "3 - Jawaban sesuai pertanyaan dan menyampaikan ide pokok, namun masih kurang lengkap atau melewatkan beberapa detail penting.\n"
                "2 - Jawaban masih terkait dengan topik, tetapi penjelasan tidak tepat/keliru atau fokus utamanya salah meski mengandung kata kunci.\n"
                "1 - Jawaban sama sekali tidak menjawab inti soal (misalnya hanya opini umum atau mengalihkan topik) walaupun panjangnya cukup."
            )
        }
    
    @staticmethod
    def _conservative_default_score(scoring_config: Dict[str, Any]) -> int:
        """
        Pilih skor fallback konservatif saat parsing gagal.
        Untuk soal singkat -> skor terendah (biasanya 0).
        Untuk soal panjang -> ambil skor rendah yang masih mencerminkan jawaban berisi (prefer 2 jika ada).
        """
        allowed = sorted(scoring_config["allowed_scores"])
        if scoring_config["type"] == "singkat":
            return allowed[0]
        if 2 in allowed:
            return 2
        positive_scores = [s for s in allowed if s > 0]
        return positive_scores[0] if positive_scores else allowed[0]
    
    @staticmethod
    def _is_blank_answer(answer: Optional[str]) -> bool:
        """
        Deteksi apakah jawaban dianggap kosong/null oleh sistem.
        """
        if answer is None:
            return True
        normalized = str(answer).strip()
        if not normalized:
            return True
        normalized_lower = normalized.lower()
        return normalized_lower in {"null", "tidak ada jawaban", "n/a", "-", "(null)"}
        
    def _clean_evaluation_output(self, evaluation_text: str) -> str:
        """
        Membersihkan output evaluasi dari tag dan karakter formatting
        
        Args:
            evaluation_text: Teks evaluasi yang akan dibersihkan
            
        Returns:
            Teks evaluasi yang sudah dibersihkan
        """
        if not evaluation_text:
            return ""
            
        import re
        
        # Hapus tag model seperti <|im_start|> dan <|im_end|>
        cleaned = re.sub(r'<\|im_start\|>|<\|im_end\|>', '', evaluation_text)
        
        # Hapus karakter ANSI escape (kode warna terminal)
        cleaned = re.sub(r'\u001b\[\d+m', '', cleaned)
        
        # Hapus karakter formatting lainnya
        cleaned = re.sub(r'\*\*|__', '', cleaned)  # Bold/underline markdown
        
        # Hapus whitespace berlebih
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)  # Ganti multiple newlines dengan double newline
        cleaned = cleaned.strip()
        
        return cleaned
    
    def _force_format(self, evaluation_text: str) -> str:
        """Pastikan evaluasi mengikuti pola '1. Skor: ...' dan '2. Kata kunci penting: ...'."""
        if not evaluation_text:
            return evaluation_text
        
        import re
        
        score_match = re.search(r'(?i)skor\s*:\s*([0-4])', evaluation_text)
        keywords_match = re.search(r'(?i)kata\s*kunci\s*penting\s*:\s*(.*)', evaluation_text, re.DOTALL)
        
        parts = []
        if score_match:
            parts.append(f"1. Skor: {score_match.group(1)}")
        if keywords_match:
            keywords_value = keywords_match.group(1).strip()
            parts.append(f"2. Kata kunci penting: {keywords_value}")
        
        if parts:
            return "\n".join(parts)
        return evaluation_text
        
    # Fungsi ekstraksi kata kunci dihapus karena sekarang LLM yang akan mengidentifikasi kata kunci
    
    def _validate_score(self, extracted_score: int, evaluation_text: str, allowed_scores: List[int]) -> int:
        """
        Memvalidasi skor yang diekstrak dengan yang tertulis dalam teks
        
        Args:
            extracted_score: Skor yang diekstrak dari pola regex
            evaluation_text: Teks evaluasi lengkap
            allowed_scores: Daftar skor yang diperbolehkan
            
        Returns:
            Skor yang sudah divalidasi
        """
        import re
        
        score_pattern = "|".join(map(str, sorted(set(allowed_scores))))
        score_regex = rf'Skor[:\s]*\(?({score_pattern})\)?'
        
        # Cek apakah ada skor yang tertulis dalam teks
        written_scores = re.findall(score_regex, evaluation_text)
        
        if written_scores:
            written_score = int(written_scores[0])
            if written_score != extracted_score:
                logger.warning(
                    f"Skor yang diekstrak ({extracted_score}) berbeda dengan yang tertulis ({written_score})"
                )
            if written_score in allowed_scores:
                return written_score
        
        if extracted_score not in allowed_scores:
            nearest_score = min(allowed_scores, key=lambda s: abs(s - extracted_score))
            logger.warning(
                f"Skor {extracted_score} tidak ada dalam opsi yang diizinkan {allowed_scores}. "
                f"Menggunakan skor terdekat {nearest_score}."
            )
            extracted_score = nearest_score
        return extracted_score
    
    # Fungsi _create_default_evaluation dihapus karena kita tidak lagi menggunakan evaluasi default
    
    def _ensure_evaluation_format(self, evaluation: str, score: int) -> str:
        """
        Memastikan evaluasi memiliki format yang benar
        
        Args:
            evaluation: Teks evaluasi
            score: Skor yang sudah diekstrak
            
        Returns:
            Teks evaluasi yang sudah diformat
        """
        import re
        
        # Jika evaluasi sangat pendek atau tidak valid, kembalikan apa adanya
        if len(evaluation.strip()) < 10:
            return evaluation
        
        # Cek apakah evaluasi sudah memiliki format yang benar
        has_score = re.search(r'\b1\.\s*Skor', evaluation) is not None
        has_keywords = re.search(r'\b2\.\s*Kata\s*kunci', evaluation) is not None
        
        if has_score and has_keywords:
            return evaluation
        
        # Jika evaluasi tidak sesuai format yang diharapkan, kembalikan evaluasi asli
        # dengan pesan bahwa format tidak sesuai, tapi jangan buat evaluasi default
        if not (has_score or has_keywords):
            logger.warning("Format evaluasi tidak sesuai dengan yang diharapkan")
            return f"Format evaluasi tidak sesuai. Evaluasi asli:\n\n{evaluation}"
        
        # Jika beberapa bagian ada tapi tidak lengkap, coba ekstrak bagian-bagian yang ada
        parts = []
        
        # Tambahkan skor
        if has_score:
            score_match = re.search(r'\b1\.\s*Skor[^\n]*', evaluation)
            if score_match:
                parts.append(score_match.group(0))
            else:
                parts.append(f"1. Skor: {score}")
        else:
            parts.append(f"1. Skor: {score}")
        
        # Tambahkan kata kunci jika ada
        if has_keywords:
            keywords_match = re.search(r'\b2\.\s*Kata\s*kunci[^\n]*(?:\n.*?)?(?=\b3\.\s*|$)', evaluation, re.DOTALL)
            if keywords_match:
                parts.append(keywords_match.group(0).strip())
            else:
                # Coba ekstrak kata kunci dari evaluasi
                words = re.findall(r'\b\w{4,}\b', evaluation.lower())
                frequent_words = [word for word in set(words) if words.count(word) > 1 and word not in ['yang', 'dengan', 'adalah', 'untuk', 'dalam', 'pada', 'dari', 'tidak', 'ini', 'itu', 'juga', 'atau', 'tetapi', 'namun', 'karena', 'sebagai', 'seperti', 'dapat', 'akan', 'telah', 'sudah', 'harus', 'dapat', 'bisa', 'perlu', 'masih', 'sangat', 'cukup', 'kurang', 'lebih', 'semua', 'beberapa', 'banyak', 'sedikit']]
                if frequent_words:
                    parts.append(f"2. Kata kunci penting: {', '.join(frequent_words[:5])}")
                else:
                    parts.append("2. Kata kunci penting: (tidak terdeteksi)")
        else:
            # Coba ekstrak kata kunci dari evaluasi
            words = re.findall(r'\b\w{4,}\b', evaluation.lower())
            frequent_words = [word for word in set(words) if words.count(word) > 1 and word not in ['yang', 'dengan', 'adalah', 'untuk', 'dalam', 'pada', 'dari', 'tidak', 'ini', 'itu', 'juga', 'atau', 'tetapi', 'namun', 'karena', 'sebagai', 'seperti', 'dapat', 'akan', 'telah', 'sudah', 'harus', 'dapat', 'bisa', 'perlu', 'masih', 'sangat', 'cukup', 'kurang', 'lebih', 'semua', 'beberapa', 'banyak', 'sedikit']]
            if frequent_words:
                parts.append(f"2. Kata kunci penting: {', '.join(frequent_words[:5])}")
            else:
                parts.append("2. Kata kunci penting: (tidak terdeteksi)")
        
        # Gabungkan semua bagian
        return "\n\n".join(parts)
        
    def _calculate_answer_similarity(self, student_answer: str, reference_texts: List[str]) -> float:
        """
        Menghitung kemiripan antara jawaban siswa dan referensi
        
        Args:
            student_answer: Jawaban siswa
            reference_texts: Teks referensi
            
        Returns:
            Skor kemiripan (0-1)
        """
        # Tokenisasi sederhana
        def tokenize(text):
            # Bersihkan teks dan tokenisasi
            text = text.lower()
            # Hapus karakter khusus
            text = re.sub(r'[^\w\s]', ' ', text)
            # Tokenisasi
            return set(text.split())
        
        # Tokenisasi jawaban siswa
        student_tokens = tokenize(student_answer)
        
        # Gabungkan semua referensi
        combined_reference = " ".join(reference_texts)
        reference_tokens = tokenize(combined_reference)
        
        # Hitung Jaccard similarity
        if not student_tokens or not reference_tokens:
            return 0.0
        
        intersection = len(student_tokens.intersection(reference_tokens))
        union = len(student_tokens.union(reference_tokens))
        
        return intersection / union if union > 0 else 0.0
    
    def create_evaluation_prompt(
        self,
        question: str,
        student_answer: str,
        reference_texts: List[str],
        scoring_config: Optional[Dict[str, Any]] = None,
        reference_hint: str = ""
    ) -> str:
        """
        Membuat prompt untuk evaluasi jawaban
        
        Args:
            question: Pertanyaan yang diberikan
            student_answer: Jawaban siswa
            reference_texts: Teks referensi dari retriever
            scoring_config: Konfigurasi penilaian khusus tipe soal
            reference_hint: Petunjuk tambahan tentang kemiripan dengan referensi
            
        Returns:
            Prompt untuk model
        """
        config = scoring_config or self._get_scoring_config(None)
        max_score = config["max_score"]
        references = "\n\n".join(reference_texts)
        if config["type"] == "singkat":
            scoring_instructions = (
                "Soal ini bertipe singkat. Gunakan hanya skor 0 atau 2 sesuai rubrik berikut:\n"
                f"{config['rubric']}\n"
                f"{config['top_score_instruction']}"
            )
            additional_guidelines = [
                "Nilai berdasarkan kesesuaian konsep utama dengan referensi; sinonim diperbolehkan.",
                "Berikan skor 0 bila jawaban salah, tidak relevan, atau kosong.",
                "Jangan menambahkan ulasan di luar format yang diminta."
            ]
        else:
            scoring_instructions = (
                "Soal ini bertipe uraian. Gunakan skor 1, 2, 3, atau 4 sesuai rubrik berikut:\n"
                f"{config['rubric']}\n"
                f"{config['top_score_instruction']}"
            )
            additional_guidelines = [
                "Nilai berdasarkan kelengkapan dan ketepatan konsep dibanding referensi.",
                "Jawaban kosong sudah ditangani sistem; fokuskan penilaian pada jawaban yang berisi.",
                "Jangan menambahkan ulasan di luar format yang diminta."
            ]

        guidelines_text = "\n".join(f"{idx}. {item}" for idx, item in enumerate(additional_guidelines, start=1))

        prompt = f"""<|im_start|>system
Anda adalah sistem penilaian otomatis yang objektif untuk jawaban esai IPA.
Gunakan referensi yang diberikan dan terapkan rubrik berikut tanpa penyimpangan.

{scoring_instructions}

Instruksi tambahan:
{guidelines_text}

Format output wajib:

1. Skor: [angka {config['score_options_display']}]
2. Kata kunci penting: [kata kunci penting]

Jangan ubah awalan angka di atas (harus persis "1." dan "2.").

<|im_end|>

<|im_start|>user
PERTANYAAN:
{question}

JAWABAN SISWA:
{student_answer}

REFERENSI:
{references}{reference_hint}

Beri skor jawaban siswa mengikuti rubrik di atas.
<|im_end|>

<|im_start|>assistant
"""
        return prompt
    
    def evaluate_answer(
        self,
        question: str,
        student_answer: str,
        top_k: int = 5,
        question_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mengevaluasi jawaban siswa
        
        Args:
            question: Pertanyaan yang diberikan
            student_answer: Jawaban siswa
            top_k: Jumlah dokumen referensi yang akan diambil
            question_type: Jenis soal untuk menentukan rubrik penilaian
            
        Returns:
            Hasil evaluasi
        """
        scoring_config = self._get_scoring_config(question_type)
        allowed_scores = scoring_config["allowed_scores"]
        max_score = scoring_config["max_score"]
        
        if (
            scoring_config["type"] == "panjang"
            and self._is_blank_answer(student_answer)
        ):
            logger.info("Jawaban panjang kosong; mengembalikan skor 0 tanpa memanggil LLM.")
            empty_evaluation = "1. Skor: 0\n2. Kata kunci penting: (jawaban kosong)"
            return {
                "score": 0,
                "evaluation": empty_evaluation,
                "references": [],
                "max_score": max_score,
                "allowed_scores": allowed_scores,
                "question_type": scoring_config["type"]
            }
        
        # Gabungkan pertanyaan (dengan bobot lebih) dan jawaban untuk retrieval
        # Biarkan LLM yang mengidentifikasi kata kunci penting
        query = f"{question} {question} {student_answer}"
        
        # Ambil referensi yang relevan dengan skor minimum
        retrieved_docs = self.retriever.retrieve(query, top_k=top_k, min_score=1.0)
        
        # Jika tidak cukup referensi yang ditemukan, coba lagi dengan skor minimum yang lebih rendah
        if len(retrieved_docs) < max(3, top_k):
            logger.warning(f"Hanya menemukan {len(retrieved_docs)} referensi dengan skor minimum 1.0, mencoba lagi dengan skor minimum 0.5")
            retrieved_docs = self.retriever.retrieve(query, top_k=top_k, min_score=0.5)
            
        reference_texts = [doc["chunk"] for doc in retrieved_docs]
        
        if not reference_texts:
            logger.warning("Tidak ada referensi yang ditemukan untuk evaluasi")
            reference_texts = ["Tidak ada referensi yang ditemukan."]

        # Validasi kesesuaian jawaban dengan referensi
        similarity_score = self._calculate_answer_similarity(student_answer, reference_texts)
        logger.info(f"Similarity score antara jawaban dan referensi: {similarity_score:.2f}")
        
        # Jika jawaban sangat mirip dengan referensi, tambahkan petunjuk khusus ke prompt
        reference_hint = ""
        if similarity_score > 0.8:
            reference_hint = (
                f"\n\nPERHATIAN KHUSUS: Jawaban siswa sangat mirip dengan referensi "
                f"(similarity score > 0.8). Jika jawaban mencakup semua poin penting dan akurat, "
                f"berikan nilai {max_score}."
            )
        
        # Buat prompt evaluasi
        prompt = self.create_evaluation_prompt(
            question,
            student_answer,
            reference_texts,
            scoring_config=scoring_config,
            reference_hint=reference_hint
        )
        
        # Dapatkan hasil evaluasi dari model
        evaluation_result = self.llm.generate(prompt, max_tokens=512, temperature=0.3)
        
        # Parse hasil evaluasi
        try:
            # Bersihkan output evaluasi terlebih dahulu
            evaluation_result = self._clean_evaluation_output(evaluation_result)
            evaluation_result = self._force_format(evaluation_result)
            
            # Jika evaluasi kosong, coba lagi dengan parameter berbeda
            if not evaluation_result:
                logger.warning("Evaluasi kosong, mencoba lagi dengan parameter berbeda")
                # Coba lagi dengan temperature lebih tinggi untuk mendorong kreativitas
                evaluation_result = self.llm.generate(prompt, max_tokens=1024, temperature=0.7)
                evaluation_result = self._clean_evaluation_output(evaluation_result)
                evaluation_result = self._force_format(evaluation_result)
                
                # Jika masih kosong, log error tapi jangan gunakan default
                if not evaluation_result:
                    logger.error("LLM tidak menghasilkan evaluasi yang valid setelah mencoba ulang")
                    # Kembalikan evaluasi kosong dengan skor 0, biarkan sistem menangani kasus ini
                    return {
                        "score": 0,
                        "evaluation": "LLM tidak menghasilkan evaluasi yang valid.",
                        "references": reference_texts
                    }
            
            # Coba ekstrak skor dari hasil dengan berbagai pola yang mungkin
            import re
            
            # Pola yang mungkin untuk ekstraksi skor
            score_pattern = "|".join(map(str, sorted(set(allowed_scores))))
            patterns = [
                rf'Skor[:\s]*\(?({score_pattern})\)?',            # Skor: 2, Skor (0)
                rf'\b({score_pattern})[\s\.\)]\s*(?:Alasan|Skor)',  # 2. Alasan atau 0) Skor
                rf'\b({score_pattern})\s*/\s*{max_score}',         # 2/2 atau 3/4
                rf'^({score_pattern})\b',                          # Dimulai dengan angka yang valid
                rf'\b({score_pattern})\b'                          # Angka valid yang berdiri sendiri
            ]
            
            score: Optional[int] = None
            for pattern in patterns:
                score_match = re.search(pattern, evaluation_result)
                if score_match:
                    score = int(score_match.group(1))
                    if score in allowed_scores:
                        break
            
            # Jika masih 0, coba analisis teks untuk kata-kata yang menunjukkan penilaian
            if score is None:
                lowered_result = evaluation_result.lower()
                if scoring_config["type"] == "singkat":
                    if re.search(r'tidak menjawab|jawaban kosong|tidak ada jawaban|kosong', lowered_result):
                        score = 0
                    elif re.search(r'salah|tidak tepat|tidak relevan|keliru', lowered_result):
                        score = 0
                    elif re.search(r'benar|tepat|sesuai|akurat|correct', lowered_result):
                        score = max_score
                    else:
                        score = self._conservative_default_score(scoring_config)
                else:
                    if re.search(r'tidak menjawab|jawaban kosong|tidak ada jawaban', lowered_result):
                        score = 1
                    elif re.search(r'sangat sesuai dengan referensi|sangat akurat|sempurna|identik|sama persis|mencakup semua|sangat baik|lengkap|mendalam', lowered_result):
                        score = max_score
                    elif re.search(r'sebagian besar benar|beberapa poin benar|menyebutkan beberapa poin|sebagian benar|cukup benar', lowered_result):
                        score = 3
                    elif re.search(r'salah tetapi masih dalam topik|masih satu topik|masih relevan|pemahaman dasar', lowered_result):
                        score = 2
                    elif re.search(r'tidak relevan|di luar topik|sangat kurang|kesalahpahaman', lowered_result):
                        score = 1
                    else:
                        score = self._conservative_default_score(scoring_config)
                    
            # Tambahan: Periksa kesesuaian dengan referensi
            # Jika jawaban sangat sesuai dengan referensi, pastikan nilainya 4
            if re.search(r'sangat sesuai dengan referensi|sangat akurat|sempurna|identik|sama persis|mencakup semua', evaluation_result.lower()):
                if score is not None and score < max_score:
                    logger.info(
                        f"Meningkatkan skor dari {score} menjadi {max_score} karena jawaban sangat sesuai dengan referensi"
                    )
                    score = max_score

            if score is None:
                score = self._conservative_default_score(scoring_config)
            
            # Validasi skor dengan yang tertulis dalam teks
            score = self._validate_score(score, evaluation_result, allowed_scores)

            if (
                scoring_config["type"] == "panjang"
                and not self._is_blank_answer(student_answer)
                and score == 0
            ):
                logger.info(
                    "Menyesuaikan skor 0 menjadi 1 karena jawaban panjang berisi konten."
                )
                score = 1
                evaluation_result = re.sub(
                    r'(1\.\s*Skor:\s*)(-?\d+)',
                    r'\g<1>1',
                    evaluation_result,
                    count=1
                )
            
            logger.info(f"Skor terdeteksi: {score} dari evaluasi: {evaluation_result[:100]}...")
            
            # Pastikan evaluasi memiliki format yang benar
            formatted_evaluation = self._ensure_evaluation_format(evaluation_result, score)
            
            return {
                "score": score,
                "evaluation": formatted_evaluation,
                "references": reference_texts,
                "max_score": max_score,
                "allowed_scores": allowed_scores,
                "question_type": scoring_config["type"]
            }
        except Exception as e:
            logger.error(f"Error saat parsing hasil evaluasi: {e}")
            logger.error(f"Error saat parsing hasil evaluasi: {e}")
            # Jangan gunakan evaluasi default, kembalikan evaluasi asli dengan skor 0
            return {
                "score": 0,
                "evaluation": evaluation_result,
                "references": reference_texts,
                "max_score": max_score,
                "allowed_scores": allowed_scores,
                "question_type": scoring_config["type"],
                "error": str(e)
            }

# Fungsi utama
def load_template_qa(file_path: str) -> Dict[str, Any]:
    """Load template soal dan jawaban dari file JSON (format template_qa.json lama)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Error saat memuat template: {e}")
        sys.exit(1)

def _convert_aes_dataset_to_template(dataset_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Konversi format aes_dataset.json (list baris) menjadi format internal template:
    {
      "questions": [{"id": int, "question": str}, ...],
      "student_answers": [
         {"student_id": str, "name": str, "answers": [{"question_id": int, "answer": str}, ...]}, ...
      ]
    }
    """
    # Petakan teks pertanyaan -> id numerik stabil
    question_id_by_text: Dict[str, int] = {}
    questions_list: List[Dict[str, Any]] = []
    next_qid: int = 1

    # Kelompokkan per siswa (nama)
    answers_by_student: Dict[str, Dict[str, Any]] = {}

    for row in dataset_rows:
        question_text = str(row.get("pertanyaan", "")).strip()
        answer_text = row.get("jawaban")
        student_name = str(row.get("nama", "Siswa")).strip()
        question_type = str(row.get("tipe_soal", "") or "").strip().lower()

        # Normalisasi jawaban None
        if answer_text is None:
            answer_text = ""
        else:
            answer_text = str(answer_text)

        if question_text not in question_id_by_text:
            question_id_by_text[question_text] = next_qid
            questions_list.append({"id": next_qid, "question": question_text})
            next_qid += 1

        qid = question_id_by_text[question_text]

        if student_name not in answers_by_student:
            # Gunakan student_id sederhana dari nama
            student_id = student_name
            answers_by_student[student_name] = {
                "student_id": student_id,
                "name": student_name,
                "answers": []
            }

        answers_by_student[student_name]["answers"].append({
            "question_id": qid,
            "answer": answer_text,
            "question_type": question_type
        })

    template = {
        "questions": questions_list,
        "student_answers": list(answers_by_student.values())
    }
    return template

def load_any_template(file_path: str) -> Dict[str, Any]:
    """
    Loader yang mendeteksi otomatis apakah file adalah template_qa.json (dict)
    atau aes_dataset.json (list baris), lalu mengembalikan struktur template internal.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Jika list -> format aes_dataset.json
        if isinstance(data, list):
            return _convert_aes_dataset_to_template(data)
        # Jika dict dengan kunci template lama
        if isinstance(data, dict) and "questions" in data and "student_answers" in data:
            return data
        # Format tidak dikenali
        raise ValueError("Format file template tidak dikenali. Harap gunakan template_qa.json atau aes_dataset.json")
    except Exception as e:
        logger.error(f"Error saat memuat template/dataset: {e}")
        sys.exit(1)

def evaluate_batch(evaluator: AnswerEvaluator, template_data: Dict[str, Any], parallel: bool = False, debug: bool = True) -> Dict[str, Any]:
    """Evaluasi batch jawaban siswa"""
    results = []
    
    # Buat mapping pertanyaan untuk akses cepat
    questions_map = {q["id"]: q for q in template_data["questions"]}
    
    # Hitung total jawaban yang akan dievaluasi
    total_answers = sum(len(student["answers"]) for student in template_data["student_answers"])
    answers_evaluated = 0
    
    print(f"\nAkan mengevaluasi {total_answers} jawaban dari {len(template_data['student_answers'])} siswa...")
    
    if parallel:
        # Evaluasi paralel dengan ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Buat list tugas evaluasi
            futures = []
            for student in template_data["student_answers"]:
                for answer in student["answers"]:
                    question_id = answer["question_id"]
                    question_text = questions_map[question_id]["question"]
                    student_answer = answer["answer"]
                    question_type = answer.get("question_type")
                    
                    future = executor.submit(
                        evaluator.evaluate_answer,
                        question_text,
                        student_answer,
                        3,  # top_k
                        question_type=question_type
                    )
                    futures.append((student["student_id"], student["name"], question_id, question_type, future))
            
            # Proses hasil evaluasi
            for student_id, student_name, question_id, question_type, future in futures:
                try:
                    evaluation = future.result()
                    
                    # Debug info
                    max_score = evaluation.get("max_score", 4)
                    if debug:
                        print(f"\nEvaluasi untuk {student_name}, pertanyaan {question_id}:")
                        print(f"Skor: {evaluation['score']}/{max_score}")
                        print(f"Evaluasi: {evaluation['evaluation'][:150]}..." if len(evaluation['evaluation']) > 150 else evaluation['evaluation'])
                    
                    results.append({
                        "student_id": student_id,
                        "student_name": student_name,
                        "question_id": question_id,
                        "score": evaluation["score"],
                        "max_score": max_score,
                        "question_type": evaluation.get("question_type"),
                        "question_type_source": question_type,
                        "evaluation": evaluation["evaluation"],
                        "references": evaluation["references"]
                    })
                    answers_evaluated += 1
                    print(f"Progress: {answers_evaluated}/{total_answers} [{answers_evaluated/total_answers*100:.1f}%]")
                except Exception as e:
                    logger.error(f"Error saat evaluasi paralel: {e}")
    else:
        # Evaluasi sekuensial
        for student_idx, student in enumerate(template_data["student_answers"], 1):
            print(f"\nMengevaluasi jawaban siswa {student_idx}/{len(template_data['student_answers'])}: {student['name']}")
            
            for answer_idx, answer in enumerate(student["answers"], 1):
                question_id = answer["question_id"]
                question_text = questions_map[question_id]["question"]
                student_answer = answer["answer"]
                question_type = answer.get("question_type")
                
                print(f"  Mengevaluasi pertanyaan {answer_idx}/{len(student['answers'])}...")
                start_time = time.time()
                
                evaluation = evaluator.evaluate_answer(
                    question_text,
                    student_answer,
                    top_k=3,
                    question_type=question_type
                )
                max_score = evaluation.get("max_score", 4)
                
                elapsed_time = time.time() - start_time
                print(f"  Selesai! Skor: {evaluation['score']}/{max_score} (waktu: {elapsed_time:.2f}s)")
                
                # Debug info
                if debug:
                    print(f"  Evaluasi: {evaluation['evaluation'][:150]}..." if len(evaluation['evaluation']) > 150 else evaluation['evaluation'])
                
                results.append({
                    "student_id": student["student_id"],
                    "student_name": student["name"],
                    "question_id": question_id,
                    "score": evaluation["score"],
                    "max_score": max_score,
                    "question_type": evaluation.get("question_type"),
                    "question_type_source": question_type,
                    "evaluation": evaluation["evaluation"],
                    "references": evaluation["references"]
                })
                
                answers_evaluated += 1
    
    print(f"\nEvaluasi selesai! Total: {answers_evaluated} jawaban dievaluasi.")
    return {"results": results}

def display_batch_results(results: Dict[str, Any], template_data: Dict[str, Any]):
    """Tampilkan hasil evaluasi batch"""
    # Buat mapping pertanyaan untuk akses cepat
    questions_map = {q["id"]: q for q in template_data["questions"]}
    
    # Kelompokkan hasil berdasarkan siswa
    student_results = {}
    for result in results["results"]:
        student_id = result["student_id"]
        if student_id not in student_results:
            student_results[student_id] = {
                "name": result["student_name"],
                "evaluations": []
            }
        student_results[student_id]["evaluations"].append(result)
    
    # Tampilkan hasil per siswa
    print("\n===== HASIL EVALUASI BATCH =====")
    for student_id, data in student_results.items():
        print(f"\nSiswa: {data['name']} (ID: {student_id})")
        
        total_score = 0
        total_possible = 0
        for eval_result in data["evaluations"]:
            question_id = eval_result["question_id"]
            question = questions_map[question_id]["question"]
            score = eval_result["score"]
            max_score = eval_result.get("max_score", 4)
            total_score += score
            total_possible += max_score
            
            print(f"  Pertanyaan {question_id}: {question[:50]}..." if len(question) > 50 else question)
            print(f"  Skor: {score}/{max_score}")
        
        # Hitung rata-rata skor
        evaluations_count = len(data["evaluations"])
        if evaluations_count:
            avg_score = total_score / evaluations_count
            avg_possible = total_possible / evaluations_count
            percentage = (total_score / total_possible * 100) if total_possible else 0
            print(f"  Rata-rata skor: {avg_score:.2f}/{avg_possible:.2f} (~{percentage:.1f}%)")
        else:
            print("  Rata-rata skor: 0/0 (~0.0%)")

def save_results_to_json(results: Dict[str, Any], output_path: str):
    """Simpan hasil evaluasi ke file JSON"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Hasil evaluasi disimpan ke {output_path}")
        print(f"\nHasil evaluasi disimpan ke {output_path}")
    except Exception as e:
        logger.error(f"Error saat menyimpan hasil: {e}")

def main():
    """Fungsi utama program"""
    parser = argparse.ArgumentParser(description="Sistem Penilaian Otomatis Jawaban Siswa")
    parser.add_argument("--pdf", type=str, default="BUKU_IPA.pdf", help="Path ke file PDF referensi")
    parser.add_argument("--model", type=str, default="models/Llama-3.2-8B-Instruct-Q8_0.gguf", 
                        help="Path ke model LLM")
    parser.add_argument("--llama-path", type=str, help="Path ke binary llama-run.exe")
    parser.add_argument("--question", type=str, help="Pertanyaan untuk dievaluasi")
    parser.add_argument("--answer", type=str, help="Jawaban siswa untuk dievaluasi")
    parser.add_argument("--interactive", action="store_true", help="Mode interaktif")
    parser.add_argument("--template", type=str, help="Path ke file template soal dan jawaban")
    parser.add_argument("--output", type=str, help="Path untuk menyimpan hasil evaluasi")
    parser.add_argument("--parallel", action="store_true", help="Evaluasi jawaban secara paralel")
    parser.add_argument("--n-gpu-layers", type=int, default=999, 
                        help="Jumlah layer yang akan dijalankan di GPU (default: 999)")
    parser.add_argument("--ctx-size", type=int, default=16384, 
                        help="Ukuran konteks maksimum (default: 16384)")
    
    args = parser.parse_args()
    
    # Pastikan path file absolut
    pdf_path = os.path.abspath(args.pdf)
    model_path = os.path.abspath(args.model)
    
    # Inisialisasi komponen
    logger.info(f"Memproses dokumen: {pdf_path}")
    doc_processor = DocumentProcessor(pdf_path)
    chunks = doc_processor.chunk_text(chunk_size=500, overlap=50)
    logger.info(f"Dokumen berhasil dibagi menjadi {len(chunks)} chunk")
    
    logger.info("Menginisialisasi BM25 retriever...")
    retriever = BM25Retriever(chunks)
    
    logger.info(f"Memuat model LLM: {model_path}")
    llm = LlamaModelCpp(
        model_path=model_path,
        llama_path=args.llama_path,
        n_gpu_layers=args.n_gpu_layers,
        ctx_size=args.ctx_size
    )
    
    evaluator = AnswerEvaluator(llm, retriever)
    
    # Mode template evaluation
    if args.template:
        template_path = os.path.abspath(args.template)
        logger.info(f"Memuat template dari {template_path}")
        template_data = load_any_template(template_path)
        
        print(f"\nMengevaluasi jawaban dari template {template_path}...")
        results = evaluate_batch(evaluator, template_data, parallel=args.parallel, debug=True)
        
        # Tampilkan hasil
        display_batch_results(results, template_data)
        
        # Simpan hasil jika diminta
        if args.output:
            output_path = os.path.abspath(args.output)
            save_results_to_json(results, output_path)
    
    # Mode interaktif
    elif args.interactive:
        print("\n===== SISTEM PENILAIAN OTOMATIS JAWABAN SISWA =====")
        print("Ketik 'exit' untuk keluar\n")
        
        while True:
            question = input("\nMasukkan pertanyaan: ")
            if question.lower() == 'exit':
                break
                
            answer = input("Masukkan jawaban siswa: ")
            if answer.lower() == 'exit':
                break
            
            print("\nMengevaluasi jawaban...")
            start_time = time.time()
            result = evaluator.evaluate_answer(question, answer, top_k=3)
            elapsed_time = time.time() - start_time
            
            print(f"\n===== HASIL EVALUASI (waktu: {elapsed_time:.2f} detik) =====")
            max_score = result.get("max_score", 4)
            print(f"Skor: {result['score']}/{max_score}")
            print(f"\nEvaluasi:\n{result['evaluation']}")
            
            print("\nReferensi yang digunakan:")
            for i, ref in enumerate(result['references'], 1):
                print(f"\nReferensi {i}:")
                print(ref[:200] + "..." if len(ref) > 200 else ref)
    
    # Mode evaluasi tunggal
    elif args.question and args.answer:
        result = evaluator.evaluate_answer(args.question, args.answer, top_k=3)
        
        print("\n===== HASIL EVALUASI =====")
        max_score = result.get("max_score", 4)
        print(f"Skor: {result['score']}/{max_score}")
        print(f"\nEvaluasi:\n{result['evaluation']}")
        
        print("\nReferensi yang digunakan:")
        for i, ref in enumerate(result['references'], 1):
            print(f"\nReferensi {i}:")
            print(ref[:200] + "..." if len(ref) > 200 else ref)
    
    # Jika tidak ada mode yang dipilih, tampilkan bantuan
    else:
        # Default: prioritaskan aes_dataset.json jika ada, jika tidak fallback ke template_qa.json
        default_dataset = os.path.join(current_dir, "aes_dataset.json")
        default_template = os.path.join(current_dir, "template_qa.json")
        if os.path.exists(default_dataset):
            print(f"\nDataset AES ditemukan di {default_dataset}")
            print("Gunakan perintah berikut untuk mengevaluasi dataset:")
            print(f"python {sys.argv[0]} --template {default_dataset}")
        elif os.path.exists(default_template):
            print(f"\nTemplate soal dan jawaban ditemukan di {default_template}")
            print("Gunakan perintah berikut untuk mengevaluasi template:")
            print(f"python {sys.argv[0]} --template {default_template}")
        
        parser.print_help()

if __name__ == "__main__":
    main()
