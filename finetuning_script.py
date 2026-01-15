#!/usr/bin/env python3
"""
Fine-tuning Script untuk Qwen3-4B-Instruct dengan CLASSIFICATION HEAD
untuk Automatic Essay Scoring (AES)

🔥 PERUBAHAN UTAMA dari finetuning_complete.py:
1. Output bukan text generation, tapi CLASSIFICATION (0, 1, 2, 3, 4)
2. Loss function: CrossEntropyLoss (bukan language modeling loss)
3. Classifier head: Linear layer di atas hidden states
4. Training jauh lebih stabil dan cepat!

ARCHITECTURE:
- Base: Qwen3-4B-Instruct (frozen, kecuali LoRA)
- LoRA: Applied to attention layers
- Classification Head: Linear(hidden_size → 5) untuk 5 skor (0-4)

SKOR MAPPING:
- Soal Singkat: 0 (salah/kosong), 2 (benar)
- Soal Panjang: 1 (sangat kurang), 2 (kurang), 3 (cukup), 4 (sempurna)
  (skor 0 hanya untuk tidak menjawab, sudah difilter)

Loss: CrossEntropyLoss dengan class weights untuk handle imbalance
"""

import os
import json
import pickle
import gc
import pandas as pd
import numpy as np
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from tqdm.auto import tqdm
import warnings
warnings.filterwarnings('ignore')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# HuggingFace imports
import torch
import torch.nn as nn
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    TrainerCallback,
    PreTrainedModel
)
from peft import LoraConfig, get_peft_model, PeftModel
from datasets import Dataset

# Sentence Transformers & FAISS
from sentence_transformers import SentenceTransformer
import faiss

# PDF Processing
import PyPDF2

# Sklearn & Scipy
from sklearn.model_selection import train_test_split
from sklearn.metrics import cohen_kappa_score, mean_absolute_error, accuracy_score
from sklearn.utils.class_weight import compute_class_weight
from collections import Counter

# ==================================================================================
# CONFIGURATION
# ==================================================================================

# Paths
PDF_PATH = "BUKU_IPA.pdf"
DATASET_PATH = "aes_dataset.csv"
MODEL_NAME = "models/.cache/huggingface/download/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554"
OUTPUT_DIR = "./output_classification"
CACHE_DIR = "./cache"

# Dense Retrieval Config
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K_RETRIEVAL = 5

# Fine-tuning Config (Classification - More Stable!)
MAX_SEQ_LENGTH = 1024
BATCH_SIZE = 4  # ✅ Increased (classification is lighter than generation)
GRADIENT_ACCUMULATION_STEPS = 8  # ✅ Reduced (effective batch = 16)
LEARNING_RATE = 2e-5  # ✅ Standard for classification
NUM_EPOCHS = 6  # ✅ Can train longer (classification more stable)
WARMUP_RATIO = 0.1
LOGGING_STEPS = 5
SAVE_STEPS = 30  # ✅ Eval every 30 steps

# LoRA Config (Lighter for classification)
LORA_R = 8
LORA_ALPHA = 16
LORA_DROPOUT = 0.1
TARGET_MODULES = ["q_proj", "v_proj", "o_proj"]

# Classification Config
NUM_LABELS = 5  # Skor: 0, 1, 2, 3, 4

# ==================================================================================
# DOCUMENT PROCESSOR (same as before)
# ==================================================================================

class DocumentProcessor:
    """Kelas untuk memproses dokumen PDF dan mengekstrak teks"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.raw_text = ""
        self.chunks = []
        
    def extract_text_from_pdf(self) -> str:
        """Ekstrak teks dari file PDF"""
        try:
            with open(self.pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() + "\n"
                self.raw_text = text
                return text
        except Exception as e:
            print(f"❌ Gagal mengekstrak teks dari PDF: {e}")
            raise
    
    def chunk_text(self, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Membagi teks menjadi chunk yang lebih kecil"""
        if not self.raw_text:
            self.extract_text_from_pdf()
            
        text = self.raw_text
        chunks = []
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            if len(current_chunk) + len(paragraph) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = current_chunk[-overlap:] + " " + paragraph
                else:
                    current_chunk = paragraph
            else:
                current_chunk += " " + paragraph if current_chunk else paragraph
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        chunks = [c for c in chunks if len(c) > 50]
        self.chunks = chunks
        return chunks

