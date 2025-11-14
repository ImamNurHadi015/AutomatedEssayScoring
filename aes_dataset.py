import json
import sys
import time
import os
import argparse
import psutil
import GPUtil
import pandas as pd
import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix, classification_report
from concurrent.futures import ThreadPoolExecutor, as_completed
from aes_system import DocumentProcessor, BM25Retriever, LlamaModelCpp, AnswerEvaluator, HybridRetriever, DenseRetriever
import logging

# ===========================
# KONFIGURASI DASAR
# ===========================
PDF_PATH = "BUKU_IPA.pdf"
MODEL_PATH = "models/Llama-3.2-8B-Instruct-Q8_0.gguf"
LLAMA_RUN_PATH = "llama.cpp/build/bin/Release/llama-run.exe"
DATASET_PATH = "aes_dateset2.csv"

MAX_TOKENS = 256
CTX_SIZE = 4096
SAFE_VRAM_THRESHOLD = 10  # GB
SAFE_RAM_THRESHOLD = 14  # GB
# ===========================

# Logging setup - Ubah ke INFO untuk debugging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AES_Dataset")

RESULTS_JSON_TEMPLATE = "results_{mode}_rag.json"
RESULTS_CSV_TEMPLATE = "results_{mode}_rag.csv"
SUMMARY_JSON_PATH = "results_retrieval_summary.json"
DENSE_CACHE_DIR = os.path.join("cache", "dense_retriever")

# 🔹 Evaluator dengan cache BM25
class CachedEvaluator(AnswerEvaluator):
    def __init__(self, llm, retriever):
        super().__init__(llm, retriever)
        self.cache = {}

    def evaluate_answer_cached(self, question, answer, question_type=None, top_k=3):
        """Gunakan cache BM25 agar tidak menghitung ulang untuk soal yang sama."""
        cache_key = (question, question_type)
        if cache_key in self.cache:
            top_docs = self.cache[cache_key]
        else:
            top_docs = self.retriever.retrieve(question, top_k)
            self.cache[cache_key] = top_docs
        return self.evaluate_answer(question, answer, top_k=top_k, question_type=question_type)

def get_safe_worker_count():
    """Hitung jumlah thread aman berdasarkan VRAM dan RAM."""
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            free_vram = gpu.memoryFree
        else:
            free_vram = 0
    except Exception:
        free_vram = 0

    total_ram = psutil.virtual_memory().available / (1024 ** 3)

    # Estimasi jumlah worker aman
    if free_vram >= SAFE_VRAM_THRESHOLD and total_ram >= SAFE_RAM_THRESHOLD:
        return 1
    elif free_vram >= 8:
        return 1
    else:
        return 1

def _normalize_answer_field(value):
    if pd.isna(value):
        return "null"
    text = str(value).strip()
    return text if text else "null"

def evaluate_dataset_with_retriever(mode_name, evaluator, df, max_workers, question_type_filter="all"):
    """Jalankan evaluasi dataset untuk mode retrieval tertentu."""
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
            if raw_id is None or (isinstance(raw_id, float) and pd.isna(raw_id)) or str(raw_id).strip() == "":
                row_id = idx
            else:
                try:
                    row_id = int(str(raw_id).strip())
                except (TypeError, ValueError):
                    row_id = idx
            # Ambil nilai skor dari dataframe yang sudah dikonversi ke numerik
            true_score = int(row["skor"])
            # Log jika skor adalah 0 untuk debugging
            if true_score == 0:
                logger.info(f"Skor 0 terdeteksi untuk ID {row_id}, nama: {row['nama']}, pertanyaan: {question_text[:30]}...")

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
                "retrieval_mode": mode_name,
                "question_type_filter": question_type_filter
            })

            max_score = eval_result.get("max_score")
            if max_score:
                logger.warning(
                    f"[{mode_name.upper()}][{question_type_filter.upper() if question_type_filter else 'ALL'}][{progress}/{total}] Skor AES: {eval_result['score']}/{max_score} | "
                    f"Guru: {row['skor']} | True Score: {true_score}"
                )
            else:
                logger.warning(
                    f"[{mode_name.upper()}][{question_type_filter.upper() if question_type_filter else 'ALL'}][{progress}/{total}] Skor AES: {eval_result['score']} | "
                    f"Guru: {row['skor']} | True Score: {true_score}"
                )

    elapsed = time.time() - start_time
    return results, elapsed

def compute_metrics(df_result):
    """Hitung metrik evaluasi utama dari dataframe hasil."""
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

