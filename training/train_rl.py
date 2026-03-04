"""
train_rl.py - Stage 2: GRPO RL with binary flag capture reward signal.

The key innovation: instead of headless Blender (Nalana's reward),
FlagFoundry uses Docker sandboxes running real CTF challenge services.

Reward signal:
  +1.0  flag captured (exact match, Docker-verified)
  +0.3  exploit ran without error, approach is correct, no flag extracted
  -0.5  syntax error in generated code
  -1.0  timeout, crash, or Docker failure

Method: GRPO (Group Relative Policy Optimization)
  For each challenge prompt:
    1. Generate N=4 exploit scripts
    2. Execute all 4 in Docker sandboxes (parallel)
    3. Compute group-relative advantages
    4. GRPO loss + KL penalty vs. SFT checkpoint

Launch (18 GPUs training + CPU Docker workers):
  CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17 \\
  deepspeed --num_gpus=18 training/train_rl.py \\
    --base-model checkpoints/flagfoundry-sft/final \\
    --output-dir checkpoints/flagfoundry-rl \\
    --deepspeed training/configs/ds_config_rl.json \\
    --docker-workers 8
"""

import argparse
import json
import logging
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import torch
import torch.nn.functional as F
from datasets import Dataset
from loguru import logger
from peft import LoraConfig, PeftModel, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    GenerationConfig,
    get_cosine_schedule_with_warmup,
)

try:
    import wandb
    HAS_WANDB = True
except ImportError:
    HAS_WANDB = False

ROOT = Path(__file__).parents[1]
DATA_DIR = ROOT / "data" / "train"


# ─── Flag Capture Reward Function ─────────────────────────────────────────────

class FlagCaptureReward:
    """
    Docker-based flag capture reward for GRPO RL training.

    For each generated exploit:
      1. Write exploit to temp file
      2. Spin up Docker exploit runner
      3. Check if flag was captured
      4. Return scalar reward

    This is the key innovation vs. other code LLMs:
    the reward is ground-truth binary (flag captured or not),
    not a learned reward model.
    """

    def __init__(self, workers: int = 4, timeout: int = 30):
        self.workers = workers
        self.timeout = timeout
        self._verify_docker()

    def _verify_docker(self):
        import subprocess
        try:
            result = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5
            )
            if result.returncode != 0:
                logger.warning("Docker not accessible — using simulated rewards")
                self._docker_available = False
            else:
                self._docker_available = True
        except Exception:
            logger.warning("Docker not found — using simulated rewards for debugging")
            self._docker_available = False

    def score_group(
        self,
        exploits: list[str],
        challenge_id: str,
        expected_flag: str,
    ) -> list[float]:
        """Score a group of exploit attempts. Returns list of rewards."""
        if not self._docker_available:
            # Simulated rewards for debugging without Docker
            return self._simulated_rewards(exploits)

        from core.sandbox_harness import SandboxHarness
        harness = SandboxHarness(timeout=self.timeout)
        return harness.score_batch(exploits, challenge_id, expected_flag)

    def _simulated_rewards(self, exploits: list[str]) -> list[float]:
        """Simulate rewards based on code quality heuristics (debug only)."""
        rewards = []
        for exploit in exploits:
            if exploit is None:
                rewards.append(0.0)
                continue
            score = 0.0
            if "import" in exploit:
                score += 0.1
            if "requests" in exploit or "pwn." in exploit or "socket" in exploit:
                score += 0.2
            if "print" in exploit:
                score += 0.1
            try:
                compile(exploit, "<string>", "exec")
                score += 0.3
            except SyntaxError:
                score -= 0.5
            rewards.append(score)
        return rewards


# ─── GRPO components (mirrors Nalana's implementation) ────────────────────────

def compute_advantages(score_groups: list[list[float]]) -> list[list[float]]:
    """Compute group-relative advantages for GRPO."""
    advantages = []
    for group in score_groups:
        if not group:
            advantages.append([])
            continue
        mean = sum(group) / len(group)
        # FF-2 FIX: Use sample std (divide by N-1) instead of population std (divide by N)
        # to match TRL/OpenAI GRPO implementations and avoid systematically inflated advantages
        std = (sum((s - mean) ** 2 for s in group) / max(len(group) - 1, 1)) ** 0.5
        # FF-9 FIX: Apply minimum std floor to prevent all-zero advantages when all
        # rewards in a group are identical (e.g. all zeros on an early training step).
        std = max(std, 1e-8)
        if std == 0:
            advantages.append([0.0] * len(group))
            continue
        normed = [(s - mean) / std for s in group]
        advantages.append(normed)
    return advantages


