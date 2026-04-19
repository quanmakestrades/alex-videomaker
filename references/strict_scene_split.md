# Strict Scene Split (80-line batch mode)

An alternative to videomaker's default one-call script+scenes approach. Use when you need **guaranteed line-for-line fidelity** between the narration and the scene split — no skipping, no merging, no paraphrasing.

**Trade-off:** 2–3 LLM calls instead of 1. ~2–3x the tokens. Worth it when you care about every sentence being its own beat.

**When to use:**
- You already have a finished script and just want to generate images for it (skip the writer entirely).
- You're producing content where missing a line would matter (e.g., video matches existing narration from a voice actor).
- You've had the default one-call mode skip/merge scenes in past runs.

**When NOT to use:** default case. The one-call mode is coherent, cheaper, and fine for 95% of videos.

---

## The approach (adapted from provided workflow)

### Step 1 — Split the script into visual scenes (separate chat)

Use this prompt in a **fresh chat** (context buildup causes errors):

```
Break the following script into individually numbered visual scenes. Use these rules:

1. Every sentence that ends with a full stop gets its own numbered line.
2. If a single sentence contains multiple distinct visual moments separated by commas,
   semicolons, or conjunctions (and, but, while, as) — split them into separate numbered lines.
3. Ask yourself: would an illustrator need two different drawings for this sentence?
   If yes, split it.
4. Do NOT rewrite, paraphrase, or change any wording. Just split and number.
5. At the end, tell me the exact total count of lines.

Output format: one line per scene, numbered. Plain text.

SCRIPT START:

[paste your full script]
```

Save the numbered list somewhere durable (txt file, Google Doc). This is your **master reference**.

### Step 2 — Calculate batches

Divide total lines by 80. Each batch ≤ 80 lines. Example for 210 lines:
- Batch 1: lines 1–80
- Batch 2: lines 81–160
- Batch 3: lines 161–210

**Never exceed 80 lines per batch.** Larger batches → Claude starts skipping.

### Step 3 — Generate prompts batch by batch (new chat)

```
You are an AI image prompt generator. I will give you a numbered script that has already
been split into individual visual scenes. Your ONLY job is to generate one image prompt
per line.

STRICT RULES:
1. Each numbered line below is ONE visual scene. Generate EXACTLY one image prompt per line.
2. Do NOT split, merge, combine, or skip any lines. That work is already done.
3. Do NOT paraphrase or rewrite the original line.
4. Prompts must be short and punchy. Just describe what is visually happening in plain
   language. No emotional descriptors, no flowery language, no mood direction.
5. [Insert topic-specific visual hints here — e.g., "These scripts are about space topics.
   When the script describes space environments, planets, spacecraft, the prompts should
   depict those."]
6. In every prompt, briefly describe the environment/location of the scene. Never leave
   a prompt without a sense of where it is taking place.
7. Every single prompt must end with EXACTLY this style suffix (do not modify):

   "[your style suffix — e.g., the first paragraph of prompts/image_style.md]"

8. Each prompt is a single unbroken line. Visual description + style suffix on same line.

OUTPUT FORMAT — two documents:

Document 1 — PROMPTS ONLY:
  No numbers. One blank line between each prompt.

Document 2 — NUMBERED WITH SCRIPT LINES:
  [Line number]. [Original script line]
  Prompt: [Your image prompt]
  (blank line)

Both documents must have IDENTICAL prompt counts and IDENTICAL prompt text.

This batch contains lines [X] to [Y]. That is exactly [Z] lines. Your output MUST have
exactly [Z] prompts in each document. Count and confirm the total at the end.

SCRIPT START:

[paste lines 1–80 here]
```

For subsequent batches in the **same chat**:

```
Continue. Process lines [81] to [160]. That is exactly [80] lines. Your output MUST have
exactly [80] prompts in each document. Count and confirm at the end.

[paste lines 81–160 here]
```

### Step 4 — Verify each batch

- **Prompt count matches** the line count.
- **No lines skipped** — Document 2 should have every original line above its prompt.
- **Suffix intact** on every prompt (spot-check 5–10).
- **No paraphrasing** — original script lines in Document 2 match master reference exactly.

If a batch is broken, **regenerate the whole batch from scratch** — fixing is less reliable than redoing.

### Step 5 — Combine

Copy-paste all batches into one document, or ask Claude in-chat:

```
Combine all batches into one final Document 1 and one final Document 2. The total must
be exactly [TOTAL] prompts. Count and confirm.
```

---

## How to use with videomaker

**Not yet wired into the CLI.** To use the strict approach today:

1. Generate script separately (or use `videomaker run --dry-run` to get `script.txt`).
2. Run Steps 1–5 above manually via Claude chat.
3. Save Document 1 (prompts only, one per line) as `prompts.txt` and your narration split (Document 1 from Step 1) as `narrations.txt`.
4. Stub a small Python script that reads both files and writes them into `manifest.json` for an existing run:

```python
from pathlib import Path
from videomaker.scene_manager import Manifest, Scene

run_dir = Path("~/.videomaker/runs/20260419-110142").expanduser()
m = Manifest.load_or_new(run_dir)
narrations = Path("narrations.txt").read_text().strip().split("\n")
prompts    = Path("prompts.txt").read_text().strip().split("\n\n")
assert len(narrations) == len(prompts)
m.scenes = [Scene(index=i+1, narration=n, image_prompt=p,
                  styled_prompt=p,
                  audio_path=str(run_dir/"audio"/f"scene_{i+1:03d}.mp3"),
                  image_path=str(run_dir/"images"/f"scene_{i+1:03d}.png"))
            for i, (n, p) in enumerate(zip(narrations, prompts))]
m.save()
print(f"Wrote {len(m.scenes)} scenes.")
```

Then resume the run — TTS + image gen + stitch will proceed from the manifest:

```bash
videomaker run --topic "..." --resume 20260419-110142
```

**v0.2 goal:** make this a first-class `--strict-split` flag on `videomaker run` that automates the above.

---

Source: provided by user as `Script_To_Image_-_Space_docx.pdf`.