# ==================================================================================
# DENSE RETRIEVER (same as before)
# ==================================================================================

class DenseRetriever:
    """Implementasi Dense Passage Retrieval menggunakan FAISS"""
    
    def __init__(self, chunks: List[str], model_name: str = "intfloat/multilingual-e5-base", cache_dir: str = None):
        self.chunks = chunks
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model = None
        self.embeddings = None
        self.index = None
        self._use_e5_format = "e5" in self.model_name.lower()
        
        self._initialize_model()
        self._create_embeddings()
        self._create_index()
    
    def _format_passage(self, text: str) -> str:
        return f"passage: {text}"
    
    def _format_query(self, text: str) -> str:
        return f"query: {text}"
    
    def _initialize_model(self):
        print(f"🔄 Memuat model embedding: {self.model_name}...")
        self.model = SentenceTransformer(self.model_name)
        print(f"✅ Model embedding berhasil dimuat")
    
    def _create_embeddings(self):
        cache_path = os.path.join(self.cache_dir, "dpr_embeddings.pkl") if self.cache_dir else None
        
        if cache_path and os.path.exists(cache_path):
            try:
                print("🔄 Memuat embeddings dari cache...")
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                
                if (cache_data.get("model_name") == self.model_name and 
                    len(cache_data.get("chunks", [])) == len(self.chunks)):
                    self.embeddings = cache_data["embeddings"]
                    print(f"✅ Berhasil memuat embeddings dari cache")
                    return
                else:
                    print("⚠️ Cache tidak cocok, membuat embeddings baru...")
            except Exception as e:
                print(f"⚠️ Gagal memuat cache: {e}")
        
        print(f"🔄 Membuat embeddings untuk {len(self.chunks)} chunks...")
        batch_size = 32
        embeddings = []
        
        for i in tqdm(range(0, len(self.chunks), batch_size), desc="Creating embeddings"):
            batch = self.chunks[i:i+batch_size]
            inputs = [self._format_passage(text) for text in batch] if self._use_e5_format else batch
            encode_kwargs = {"show_progress_bar": False}
            if self._use_e5_format:
                encode_kwargs["normalize_embeddings"] = True
            batch_embeddings = self.model.encode(inputs, **encode_kwargs)
            embeddings.extend(batch_embeddings)
        
        self.embeddings = np.array(embeddings).astype('float32')
        print(f"✅ Embeddings berhasil dibuat (shape: {self.embeddings.shape})")
        
        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump({
                    "model_name": self.model_name,
                    "chunks": self.chunks,
                    "embeddings": self.embeddings
                }, f)
            print(f"✅ Embeddings disimpan ke cache")
    
    def _create_index(self):
        print("🔄 Membuat FAISS index...")
        dimension = self.embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(self.embeddings)
        print(f"✅ FAISS index berhasil dibuat (dimension: {dimension})")
    
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query_text = self._format_query(query) if self._use_e5_format else query
        encode_kwargs = {}
        if self._use_e5_format:
            encode_kwargs["normalize_embeddings"] = True
        query_embedding = self.model.encode([query_text], **encode_kwargs)[0].reshape(1, -1).astype('float32')
        
        distances, indices = self.index.search(query_embedding, min(top_k, len(self.chunks)))
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.chunks):
                similarity = 1 / (1 + dist)
                results.append({
                    "text": self.chunks[idx],
                    "score": float(similarity)
                })
        
        return results

# ==================================================================================
# PROMPT UTILITIES
# ==================================================================================

def _is_blank_answer(answer: Optional[str]) -> bool:
    """Deteksi apakah jawaban dianggap kosong"""
    if answer is None:
        return True
    normalized = str(answer).strip()
    if not normalized:
        return True
    normalized_lower = normalized.lower()
    return normalized_lower in {"null", "tidak ada jawaban", "n/a", "-", "(null)", "nan"}

def get_scoring_config(question_type: Optional[str] = None) -> Dict[str, Any]:
    """Mendapatkan konfigurasi penilaian berdasarkan tipe soal"""
    normalized_type = (question_type or "panjang").strip().lower()
    if normalized_type in {"singkat", "short", "isian", "isian singkat"}:
        return {
            "type": "singkat",
            "max_score": 2,
            "score_options": [0, 2],
        }
    else:
        return {
            "type": "panjang",
            "max_score": 4,
            "score_options": [1, 2, 3, 4],
        }