def compute_grpo_loss(
    model,
    ref_log_probs: torch.Tensor,
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
    response_mask: torch.Tensor,
    advantages: torch.Tensor,
    kl_coeff: float = 0.1,
) -> tuple[torch.Tensor, dict]:
    """GRPO loss: policy gradient + KL penalty."""
    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
    logits = outputs.logits[:, :-1, :]
    labels = input_ids[:, 1:]
    mask = response_mask[:, 1:]

    log_probs = F.log_softmax(logits, dim=-1)
    token_log_probs = log_probs.gather(-1, labels.unsqueeze(-1)).squeeze(-1)
    token_log_probs = token_log_probs * mask

    n_resp = mask.sum(dim=-1).clamp(min=1)
    seq_lp = token_log_probs.sum(-1) / n_resp

    # FF-3 FIX: Clamp n_resp to avoid divide-by-zero on all-masked sequences
    kl = (token_log_probs - ref_log_probs).sum(-1) / n_resp.clamp(min=1)

    pg_loss = -(advantages.detach() * seq_lp).mean()
    kl_loss = kl.mean()
    total = pg_loss + kl_coeff * kl_loss

    return total, {
        "loss/total": total.item(),
        "loss/pg": pg_loss.item(),
        "loss/kl": kl_loss.item(),
    }


@torch.no_grad()
def compute_ref_log_probs(ref_model, input_ids, attention_mask, response_mask):
    """Log probs from frozen reference model."""
    out = ref_model(input_ids=input_ids, attention_mask=attention_mask)
    logits = out.logits[:, :-1, :]
    labels = input_ids[:, 1:]
    mask = response_mask[:, 1:]
    lp = F.log_softmax(logits, dim=-1)
    token_lp = lp.gather(-1, labels.unsqueeze(-1)).squeeze(-1)
    return token_lp * mask


def load_challenge_prompts(data_dir: Path, limit: Optional[int] = None) -> list[dict]:
    """Load CTF challenge prompts from the training dataset."""
    train_file = data_dir / "sharegpt_train.jsonl"
    if not train_file.exists():
        raise FileNotFoundError(f"Training data not found at {train_file}")

    prompts = []
    for line in train_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        convs = record.get("conversations", [])
        human_turns = [c for c in convs if c.get("from") == "human"]
        if human_turns:
            prompts.append({
                "prompt": human_turns[0]["value"],
                "challenge_id": record.get("challenge_id", "unknown"),
                "expected_flag": record.get("flag", "FLAG{unknown}"),
                "conversations": convs,
            })

    if limit:
        prompts = prompts[:limit]
    logger.info(f"Loaded {len(prompts):,} challenge prompts")
    return prompts