def save_mode_outputs(mode_name, results, df_result, metrics, type_suffix=""):
    """Simpan hasil evaluasi dan metrik untuk suatu mode ke file."""
    suffix = type_suffix or ""
    json_path = RESULTS_JSON_TEMPLATE.format(mode=f"{mode_name}{suffix}")
    csv_path = RESULTS_CSV_TEMPLATE.format(mode=f"{mode_name}{suffix}")

    # Simpan JSON dengan metadata
    payload = {
        "metadata": {
            "model_used": MODEL_PATH,
            "model_name": os.path.basename(MODEL_PATH),
            "pdf_source": PDF_PATH,
            "evaluation_date": time.strftime("%Y-%m-%d"),
            "evaluation_datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": mode_name,
            "question_type_filter": suffix.lstrip("_") if suffix else "all"
        },
        "results": results,
        "metrics": metrics
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Simpan CSV
    df_to_save = df_result.copy()
    df_to_save.to_csv(csv_path, index=False, encoding="utf-8-sig")

    return json_path, csv_path

def main():
    parser = argparse.ArgumentParser(description="Evaluasi AES dengan berbagai mode retrieval")
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["sparse", "dense", "hybrid"],
        help="Pilih mode retrieval yang akan dijalankan (default: semua)"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Gunakan mode paralel (tetap dibatasi oleh kebijakan get_safe_worker_count)"
    )
    parser.add_argument(
        "--question-types",
        nargs="+",
        choices=["singkat", "panjang"],
        help="Filter evaluasi pada tipe soal tertentu (default: semua tipe)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Batasi jumlah data yang diproses (0 = semua data)"
    )
    args = parser.parse_args()

    start_total = time.time()

    df = pd.read_csv(DATASET_PATH, encoding="latin1", sep=";")
    df["tipe_soal"] = df["tipe_soal"].fillna("").astype(str)
    df["tipe_soal_normalized"] = df["tipe_soal"].str.strip().str.lower()
    
    # Pastikan kolom skor dikonversi dengan benar ke numerik
    df["skor"] = pd.to_numeric(df["skor"], errors="coerce").fillna(0).astype(int)
    
    # Tampilkan distribusi skor untuk debugging
    skor_counts = df["skor"].value_counts().sort_index()
    logger.warning(f"Dataset dimuat, total {len(df)} jawaban siswa dengan rata-rata skor {df['skor'].mean():.2f}")
    logger.warning(f"Distribusi skor: {dict(skor_counts)}")
    
    # Batasi jumlah data jika parameter limit diberikan
    if args.limit > 0:
        df = df.head(args.limit)
        logger.warning(f"Dataset dibatasi menjadi {len(df)} data sesuai parameter --limit={args.limit}")





    if args.question_types:
        requested_types = [t.strip().lower() for t in args.question_types]
        type_groups = []
        for qt in requested_types:
            subset = df[df["tipe_soal_normalized"] == qt].copy()
            if subset.empty:
                logger.warning(f"Tidak ada jawaban dengan tipe soal '{qt}'. Melewati tipe ini.")
                continue
            type_groups.append((qt, subset))
        if not type_groups:
            logger.error("Tidak ada data yang sesuai dengan filter tipe soal yang diberikan.")
            sys.exit(1)
    else:
        type_groups = [("all", df)]

    # 1️⃣ Proses referensi PDF
    doc_processor = DocumentProcessor(PDF_PATH)
    chunks = doc_processor.chunk_text(chunk_size=500, overlap=50)
    logger.warning(f"Dokumen dibagi menjadi {len(chunks)} chunk untuk retrieval")

    # 2️⃣ Siapkan berbagai retriever
    sparse_retriever = BM25Retriever(chunks)
    selected_modes = set(args.modes) if args.modes else None

    retriever_configs = [
        ("sparse", "Sparse BM25", sparse_retriever),
        ("dense", "Dense DPR", True),
        ("hybrid", "Hybrid Sparse+Dense", True)
    ]

    if selected_modes:
        retriever_configs = [cfg for cfg in retriever_configs if cfg[0] in selected_modes]

    # 3️⃣ Inisialisasi LLM
    llm = LlamaModelCpp(
    model_path=MODEL_PATH,
        llama_path=LLAMA_RUN_PATH,
    n_gpu_layers=999,
        ctx_size=CTX_SIZE
    )

    # 4️⃣ Hitung jumlah thread aman
    max_workers = get_safe_worker_count()
    if not args.parallel:
        max_workers = 1
    logger.warning(f"Menjalankan evaluasi dengan {max_workers} thread paralel")

    comparison_summary = []
    combined_results_df = []

    for type_name, df_subset in type_groups:
        display_type = "semua tipe" if type_name == "all" else type_name
        logger.warning(
            f"\n===== Memulai evaluasi untuk tipe soal: {display_type.upper()} (total {len(df_subset)} jawaban) ====="
        )

        for mode_name, mode_desc, info in retriever_configs:
            retriever = info if not isinstance(info, bool) else None
            if info:
                dense_retriever = DenseRetriever(chunks=chunks, cache_dir=DENSE_CACHE_DIR)
                if mode_name == "dense":
                    retriever = dense_retriever
                elif mode_name == "hybrid":
                    retriever = HybridRetriever(sparse_retriever, dense_retriever, alpha=0.5)
            logger.warning(
                f"\n===== Memulai evaluasi dengan mode retrieval: {mode_name.upper()} ({mode_desc}) "
                f"untuk tipe {display_type.upper()} ====="
            )
            evaluator = CachedEvaluator(llm, retriever)
            mode_results, elapsed_seconds = evaluate_dataset_with_retriever(
                mode_name,
                evaluator,
                df_subset,
                max_workers,
                question_type_filter=type_name
            )
            if not mode_results:
                logger.warning(f"Tidak ada hasil evaluasi untuk mode {mode_name} pada tipe {display_type}")
                continue

            df_mode = pd.DataFrame(mode_results)
            metrics = compute_metrics(df_mode)
            metrics["elapsed_seconds"] = float(elapsed_seconds)
            metrics["answers_evaluated"] = int(len(df_mode))
            metrics["question_type_filter"] = type_name

            type_suffix = "" if type_name == "all" else f"_{type_name}"
            json_path, csv_path = save_mode_outputs(
                mode_name,
                mode_results,
                df_mode,
                metrics,
                type_suffix=type_suffix
            )
            logger.warning(f"Hasil mode {mode_name} (tipe {display_type}) disimpan ke {json_path} dan {csv_path}")

            comparison_summary.append({
                "mode": mode_name,
                "description": mode_desc,
                "question_type": type_name,
                "metrics": metrics,
                "json_path": json_path,
                "csv_path": csv_path
            })
            df_mode["question_type_filter"] = type_name
            combined_results_df.append(df_mode)

    total_time = time.time() - start_total

    if comparison_summary:
        print("\n===== RINGKASAN PERFORMA RETRIEVAL =====")
        for entry in comparison_summary:
            m = entry["metrics"]
            exact = m.get("exact_match", 0.0) * 100
            mae = m.get("mae", float("nan"))
            qwk = m.get("qwk", float("nan"))
            elapsed = m.get("elapsed_seconds", 0.0)
            qtype_label = entry.get("question_type", "all")
            print(
                f"{entry['mode'].upper():<8} | {entry['description']:<22} | "
                f"Tipe: {qtype_label.upper():<8} | "
                f"Akurasi: {exact:6.2f}% | MAE: {mae:5.3f} | QWK: {qwk:6.4f} | "
                f"Waktu: {elapsed/60:.2f} menit"
            )
    else:
        print("Tidak ada hasil evaluasi yang berhasil dihasilkan.")

    if combined_results_df:
        combined_df = pd.concat(combined_results_df, ignore_index=True)
        combined_csv_path = "results_all_modes.csv"
        combined_df.to_csv(combined_csv_path, index=False, encoding="utf-8-sig")
        logger.warning(f"Hasil gabungan semua mode disimpan ke {combined_csv_path}")
    else:
        combined_csv_path = None

    summary_payload = {
        "model_used": MODEL_PATH,
        "model_name": os.path.basename(MODEL_PATH),
        "pdf_source": PDF_PATH,
        "evaluation_date": time.strftime("%Y-%m-%d"),
        "evaluation_datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_answers": int(len(df)),
        "total_time_seconds": float(total_time),
        "summary": comparison_summary,
        "combined_results_csv": combined_csv_path,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(SUMMARY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, ensure_ascii=False, indent=2)

    print("\n===== Proses selesai =====")
    print(f"Total waktu eksekusi: {total_time/60:.2f} menit")
    print(f"Ringkasan disimpan ke: {SUMMARY_JSON_PATH}")


if __name__ == "__main__":
    main()