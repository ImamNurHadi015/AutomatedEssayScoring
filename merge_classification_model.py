#!/usr/bin/env python3
"""
Merge LoRA Classification Model to Base

Merge LoRA adapters + classifier head untuk inference lebih cepat
PENTING: Hasil tidak bisa di-convert ke GGUF (karena classifier head custom)
"""

import os
import json
import torch
import torch.nn as nn
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

# Import from finetuning_classification
import sys
sys.path.insert(0, str(Path(__file__).parent))
from finetuning_classification import QwenForSequenceClassification

# ==================================================================================
# CONFIGURATION
# ==================================================================================

BASE_MODEL_PATH = "models/.cache/huggingface/download/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554"
LORA_CHECKPOINT = "output_classification/checkpoint-150"  # ✅ Best checkpoint
OUTPUT_PATH = "output_classification/merged_model"

NUM_LABELS = 5

# ==================================================================================
# MAIN
# ==================================================================================

def find_best_checkpoint(checkpoints_dir: str = "output_classification") -> str:
    """Find checkpoint with lowest eval_loss"""
    import glob
    
    checkpoints = glob.glob(f"{checkpoints_dir}/checkpoint-*/trainer_state.json")
    if not checkpoints:
        raise ValueError(f"No checkpoints found in {checkpoints_dir}")
    
    best_checkpoint = None
    best_loss = float('inf')
    
    for ckpt_path in checkpoints:
        with open(ckpt_path) as f:
            state = json.load(f)
        
        # Find last eval_loss
        eval_logs = [log for log in state['log_history'] if 'eval_loss' in log]
        if eval_logs:
            last_eval = eval_logs[-1]
            eval_loss = last_eval['eval_loss']
            
            if eval_loss < best_loss:
                best_loss = eval_loss
                best_checkpoint = str(Path(ckpt_path).parent)
    
    return best_checkpoint, best_loss