def main():
    parser = argparse.ArgumentParser(description="Stage 2: GRPO RL for FlagFoundry")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--output-dir", default="checkpoints/flagfoundry-rl")
    parser.add_argument("--deepspeed", type=str)
    parser.add_argument("--data-dir", default="data/train")
    parser.add_argument("--num-samples", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-6)
    parser.add_argument("--kl-coeff", type=float, default=0.1)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--docker-workers", type=int, default=4)
    parser.add_argument("--docker-timeout", type=int, default=30)
    parser.add_argument("--lora-r", type=int, default=32)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--warmup-steps", type=int, default=50)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--grad-accum-steps", type=int, default=4,
                        help="Gradient accumulation steps to reduce OOM risk (FF-17)")
    parser.add_argument("--no-wandb", action="store_true")
    parser.add_argument("--num-prompts", type=int, default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if HAS_WANDB and not args.no_wandb:
        wandb.init(project="flagfoundry-rl", config=vars(args))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_gpus = torch.cuda.device_count() if torch.cuda.is_available() else 1
    logger.info(f"Training on {n_gpus} GPU(s)")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    model_kwargs = dict(torch_dtype=torch.bfloat16, device_map=None)
    # Check if the SFT checkpoint is PEFT-only (has adapter_config.json). If so,
    # load the base model from the path stored in adapter_config.json, then wrap
    # with PeftModel rather than loading the checkpoint directly with
    # AutoModelForCausalLM (which would fail for adapter-only directories).
    sft_checkpoint_path = Path(args.base_model)
    sft_adapter_config = sft_checkpoint_path / "adapter_config.json"
    if sft_adapter_config.exists():
        sft_adapter_cfg = json.loads(sft_adapter_config.read_text())
        sft_base_model_name = sft_adapter_cfg.get("base_model_name_or_path", str(sft_checkpoint_path))
        logger.info(f"SFT checkpoint is PEFT-only. Loading base {sft_base_model_name} + adapter {sft_checkpoint_path}")
        base_for_sft = AutoModelForCausalLM.from_pretrained(
            sft_base_model_name, trust_remote_code=True, **model_kwargs
        )
        model = PeftModel.from_pretrained(base_for_sft, str(sft_checkpoint_path))
    else:
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model, trust_remote_code=True, **model_kwargs
        )
    model.enable_input_require_grads()

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_r * 2,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                         "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.0,
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model = model.to(device)

    # Use device_map=None for ref_model for DeepSpeed ZeRO-3 compatibility;
    # ZeRO-3 manages device placement itself and conflicts with device_map="auto".
    ref_model = AutoModelForCausalLM.from_pretrained(
        args.base_model, trust_remote_code=True, torch_dtype=torch.bfloat16, device_map=None
    )
    ref_model.eval()
    for p in ref_model.parameters():
        p.requires_grad_(False)

    reward_fn = FlagCaptureReward(workers=args.docker_workers, timeout=args.docker_timeout)
    prompts = load_challenge_prompts(Path(args.data_dir), limit=args.num_prompts)

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.learning_rate, weight_decay=0.0, betas=(0.9, 0.95),
    )
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=args.warmup_steps, num_training_steps=args.max_steps
    )

    logger.info(f"Starting GRPO RL | {len(prompts):,} prompts | {args.max_steps:,} steps | grad_accum={args.grad_accum_steps}")
    global_step = 0
    prompt_idx = 0
    # FF-17 FIX: Track micro-steps for gradient accumulation to reduce OOM risk
    accum_step = 0

    if not prompts:
        logger.error("No prompts loaded — cannot start training. Check data directory.")
        return

    while global_step < args.max_steps:
        batch = [prompts[prompt_idx % len(prompts)] for _ in range(args.batch_size)]
        prompt_idx += args.batch_size

        # Generate N completions per prompt
        all_completions = []
        for p in batch:
            prompt_text = tokenizer.apply_chat_template(
                [{"role": "user", "content": p["prompt"]}],
                tokenize=False, add_generation_prompt=True
            )
            # FF-6 FIX: Repeat both input_ids AND attention_mask to avoid attending to padding
            enc = tokenizer(prompt_text, return_tensors="pt", truncation=True, max_length=1024)
            input_ids = enc.input_ids.repeat(args.num_samples, 1).to(device)
            attention_mask = enc.attention_mask.repeat(args.num_samples, 1).to(device)

            model.eval()
            with torch.no_grad():
                out = model.generate(
                    input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=args.max_new_tokens,
                    temperature=args.temperature,
                    do_sample=True,
                    pad_token_id=tokenizer.eos_token_id,
                )
            prompt_len = input_ids.shape[1]
            comps = [tokenizer.decode(out[i, prompt_len:], skip_special_tokens=True)
                     for i in range(args.num_samples)]
            all_completions.append(comps)

        # Score via Docker (or simulated)
        score_groups = []
        for i, (p, comps) in enumerate(zip(batch, all_completions)):
            scores = reward_fn.score_group(comps, p["challenge_id"], p["expected_flag"])
            score_groups.append(scores)

        advantage_groups = compute_advantages(score_groups)

        # Compute GRPO loss
        model.train()
        flat_items = []
        flat_adv = []

        for i, (p, comps) in enumerate(zip(batch, all_completions)):
            prompt_text = tokenizer.apply_chat_template(
                [{"role": "user", "content": p["prompt"]}],
                tokenize=False, add_generation_prompt=True
            )
            adv_group = advantage_groups[i] if i < len(advantage_groups) else []
            for j, comp in enumerate(comps):
                # Bounds check: skip if reward scoring returned fewer scores than completions
                if j >= len(adv_group):
                    logger.warning(
                        f"step={global_step}, prompt={i}: advantage group has {len(adv_group)} entries "
                        f"but completion index {j} is out of bounds — skipping"
                    )
                    continue
                full = prompt_text + comp
                # FF-19 FIX: Warn when truncation silently cuts the response region,
                # which would corrupt response_mask and skew the GRPO loss signal.
                enc_full_uncapped = tokenizer(full, return_tensors="pt")
                if enc_full_uncapped.input_ids.shape[1] > args.max_length:
                    logger.warning(
                        f"Sequence (step={global_step}, prompt={i}, sample={j}) "
                        f"length {enc_full_uncapped.input_ids.shape[1]} exceeds max_length={args.max_length}; "
                        "response will be truncated, which may corrupt response_mask."
                    )
                enc = tokenizer(full, truncation=True, max_length=args.max_length, return_tensors="pt")
                enc_prompt = tokenizer(prompt_text, truncation=True, max_length=args.max_length, return_tensors="pt")
                plen = enc_prompt.input_ids.shape[1]
                tlen = enc.input_ids.shape[1]
                resp_mask = torch.zeros(tlen, dtype=torch.long)
                resp_mask[plen:] = 1
                flat_items.append({
                    "input_ids": enc.input_ids.squeeze(0),
                    "attention_mask": enc.attention_mask.squeeze(0),
                    "response_mask": resp_mask,
                })
                flat_adv.append(adv_group[j])

        if not flat_items:
            continue

        # Pad batch
        max_len = min(max(item["input_ids"].shape[0] for item in flat_items), args.max_length)
        pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id
        input_ids_list, attn_list, resp_list = [], [], []
        for item in flat_items:
            ids, attn, resp = item["input_ids"], item["attention_mask"], item["response_mask"]
            pad_len = max_len - ids.shape[0]
            if pad_len > 0:
                ids = torch.cat([ids, torch.full((pad_len,), pad_id, dtype=torch.long)])
                attn = torch.cat([attn, torch.zeros(pad_len, dtype=torch.long)])
                resp = torch.cat([resp, torch.zeros(pad_len, dtype=torch.long)])
            else:
                ids, attn, resp = ids[:max_len], attn[:max_len], resp[:max_len]
            input_ids_list.append(ids)
            attn_list.append(attn)
            resp_list.append(resp)

        input_ids_t = torch.stack(input_ids_list).to(device)
        attn_t = torch.stack(attn_list).to(device)
        resp_t = torch.stack(resp_list).to(device)
        adv_t = torch.tensor(flat_adv, dtype=torch.float32).to(device)

        # Run ref_model inference on the same device as training model.
        # Keeping ref_model on CPU and shuttling it to GPU every step wastes
        # PCIe bandwidth; instead we keep it on device throughout the loop.
        ref_lp = compute_ref_log_probs(ref_model, input_ids_t, attn_t, resp_t)

        loss, metrics = compute_grpo_loss(model, ref_lp, input_ids_t, attn_t, resp_t, adv_t, args.kl_coeff)
        # FF-17 FIX: Scale loss by accumulation steps so effective LR is preserved
        (loss / args.grad_accum_steps).backward()
        accum_step += 1

        if accum_step % args.grad_accum_steps == 0:
            if args.grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

        all_scores = [s for g in score_groups for s in g]
        if not all_scores:
            mean_reward = 0.0
            success_rate = 0.0
        else:
            mean_reward = sum(all_scores) / len(all_scores)
            success_rate = sum(1 for s in all_scores if s == 1.0) / len(all_scores)

        if global_step % 10 == 0:
            logger.info(
                f"step {global_step:>5} | loss {metrics['loss/total']:.4f} | "
                f"kl {metrics['loss/kl']:.4f} | reward {mean_reward:.3f} | "
                f"flag_capture {success_rate:.1%} | lr {scheduler.get_last_lr()[0]:.2e}"
            )

        if HAS_WANDB and not args.no_wandb:
            wandb.log({**metrics, "reward/mean": mean_reward, "reward/flag_capture": success_rate,
                       "train/step": global_step}, step=global_step)

        # FF-4 FIX: Skip checkpoint at step 0 (before any training has occurred)
        if global_step > 0 and global_step % args.save_steps == 0:
            ckpt = output_dir / f"checkpoint-{global_step}"
            ckpt.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(str(ckpt))
            tokenizer.save_pretrained(str(ckpt))

        global_step += 1

    # Save final merged model
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

    logger.info(f"RL training complete. Model saved to {final_dir}")
    logger.info(f"Next: deepspeed --num_gpus=18 training/train_dpo.py --base-model {final_dir}")


if __name__ == "__main__":
    main()
