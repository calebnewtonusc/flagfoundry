"""
train_dpo.py - Stage 3: DPO on writeup explanation quality.

Teaches FlagFoundry to produce high-quality, pedagogical writeup-style explanations.

Chosen: detailed step-by-step reasoning → working exploit → clear flag extraction
        (writeup quality that would get upvoted on CTFtime)

Rejected: minimal, just the exploit script, no explanation of the attack

Sources:
  - execution: pairs from RL (successful exploit = chosen, failed = rejected)
  - quality:   human-ranked writeup quality pairs (expert vs. minimal)
  - approach:  correct vuln class = chosen, wrong class = rejected

Launch (18 GPUs):
  deepspeed --num_gpus=18 training/train_dpo.py \\
    --base-model checkpoints/flagfoundry-rl/final \\
    --output-dir checkpoints/flagfoundry-final \\
    --deepspeed training/configs/ds_config.json
"""

import argparse
import json
import logging
import math
import os
import random
import time
from pathlib import Path

import torch
from loguru import logger
from peft import LoraConfig, PeftModel, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainerCallback,
    TrainingArguments,
)

try:
    from trl import DPOConfig, DPOTrainer
    HAS_TRL = True
except ImportError:
    HAS_TRL = False

try:
    import wandb
    HAS_WANDB = True
except ImportError:
    HAS_WANDB = False

ROOT = Path(__file__).parents[1]


class DPODataset:
    """Load FlagFoundry DPO preference pairs from multiple sources."""

    SOURCE_FILES = {
        "execution": "data/dpo/execution_pairs.jsonl",
        "quality":   "data/dpo/quality_pairs.jsonl",
        "approach":  "data/dpo/approach_pairs.jsonl",
    }

    def __init__(
        self,
        root: Path,
        sources: list[str],
        max_pairs: int | None = None,
        val_split: float = 0.05,
    ):
        self.root = root
        self.pairs: list[dict] = []
        for source in sources:
            pairs = self._load(source)
            self.pairs.extend(pairs)
            logger.info(f"  DPO source '{source}': {len(pairs):,} pairs")

        random.shuffle(self.pairs)
        if max_pairs:
            self.pairs = self.pairs[:max_pairs]

        n_val = max(1, int(len(self.pairs) * val_split))
        self.val_pairs = self.pairs[:n_val]
        self.train_pairs = self.pairs[n_val:]
        logger.info(f"DPO total: {len(self.train_pairs):,} train | {len(self.val_pairs):,} val")

    def _load(self, source: str) -> list[dict]:
        path = self.root / self.SOURCE_FILES.get(source, "")
        if not path.exists():
            logger.warning(f"DPO source not found: {path}. Generate with generate_dpo_pairs.py")
            return []
        pairs = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                p = json.loads(line)
                if all(k in p for k in ("prompt", "chosen", "rejected")):
                    pairs.append(p)
            except json.JSONDecodeError:
                pass
        return pairs

    def to_hf(self):
        from datasets import Dataset
        train = Dataset.from_list([
            {"prompt": p["prompt"], "chosen": p["chosen"], "rejected": p["rejected"]}
            for p in self.train_pairs
        ])
        val = Dataset.from_list([
            {"prompt": p["prompt"], "chosen": p["chosen"], "rejected": p["rejected"]}
            for p in self.val_pairs
        ])
        return train, val


class DPOMetricsCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        if not logs:
            return
        step = state.global_step
        loss = logs.get("loss")
        margin = logs.get("rewards/margins")
        acc = logs.get("rewards/accuracies")
        parts = [f"step {step:>5}"]
        if loss is not None:
            parts.append(f"loss {loss:.4f}")
        if margin is not None:
            parts.append(f"margin {margin:.3f}")
        if acc is not None:
            parts.append(f"acc {acc:.1%}")
        logger.info(" | ".join(parts))


