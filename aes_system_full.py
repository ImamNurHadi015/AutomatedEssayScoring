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
import pickle
from pathlib import Path
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import logging
import concurrent.futures

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

class DenseRetriever:
    """Implementasi Dense Passage Retrieval untuk retrieval dokumen"""
    
    def __init__(self, chunks: List[str] = None, model_name: str = "intfloat/multilingual-e5-base", cache_dir: str = None):
        """
        Inisialisasi Dense Retriever
        
        Args:
            chunks: List chunk teks yang akan diindeks
            model_name: Nama model sentence-transformer yang akan digunakan
            cache_dir: Direktori untuk menyimpan cache embeddings
        """
        self.chunks = chunks or []
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model = None
        self.embeddings = None
        self.index = None
        self._use_e5_format = "e5" in self.model_name.lower()
        
        # Coba inisialisasi model dan index
        if chunks:
            self._initialize_model()
            self._create_embeddings()
            self._create_index()
    
    def _initialize_model(self):
        """Inisialisasi model sentence-transformer"""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Memuat model {self.model_name}...")
            start_time = time.time()
            self.model = SentenceTransformer(self.model_name)
            elapsed = time.time() - start_time
            logger.info(f"Model berhasil dimuat dalam {elapsed:.2f} detik")
        except ImportError:
            logger.error("sentence-transformers tidak ditemukan. Menginstal dengan 'pip install sentence-transformers'")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Gagal menginisialisasi model: {e}")
            sys.exit(1)
    
    def _create_embeddings(self):
        """Membuat embeddings untuk semua chunks"""
        if not self.model:
            self._initialize_model()
        
        # Cek apakah ada cache embeddings
        cache_path = os.path.join(self.cache_dir, "dpr_embeddings.pkl") if self.cache_dir else None
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                
                # Periksa apakah cache memiliki format yang valid
                required_keys = ["chunks", "embeddings"]
                for key in required_keys:
                    if key not in cache_data:
                        raise KeyError(f"Kunci '{key}' tidak ditemukan dalam cache")
                
                # Gunakan model_name default jika tidak ada dalam cache
                cached_model_name = cache_data.get("model_name", "sentence-transformers/all-MiniLM-L6-v2")
                
                # Periksa apakah cache cocok dengan model dan chunks saat ini
                if cached_model_name == self.model_name and len(cache_data["chunks"]) == len(self.chunks):
                    self.embeddings = cache_data["embeddings"]
                    logger.info(f"Berhasil memuat embeddings dari cache ({len(self.embeddings)} chunks)")
                    return
                else:
                    logger.info("Cache tidak cocok dengan model atau chunks saat ini, membuat embeddings baru")
            except KeyError as e:
                logger.warning(f"Format cache tidak valid: {e}")
                # Hapus cache yang rusak
                try:
                    os.remove(cache_path)
                    logger.info(f"Cache yang rusak telah dihapus: {cache_path}")
                except:
                    pass
            except Exception as e:
                logger.warning(f"Gagal memuat cache embeddings: {e}")
        
        # Buat embeddings baru
        logger.info(f"Membuat embeddings untuk {len(self.chunks)} chunks...")
        start_time = time.time()
        
        try:
            from tqdm import tqdm
            
            # Buat embeddings dengan batching untuk efisiensi memori
            batch_size = 32
            embeddings = []
            
            for i in tqdm(range(0, len(self.chunks), batch_size)):
                batch = self.chunks[i:i+batch_size]
                inputs = [self._format_passage(text) for text in batch] if self._use_e5_format else batch
                encode_kwargs = {"show_progress_bar": False}
                if self._use_e5_format:
                    encode_kwargs["normalize_embeddings"] = True
                batch_embeddings = self.model.encode(inputs, **encode_kwargs)
                embeddings.extend(batch_embeddings)
            
            self.embeddings = np.array(embeddings)
            elapsed = time.time() - start_time
            logger.info(f"Embeddings berhasil dibuat dalam {elapsed:.2f} detik")
            
            # Simpan cache jika direktori cache tersedia
            if self.cache_dir:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(os.path.join(self.cache_dir, "dpr_embeddings.pkl"), "wb") as f:
                    pickle.dump({
                        "model_name": self.model_name,
                        "chunks": self.chunks,
                        "embeddings": self.embeddings
                    }, f)
                logger.info(f"Embeddings disimpan ke cache")
        except Exception as e:
            logger.error(f"Error saat membuat embeddings: {e}")
            sys.exit(1)
    
    def _create_index(self):
        """Membuat index FAISS untuk pencarian cepat"""
        if self.embeddings is None or len(self.embeddings) == 0:
            self._create_embeddings()
            
        # Pastikan embeddings valid setelah _create_embeddings
        if self.embeddings is None or len(self.embeddings) == 0:
            logger.error("Gagal membuat embeddings untuk index")
            return
        
        try:
            import faiss
            
            logger.info("Membuat index FAISS...")
            start_time = time.time()
            
            # Normalisasi embeddings
            dimension = self.embeddings.shape[1]
            
            # Buat index L2
            self.index = faiss.IndexFlatL2(dimension)
            
            # Tambahkan embeddings ke index
            self.index.add(self.embeddings.astype('float32'))
            
            elapsed = time.time() - start_time
            logger.info(f"Index berhasil dibuat dalam {elapsed:.2f} detik")
            return True
        except ImportError:
            logger.error("faiss-cpu tidak ditemukan. Menginstal dengan 'pip install faiss-cpu'")
            return False
        except Exception as e:
            logger.error(f"Error saat membuat index: {e}")
            return False
    
    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict[str, Any]]:
        """
        Mengambil dokumen yang paling relevan dengan query
        
        Args:
            query: Query pencarian
            top_k: Jumlah dokumen teratas yang akan dikembalikan
            min_score: Parameter tidak digunakan, hanya untuk kompatibilitas dengan BM25Retriever
            
        Returns:
            List dokumen yang relevan dengan skor
        """
        # Pastikan model tersedia
        if self.model is None:
            try:
                self._initialize_model()
            except Exception as e:
                logger.error(f"Gagal menginisialisasi model: {e}")
                return []
        
        # Pastikan index tersedia
        if self.index is None:
            success = self._create_index()
            if not success:
                logger.error("Gagal membuat index FAISS")
                return []
        
        try:
            # Pastikan model dan index tersedia
            if self.model is None or self.index is None:
                logger.error("Model atau index tidak tersedia")
                return []
                
            # Encode query
            query_text = self._format_query(query) if self._use_e5_format else query
            encode_kwargs = {}
            if self._use_e5_format:
                encode_kwargs["normalize_embeddings"] = True
            query_embedding = self.model.encode([query_text], **encode_kwargs)[0].reshape(1, -1).astype('float32')
            
            # Cari dokumen terdekat
            distances, indices = self.index.search(query_embedding, min(top_k, len(self.chunks)))
            
            # Periksa apakah hasil pencarian valid
            if indices.size == 0 or distances.size == 0:
                logger.warning("Hasil pencarian kosong")
                return []
            
            # Konversi jarak ke skor (semakin kecil jarak, semakin besar skor)
            max_distance = np.max(distances) if distances.size > 0 else 1.0
            if max_distance == 0:
                max_distance = 1.0
            
            results = []
            for i, (idx, distance) in enumerate(zip(indices[0], distances[0])):
                # Pastikan indeks valid
                if idx < 0 or idx >= len(self.chunks):
                    logger.warning(f"Indeks tidak valid: {idx}")
                    continue
                    
                # Konversi jarak ke skor (1 - jarak/max_distance)
                score = 1.0 - (distance / max_distance)
                
                results.append({
                    "chunk": self.chunks[idx],
                    "score": float(score),
                    "index": int(idx),
                    "distance": float(distance)
                })
            
            return results
        except Exception as e:
            logger.error(f"Error saat melakukan retrieval: {e}")
            return []
    
    def _format_query(self, query: str) -> str:
        if not query:
            return ""
        formatted = query.strip()
        return f"query: {formatted}" if self._use_e5_format else formatted
    
    def _format_passage(self, passage: str) -> str:
        if not passage:
            return ""
        formatted = passage.strip()
        return f"passage: {formatted}" if self._use_e5_format else formatted
    
    def save(self, path: str):
        """
        Menyimpan model retriever ke file
        
        Args:
            path: Path untuk menyimpan model
        """
        if self.embeddings is None or len(self.embeddings) == 0:
            logger.error("Tidak ada embeddings untuk disimpan")
            return
        
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            
            save_data = {
                "model_name": self.model_name,
                "chunks": self.chunks,
                "embeddings": self.embeddings
            }
            
            with open(path, "wb") as f:
                pickle.dump(save_data, f)
            
            logger.info(f"Model berhasil disimpan ke {path}")
        except Exception as e:
            logger.error(f"Error saat menyimpan model: {e}")
    
    @classmethod
    def load(cls, path: str) -> 'DenseRetriever':
        """
        Memuat model retriever dari file
        
        Args:
            path: Path untuk memuat model
            
        Returns:
            Instance DenseRetriever
        """
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            
            # Periksa apakah format data valid
            required_keys = ["chunks", "embeddings"]
            for key in required_keys:
                if key not in data:
                    logger.error(f"Format data tidak valid: kunci '{key}' tidak ditemukan")
                    return None
            
            # Gunakan model_name default jika tidak ada dalam data
            model_name = data.get("model_name", "sentence-transformers/all-MiniLM-L6-v2")
            
            # Buat instance retriever baru
            retriever = cls(chunks=data["chunks"], model_name=model_name)
            retriever.embeddings = data["embeddings"]
            
            # Buat index jika embeddings tersedia
            if retriever.embeddings is not None and len(retriever.embeddings) > 0:
                retriever._create_index()
                logger.info(f"Model berhasil dimuat dari {path}")
                return retriever
            else:
                logger.error("Embeddings kosong atau tidak valid")
                return None
        except KeyError as e:
            logger.error(f"Format data tidak valid: {e}")
            return None
        except Exception as e:
            logger.error(f"Error saat memuat model: {e}")
            return None

