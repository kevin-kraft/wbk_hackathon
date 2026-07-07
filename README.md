# wbk_hackathon — VLM-Guided Robotic Disassembly

WBK Hackathon Group · 2026-07-07

## What we're building

A robot arm that **disassembles a part step by step**, guided by a vision-language /
computer-vision model in the loop. The vision model drives three jobs:

1. **Identify the next part to disassemble** — locate and point to the next component
   the arm should remove, in the correct sequence.
2. **Rectify grabbing mistakes** — verify the grip after the arm attempts a pick; if the
   grasp failed or grabbed the wrong component, detect it and retry / correct.
3. **Quality inspection (OK / not-OK)** — classify each part as OK or **damaged**
   (not-OK) during the process.

## How it works (pipeline)

```
 camera ──► perception (VLM / CV)
              │  • next-part detection & pointing
              │  • grasp verification (before / after diff)
              │  • damage classification (OK / not-OK)
              ▼
        state machine ──► robot arm control ──► pick & remove ──► loop
```

The perception layer proposes the next action, a critic verifies each step
(right part? gripped correctly? actually removed?) before the state machine advances,
and every removed part is inspected and tagged OK / not-OK.

## Candidate model stack

- **Pointing / grounding:** point-native models (e.g. Qwen2.5-VL, Molmo) preferred over
  prompting a generic VLM for pixel coordinates.
- **Reasoning / critic:** a capable VLM verifies steps and adjudicates OK vs. damaged.
- **Grasp check:** per-part reference images + before/after frame diffing rather than a
  single-frame judgment (grip success is subjective from one frame).

## Status

Hackathon build — scaffolding in progress. See issues / project board for tasks.
