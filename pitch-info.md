# disassemblr — The Idea

*WBK Hackathon Group · started 2026-07-07 · working brand name: **disassemblr***

## In one sentence

**disassemblr** is a robot arm that **takes a product apart, one part at a time,
guided by vision and language models in the loop** — it knows what to remove
next, whether it grabbed the right thing, and whether each removed part is good
or scrap.

## The problem

Disassembly is the neglected half of manufacturing. Assembly lines are
automated to death; taking things *back* apart — for remanufacturing, repair, or
recycling — is still mostly manual. It's hard to automate because every incoming
unit is a little different: parts are worn, positioned unpredictably, sometimes
damaged, and the "correct" teardown order depends on which product is on the
bench. A fixed, pre-programmed robot routine breaks the moment reality deviates
from the CAD model it was taught on.

## Why now — the story

disassemblr sits at the intersection of three shifts that are all happening at
once. The pitch is a story in three acts.

### Act 1 — Recycling is no longer optional, and it starts with disassembly

The world is moving from a linear "make → use → throw away" economy to a
**circular** one, where end-of-life products are torn back down and their parts
and materials recovered. This isn't a fringe idea — it's exactly where the
**wbk** is placing its bets: the institute's "Sustainable Production" focus and
its **Circular Factory** vision are about reprocessing used products in an
automated way so they leave the factory *as new products again*, with wbk teams
already working on **automated disassembly and condition-based remanufacturing
of lithium-ion battery modules**.

But here's the catch: **the entire circular economy is bottlenecked at
disassembly.** Every recovered part, every clean material stream, every
remanufactured module starts with someone taking a product apart — and today
that's overwhelmingly manual, slow, and expensive. Two capabilities unlock the
whole loop, and they're exactly what disassemblr provides:

- **Automated disassembly** — the robot takes the product apart itself.
- **Automated fault detection** — it inspects each recovered part and decides
  *good vs. scrap*, so only sound parts re-enter the loop.

The market is already pricing this in: European **remanufacturing is ~€31B today,
projected toward €100B by 2030** (~500,000 jobs), pulled by the EU Circular
Economy Action Plan, Extended Producer Responsibility, and battery/e-waste
rules. **Automating teardown is the enabling technology for all of it.**

### Act 2 — An aging workforce, freed up for work that matters

Germany is running out of workers, and fast:

- The working-age population (20–64) shrinks by **~3.9M to 45.9M by 2030**;
  by 2030 there are roughly **50 retirees per 100 workers**, up from 32/100 in
  2005.
- A projected **~1.3M skilled-worker shortfall by 2030**, with **over half of
  German companies** already reporting the skills gap hurting output.

The naïve reading is "robots replace people." The real story is the opposite:
with **fewer workers**, we cannot afford to spend a single one of them on
mind-numbing, repetitive labor. We want to **upskill the remaining workforce
onto higher-value work** — process design, quality judgment, supervising fleets
of cells — and let machines absorb the menial, ergonomically punishing tasks
that disassembly is full of.

> **Personal note (Daimler production line).** I've done this work. On the
> production floor at Daimler, the task was mind-numbing — the same motion, the
> same part, hour after hour. It's the kind of work that wastes a capable person
> and that nobody should have to do when a machine can. That's not a job we're
> taking away; it's a job we're **giving back** as something better.

Disassembly is *precisely* the category of work that's hard to staff, hard on
the body, and low on judgment-per-hour — the ideal thing to automate first while
the humans move up.

### Act 3 — Staying relevant in frontier tech, not outsourcing it to China

Meanwhile China is taking what the Wall Street Journal called *"the last
stronghold of German industry"* — machinery:

- Chinese competitors already command **~⅓ of global machinery production**
  (VDMA), with warnings of **40–50%** ahead.
- Germany's capital-goods trade balance with China flipped from a **€750M
  surplus to a €500M deficit** (mid-2024 → Aug 2025); machine-tool exports to
  China fell **~⅓** year-on-year in Q1.
- Germany is shedding **>10,000 industrial jobs every month** (EY); **~53% of
  German machinery firms** believe technology leadership has already moved, or
  will move, abroad.

The wrong answer is to compete on cheap production, or to just hand the whole
value chain to China. Here's **why we should keep this capability at home** —
and why circular, AI-driven disassembly is the *right* place to plant that flag:

1. **You can't innovate in what you no longer make.** Manufacturing know-how is
   tacit — it lives in the people and processes on the floor, not in a spec
   sheet. Offshore the making, and within a product generation you lose the
   ability to *design* it too. Robotic disassembly + AI perception is a frontier
   where Germany can still build that know-how first, at home.
2. **Circular value chains are inherently local.** Unlike new production, the
   feedstock for the circular economy — end-of-life products — is *already here*,
   where the consumers are. You can't cheaply ship worn-out gearboxes to Asia and
   back. This is a high-value industry that **physically anchors in Europe** —
   if we build the technology to serve it.