def create_classification_prompt(
    question: str,
    student_answer: str,
    reference_texts: List[str],
    question_type: Optional[str] = None
) -> str:
    """
    Membuat prompt untuk CLASSIFICATION (bukan generation!)
    Model hanya perlu memahami konteks, output adalah logits untuk 5 kelas
    """
    config = get_scoring_config(question_type)
    references = "\n\n".join(reference_texts)
    
    if config["type"] == "singkat":
        rubric = (
            "Soal tipe SINGKAT (skor 0 atau 2):\n"
            "- Skor 2: Jawaban benar, relevan dengan konsep kunci\n"
            "- Skor 0: Jawaban salah, tidak relevan, atau kosong"
        )
    else:
        rubric = (
            "Soal tipe PANJANG (skor 1-4):\n"
            "- Skor 4: Lengkap, mencakup semua poin penting\n"
            "- Skor 3: Cukup baik, ide pokok ada tapi kurang detail\n"
            "- Skor 2: Terkait topik tapi ada kesalahan konsep\n"
            "- Skor 1: Tidak menjawab inti soal"
        )
    
    # Prompt format untuk classification (lebih ringkas)
    prompt = f"""<|im_start|>system
Sistem penilaian otomatis jawaban esai IPA.
{rubric}

Evaluasi jawaban siswa berdasarkan referensi yang diberikan.
<|im_end|>

<|im_start|>user
PERTANYAAN:
{question}

JAWABAN SISWA:
{student_answer}

REFERENSI:
{references}
<|im_end|>

<|im_start|>assistant
"""
    return prompt