def main():
    print("="*80)
    print("MERGE LORA CLASSIFICATION MODEL")
    print("="*80)
    
    # 1. Find best checkpoint
    print("\n📊 Step 1: Finding Best Checkpoint...")
    best_ckpt, best_loss = find_best_checkpoint()
    print(f"✅ Best checkpoint: {best_ckpt}")
    print(f"   Eval loss: {best_loss:.4f}")
    
    # Override LORA_CHECKPOINT with best
    global LORA_CHECKPOINT
    LORA_CHECKPOINT = best_ckpt
    
    # 2. Load tokenizer (from base model, not checkpoint)
    print("\n📝 Step 2: Loading Tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True)
    print("✅ Tokenizer loaded")
    
    # 3. Load base model
    print("\n🤖 Step 3: Loading Base Model...")
    if torch.cuda.is_available():
        base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL_PATH,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )
        print("✅ Base model loaded (FP16, GPU)")
    else:
        base_model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL_PATH,
            torch_dtype=torch.float32,
            trust_remote_code=True,
        )
        print("✅ Base model loaded (FP32, CPU)")
    
    # 4. Load LoRA adapters
    print("\n🔧 Step 4: Loading LoRA Adapters...")
    base_model = PeftModel.from_pretrained(base_model, LORA_CHECKPOINT)
    print("✅ LoRA adapters loaded")
    
    # 5. Merge LoRA to base
    print("\n🔀 Step 5: Merging LoRA to Base Model...")
    merged_model = base_model.merge_and_unload()
    print("✅ LoRA merged into base model")
    
    # 6. Wrap with classification head
    print("\n🎯 Step 6: Adding Classification Head...")
    classification_model = QwenForSequenceClassification(merged_model, num_labels=NUM_LABELS)
    
    # Get device and dtype from base model
    device = next(classification_model.base_model.parameters()).device
    dtype = next(classification_model.base_model.parameters()).dtype
    print(f"   Base model device: {device}")
    print(f"   Base model dtype: {dtype}")
    
    # Load classifier head weights
    classifier_path = os.path.join(LORA_CHECKPOINT, "classifier_head.pt")
    if os.path.exists(classifier_path):
        # Load state dict
        classifier_state = torch.load(classifier_path, map_location=device)
        # Convert all tensors in state dict to match base model dtype
        classifier_state = {k: v.to(dtype=dtype) if isinstance(v, torch.Tensor) else v 
                            for k, v in classifier_state.items()}
        classification_model.classifier.load_state_dict(classifier_state)
        # Ensure entire model is on correct device and dtype
        classification_model = classification_model.to(device=device, dtype=dtype)
        print(f"✅ Classifier head loaded and moved to {device} with dtype {dtype}")
    else:
        print("⚠️ Classifier head not found!")
        return
    
    # 7. Save merged model
    print("\n💾 Step 7: Saving Merged Model...")
    os.makedirs(OUTPUT_PATH, exist_ok=True)
    
    # Save base model (with merged LoRA)
    classification_model.base_model.save_pretrained(OUTPUT_PATH)
    tokenizer.save_pretrained(OUTPUT_PATH)
    
    # Save classifier head
    torch.save(classification_model.classifier.state_dict(), f"{OUTPUT_PATH}/classifier_head.pt")
    
    # Save config
    config = {
        "model_type": "classification",
        "num_labels": NUM_LABELS,
        "base_model": BASE_MODEL_PATH,
        "lora_checkpoint": LORA_CHECKPOINT,
        "best_eval_loss": float(best_loss),
        "merged": True
    }
    
    with open(f"{OUTPUT_PATH}/model_config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Merged model saved to: {OUTPUT_PATH}")
    print(f"   - Base model: pytorch_model.bin (atau model.safetensors)")
    print(f"   - Classifier head: classifier_head.pt")
    print(f"   - Config: model_config.json")
    
    # 8. Test inference
    print("\n🧪 Step 8: Testing Inference...")
    test_prompt = """<|im_start|>system
Sistem penilaian otomatis jawaban esai IPA.
Soal tipe SINGKAT (skor 0 atau 2):
- Skor 2: Jawaban benar, relevan dengan konsep kunci
- Skor 0: Jawaban salah, tidak relevan, atau kosong

Evaluasi jawaban siswa berdasarkan referensi yang diberikan.
<|im_end|>

<|im_start|>user
PERTANYAAN:
Pencernaan yang terjadi dengan bantuan enzim disebut dengan pencernaan secara...

JAWABAN SISWA:
Kimiawi

REFERENSI:
Enzim adalah protein yang berfungsi sebagai biokatalisator dalam proses pencernaan. Pencernaan secara kimiawi menggunakan enzim untuk memecah makanan.
<|im_end|>

<|im_start|>assistant
"""
    
    classification_model.eval()
    inputs = tokenizer(test_prompt, return_tensors="pt", truncation=True, max_length=1024, padding="max_length")
    inputs = {k: v.to(classification_model.base_model.device) for k, v in inputs.items()}
    
    with torch.no_grad():
        outputs = classification_model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"]
        )
        pred_score = outputs["predictions"][0].item()
        logits = outputs["logits"][0]
    
    print(f"\n📊 Test Inference Results:")
    print(f"   Prompt: 'Pencernaan enzim = kimiawi'")
    print(f"   Predicted Score: {pred_score}")
    print(f"   Logits: {logits.cpu().numpy()}")
    print(f"   Expected: 2 (benar)")
    
    if pred_score == 2:
        print("   ✅ CORRECT!")
    else:
        print(f"   ❌ WRONG (expected 2, got {pred_score})")
    
    print("\n" + "="*80)
    print("✅ MERGE COMPLETE!")
    print("="*80)
    print(f"\n📁 Output: {OUTPUT_PATH}")
    print(f"   Contains: Merged base model + classifier head")
    print(f"\n⚠️ NOTE:")
    print(f"   - This model is for PYTHON INFERENCE only")
    print(f"   - CANNOT be converted to GGUF (classifier head not supported)")
    print(f"   - Use evaluate_classification.py to evaluate on dataset")
    print("="*80)

if __name__ == "__main__":
    main()