3. **Dependency is leverage against you.** China dominates the processing of the
   critical materials behind semiconductors, EVs, and defense; export controls
   can be — and have been — used as economic coercion. A domestic circular loop
   that *recovers* those materials is direct **strategic autonomy**, reducing the
   dependency instead of deepening it.
4. **This is the frontier, not the past.** Robotics + VLMs + AI-driven quality
   inspection is an emerging technology layer. Ceding it means ceding the
   high-margin future, not just today's machine sales. disassemblr is a bet that
   Germany leads *here*, on the next thing.

**The one-liner:** *Recycling is the future and the wbk is building it;
automated disassembly and fault detection are the missing piece. An aging
Germany can't waste people on mind-numbing work — so automate it and upskill
them. And this frontier is one we should own, not outsource. disassemblr is that
piece.*

*(Sources: [KIT wbk — Sustainable Production](https://www.wbk.kit.edu/english/Sustainable-Production.php)
& [Circular Factory press release](https://www.kit.edu/kit/english/pi_2023_pi_vision-of-the-perpetual-innovative-product-circular-factory-to-revolutionize-production.php);
OECD Germany 2025; Statista; WSJ (Cheng, 2026); VDMA; EY; European remanufacturing
market estimates; EU Circular Economy Action Plan; European Parliament & ECFR on
strategic autonomy / China dependency.)*

## The bet

Instead of scripting the robot for one product, we let **perception and
reasoning models close the loop at runtime**. The robot doesn't follow a fixed
trajectory — it follows a *plan that is generated and grounded live*:

1. **What comes off next?** An operator picks the product in an ERP system; an
   LLM reads that product's part list and generates the ordered teardown plan
   ("first the cover, then the gearbox, then the bearing…"). Vision then locates
   the specific part for the current step in the actual scene.
2. **Did I grab the right thing, the right way?** After each pick attempt, the
   system verifies the grip. A failed grasp or a wrong component is detected and
   the step is retried or corrected — the robot recovers instead of blindly
   continuing.
3. **Is this part OK or scrap?** Once a part is removed, a vision-language model
   judges it **OK / not-OK**, and it's sorted into a working bin or a reject
   bin. Ambiguity fails closed — anything uncertain goes to reject.

This turns a brittle scripted arm into an **adaptive, plan-driven cell**: change
the product, and the plan regenerates; move the parts around, and perception
re-grounds; damage a part, and inspection catches it.

## Why "VLM-guided" — and where the guardrails are

The interesting risk is obvious: you don't want a language model inventing robot
coordinates and swinging a real arm around. So the LLMs here are deliberately
**boxed in as selectors, not generators**:

- **Plan generation** may only *order and describe* the ERP's known part list.
  It cannot invent parts that aren't on the product.
- **Action synthesis** picks from a small, fixed action vocabulary and refers to
  poses *by name* — poses that the perception + 6DoF-pose pipeline computed. It
  never emits raw numbers. A deterministic validator rejects anything outside
  the vocabulary before it reaches the robot, and falls back to a scripted grasp
  sequence.

So the models supply **judgment and sequencing**; the geometry, the safety
checks, and the final motion stay deterministic. Intelligence at the edges, hard
rails in the middle.

## How it hangs together

A pipeline of small, swappable services — each stage does one job and hands off
a simple contract to the next:

```
 ERP product pick ─► LLM plan ─► [ per step ] locate part ─► 6DoF pose ─► action synthesis ─► grasp / remove
    (operator)       (ordered      (perception grounds        (where &      (constrained,        │
                      steps)         the plan's part)           how to grab)  validated)          ▼
                                                                                         grip check ──► retry?
                                                                                              │
                                                                                              ▼
                                                                        damage inspection ──► OK bin / reject bin
                                                                                              │
                                                                                              └──► next part (loop)
```

Because every stage talks over a simple interface, the whole loop can run today
against **mocks** — demoing end to end while the real vision models, the robot's
motion endpoint, and the grip sensor are still being tuned. Real components swap
in behind the same seams without touching the loop. And the same run can drive
the **real arm, a simulated digital twin, or both at once**, so the system is
demonstrable even without hardware in hand.

## What makes it more than a demo

- **Product-agnostic by design.** The teardown sequence comes from data (ERP) +
  reasoning, not from a hand-coded routine per product.
- **Self-correcting.** It checks its own grip and retries, rather than assuming
  every pick succeeds.
- **Quality-aware.** It doesn't just remove parts — it triages them, fail-closed.
- **Safe by construction.** The models never touch coordinates; a validator and
  scripted fallback stand between any LLM output and the motors.

---

*For the concrete architecture, service map, and ports, see
[`README.md`](README.md) and [`docs/architecture.md`](docs/architecture.md). For
the design decisions behind each choice, see the ADRs in
[`.agent/Decisions/`](.agent/Decisions/).*
