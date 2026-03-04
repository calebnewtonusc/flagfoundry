"""
train.py - Stage 1: SFT on FlagFoundry (challenge, reasoning, exploit) dataset.

Hardware target: 18x A6000 (48GB each)
Base model: Qwen2.5-Coder-7B-Instruct
Method: LoRA SFT + DeepSpeed ZeRO-3

Launch (18 GPUs):
  CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17 \\
  deepspeed --num_gpus=18 training/train.py \\
    --deepspeed training/configs/ds_config.json \\
    --model Qwen/Qwen2.5-Coder-7B-Instruct \\
    --data-dir data/train \\
    --output-dir checkpoints/flagfoundry-sft

Launch (4 GPUs, reduced batch):
  CUDA_VISIBLE_DEVICES=0,1,2,3 deepspeed --num_gpus=4 training/train.py \\
    --deepspeed training/configs/ds_config.json \\
    --batch-size 2 --grad-accum 8
"""

import argparse
import json
import math
import os
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainerCallback,
)
from trl import SFTConfig, SFTTrainer
from loguru import logger


def load_dataset(jsonl_path: str) -> Dataset:
    """Load ShareGPT-format JSONL training data."""
    records = []
    for line in Path(jsonl_path).read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    logger.info(f"Loaded {len(records):,} records from {jsonl_path}")
    return Dataset.from_list(records)


def format_to_text(example: dict, tokenizer) -> dict:
    """Convert ShareGPT format to text using the model's chat template."""
    conversations = example.get("conversations", [])
    messages = []

    system_msgs = [c for c in conversations if c.get("from") == "system"]
    if system_msgs:
        messages.append({"role": "system", "content": system_msgs[0]["value"]})

    for c in conversations:
        if c.get("from") == "human":
            messages.append({"role": "user", "content": c["value"]})
        elif c.get("from") == "gpt":
            messages.append({"role": "assistant", "content": c["value"]})

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return {"text": text}


class PrintMetricsCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs:
            step = state.global_step
            loss = logs.get("loss", "—")
            lr = logs.get("learning_rate", "—")
            if isinstance(loss, float):
                logger.info(f"step {step:>6} | loss {loss:.4f} | lr {lr:.2e}")


def build_lora_config(r: int = 64) -> LoraConfig:
    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=r,
        lora_alpha=r * 2,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_dropout=0.05,
        bias="none",
    )


def main():
    parser = argparse.ArgumentParser(description="Stage 1 SFT: FlagFoundry")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--data-dir", default="data/train")
    parser.add_argument("--output-dir", default="checkpoints/flagfoundry-sft")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=3072,
                        help="CTF exploits can be long — 3k tokens")
    parser.add_argument("--lora-r", type=int, default=64)
    parser.add_argument("--deepspeed", type=str)
    # FF-27 FIX: action="store_true" with default=True means --flash-attn is always
    # True — the flag can never be disabled because store_true only sets True when
    # the flag is present, but default=True keeps it True when absent.
    # Default to False so flash-attn is opt-in (not available in all environments).
    parser.add_argument("--flash-attn", action="store_true", default=False)
    parser.add_argument("--wandb-project", default="flagfoundry-sft")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    train_file = data_dir / "sharegpt_train.jsonl"
    val_file = data_dir / "sharegpt_val.jsonl"

    if not train_file.exists():
        logger.error(f"Training data not found at {train_file}. Run train_prep.py first.")
        return

    logger.info(f"Loading model: {args.model}")
    model_kwargs = dict(torch_dtype=torch.bfloat16, device_map=None)
    if args.flash_attn:
        model_kwargs["attn_implementation"] = "flash_attention_2"

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.model, trust_remote_code=True, **model_kwargs
    )
    model.enable_input_require_grads()

    lora_cfg = build_lora_config(args.lora_r)
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    logger.info("Loading datasets...")
    train_ds = load_dataset(str(train_file))
    val_ds = load_dataset(str(val_file)) if val_file.exists() else None

    train_ds = train_ds.map(lambda ex: format_to_text(ex, tokenizer))
    if val_ds:
        val_ds = val_ds.map(lambda ex: format_to_text(ex, tokenizer))

    n_gpus = torch.cuda.device_count() or 1
    effective_batch = args.batch_size * args.grad_accum * n_gpus
    steps_per_epoch = math.ceil(len(train_ds) / effective_batch)
    total_steps = steps_per_epoch * args.epochs
    logger.info(f"GPUs: {n_gpus} | Effective batch: {effective_batch} | Steps: {total_steps:,}")

    training_args = SFTConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        weight_decay=0.01,
        bf16=True,
        fp16=False,
        logging_steps=10,
        eval_strategy="steps" if val_ds else "no",
        eval_steps=max(1, steps_per_epoch // 4) if val_ds else None,
        save_strategy="steps",
        save_steps=max(1, steps_per_epoch // 2),
        save_total_limit=3,
        load_best_model_at_end=bool(val_ds),
        report_to=["wandb"] if os.environ.get("WANDB_API_KEY") else [],
        run_name=f"flagfoundry-sft",
        dataloader_num_workers=4,
        remove_unused_columns=False,
        deepspeed=args.deepspeed,
        ddp_find_unused_parameters=False,
        dataset_text_field="text",
        max_seq_length=args.max_length,
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        callbacks=[PrintMetricsCallback()],
    )

    logger.info(f"\nStarting SFT training → {args.output_dir}")
    trainer.train()

    final_dir = Path(args.output_dir) / "final"
    logger.info(f"Merging LoRA weights → {final_dir}")
    merged = model.merge_and_unload()
    merged.save_pretrained(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    logger.info(f"Done. Model saved to {final_dir}")
    logger.info(f"\nNext: deepspeed --num_gpus=16 training/train_rl.py --base-model {final_dir}")


if __name__ == "__main__":
    main()
