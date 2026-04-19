# Script DNA Extraction & Voice Calibration

A system for making videomaker's script writer produce scripts **indistinguishable in voice** from a specific creator or channel. Based on a 3-phase prompt approach.

**When to use:** you have 3+ reference scripts from a channel/creator whose voice you want to replicate (or your own prior scripts you want to stay consistent with).

**When not to use:** you just want a generic good explainer script. The default system prompt already produces strong Primer/Kurzgesagt-style voice.

---

## How to use with videomaker

### Step 1: Extract the Style Codex (one-time, per-voice)

Run this in any Claude chat (not through videomaker — this is a pre-processing step):

> Paste the **Phase 1 prompt** below.
> Then paste **3–5 full reference scripts** from the voice you want to replicate.
> Claude produces a detailed breakdown.

### Step 2: Save the Style Codex

Claude will output a Style Codex in Phase 2 — a compact set of rules. Save it to a file like:

```
~/.videomaker/voices/primer.md
~/.videomaker/voices/my-voice.md
~/.videomaker/voices/darkroom-deconstruction.md
```

### Step 3: Point videomaker at it

Two options:

**Option A — append to system prompt (recommended):**
```bash
videomaker run --topic "..." --voice ~/.videomaker/voices/primer.md
```
The `--voice` flag reads the codex file and prepends it to the script writer's system prompt.

*Note: `--voice` flag is implemented in v0.2. For v0.1, manually edit `prompts/script_system.md` to append your codex under a "## Voice Codex" section.*

**Option B — pre-process via skill:**
Build a wrapper skill that calls `videomaker run` with a curated system-prompt addendum.

---

## Phase 1 — Deep Analysis Prompt

```
You are a scriptwriting analyst and ghostwriter. Your job is to deeply study the reference
scripts I provide, extract every element of the writer's unique style, and then use that
extracted "writing DNA" to produce new scripts that are indistinguishable from the originals
in voice, tone, and craft.

PHASE 1 — DEEP ANALYSIS (Do this first, before writing anything)

Study every script I provide and produce a detailed breakdown covering:

Voice & Tone
- Overall attitude toward the subject (reverent, irreverent, darkly humorous, deadpan, hype,
  conversational, authoritative, etc.)
- Emotional register — how does the writer modulate between serious, playful, intense, reflective?
- Relationship with the viewer — are they a friend, a professor, a narrator in the dark,
  a fellow enthusiast?
- Level of formality vs. casualness. Exact ratio.

Sentence-Level Craft
- Average sentence length and how it varies (short punchy vs. long flowing)
- Use of fragments, one-liners, rhetorical questions
- Signature punctuation habits (em dashes, ellipses, colons, etc.)
- How transitions between ideas work — abrupt cuts, smooth bridges, callbacks?

Paragraph/Section Structure
- How does each section typically open and close?
- How long are paragraphs on average?
- Pattern of build-up → payoff within sections

Hooks & Retention Mechanics
- How does the script open? (First 30 seconds structure)
- What open loops, cliffhangers, or tension devices are used?
- How often and where are re-hooks placed throughout?
- How does the writer prevent the viewer from clicking away?

Vocabulary & Language Fingerprint
- Recurring words, phrases, or verbal tics
- Level of jargon vs. simplification
- Use of analogies, metaphors, comparisons — how frequent and what style?
- Slang, colloquialisms, or cultural references

Narrative Architecture
- What is the macro structure? (mystery → investigation → reveal, chronological,
  thematic clusters, escalating lists)
- How does the writer handle exposition — front-loaded, woven in, drip-fed?
- Pacing: where does it speed up, slow down, and why?
- How does the script end? What's the closing pattern?

Emotional Engineering
- How does the writer create tension, curiosity, shock, awe, empathy?
- What emotional arc does the viewer go through start to finish?
- Use of contrast (dark/light, big/small, serious/funny)
```

## Phase 2 — Style Codex

```
After analyzing, compile everything into a concise "Style Codex" — a reference document
I can reuse. Format it as a set of clear rules and patterns, e.g.:

- "Sentences average 8-14 words. Every 3rd or 4th sentence is a fragment."
- "Each section opens with a bold claim or shocking fact, never a question."
- "The writer uses 'And here's the thing...' as a signature transition."
- "Analogies reference everyday objects, never academic comparisons."
```

## Phase 3 — Script Generation

```
When I give you a topic for a new script, apply the Style Codex strictly. The output should:

- Be indistinguishable in voice from the reference scripts
- Follow the same structural architecture
- Use the same hook patterns, retention devices, and pacing rhythm
- Match vocabulary level, sentence patterns, and emotional modulation
- Feel like it was written by the same person on the same channel

Before delivering the final script, do a self-audit: compare your draft against the Style
Codex point by point and fix any deviations.
```

---

## Tips

- **3 scripts minimum, 5 ideal.** Fewer than 3 and the extracted "DNA" is too generic; more than 5 is diminishing returns.
- **Use full scripts, not excerpts.** Openings and closings are where voice is strongest — partial scripts miss those.
- **Re-run when the voice drifts.** If your channel evolves, re-extract every 20-30 videos.
- **Store codexes in git.** They're valuable artifacts. Version them.

Source: provided by user as `YOUTUBE_SCRIPT_DNA_EXTRACTION___REPLICATION_SYSTEM.pdf`.