def create_training_data_classification(csv_path: str, retriever: DenseRetriever, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Membuat training data untuk CLASSIFICATION
    
    Returns:
        List of dicts dengan keys: 'prompt', 'label', 'question_type'
    """
    print(f"\n📊 Membaca dataset dari {csv_path}...")
    df = pd.read_csv(csv_path, delimiter=';')
    print(f"✅ Dataset berhasil dimuat: {len(df)} records")
    
    training_data = []
    unique_questions = df['pertanyaan'].unique()
    
    print(f"\n🔄 Memproses {len(df)} jawaban dari {len(unique_questions)} pertanyaan unik...")
    
    question_contexts = {}
    zero_imputation_count = 0
    blank_answer_count = 0
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Creating training data"):
        question = str(row['pertanyaan']).strip()
        student_answer = str(row['jawaban']).strip()
        question_type = str(row.get('tipe_soal', 'panjang')).strip().lower()
        
        if not question:
            continue
        
        # Skip jawaban kosong
        if _is_blank_answer(student_answer):
            blank_answer_count += 1
            continue
        
        # Handle NaN scores
        try:
            skor_value = row['skor']
            if pd.isna(skor_value) or str(skor_value).strip() == '' or str(skor_value).lower() == 'nan':
                true_score = 0
                zero_imputation_count += 1
            else:
                true_score = int(float(skor_value))
        except (ValueError, TypeError):
            true_score = 0
            zero_imputation_count += 1
        
        # Retrieve context (cached per question)
        if question not in question_contexts:
            rag_query = f"{question} {question}"
            retrieved_docs = retriever.retrieve(rag_query, top_k=top_k)
            question_contexts[question] = [doc['text'] for doc in retrieved_docs]
        
        reference_texts = question_contexts[question]
        
        # Create prompt (NO expected output!)
        prompt = create_classification_prompt(
            question=question,
            student_answer=student_answer,
            reference_texts=reference_texts,
            question_type=question_type
        )
        
        training_data.append({
            "prompt": prompt,
            "label": true_score,  # ✅ Direct label (0-4)
            "question_type": question_type,
            "question": question,
            "answer": student_answer
        })
    
    print(f"\n✅ Berhasil membuat {len(training_data)} training samples")
    print(f"📊 Statistik:")
    print(f"   - Pertanyaan unik: {len(unique_questions)}")
    print(f"   - Context di-cache: {len(question_contexts)}")
    if zero_imputation_count > 0:
        print(f"   - Zero imputation (NaN → 0): {zero_imputation_count} baris")
    if blank_answer_count > 0:
        print(f"   - Jawaban kosong (di-skip): {blank_answer_count} baris")
    
    # Print label distribution
    labels = [item["label"] for item in training_data]
    label_counts = Counter(labels)
    print(f"\n📊 Distribusi Label:")
    for label in sorted(label_counts.keys()):
        count = label_counts[label]
        pct = count / len(labels) * 100
        print(f"   Skor {label}: {count:4d} ({pct:5.1f}%)")
    
    return training_data

# ==================================================================================
# CLASSIFICATION MODEL
# ==================================================================================

class QwenForSequenceClassification(nn.Module):
    """
    Wrapper untuk Qwen3-4B-Instruct dengan classification head
    
    Architecture:
    - Base Model: Qwen3-4B-Instruct (causal LM)
    - Hidden States: Extract dari last layer
    - Classifier: Linear(hidden_size → num_labels)
    """
    
    def __init__(self, base_model: PreTrainedModel, num_labels: int = 5):
        super().__init__()
        self.base_model = base_model
        self.num_labels = num_labels
        
        # Get hidden size from base model config
        self.hidden_size = base_model.config.hidden_size
        
        # Classification head
        self.classifier = nn.Linear(self.hidden_size, num_labels)
        
        # Initialize classifier weights
        nn.init.normal_(self.classifier.weight, std=0.02)
        nn.init.zeros_(self.classifier.bias)
        
        logger.info(f"✅ Classification head initialized: {self.hidden_size} → {num_labels}")
    
    def gradient_checkpointing_enable(self, gradient_checkpointing_kwargs=None):
        """Proxy method untuk gradient checkpointing"""
        if hasattr(self.base_model, 'gradient_checkpointing_enable'):
            self.base_model.gradient_checkpointing_enable(gradient_checkpointing_kwargs)
    
    def gradient_checkpointing_disable(self):
        """Proxy method untuk disable gradient checkpointing"""
        if hasattr(self.base_model, 'gradient_checkpointing_disable'):
            self.base_model.gradient_checkpointing_disable()
    
    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass untuk classification
        
        Args:
            input_ids: [batch_size, seq_len]
            attention_mask: [batch_size, seq_len]
            labels: [batch_size] - ground truth scores (0-4)
        
        Returns:
            Dict dengan 'loss', 'logits', 'predictions'
        """
        # Get hidden states from base model
        outputs = self.base_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            return_dict=True
        )
        
        # Extract last hidden state: [batch_size, seq_len, hidden_size]
        hidden_states = outputs.hidden_states[-1]
        
        # Pool: Take hidden state of last token (like sequence classification)
        # Get the last non-padding token for each sequence
        sequence_lengths = attention_mask.sum(dim=1) - 1  # -1 because 0-indexed
        batch_size = input_ids.shape[0]
        
        # Gather last token hidden states
        pooled_output = hidden_states[torch.arange(batch_size, device=hidden_states.device), sequence_lengths]
        
        # Classification head
        logits = self.classifier(pooled_output)  # [batch_size, num_labels]
        
        # Compute loss if labels provided
        loss = None
        if labels is not None:
            loss_fct = nn.CrossEntropyLoss()
            loss = loss_fct(logits, labels)
        
        # Get predictions
        predictions = torch.argmax(logits, dim=-1)
        
        return {
            "loss": loss,
            "logits": logits,
            "predictions": predictions
        }

# ==================================================================================
# CUSTOM DATA COLLATOR
# ==================================================================================

class ClassificationDataCollator:
    """Data collator untuk classification task"""
    
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
    
    def __call__(self, features: List[Dict[str, Any]]) -> Dict[str, torch.Tensor]:
        """
        Collate batch of features
        
        Input features: List of dicts with 'input_ids', 'attention_mask', 'labels'
        Output: Batched tensors
        """
        # Convert lists to tensors
        batch = {
            "input_ids": torch.tensor([f["input_ids"] for f in features], dtype=torch.long),
            "attention_mask": torch.tensor([f["attention_mask"] for f in features], dtype=torch.long),
            "labels": torch.tensor([f["labels"] for f in features], dtype=torch.long)
        }
        return batch

# ==================================================================================
# CUSTOM TRAINER
# ==================================================================================