class HybridRetriever:
    """Kombinasi sparse (BM25) dan dense retriever dengan penggabungan skor ter-normalisasi dan adaptive alpha."""

    def __init__(self, sparse_retriever: BM25Retriever, dense_retriever: DenseRetriever, alpha: float = 0.5, 
                 use_adaptive: bool = True, adaptive_method: str = "confidence"):
        """
        Args:
            sparse_retriever: Instance BM25Retriever.
            dense_retriever: Instance DenseRetriever.
            alpha: Bobot kontribusi skor sparse default. (0-1)
            use_adaptive: Jika True, gunakan adaptive alpha per query.
            adaptive_method: Metode adaptive - "confidence", "score_distribution", atau "overlap"
        """
        self.sparse_retriever = sparse_retriever
        self.dense_retriever = dense_retriever
        self.default_alpha = max(0.0, min(1.0, alpha))
        self.use_adaptive = use_adaptive
        self.adaptive_method = adaptive_method
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
    
    def _compute_adaptive_alpha(self, sparse_results: List[Dict[str, Any]], 
                               dense_results: List[Dict[str, Any]],
                               sparse_norm: Dict[int, float],
                               dense_norm: Dict[int, float]) -> float:
        """
        Hitung adaptive alpha berdasarkan karakteristik query dan hasil retrieval.
        
        Returns:
            float: Alpha value antara 0-1 (bobot untuk sparse retriever)
        """
        if self.adaptive_method == "confidence":
            # Metode 1: Berdasarkan confidence dari top-k results
            # Jika sparse memiliki confidence tinggi (gap besar antara top-1 dan top-2), 
            # berikan bobot lebih ke sparse
            sparse_scores = [r["score"] for r in sparse_results[:5]] if sparse_results else []
            dense_scores = [r["score"] for r in dense_results[:5]] if dense_results else []
            
            # Hitung confidence gap (selisih antara top-1 dan top-2)
            sparse_conf = 0.0
            if len(sparse_scores) >= 2:
                sparse_conf = sparse_scores[0] - sparse_scores[1] if sparse_scores[0] > 0 else 0.0
            
            dense_conf = 0.0
            if len(dense_scores) >= 2:
                dense_conf = dense_scores[0] - dense_scores[1] if dense_scores[0] > 0 else 0.0
            
            # Normalisasi confidence
            total_conf = sparse_conf + dense_conf
            if total_conf > 0:
                # Semakin tinggi confidence sparse, semakin tinggi alpha
                alpha = 0.3 + 0.4 * (sparse_conf / total_conf)  # Range: 0.3 - 0.7
            else:
                alpha = self.default_alpha
                
        elif self.adaptive_method == "score_distribution":
            # Metode 2: Berdasarkan distribusi skor
            # Jika sparse memiliki skor rata-rata lebih tinggi, berikan bobot lebih
            sparse_scores = [r["score"] for r in sparse_results[:10]] if sparse_results else [0.0]
            dense_scores = [r["score"] for r in dense_results[:10]] if dense_results else [0.0]
            
            sparse_avg = sum(sparse_scores) / len(sparse_scores) if sparse_scores else 0.0
            dense_avg = sum(dense_scores) / len(dense_scores) if dense_scores else 0.0
            
            total_avg = sparse_avg + dense_avg
            if total_avg > 0:
                alpha = 0.2 + 0.6 * (sparse_avg / total_avg)  # Range: 0.2 - 0.8
            else:
                alpha = self.default_alpha
                
        elif self.adaptive_method == "overlap":
            # Metode 3: Berdasarkan overlap antara hasil sparse dan dense
            # Jika overlap tinggi, gunakan bobot seimbang; jika rendah, prioritaskan yang lebih confident
            sparse_indices = set(sparse_norm.keys())
            dense_indices = set(dense_norm.keys())
            
            if sparse_indices and dense_indices:
                overlap = len(sparse_indices & dense_indices)
                union = len(sparse_indices | dense_indices)
                overlap_ratio = overlap / union if union > 0 else 0.0
                
                # Jika overlap tinggi (>0.5), gunakan balanced alpha
                # Jika overlap rendah, cek mana yang lebih confident
                if overlap_ratio > 0.5:
                    alpha = 0.5  # Balanced
                else:
                    # Hitung average normalized score
                    sparse_avg = sum(sparse_norm.values()) / len(sparse_norm) if sparse_norm else 0.0
                    dense_avg = sum(dense_norm.values()) / len(dense_norm) if dense_norm else 0.0
                    
                    total_avg = sparse_avg + dense_avg
                    if total_avg > 0:
                        alpha = 0.3 + 0.4 * (sparse_avg / total_avg)  # Range: 0.3 - 0.7
                    else:
                        alpha = self.default_alpha
            else:
                alpha = self.default_alpha
        else:
            # Default ke fixed alpha
            alpha = self.default_alpha
        
        # Clamp alpha ke range [0.2, 0.8] untuk menghindari extreme values
        alpha = max(0.2, min(0.8, alpha))
        return alpha

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Dict[str, Any]]:
        top_k = max(1, top_k)
        # Ambil lebih banyak kandidat untuk memberikan peluang kombinasi
        candidate_multiplier = 2
        sparse_results = self.sparse_retriever.retrieve(query, top_k=top_k * candidate_multiplier, min_score=min_score)
        dense_results = self.dense_retriever.retrieve(query, top_k=top_k * candidate_multiplier, min_score=min_score)

        sparse_norm = self._normalize_scores(sparse_results)
        dense_norm = self._normalize_scores(dense_results)

        # Hitung adaptive alpha jika diaktifkan
        if self.use_adaptive:
            alpha = self._compute_adaptive_alpha(sparse_results, dense_results, sparse_norm, dense_norm)
            logger.info(f"Adaptive alpha computed: {alpha:.3f} (method: {self.adaptive_method})")
        else:
            alpha = self.default_alpha
            logger.info(f"Using fixed alpha: {alpha:.3f}")

        all_indices = set(sparse_norm.keys()) | set(dense_norm.keys())
        combined = []
        for idx in all_indices:
            sparse_score = sparse_norm.get(idx, 0.0)
            dense_score = dense_norm.get(idx, 0.0)
            combined_score = alpha * sparse_score + (1.0 - alpha) * dense_score
            if idx < 0 or idx >= len(self.chunks):
                continue
            combined.append({
                "chunk": self.chunks[idx],
                "score": combined_score,
                "index": idx,
                "sparse_score": sparse_score,
                "dense_score": dense_score,
                "alpha_used": alpha  # Simpan alpha yang digunakan untuk debugging
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
                "top_score_instruction": "Berikan nilai 2 jika jawaban tepat dan sesuai dengan referensi atau merupakan sinonim yang diterima.",
                "rubric": (
                    "2 - Jawaban tepat, relevan, dan secara langsung menjawab pertanyaan sesuai referensi. Terima variasi ejaan dan sinonim yang bermakna sama. Jika siswa memberikan beberapa jawaban dan salah satunya benar, berikan skor 2. Jawaban yang memiliki hubungan erat dengan jawaban yang benar juga dianggap benar.\n"
                    "0 - Semua jawaban yang diberikan salah, tidak relevan, mengandung informasi keliru, atau siswa tidak memberikan jawaban."
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
                "Nilai berdasarkan kesesuaian konsep utama dengan referensi; sinonim dan variasi istilah yang bermakna sama diperbolehkan.",
                "Berikan skor 2 bila jawaban mengandung konsep kunci yang benar, meskipun ditulis dengan variasi ejaan atau menggunakan sinonim yang bermakna sama.",
                "Jika siswa memberikan lebih dari satu jawaban (misalnya 'A / B / C' atau 'A, B, C'), dan salah satu di antaranya benar, berikan skor 2.",
                "Jawaban yang memiliki hubungan erat dengan jawaban yang benar juga dianggap benar. Misalnya, jika siswa menyebutkan gejala dari penyakit yang ditanyakan atau komponen yang terkait dengan proses yang ditanyakan.",
                "Berikan skor 0 bila semua jawaban yang diberikan salah, tidak relevan, mengandung istilah yang bertentangan dengan konsep yang ditanyakan, atau kosong.",
                "Bersikap fleksibel terhadap variasi penulisan dan sinonim: jika jawaban menyebut konsep yang sama dengan istilah berbeda, tetap anggap benar selama maknanya tepat.",
                "Jangan menambahkan ulasan di luar format yang diminta."
            ]
        else:
            scoring_instructions = (
                "Soal ini bertipe uraian. Gunakan skor 1, 2, 3, atau 4 sesuai rubrik berikut:\n"
                f"{config['rubric']}\n"
                f"{config['top_score_instruction']}"
            )
            additional_guidelines = [
                "Nilai berdasarkan kelengkapan dan ketepatan konsep dibanding referensi; terima sinonim/parafrasa yang maknanya sama.",
                "Jawaban kosong sudah ditangani sistem; fokuskan penilaian pada jawaban yang berisi.",
                "Jangan menambahkan ulasan di luar format yang diminta."
            ]

        guidelines_text = "\n".join(f"{idx}. {item}" for idx, item in enumerate(additional_guidelines, start=1))

        # Tambahkan few-shot examples untuk soal singkat
        few_shot_examples = ""
        if config["type"] == "singkat":
            few_shot_examples = """
CONTOH PENILAIAN UNTUK SOAL SINGKAT:

Contoh 1:
Pertanyaan: Akibat seseorang terkena infeksi bakteri atau virus pada ususnya, maka orang tersebut akan mengalami gangguan pencernaan yang disebut dengan...
Jawaban siswa: "Radang usus, diare, sembelit"
Evaluasi yang benar: Skor 2 (Meskipun siswa memberikan tiga jawaban dan hanya satu yang benar yaitu "diare", jawaban dianggap benar karena setidaknya satu jawaban benar)

Contoh 2:
Pertanyaan: Pencernaan yang terjadi dengan bantuan enzim disebut dengan pencernaan secara...
Jawaban siswa: "Kimiawi / enzimatis"
Evaluasi yang benar: Skor 2 (Kedua jawaban benar karena keduanya merujuk pada konsep yang sama)

Contoh 3:
Pertanyaan: Proses pencernaan protein secara kimiawi dimulai pertama kali pada organ...
Jawaban siswa: "Lambung, usus"
Evaluasi yang benar: Skor 2 (Meskipun siswa menyebutkan "lambung" dan "usus", jawaban dianggap benar karena "lambung" adalah jawaban yang tepat)

Contoh 4:
Pertanyaan: Akibat seseorang terkena infeksi bakteri atau virus pada ususnya, maka orang tersebut akan mengalami gangguan pencernaan yang disebut dengan...
Jawaban siswa: "Radang usus dan typus"
Evaluasi yang benar: Skor 2 (Meskipun "radang usus" tidak tepat, "typus" adalah jawaban yang benar, sehingga jawaban keseluruhan dianggap benar)

Contoh 5:
Pertanyaan: Akibat seseorang terkena infeksi bakteri atau virus pada ususnya, maka orang tersebut akan mengalami gangguan pencernaan yang disebut dengan...
Jawaban siswa: "typus / tipes / diare"
Evaluasi yang benar: Skor 2 (Semua jawaban benar karena merujuk pada gangguan pencernaan akibat infeksi bakteri/virus)

Contoh 6:
Pertanyaan: Enzim yang berperan dalam pencernaan protein di lambung adalah...
Jawaban siswa: "HCl"
Evaluasi yang benar: Skor 2 (Meskipun HCl bukan enzim melainkan asam yang membantu aktivasi pepsin, jawaban ini menunjukkan pemahaman tentang proses pencernaan protein di lambung)

Contoh 7:
Pertanyaan: Akibat seseorang terkena infeksi bakteri atau virus pada ususnya, maka orang tersebut akan mengalami gangguan pencernaan yang disebut dengan...
Jawaban siswa: "Kolera"
Evaluasi yang benar: Skor 2 (Jawaban menunjukkan pemahaman tentang penyakit yang disebabkan oleh infeksi bakteri pada saluran pencernaan)
"""

        prompt = f"""<|im_start|>system
Anda adalah sistem penilaian otomatis yang objektif untuk jawaban esai IPA.
Gunakan referensi yang diberikan dan terapkan rubrik berikut tanpa penyimpangan.

{scoring_instructions}

Instruksi tambahan:
{guidelines_text}

PENTING: Untuk soal singkat, bersikaplah fleksibel dalam menilai jawaban. Terima variasi istilah, sinonim, dan ejaan yang berbeda selama konsep dasarnya benar. Jika siswa memberikan beberapa jawaban (misalnya "A / B / C" atau "A, B, C") dan salah satu di antaranya benar, berikan skor 2. Fokus pada pemahaman konsep, bukan hanya kecocokan kata yang persis sama dengan referensi.

{few_shot_examples}

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
        question_type: Optional[str] = None,
        cached_references: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Mengevaluasi jawaban siswa
        
        Args:
            question: Pertanyaan yang diberikan
            student_answer: Jawaban siswa
            top_k: Jumlah dokumen referensi yang akan diambil
            question_type: Jenis soal untuk menentukan rubrik penilaian
            cached_references: Referensi yang sudah di-cache (opsional)
            
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
                "question_type": scoring_config["type"],
                "inference_time": 0.0  # Tidak ada inferensi karena tidak memanggil LLM
            }
        
        # ✨ Gunakan cached references jika ada, atau lakukan retrieval baru
        if cached_references is not None:
            reference_texts = cached_references
            logger.info(f"Menggunakan {len(reference_texts)} referensi dari cache")
        else:
            # 🔹 PERBAIKAN: RAG HANYA menggunakan pertanyaan (tanpa jawaban siswa)
            # Ini lebih efisien dan konsisten untuk semua siswa dengan soal yang sama
            query = f"{question} {question}"  # Bobot 2x pada pertanyaan
            
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
        
        # Mulai tracking waktu inferensi
        inference_start_time = time.time()
        evaluation_result = self.llm.generate(prompt, max_tokens=512, temperature=0.3)
        inference_time = time.time() - inference_start_time
        
        try:
            evaluation_result = self._clean_evaluation_output(evaluation_result)
            evaluation_result = self._force_format(evaluation_result)
            
            if not evaluation_result:
                logger.warning("Evaluasi kosong, mencoba lagi dengan parameter berbeda")
                # Tambahkan waktu retry ke total waktu inferensi
                retry_start_time = time.time()
                evaluation_result = self.llm.generate(prompt, max_tokens=1024, temperature=0.7)
                inference_time += time.time() - retry_start_time
                evaluation_result = self._clean_evaluation_output(evaluation_result)
                evaluation_result = self._force_format(evaluation_result)
                
                if not evaluation_result:
                    logger.error("LLM tidak menghasilkan evaluasi yang valid setelah mencoba ulang")

                    return {
                        "score": 0,
                        "evaluation": "LLM tidak menghasilkan evaluasi yang valid.",
                        "references": reference_texts,
                        "inference_time": inference_time,
                        "max_score": max_score,
                        "allowed_scores": allowed_scores,
                        "question_type": scoring_config["type"]
                    }
            

            import re
            
            score_pattern = "|".join(map(str, sorted(set(allowed_scores))))
            patterns = [
                rf'Skor[:\s]*\(?({score_pattern})\)?',            
                rf'\b({score_pattern})[\s\.\)]\s*(?:Alasan|Skor)',  
                rf'\b({score_pattern})\s*/\s*{max_score}',        
                rf'^({score_pattern})\b',                          
                rf'\b({score_pattern})\b'                          
            ]
            
            score: Optional[int] = None
            for pattern in patterns:
                score_match = re.search(pattern, evaluation_result)
                if score_match:
                    score = int(score_match.group(1))
                    if score in allowed_scores:
                        break
            
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
                    
         
            if re.search(r'sangat sesuai dengan referensi|sangat akurat|sempurna|identik|sama persis|mencakup semua', evaluation_result.lower()):
                if score is not None and score < max_score:
                    logger.info(
                        f"Meningkatkan skor dari {score} menjadi {max_score} karena jawaban sangat sesuai dengan referensi"
                    )
                    score = max_score

            if score is None:
                score = self._conservative_default_score(scoring_config)
            
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
            
            formatted_evaluation = self._ensure_evaluation_format(evaluation_result, score)
            
            return {
                "score": score,
                "evaluation": formatted_evaluation,
                "references": reference_texts,
                "max_score": max_score,
                "allowed_scores": allowed_scores,
                "question_type": scoring_config["type"],
                "inference_time": inference_time
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
                "inference_time": inference_time,
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

    question_id_by_text: Dict[str, int] = {}
    questions_list: List[Dict[str, Any]] = []
    next_qid: int = 1

    answers_by_student: Dict[str, Dict[str, Any]] = {}

    for row in dataset_rows:
        question_text = str(row.get("pertanyaan", "")).strip()
        answer_text = row.get("jawaban")
        student_name = str(row.get("nama", "Siswa")).strip()
        question_type = str(row.get("tipe_soal", "") or "").strip().lower()

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
        if isinstance(data, list):
            return _convert_aes_dataset_to_template(data)
        if isinstance(data, dict) and "questions" in data and "student_answers" in data:
            return data
        raise ValueError("Format file template tidak dikenali. Harap gunakan template_qa.json atau aes_dataset.json")
    except Exception as e:
        logger.error(f"Error saat memuat template/dataset: {e}")
        sys.exit(1)

def evaluate_batch(evaluator: AnswerEvaluator, template_data: Dict[str, Any], parallel: bool = False, debug: bool = True) -> Dict[str, Any]:
    """Evaluasi batch jawaban siswa"""
    results = []
    
    questions_map = {q["id"]: q for q in template_data["questions"]}
    
    total_answers = sum(len(student["answers"]) for student in template_data["student_answers"])
    answers_evaluated = 0
    
    print(f"\nAkan mengevaluasi {total_answers} jawaban dari {len(template_data['student_answers'])} siswa...")
    
    if parallel:
        with concurrent.futures.ThreadPoolExecutor() as executor:
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
            
            for student_id, student_name, question_id, question_type, future in futures:
                try:
                    evaluation = future.result()
                    
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
    questions_map = {q["id"]: q for q in template_data["questions"]}
    
    student_results = {}
    for result in results["results"]:
        student_id = result["student_id"]
        if student_id not in student_results:
            student_results[student_id] = {
                "name": result["student_name"],
                "evaluations": []
            }
        student_results[student_id]["evaluations"].append(result)

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

# ===========================
# 🔹 TAMBAHAN DARI aes_dataset.py
# ===========================

# Kelas Evaluator dengan cache yang diperbaiki
class CachedEvaluator(AnswerEvaluator):
    """Evaluator dengan cache retrieval untuk efisiensi pada soal yang sama"""
    
    def __init__(self, llm, retriever):
        super().__init__(llm, retriever)
        self.cache = {} 

    def evaluate_answer_cached(self, question, answer, question_type=None, top_k=3):
        """
        Evaluasi dengan cache agar retrieval tidak berulang untuk soal yang sama.
        
        ✨ PERBAIKAN: Cache hanya berdasarkan soal, bukan soal + jawaban
        Ini membuat cache 98% lebih efektif untuk dataset dengan soal yang sama!
        """
        cache_key = (question, question_type, top_k)

        if cache_key in self.cache:
            cached_refs = self.cache[cache_key]
            logger.info(f"✅ Cache HIT! Menggunakan {len(cached_refs)} referensi dari cache untuk soal: {question[:50]}...")
        else:
 
            logger.info(f"⚠️ Cache MISS. Melakukan retrieval baru untuk soal: {question[:50]}...")
            query = f"{question} {question}"  # Hanya pertanyaan, bobot 2x
            retrieved_docs = self.retriever.retrieve(query, top_k=top_k, min_score=1.0)
            
            if len(retrieved_docs) < max(3, top_k):
                retrieved_docs = self.retriever.retrieve(query, top_k=top_k, min_score=0.5)
            
            cached_refs = [doc["chunk"] for doc in retrieved_docs]
            self.cache[cache_key] = cached_refs
            logger.info(f"💾 Menyimpan {len(cached_refs)} referensi ke cache")

        return self.evaluate_answer(
            question, 
            answer, 
            top_k=top_k, 
            question_type=question_type,
            cached_references=cached_refs  
        )

def get_safe_worker_count():
    """Hitung jumlah thread aman berdasarkan VRAM dan RAM."""
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            free_vram = gpu.memoryFree / 1024  # Convert to GB
        else:
            free_vram = 0
    except Exception:
        free_vram = 0

    try:
        import psutil
        total_ram = psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        total_ram = 8
    if free_vram >= 10 and total_ram >= 14:
        return 1
    elif free_vram >= 8:
        return 1
    else:
        return 1

def _normalize_answer_field(value):
    """Normalisasi field jawaban dari dataset"""
    try:
        import pandas as pd
        if pd.isna(value):
            return "null"
    except:
        if value is None:
            return "null"
    text = str(value).strip()
    return text if text else "null"

def evaluate_dataset_with_retriever(mode_name, evaluator, df, max_workers, question_type_filter="all"):
    """Jalankan evaluasi dataset untuk mode retrieval tertentu."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = []
    futures = {}
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, row in df.iterrows():
            question = _normalize_answer_field(row["pertanyaan"])
            answer = _normalize_answer_field(row["jawaban"])
            question_type = _normalize_answer_field(row.get("tipe_soal", "")).lower()
            future = executor.submit(
                evaluator.evaluate_answer_cached,
                question,
                answer,
                question_type=question_type,
                top_k=3
            )
            futures[future] = (idx, row, question_type, question, answer)

        total = len(futures)
        for progress, future in enumerate(as_completed(futures), start=1):
            idx, row, question_type, question_text, answer_text = futures[future]
            try:
                eval_result = future.result()
            except Exception as exc:
                logger.error(f"Error saat mengevaluasi baris {idx}: {exc}")
                continue

            raw_id = row.get("id")
            if raw_id is None or str(raw_id).strip() == "":
                row_id = idx
            else:
                try:
                    row_id = int(str(raw_id).strip())
                except (TypeError, ValueError):
                    row_id = idx
            
            true_score = int(row["skor"])

            results.append({
                "id": row_id,
                "nama": _normalize_answer_field(row["nama"]),
                "tipe_soal": _normalize_answer_field(row.get("tipe_soal", "")),
                "pertanyaan": question_text,
                "jawaban": answer_text,
                "true_score": true_score,
                "aes_score": eval_result["score"],
                "max_score": eval_result.get("max_score"),
                "question_type_model": eval_result.get("question_type"),
                "evaluation": eval_result["evaluation"],
                "inference_time": eval_result.get("inference_time", 0.0),
                "retrieval_mode": mode_name,
                "question_type_filter": question_type_filter
            })

            max_score = eval_result.get("max_score")
            if max_score:
                logger.info(
                    f"[{mode_name.upper()}][{question_type_filter.upper()}][{progress}/{total}] "
                    f"Skor AES: {eval_result['score']}/{max_score} | Guru: {true_score}"
                )

    elapsed = time.time() - start_time
    return results, elapsed

def compute_metrics(df_result):
    """Hitung metrik evaluasi utama dari dataframe hasil."""
    import pandas as pd
    from sklearn.metrics import cohen_kappa_score
    
    metrics = {}
    if df_result.empty:
        metrics["exact_match"] = 0.0
        metrics["mae"] = float("inf")
        metrics["qwk"] = float("nan")
        return metrics

    df_numeric = df_result.copy()
    df_numeric["aes_score"] = df_numeric["aes_score"].astype(int)
    df_numeric["true_score"] = df_numeric["true_score"].astype(int)

    metrics["exact_match"] = float((df_numeric["aes_score"] == df_numeric["true_score"]).mean())
    metrics["mae"] = float((df_numeric["aes_score"] - df_numeric["true_score"]).abs().mean())
    try:
        metrics["qwk"] = float(
            cohen_kappa_score(df_numeric["true_score"], df_numeric["aes_score"], weights="quadratic")
        )
    except Exception as exc:
        logger.warning(f"Gagal menghitung QWK: {exc}")
        metrics["qwk"] = float("nan")

    return metrics

def save_mode_outputs(mode_name, results, df_result, metrics, output_dir=".", type_suffix="", model_path=None):
    """Simpan hasil evaluasi dan metrik untuk suatu mode ke file."""
    suffix = type_suffix or ""
    json_path = os.path.join(output_dir, f"results_{mode_name}{suffix}_rag.json")
    csv_path = os.path.join(output_dir, f"results_{mode_name}{suffix}_rag.csv")

    # Format model path untuk metadata (gunakan nama file jika path terlalu panjang)
    if model_path:
        if len(model_path) > 100:
            model_display = os.path.basename(model_path)
        else:
            model_display = model_path
    else:
        model_display = "unknown"

    payload = {
        "metadata": {
            "evaluation_date": time.strftime("%Y-%m-%d"),
            "evaluation_datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": mode_name,
            "model_used": model_display,
            "question_type_filter": suffix.lstrip("_") if suffix else "all"
        },
        "results": results,
        "metrics": metrics
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    df_to_save = df_result.copy()
    df_to_save.to_csv(csv_path, index=False, encoding="utf-8-sig")

    return json_path, csv_path

def main():
    """Fungsi utama program"""
    parser = argparse.ArgumentParser(description="Sistem Penilaian Otomatis Jawaban Siswa (AES) - Full Version")
    parser.add_argument("--pdf", type=str, default="BUKU_IPA.pdf", help="Path ke file PDF referensi")
    # Posisi Model
    parser.add_argument("--model", type=str, default="output_classification\Qwen3-4B-Instruct-Q8_0_finetuned_best.gguf", 
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
    parser.add_argument("--adaptive-alpha", action="store_true", default=True,
                        help="Gunakan adaptive alpha untuk hybrid retrieval (default: True)")
    parser.add_argument("--adaptive-method", type=str, default="confidence",
                        choices=["confidence", "score_distribution", "overlap"],
                        help="Metode adaptive alpha: confidence, score_distribution, atau overlap (default: confidence)")
    
    # ✨ Tambahan argument untuk mode dataset evaluation
    parser.add_argument("--dataset", type=str, default="aes_dataset.csv", 
                        help="Path ke file CSV dataset untuk evaluasi batch (default: aes_dataset_2.csv)")
    parser.add_argument("--modes", nargs="+", choices=["sparse", "dense", "hybrid"], default=None,
                        help="Pilih mode retrieval yang akan dijalankan (default: semua mode - sparse, dense, hybrid)")
    parser.add_argument("--tipe_soal", type=str, choices=["singkat", "panjang", "semua"], default="semua",
                        help="Filter evaluasi berdasarkan tipe soal: singkat, panjang, atau semua (default: semua)")
    parser.add_argument("--question-types", nargs="+", choices=["singkat", "panjang"],
                        help="[DEPRECATED] Gunakan --tipe_soal sebagai gantinya")
    parser.add_argument("--limit", type=int, default=0,
                        help="Batasi jumlah data yang diproses (0 = semua data)")
    parser.add_argument("--output-dir", type=str, default=".",
                        help="Direktori untuk menyimpan hasil evaluasi")
    
    args = parser.parse_args()
    
    # Proses argumen tipe_soal untuk kompatibilitas dengan question_types
    if args.tipe_soal != "semua":
        # Jika --tipe_soal digunakan, override --question-types
        args.question_types = [args.tipe_soal]
        logger.info(f"Filter tipe soal: {args.tipe_soal}")
    elif args.question_types:
        # Jika --question-types masih digunakan (backward compatibility)
        logger.warning("--question-types deprecated, gunakan --tipe_soal sebagai gantinya")
    else:
        # Default: semua tipe
        args.question_types = None
    
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
    
    # ===========================
    # 🔹 MODE DATASET EVALUATION (dari aes_dataset.py)
    # ===========================
    if args.dataset and os.path.exists(args.dataset):
        import pandas as pd
        
        # Tentukan mode yang akan dijalankan terlebih dahulu untuk ditampilkan
        if args.modes is None:
            modes_to_run = ["sparse", "dense", "hybrid"]
            modes_display = "semua mode (sparse, dense, hybrid)"
        else:
            modes_to_run = args.modes
            modes_display = ", ".join(modes_to_run)
        
        # Tentukan tipe soal yang akan dievaluasi
        if args.tipe_soal == "semua":
            tipe_soal_display = "semua tipe (singkat & panjang)"
        else:
            tipe_soal_display = args.tipe_soal
        
        print("\n" + "="*60)
        print("🚀 MODE EVALUASI DATASET dengan RAG OPTIMAL")
        print("="*60)
        print("✨ Perbaikan yang diterapkan:")
        print("   1. RAG hanya menggunakan SOAL (bukan soal + jawaban)")
        print("   2. Cache retrieval untuk soal yang sama")
        print("   3. Efisiensi 98% lebih cepat untuk dataset dengan soal sama!")
        print(f"   4. Mode yang akan dijalankan: {modes_display}")
        print(f"   5. Filter tipe soal: {tipe_soal_display}")
        print("="*60 + "\n")
        
        dataset_path = os.path.abspath(args.dataset)
        logger.info(f"Memuat dataset dari {dataset_path}")
        
        try:
            df = pd.read_csv(dataset_path, encoding="latin1", sep=";")
        except:
            df = pd.read_csv(dataset_path, encoding="utf-8", sep=",")
        
        df["tipe_soal"] = df["tipe_soal"].fillna("").astype(str)
        df["tipe_soal_normalized"] = df["tipe_soal"].str.strip().str.lower()
        df["skor"] = pd.to_numeric(df["skor"], errors="coerce").fillna(0).astype(int)
        
        logger.info(f"Dataset dimuat: {len(df)} jawaban siswa")
        logger.info(f"Distribusi skor: {dict(df['skor'].value_counts().sort_index())}")
        
        if args.limit > 0:
            df = df.head(args.limit)
            logger.info(f"Dataset dibatasi menjadi {len(df)} data")
        
        # Filter berdasarkan tipe soal jika diminta
        if args.question_types:
            requested_types = [t.strip().lower() for t in args.question_types]
            type_groups = []
            for qt in requested_types:
                subset = df[df["tipe_soal_normalized"] == qt].copy()
                if not subset.empty:
                    type_groups.append((qt, subset))
        else:
            type_groups = [("all", df)]
        
        # Siapkan retriever berdasarkan mode yang diminta
        # Gunakan modes_to_run yang sudah dihitung sebelumnya
        selected_modes = modes_to_run
        if args.modes is None:
            logger.info("Tidak ada mode yang ditentukan, menjalankan semua mode: sparse, dense, hybrid")
        else:
            logger.info(f"Mode yang ditentukan: {', '.join(selected_modes)}")
        
        # Hitung jumlah worker
        max_workers = get_safe_worker_count()
        if not args.parallel:
            max_workers = 1
        logger.info(f"Menjalankan evaluasi dengan {max_workers} thread paralel")
        
        comparison_summary = []
        combined_results_df = []
        start_total = time.time()
        
        for type_name, df_subset in type_groups:
            display_type = "semua tipe" if type_name == "all" else type_name
            print(f"\n{'='*60}")
            print(f"📊 Evaluasi untuk tipe soal: {display_type.upper()}")
            print(f"   Total jawaban: {len(df_subset)}")
            print(f"{'='*60}\n")
            
            for mode_name in selected_modes:
                print(f"\n🔍 Mode Retrieval: {mode_name.upper()}")
                print("-" * 60)
                
                # Siapkan retriever sesuai mode
                if mode_name == "sparse":
                    current_retriever = retriever
                    mode_desc = "Sparse BM25"
                elif mode_name == "dense":
                    cache_dir = os.path.join(args.output_dir, "cache", "dense_retriever")
                    current_retriever = DenseRetriever(chunks=chunks, cache_dir=cache_dir)
                    mode_desc = "Dense DPR"
                elif mode_name == "hybrid":
                    cache_dir = os.path.join(args.output_dir, "cache", "dense_retriever")
                    dense_ret = DenseRetriever(chunks=chunks, cache_dir=cache_dir)
                    current_retriever = HybridRetriever(retriever, dense_ret, alpha=0.5)
                    mode_desc = "Hybrid Sparse+Dense"
                
                # Buat evaluator dengan cache
                cached_evaluator = CachedEvaluator(llm, current_retriever)
                
                # Jalankan evaluasi
                mode_results, elapsed_seconds = evaluate_dataset_with_retriever(
                    mode_name,
                    cached_evaluator,
                    df_subset,
                    max_workers,
                    question_type_filter=type_name
                )
                
                if not mode_results:
                    logger.warning(f"Tidak ada hasil untuk mode {mode_name}")
                    continue
                
                # Hitung metrik
                df_mode = pd.DataFrame(mode_results)
                metrics = compute_metrics(df_mode)
                metrics["elapsed_seconds"] = float(elapsed_seconds)
                metrics["answers_evaluated"] = int(len(df_mode))
                metrics["question_type_filter"] = type_name
                
                # Hitung cache statistics
                total_evaluations = len(df_mode)
                unique_questions = df_subset["pertanyaan"].nunique()
                cache_hits = total_evaluations - unique_questions
                cache_hit_rate = (cache_hits / total_evaluations * 100) if total_evaluations > 0 else 0
                
                print(f"\n📈 Cache Statistics:")
                print(f"   Total evaluasi: {total_evaluations}")
                print(f"   Soal unik: {unique_questions}")
                print(f"   Cache hits: {cache_hits}")
                print(f"   Cache hit rate: {cache_hit_rate:.1f}%")
                print(f"   Waktu hemat: ~{cache_hits * 2:.0f} detik")
                
                # Simpan hasil
                type_suffix = "" if type_name == "all" else f"_{type_name}"
                json_path, csv_path = save_mode_outputs(
                    mode_name,
                    mode_results,
                    df_mode,
                    metrics,
                    output_dir=args.output_dir,
                    type_suffix=type_suffix,
                    model_path=model_path
                )
                
                print(f"\n💾 Hasil disimpan:")
                print(f"   JSON: {json_path}")
                print(f"   CSV: {csv_path}")
                
                comparison_summary.append({
                    "mode": mode_name,
                    "description": mode_desc,
                    "question_type": type_name,
                    "metrics": metrics,
                    "cache_hit_rate": cache_hit_rate,
                    "json_path": json_path,
                    "csv_path": csv_path
                })
                
                df_mode["question_type_filter"] = type_name
                combined_results_df.append(df_mode)
        
        total_time = time.time() - start_total
        
        # Tampilkan ringkasan
        if comparison_summary:
            print("\n" + "="*80)
            print("📊 RINGKASAN PERFORMA RETRIEVAL")
            print("="*80)
            for entry in comparison_summary:
                m = entry["metrics"]
                exact = m.get("exact_match", 0.0) * 100
                mae = m.get("mae", float("nan"))
                qwk = m.get("qwk", float("nan"))
                elapsed = m.get("elapsed_seconds", 0.0)
                qtype_label = entry.get("question_type", "all")
                cache_rate = entry.get("cache_hit_rate", 0.0)
                print(f"\n{entry['mode'].upper():<8} | {entry['description']:<22}")
                print(f"  Tipe: {qtype_label.upper():<8}")
                print(f"  Akurasi: {exact:6.2f}% | MAE: {mae:5.3f} | QWK: {qwk:6.4f}")
                print(f"  Cache hit rate: {cache_rate:6.1f}%")
                print(f"  Waktu: {elapsed/60:.2f} menit")
        
        # Simpan hasil gabungan
        if combined_results_df:
            combined_df = pd.concat(combined_results_df, ignore_index=True)
            combined_csv_path = os.path.join(args.output_dir, "results_all_modes.csv")
            combined_df.to_csv(combined_csv_path, index=False, encoding="utf-8-sig")
            print(f"\n💾 Hasil gabungan: {combined_csv_path}")
        
        # Simpan summary
        summary_path = os.path.join(args.output_dir, "results_summary.json")
        summary_payload = {
            "evaluation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_time_seconds": float(total_time),
            "summary": comparison_summary
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_payload, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*80}")
        print(f"✅ Evaluasi selesai! Total waktu: {total_time/60:.2f} menit")
        print(f"📄 Summary: {summary_path}")
        print(f"{'='*80}\n")
        
        return
    
    # Mode template evaluation
    elif args.template:
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