def main():
    parser = argparse.ArgumentParser(description="Stage 3: DPO for FlagFoundry explanation quality")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--output-dir", default="checkpoints/flagfoundry-final")
    parser.add_argument("--deepspeed", type=str)
    parser.add_argument("--data-sources", nargs="+",
                        default=["execution", "quality", "approach"])
    parser.add_argument("--beta", type=float, default=0.1)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--num-epochs", type=int, default=3,
                        help="Number of training epochs (default: 3)")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-7)
    parser.add_argument("--max-length", type=int, default=3072)
    parser.add_argument("--max-prompt-length", type=int, default=1024)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--max-pairs", type=int, default=None)
    parser.add_argument("--no-wandb", action="store_true")
    args = parser.parse_args()

    if not HAS_TRL:
        logger.error("TRL not available. pip install trl>=0.11.0")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if HAS_WANDB and not args.no_wandb:
        wandb.init(project="flagfoundry-dpo", config=vars(args))

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Check if the checkpoint is a PEFT adapter (has adapter_config.json) or a full model.
    # For PEFT-only checkpoints, read the base model name from adapter_config.json, load
    # the base model, then wrap with PeftModel.  Use device_map=None for DeepSpeed ZeRO-3
    # compatibility (ZeRO-3 manages device placement itself).
    rl_checkpoint_path = Path(args.base_model)
    adapter_config_path = rl_checkpoint_path / "adapter_config.json"
    model_kwargs = dict(torch_dtype=torch.bfloat16, device_map=None)

    if adapter_config_path.exists():
        adapter_cfg = json.loads(adapter_config_path.read_text())
        base_model_name = adapter_cfg.get("base_model_name_or_path", str(rl_checkpoint_path))
        logger.info(f"Loading base model {base_model_name} then wrapping with PEFT adapter {rl_checkpoint_path}")
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name, trust_remote_code=True, **model_kwargs
        )
        model = PeftModel.from_pretrained(base_model, str(rl_checkpoint_path))
    else:
        model = AutoModelForCausalLM.from_pretrained(args.base_model, trust_remote_code=True, **model_kwargs)

    model.enable_input_require_grads()

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_r * 2,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05, bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    if adapter_config_path.exists():
        logger.info(f"Loading ref model {base_model_name} then wrapping with PEFT adapter {rl_checkpoint_path}")
        ref_base = AutoModelForCausalLM.from_pretrained(
            base_model_name, trust_remote_code=True, **model_kwargs
        )
        ref_model = PeftModel.from_pretrained(ref_base, str(rl_checkpoint_path))
    else:
        ref_model = AutoModelForCausalLM.from_pretrained(
            args.base_model, trust_remote_code=True,
            torch_dtype=torch.bfloat16, device_map=None
        )
    ref_model.eval()
    for p in ref_model.parameters():
        p.requires_grad_(False)

    dataset = DPODataset(root=ROOT, sources=args.data_sources, max_pairs=args.max_pairs)
    train_ds, val_ds = dataset.to_hf()

    if len(train_ds) == 0:
        logger.error("No DPO training data. Run synthesis/generate_dpo_pairs.py first.")
        return

    n_gpus = torch.cuda.device_count() or 1
    effective_batch = args.batch_size * args.grad_accum * n_gpus
    # FF-13 FIX: Use args.num_epochs instead of hardcoded * 3
    total_steps = min(args.max_steps, math.ceil(len(train_ds) / effective_batch) * args.num_epochs)

    # Always use DPOConfig — DPOTrainer requires it and crashes with bare TrainingArguments.
    # metric_for_best_model must be the eval-prefixed key that DPOTrainer actually logs.
    training_args = DPOConfig(
        output_dir=str(output_dir),
        max_steps=total_steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        gradient_checkpointing=True,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=30,
        bf16=True,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_rewards/margins",
        report_to=[],
        deepspeed=args.deepspeed,
        beta=args.beta,
        max_length=args.max_length,
        max_prompt_length=args.max_prompt_length,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=ref_model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        args=training_args,
        callbacks=[DPOMetricsCallback()],
    )

    logger.info(f"Starting DPO training → {output_dir}")
    trainer.train()

    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    try:
        merged = model.merge_and_unload()
        merged.save_pretrained(str(final_dir))
    except Exception as e:
        # FF-14 FIX: Log the merge failure so callers know the model was not merged
        logger.warning(f"LoRA merge failed: {e}, saving unmerged adapter instead")
        (final_dir / "MERGE_FAILED.txt").write_text(str(e))
        model.save_pretrained(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))

    if HAS_WANDB and not args.no_wandb:
        wandb.finish()

    logger.info(f"DPO complete. Final model: {final_dir}")
    logger.info(f"Evaluate: python evaluation/flagbench.py --model {final_dir} --all")


if __name__ == "__main__":
    main()