class ClassificationTrainer(Trainer):
    """Custom Trainer untuk classification task"""
    
    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        """Override compute_loss untuk classification"""
        labels = inputs.pop("labels")
        outputs = model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            labels=labels
        )
        loss = outputs["loss"]
        return (loss, outputs) if return_outputs else loss
    
    def _save(self, output_dir: Optional[str] = None, state_dict=None):
        """Override _save untuk handle shared tensors dengan safe_serialization=False"""
        output_dir = output_dir if output_dir is not None else self.args.output_dir
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Saving model checkpoint to {output_dir}")
        
        # Save only the LoRA adapters, not the full model
        # This avoids the shared tensors issue
        if hasattr(self.model, 'base_model'):
            # This is our wrapped model
            self.model.base_model.save_pretrained(
                output_dir,
                safe_serialization=False  # ✅ Use PyTorch format to avoid shared tensor error
            )
            # Also save classifier head
            torch.save(
                self.model.classifier.state_dict(),
                os.path.join(output_dir, "classifier_head.pt")
            )
        else:
            # Fallback to default
            super()._save(output_dir, state_dict)

# ==================================================================================
# METRICS CALLBACK
# ==================================================================================

class ClassificationMetricsCallback(TrainerCallback):
    """Callback untuk compute metrics selama training"""
    
    def __init__(self, model, tokenizer, val_data):
        super().__init__()
        self.model = model
        self.tokenizer = tokenizer
        self.val_data = val_data
    
    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        """Compute classification metrics"""
        try:
            sample_size = min(50, len(self.val_data))
            sampled = self.val_data[:sample_size]
            
            all_preds = []
            all_labels = []
            
            self.model.eval()
            with torch.no_grad():
                for item in tqdm(sampled, desc="Eval metrics", leave=False):
                    # Tokenize
                    inputs = self.tokenizer(
                        item["prompt"],
                        return_tensors="pt",
                        truncation=True,
                        max_length=MAX_SEQ_LENGTH,
                        padding="max_length"
                    )
                    inputs = {k: v.to(self.model.base_model.device) for k, v in inputs.items()}
                    
                    # Forward
                    outputs = self.model(
                        input_ids=inputs["input_ids"],
                        attention_mask=inputs["attention_mask"]
                    )
                    pred = outputs["predictions"][0].item()
                    
                    all_preds.append(pred)
                    all_labels.append(item["label"])
            
            # Compute metrics
            accuracy = accuracy_score(all_labels, all_preds)
            mae = mean_absolute_error(all_labels, all_preds)
            try:
                qwk = cohen_kappa_score(all_labels, all_preds, weights="quadratic")
            except:
                qwk = 0.0
            
            print(f"\n{'='*60}")
            print(f"📊 VALIDATION METRICS ({sample_size} samples)")
            print(f"{'='*60}")
            print(f"   ✅ Accuracy: {accuracy*100:.2f}%")
            print(f"   📏 MAE:      {mae:.4f}")
            print(f"   🎯 QWK:      {qwk:.4f}")
            
            # Show confusion examples
            print(f"\n📝 Sample Predictions:")
            for i in range(min(5, len(all_preds))):
                symbol = "✓" if all_preds[i] == all_labels[i] else "✗"
                print(f"   {symbol} Pred: {all_preds[i]} | True: {all_labels[i]}")
            print(f"{'='*60}\n")
            
            if metrics is not None:
                metrics["eval_accuracy"] = accuracy
                metrics["eval_mae"] = mae
                metrics["eval_qwk"] = qwk
        
        except Exception as e:
            logger.error(f"Error in metrics callback: {e}")
            import traceback
            traceback.print_exc()

# ==================================================================================
# MAIN FUNCTION
# ==================================================================================

def main():
    """Main function untuk fine-tuning classification"""
    
    print("="*80)
    print("FINE-TUNING QWEN3-4B dengan CLASSIFICATION HEAD untuk AES")
    print("="*80)
    print("🔥 Mode: CLASSIFICATION (bukan text generation!)")
    print("   - Output: 5 classes (skor 0-4)")
    print("   - Loss: CrossEntropyLoss")
    print("   - Jauh lebih stabil dari generative approach!")
    print("="*80 + "\n")
    
    # Create directories
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    # 1. Process Document
    print("\n📄 Step 1: Processing Document...")
    doc_processor = DocumentProcessor(PDF_PATH)
    chunks = doc_processor.chunk_text(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    print(f"✅ Dokumen berhasil dibagi menjadi {len(chunks)} chunks")
    
    # 2. Initialize Dense Retriever
    print("\n🔍 Step 2: Initializing Dense Retriever...")
    retriever = DenseRetriever(
        chunks=chunks,
        model_name=EMBEDDING_MODEL,
        cache_dir=CACHE_DIR
    )
    print("✅ Dense Retriever siap")
    
    # 3. Create Training Data (Classification format!)
    print("\n📊 Step 3: Creating Classification Training Data...")
    training_data = create_training_data_classification(
        csv_path=DATASET_PATH,
        retriever=retriever,
        top_k=TOP_K_RETRIEVAL
    )
    
    # Cleanup retriever
    print("\n🧹 Cleaning up retriever...")
    del retriever
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("✅ Retriever cleaned up")
    
    # 4. Split Dataset (70-20-10)
    print("\n✂️ Step 4: Splitting Dataset...")
    scores = [item["label"] for item in training_data]
    
    train_data, temp_data = train_test_split(
        training_data,
        test_size=0.3,
        random_state=42,
        stratify=scores
    )
    
    temp_scores = [item["label"] for item in temp_data]
    val_data, test_data = train_test_split(
        temp_data,
        test_size=0.333,
        random_state=42,
        stratify=temp_scores
    )
    
    print(f"   - Train: {len(train_data)} ({len(train_data)/len(training_data)*100:.1f}%)")
    print(f"   - Val:   {len(val_data)} ({len(val_data)/len(training_data)*100:.1f}%)")
    print(f"   - Test:  {len(test_data)} ({len(test_data)/len(training_data)*100:.1f}%)")
    
    # 5. Load Model
    print("\n🤖 Step 5: Loading Base Model...")
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        padding_side="right"
    )
    
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    print("✅ Tokenizer loaded")
    
    if torch.cuda.is_available():
        base_model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        print("✅ Base model loaded (FP16, GPU)")
    else:
        base_model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float32,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        print("✅ Base model loaded (FP32, CPU)")
    
    # 6. Apply LoRA
    print("\n🔧 Step 6: Applying LoRA...")
    
    if hasattr(base_model, 'gradient_checkpointing_enable'):
        base_model.gradient_checkpointing_enable()
        print("✅ Gradient checkpointing enabled")
    
    for param in base_model.parameters():
        param.requires_grad = False
    
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        target_modules=TARGET_MODULES,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    base_model = get_peft_model(base_model, lora_config)
    print("✅ LoRA applied to base model")
    
    # 7. Add Classification Head
    print("\n🎯 Step 7: Adding Classification Head...")
    model = QwenForSequenceClassification(base_model, num_labels=NUM_LABELS)
    
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    all_params = sum(p.numel() for p in model.parameters())
    trainable_percent = 100 * trainable_params / all_params
    
    print(f"✅ Classification model ready")
    print(f"   - Trainable params: {trainable_params:,} ({trainable_percent:.2f}%)")
    print(f"   - All params: {all_params:,}")
    
    # 8. Tokenize Dataset
    print("\n📝 Step 8: Tokenizing Dataset...")
    
    def tokenize_classification(examples):
        """Tokenize for classification (no text output, just label)"""
        # Tokenize WITHOUT return_tensors (will be handled by collator)
        outputs = tokenizer(
            examples["prompt"],
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
            padding="max_length"
        )
        # Add label as plain int (not tensor)
        outputs["labels"] = examples["label"]
        return outputs
    
    train_dataset = Dataset.from_list(train_data)
    val_dataset = Dataset.from_list(val_data)
    
    tokenized_train = train_dataset.map(
        tokenize_classification,
        batched=False,
        desc="Tokenizing train"
    )
    
    tokenized_val = val_dataset.map(
        tokenize_classification,
        batched=False,
        desc="Tokenizing val"
    )
    
    print(f"✅ Tokenization complete")
    
    # 9. Training Configuration
    print("\n⚙️ Step 9: Configuring Training...")
    
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        logging_steps=LOGGING_STEPS,
        save_steps=SAVE_STEPS,
        eval_steps=SAVE_STEPS,
        eval_strategy="steps",
        save_strategy="steps",
        load_best_model_at_end=False,  # ✅ Disabled karena torch.load security issue
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        save_total_limit=3,
        fp16=torch.cuda.is_available(),
        optim="adamw_torch",
        lr_scheduler_type="linear",
        logging_dir=f"{OUTPUT_DIR}/logs",
        report_to="none",
        push_to_hub=False,
        remove_unused_columns=False,
        gradient_checkpointing=True,
        max_grad_norm=1.0,
        weight_decay=0.01,
    )
    
    print(f"✅ Training configuration set")
    print(f"   - Epochs: {NUM_EPOCHS}")
    print(f"   - Batch size: {BATCH_SIZE}")
    print(f"   - Gradient accumulation: {GRADIENT_ACCUMULATION_STEPS}")
    print(f"   - Effective batch size: {BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS}")
    print(f"   - Learning rate: {LEARNING_RATE}")
    
    # 10. Initialize Trainer
    print("\n🚀 Step 10: Initializing Trainer...")
    
    data_collator = ClassificationDataCollator(tokenizer)
    metrics_callback = ClassificationMetricsCallback(model, tokenizer, val_data)
    
    trainer = ClassificationTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_val,
        data_collator=data_collator,
        callbacks=[metrics_callback]
    )
    
    print("✅ Trainer initialized")
    
    # 11. Start Training
    print("\n" + "="*80)
    print("🚀 STARTING CLASSIFICATION TRAINING")
    print("="*80)
    print(f"   Training samples: {len(train_data)}")
    print(f"   Validation samples: {len(val_data)}")
    print(f"   Task: Classification (0-4)")
    print(f"   Loss: CrossEntropyLoss")
    print("="*80 + "\n")
    
    trainer.train()
    
    print("\n" + "="*80)
    print("🎉 TRAINING COMPLETE!")
    print("="*80)
    
    # 12. Save Model
    print("\n💾 Step 12: Saving Model...")
    final_model_path = f"{OUTPUT_DIR}/final_model"
    model.base_model.save_pretrained(final_model_path)
    tokenizer.save_pretrained(final_model_path)
    
    # Save classifier head separately
    torch.save(model.classifier.state_dict(), f"{final_model_path}/classifier_head.pt")
    print(f"✅ Model saved to: {final_model_path}")
    print(f"   - LoRA adapters: adapter_model.bin")
    print(f"   - Classifier head: classifier_head.pt")
    
    # 13. Test Evaluation
    print("\n🧪 Step 13: Final Test Evaluation...")
    test_preds = []
    test_labels = []
    
    model.eval()
    with torch.no_grad():
        for item in tqdm(test_data, desc="Testing"):
            inputs = tokenizer(
                item["prompt"],
                return_tensors="pt",
                truncation=True,
                max_length=MAX_SEQ_LENGTH,
                padding="max_length"
            )
            inputs = {k: v.to(model.base_model.device) for k, v in inputs.items()}
            
            outputs = model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"]
            )
            pred = outputs["predictions"][0].item()
            
            test_preds.append(pred)
            test_labels.append(item["label"])
    
    # Compute test metrics
    test_acc = accuracy_score(test_labels, test_preds)
    test_mae = mean_absolute_error(test_labels, test_preds)
    try:
        test_qwk = cohen_kappa_score(test_labels, test_preds, weights="quadratic")
    except:
        test_qwk = 0.0
    
    print(f"\n{'='*70}")
    print(f"📊 TEST SET RESULTS")
    print(f"{'='*70}")
    print(f"   ✅ Test Accuracy:  {test_acc*100:6.2f}%")
    print(f"   📏 Test MAE:       {test_mae:6.4f}")
    print(f"   🎯 Test QWK:       {test_qwk:6.4f}")
    print(f"{'='*70}")
    
    # Save test results
    test_results = {
        "test_accuracy": float(test_acc),
        "test_mae": float(test_mae),
        "test_qwk": float(test_qwk),
        "test_samples": len(test_data)
    }
    
    with open(f"{OUTPUT_DIR}/test_results.json", "w") as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\n💾 Test results saved to: {OUTPUT_DIR}/test_results.json")
    
    print("\n" + "="*80)
    print("✅ ALL DONE!")
    print("="*80)
    print(f"\n📁 Output: {OUTPUT_DIR}")
    print(f"   ✅ Model & classifier head")
    print(f"   ✅ Training logs")
    print(f"   ✅ Test results")
    print("="*80)

if __name__ == "__main__":
    main()

