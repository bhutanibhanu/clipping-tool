# Round 4 / Stream 6 — Red-Team: Why Building on OSS Image/Video Gen Could Be a BAD Bet in 2026

*Role: skeptical counterweight. The other streams will sell you the upside; my job is to itemize how this kills you. Severity tags: [Verified] = documented fact; [High]/[Med]/[Low] = my confidence the risk bites a solo builder; [Speculative] = plausible but unproven.*

---

## TL;DR — Top risks, ranked by how likely they are to kill a solo builder's product

1. **[High] Commoditization speed.** The capability you ship a feature around is a free checkbox in the next open-weight drop. Early June 2026 alone saw 25+ open-weight models across image/video/audio/3D in a single week (Ideogram 4.0 open-weights, FLUX.2, HunyuanImage 3.0). Per-image API cost fell to **$0.005–0.02** (GPT Image Mini, Imagen 4 Fast); the floor is **$0.002**. Whatever moat "we generate X" gives you has a half-life measured in weeks.
2. **[High] Incumbents absorb your feature for free.** Adobe Firefly is now a **30+ model aggregator** (Veo, Runway, FLUX, Nano Banana, Kling) under one CC subscription, plus custom-model training and IP indemnification. Google's **Nano Banana** hit 13M users in 4 days and 5B images by Oct 2025, then went free-tier. "Feature, not a company" is the literal failure mode here.
3. **[High] Race-to-the-bottom margins + the ~80–95% wrapper failure base rate.** AI-first early-stage gross margins run **~25%** vs 80–90% for normal SaaS; "a thin layer with no proprietary data compresses to zero margin within 12 months." Even **OpenAI killed Sora** (Apr 2026) because video gen burned **~$1M/day** against $2.1M lifetime revenue. If OpenAI can't make the unit economics work, your wrapper won't.
4. **[Med-High] OSS license traps.** FLUX.1/.2 **[dev]** is **non-commercial** — and v1.1+ extended the restriction to *outputs* of revenue-generating use. SD3's launch license was so hostile that CivitAI **banned all SD3 content**. "Open weights" ≠ "you can build a business on it." Misread one clause and your whole product is illegal.
5. **[Med] Copyright / training-data liability flows downstream to you.** Andersen v. Stability (trial **Sept 8, 2026**) and Disney/Universal/Warner v. Midjourney put *induced/secondary* infringement on the table. Open models ship **zero indemnification**; Adobe sells indemnity precisely because it's a real liability. You inherit the lawsuit risk your model vendor created.
6. **[Med] Platform/distribution dependence + AI-labeling compliance cost.** EU AI Act Art. 50 machine-readable labeling is mandatory **Aug 2, 2026** (fines up to €7.5M / 1.5% turnover); C2PA certs cost **~$289/yr** with no free option. App stores purge AI-gen categories reactively (Apple pulled 28 "nudify" apps Jan 2026). Your funnel sits on land you don't own.
7. **[Med-High] Capability cliffs.** The demo always works; production consistency doesn't. Character/temporal consistency is *still* the #1 unsolved problem in mid-2026 — most tools break past **30–60s**. The gap between "viral demo" and "reliable for paying customers" is where the support/QA burden — and the refunds — live.

**One-line thesis:** the *generation* layer is a deflating commodity owned by trillion-dollar incumbents and well-capitalized labs. A solo builder who bets on *being able to generate* loses. The only defensible bets are *adjacent* to generation — workflow, consistency, compliance, vertical integration — where the model is an interchangeable input, not the product.

---

## Risk 1 — Commoditization speed [High]

**The claim:** your edge today is erased by the next open-weight release, and entire "AI-X" categories get wiped by one model update.

**2026 evidence:**
- **Release cadence is brutal.** Early June 2026 delivered **25+ open-weight models in one week** across LLM/image/audio/video/3D ([Mervin Praison](https://mer.vin/2026/06/open-weight-ai-release-week-25-models-across-llms-image-audio-video-and-3d-june-2026/)). Ideogram — every prior model API-only — **open-weighted 4.0 on June 3, 2026** ([Startup Fortune](https://startupfortune.com/ideogram-40-turns-open-weights-into-a-startup-weapon/)). FLUX.2 (32B) landed Nov 2025; HunyuanImage 3.0 from Tencent. The image-gen frontier now turns over roughly **quarter to quarter**.
- **Price collapse.** Image-gen API pricing spans a 5x range from **$0.054 down to $0.01/image**, with **Z-Image Turbo at $0.01** and a floor near **$0.002/image**; GPT Image Mini ~$0.005, Imagen 4 Fast $0.02 ([buildmvpfast](https://www.buildmvpfast.com/api-costs/ai-image), [Atlas Cloud](https://www.atlascloud.ai/blog/guides/cheapest-ai-image-generation-api-2026)). When the raw capability costs half a cent, "we do generation" is not a value proposition.
- **Feature-killed precedent (text side, same physics):** OpenAI's product cadence (GPT Store, Operator, Canvas, AgentKit) "directly cannibalized at least 200 funded GPT-wrapper startups in 2024 alone" ([machinebrief](https://www.machinebrief.com/news/death-of-ai-wrapper-startups-wont-survive-2026)). **Clara** (AI email scheduling) shut down after raising millions because Google Calendar shipped the same thing free ([same](https://www.machinebrief.com/news/death-of-ai-wrapper-startups-wont-survive-2026)). The image/video layer is on an identical trajectory, one release behind.
- Of **258 tracked AI image/video tools, ~20 are already dead or acquired — and 18 of those 20 are on the image side**, the harder-hit half ([tooldirectory.ai](https://tooldirectory.ai/blog/state-of-ai-image-and-video-generation-2026)).

**Mitigation:**
- Treat the model as a **swappable commodity input** behind an interface; never let one model's quirks define your product surface. (The client's own `Detector`/`Transcriber` protocol pattern is exactly right — apply it to gen models too.)
- Move value **up the stack**: data you own, workflow you own, a distribution wedge, a closed feedback loop. Capability is rented; these compound.
- Pick problems where the *next model release helps you* (you ride the rising tide) rather than *obsoletes you* (you were the missing capability).

**Archetype exposure:** **MOST exposed** = vertical/consumer app whose pitch is "do generation type X" (your edge is literally the model). **LEAST exposed** = infra/tooling and consistency layers that get *more valuable* as models proliferate (more models to orchestrate, more drift to correct).

---

## Risk 2 — Incumbents absorbing features for free [High]

**The claim:** Adobe, Canva, Google, Meta, Microsoft and the labs ship your feature inside products that already own the customer. "Feature, not a company."

**2026 evidence:**
- **Adobe Firefly is now an aggregation platform, not a model.** It hosts **30+ third-party models** — Google Veo 3.1 + Nano Banana 2, Runway Gen-4.5, Kling 2.5, FLUX, Luma, Pika, Ideogram, Topaz, ElevenLabs — *under one Creative Cloud subscription*, plus **custom model training (10–30 ref images)** and a **Firefly AI Assistant** that drives Photoshop/Premiere/Illustrator from one prompt ([Adobe blog](https://blog.adobe.com/en/publish/2026/03/19/adobe-firefly-expands-video-image-creation-with-new-ai-capabilities-custom-models), [VentureBeat](https://venturebeat.com/technology/adobes-new-firefly-ai-assistant-wants-to-run-photoshop-premiere-illustrator-and-more-from-one-prompt)). If your product is "pick the best model for the job + brand consistency," Adobe already shipped it to its installed base.
- **Google's distribution is a flamethrower.** Nano Banana: **13M users in 4 days, 5B images by mid-Oct 2025**, then **free tier** (3 img/day free, cross-subsidized by Gemini Pro) ([CNBC](https://www.cnbc.com/2025/11/20/google-nano-banana-pro-gemini-3.html), [evrimagaci](https://evrimagaci.org/gpt/google-launches-nano-banana-2-ai-image-tool-worldwide-531726)). A free Google feature with that reach prices a paid indie tool out of the consumer market overnight. Google also shipped Pomelli (product photography) and Stitch (AI design w/ infinite canvas).
- **Canva is acquiring the surrounding workflow:** Cavalry (animation) + MangoAI (Feb 2026), Simtheory + Ortto (Apr 2026) ([CNBC Disruptor 50](https://www.cnbc.com/2026/05/19/canva-cnbc-disruptor-50-ranking.html)). The "AI design workflow" white space is being bought up.
- **A Google exec literally warned that AI-wrapper startups are in trouble** ([PYMNTS](https://www.pymnts.com/artificial-intelligence-2/2026/google-exec-warns-ai-wrapper-startups-could-be-in-trouble/)). When the platform owner says the quiet part out loud, believe them.

**Mitigation:**
- Build where incumbents **structurally won't go**: a niche too small to matter to a $200B company, a regulated/compliance corner they avoid, an opinionated workflow that conflicts with their general-purpose surface, or on-prem/local-first/privacy use cases the cloud giants can't serve.
- Own a **direct customer relationship + proprietary data** so you're not a skinnable feature.
- Be honest about timing: if your roadmap is "what Adobe/Google will plausibly ship in 12 months," you're already dead.

**Archetype exposure:** **MOST exposed** = general-purpose consumer/prosumer image/video app (head-on with Firefly/Canva/Gemini). **LEAST exposed** = vertical apps in domains incumbents ignore, and *compliance* tooling (a cost center incumbents would rather sell you than build into the free tier).

---

## Risk 3 — OSS license traps [Med-High]

**The claim:** "open weights" routinely means **non-commercial** or hedged-commercial, and builders ship illegal products by assuming "open == free to monetize."

**2026 evidence:**
- **FLUX [dev] is non-commercial, and the trap deepened.** The **June 26, 2025 v1.1** update redefined "Non-Commercial Purpose" to exclude any use receiving "direct or indirect payment *arising from the use of … Outputs*" — i.e., the restriction reaches the **outputs**, not just the weights ([HF discussion](https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev/discussions/6)). **FLUX.2 [dev]** (license revised **Nov 25, 2025**) explicitly bars "revenue-generating activity," "direct interactions with end users," and "train/fine-tune/distill for commercial use" ([GitHub LICENSE-FLUX-DEV](https://github.com/black-forest-labs/flux2/blob/main/model_licenses/LICENSE-FLUX-DEV), [bfl.ai](https://bfl.ai/legal/non-commercial-license-terms)). Commercial use requires a paid Builder/Platform/Enterprise license — and the Builder tier is **single-domain, 10K img/mo, "not for client use or downstream applications."** A solo builder's whole agency/SaaS model can be *off-limits by default*.
- **SD3's launch license was so bad the community revolted.** CivitAI **banned all SD3-derived content**; Invoke's CEO said the revised terms still didn't fix the fundamentals ([Decrypt](https://decrypt.co/235866/sd3-license-stability-ai-civit-ai-ban)). The original Creator License capped you at **<$1M revenue, <$1M funding, <1M MAU, 6,000 images/mo** before forcing an Enterprise deal. Build past those and you owe money retroactively.
- **Vendor instability compounds it.** Stability laid off ~10% and shopped itself as an acquisition target ([Crunchbase](https://news.crunchbase.com/ai/stability-ai-layoff/)). A distressed vendor can *change the license out from under you* (FLUX already did, twice) — and you've built a product on terms that no longer exist.

**Mitigation:**
- **Read the actual LICENSE-*.md and the dated revision** before committing — not the marketing page, not a blog. Re-check on every model bump; terms change retroactively in spirit.
- Default to genuinely permissive models for the commercial core (Apache/MIT-weighted, or models with clean commercial terms), or **budget for the paid commercial license** as a hard COGS line, or build so the model is swappable and license risk is contained to one replaceable component.
- Keep a written license-provenance log per model/version — it's also your EU AI Act / due-diligence paper trail.

**Archetype exposure:** **MOST exposed** = anything that fine-tunes/distills OSS weights or self-hosts "open" models as the commercial engine (FLUX dev's exact prohibitions). **LEAST exposed** = consistency/compliance/tooling layers that are *model-agnostic orchestration* and call licensed APIs, where license risk sits with the API vendor.

---

## Risk 4 — Training-data / copyright lawsuits flow downstream [Med]

**The claim:** the unresolved legality of how these models were trained becomes *your* liability once you commercialize outputs.

**2026 evidence:**
- **Andersen v. Stability AI** survived dismissal (Aug 2024, both **direct and induced** infringement claims found plausible) and is **set for trial Sept 8, 2026** ([JIPEL/NYU](https://jipel.law.nyu.edu/andersen-v-stability-ai-the-landmark-case-unpacking-the-copyright-risks-of-ai-image-generators/), [Artnet](https://news.artnet.com/art-world/artists-vs-stability-ai-lawsuit-moves-ahead-2524849)). The **induced-infringement theory** — that distributing a model to downstream providers facilitates copying — is exactly the legal hook that can reach *builders on top of these models*.
- **Disney + Universal (June 2025) and Warner Bros. (Sept 2025) v. Midjourney** allege direct *and secondary* infringement, with outputs reproducing Superman/Batman/Bugs Bunny etc., seeking **statutory damages + injunction** ([THR](https://www.hollywoodreporter.com/business/business-news/warner-bros-discovery-sues-ai-company-copyright-infringement-1236361610/), [TIME](https://time.com/7293362/disney-universal-midjourney-lawsuit-ai/)). Midjourney's defense is fair use — *unproven*. If an injunction lands, models/features can vanish mid-product.
- **Open models give you nothing to hide behind.** Midjourney, OpenAI image, and Stability offer **zero IP indemnification**; Adobe sells indemnity (paid CC; Enterprise caps $50K+) *because the liability is real and monetizable* ([LicenseOrg](https://www.licenseorg.com/blog/adobe-firefly-indemnification-explained), [stacksheriff](https://stacksheriff.com/ai-tools/adobe-firefly-commercial-use/)). A solo builder self-hosting OSS weights has **no indemnity, no legal team, and personal/LLC exposure** if a customer's generated output infringes.
- **The Sora cautionary tale:** even OpenAI's flagship "became notorious for generating copyrighted characters," drew talent-agency legal threats, and a **$1B Disney licensing deal collapsed** — contributing to the shutdown ([TechCrunch](https://techcrunch.com/2026/03/29/why-openai-really-shut-down-sora/)). Copyright wasn't a footnote; it was load-bearing in the decision to kill the product.

**Mitigation:**
- For any commercial output use, prefer **indemnified / cleanly-licensed-training models** for the customer-facing path (this is a real reason to pay for Firefly/licensed APIs rather than self-host).
- Put **output filtering / IP-similarity guardrails** in the pipeline; document provenance (helps both legality and EU AI Act).
- Structure the business as an **LLC**, carry appropriate insurance, and write Terms that push end-user-generated-content responsibility to the user (necessary but *not* sufficient — induced-infringement theory can still reach you).

**Archetype exposure:** **MOST exposed** = consumer generators producing arbitrary user-directed imagery (max chance of infringing output, max volume). **LEAST exposed** = tooling that processes the *user's own footage/assets* (the client's clipper is a good example — it transforms content the operator already owns), and compliance/provenance layers that *sell* the solution to this problem.

---

## Risk 5 — Platform/distribution dependence + AI-labeling/regulation cost [Med]

**The claim:** your distribution and your legal-to-operate status both sit on platforms/regulators you don't control, and the compliance bill is non-trivial for a solo dev.

**2026 evidence:**
- **EU AI Act Art. 50** requires machine-readable "this is AI-generated" marking on generative outputs, **mandatory from Aug 2, 2026**, with a Code of Practice pointing at **C2PA + watermarking (e.g., SynthID) simultaneously**; non-compliance fines up to **€7.5M or 1.5% of global turnover** ([artificialintelligenceact.eu](https://artificialintelligenceact.eu/article/50/), [C2PA Viewer](https://c2paviewer.com/articles/eu-ai-act-content-credentials)). **C2PA signing needs an X.509 cert from a recognized CA — ~$289/yr, no free Let's-Encrypt equivalent** ([C2PA Viewer](https://c2paviewer.com/articles/eu-ai-act-content-credentials)). That's recurring COGS + engineering time a solo builder must absorb to legally serve EU users.
- **App-store policy is reactive and unforgiving.** Apple **removed 28 flagged AI "nudify" apps** and Google suspended several after a Jan 2026 Tech Transparency Project report ([OECD.AI](https://oecd.ai/en/incidents/2026-01-27-19a0), [Android Headlines](https://www.androidheadlines.com/2026/04/apple-google-play-ai-nudify-apps-store-ttp-report.html)). Google Play's **AI-generated-content policy** (tightened Jan 2025: labeling, moderation, minors) can get an app pulled for *category* reasons even if you're benign — generative imagery is a flagged surface, and enforcement waves are blunt ([Play Console Help](https://support.google.com/googleplay/android-developer/answer/14094294)).
- **Discovery dependence:** organic reach for AI content runs through TikTok/IG/YouTube algorithms and search — all of which can reclassify, deprioritize, or label AI content at will. (Note: the client *already rejected* auto-post farms, so this matters mostly as a reminder that the consumer-app distribution path is rented land too.)

**Mitigation:**
- Bake **C2PA/provenance + watermarking in from day one** — turn the regulatory cost into a *feature* (provenance/audit trail is exactly what enterprise buyers want).
- Favor **distribution you control** (direct web, self-serve, B2B sales, API/embed) over app-store-gated or algorithm-gated funnels.
- Geo-segment: be deliberately compliant for EU, and don't let one jurisdiction's rules silently apply everywhere unless you choose it.

**Archetype exposure:** **MOST exposed** = consumer mobile apps (app-store gatekeepers) and ad/algorithm-dependent distribution. **LEAST exposed** = B2B/API/local-first tools — and **compliance tooling is *negatively* exposed** (regulation is its tailwind, not its tax).

---

## Risk 6 — Race-to-the-bottom pricing & thin margins [High]

**The claim:** COGS is GPU-per-generation, prices are collapsing toward that floor, and the wrapper base rate is ~80–95% failure.

**2026 evidence:**
- **Base rate:** "most AI-wrapper businesses fail in their first year (**80–95% never generate meaningful revenue**)" ([machinebrief](https://www.machinebrief.com/news/death-of-ai-wrapper-startups-wont-survive-2026)); a separate piece tracks **319+ failed AI startups 2023–2026** ([IdeaProof](https://ideaproof.io/failures/ai-startups)). "The first wave of AI shutdowns has arrived, mostly among thin wrappers."
- **Margin structure is hostile:** AI-first **early-stage ~25%** gross margin vs **80–90%** normal SaaS; mature AI-first only ~60%; **84% of companies see 6%+ margin erosion** from AI infra ([SoftwareSeni](https://www.softwareseni.com/outcomes-based-pricing-and-ai-first-saas-gross-margin-economics-explained/)). "A thin layer over [a model] with no proprietary data or workflow lock-in **compresses to zero margin within 12 months.**"
- **GPU is the dominant cost:** **40–60% of technical budget** in the first two years, with startups burning **up to 80% of reserves on compute** ([Medium/Jack of all AI](https://medium.com/@jackofallai/the-hidden-cost-of-ai-how-startups-are-burning-billions-on-gpus-426c80dc899c), [GMI Cloud](https://www.gmicloud.ai/en/blog/how-much-do-gpu-cloud-platforms-cost-for-ai-startups-in-2026)). GPU *access* is itself a bottleneck — clouds prioritize internal teams and big enterprises, leaving small players paying premium spot prices.
- **The definitive proof:** **OpenAI shut down Sora (web/app Apr 26, 2026; API Sept 24, 2026)** because it burned **~$1M/day** against **$2.1M lifetime in-app revenue**, with users collapsing from ~1M to <500K ([TechCrunch](https://techcrunch.com/2026/03/29/why-openai-really-shut-down-sora/), [Futurum](https://futurumgroup.com/insights/openai-sora-discontinuation-what-the-end-of-a-platform-means-for-enterprise-ai-strategy/)). **Video generation has negative unit economics even for the best-funded lab on earth.** A solo builder reselling per-generation video has no path the incumbents couldn't find.

**Mitigation:**
- Avoid pricing models where **revenue scales with generation volume but margin is fixed near GPU cost** — that's the zero-margin trap. Prefer value-based/seat/outcome pricing decoupled from gen count, or sell tooling/infra where you're not paying per-output.
- If you must generate, **own the GPU efficiency** (batching, caching, cheaper open models for the 80% of jobs that don't need the frontier) so COGS isn't your competitor's API price.
- **Video gen as a paid consumer service is a trap in 2026** — the unit economics are publicly broken. If touching video, be the *editing/assembly/consistency/review* layer (low per-job compute), not the *generation* layer (ruinous per-second compute).

**Archetype exposure:** **MOST exposed** = pay-per-generation consumer apps, *especially video* (Sora-grade COGS). **LEAST exposed** = infra/tooling and compliance with software-like margins (compute is the customer's bill, not yours).

---

## Risk 7 — Capability cliffs: the demo works, production doesn't [Med-High]

**The claim:** generation models demo spectacularly and fail at the boring reliability/consistency/controllability that paying customers require — and that gap becomes your support, QA, and refund burden.

**2026 evidence:**
- **Character/temporal consistency is *still* the headline unsolved problem in mid-2026.** "The primary bottleneck for professional video production is no longer raw resolution, but **visual consistency**" ([Cliprise](https://medium.com/@cliprise/the-state-of-ai-video-generation-in-february-2026-every-major-model-analyzed-6dbfedbe3a5c)). "Every AI video tool **still fails** at the one thing that matters most" — the same character across shots ([dev.to](https://dev.to/weizhang_dev/the-character-consistency-problem-why-every-ai-video-tool-still-fails-at-the-one-thing-that-3386)). "What is never seen in demos is the same character in a 2nd–8th shot… tools can't do it yet."
- **Duration cliff:** "most AI video tools in 2026 still struggle beyond **30–60 seconds** of coherent footage." Short clips are great; anything story-length degrades.
- **Why this is *your* problem:** the variance between a cherry-picked demo and the median customer generation is enormous. Every failed/inconsistent output is a support ticket, a refund, a churned user, or a hand-fix you do manually. Solo builders have no QA team to absorb this — it's all you, and it scales with usage.
- This is also why **consistency itself is the rare defensible wedge**: Runway marketed Gen-4 explicitly on "solving character consistency" ([VentureBeat](https://venturebeat.com/ai/runways-gen-4-ai-solves-the-character-consistency-challenge-making-ai-filmmaking-actually-useful)) — the hard, unsolved reliability problems are where durable value lives, *if* you can actually solve them better than the next model release (which is itself a Risk-1 gamble).

**Mitigation:**
- **Demo on your *worst* outputs, not your best.** Scope the product to what the model does *reliably*, and design the UX around graceful failure (regenerate, human-in-the-loop review, approval gates — exactly the client's "operator approves" pattern).
- **Sell the human-in-the-loop, not full automation.** Position the model as a draft-generator a human curates; this matches the actual reliability and dodges the "it produced garbage" support tsink.
- If you target a capability cliff (consistency, control, long-form), be brutally honest about whether you can beat it *durably* vs. the next open-weight drop closing it for free.

**Archetype exposure:** **MOST exposed** = "fire-and-forget, fully automated, generation-is-the-product" apps (every model miss is a customer-facing failure). **LEAST exposed** = human-in-the-loop review/approval tools (failure is expected and handled) and consistency/control layers (the cliff is the *product*).

---

## Which archetypes survive best

Ranked from most-survivable to most-exposed, given everything above:

| Archetype | Verdict | Why |
|---|---|---|
| **Compliance / provenance / safety layer** (C2PA, watermarking, IP-similarity filtering, audit trails) | **Best survival** | Regulation (EU AI Act Aug 2026) is a *tailwind*; incumbents would rather sell it than give it away; license/copyright risk is the problem you *solve*, not inherit; software margins. |
| **Infra / tooling / orchestration** (model-agnostic pipelines, eval, routing, cost-optimization, fine-tune ops) | **Strong** | Gets *more* valuable as models proliferate (Risk 1 inverts in your favor); compute is the customer's bill not yours (Risk 6); license risk contained to swappable components. |
| **Consistency / control layer** (character/temporal consistency, controllability, long-form coherence) | **Good *if* you can hold the lead** | Targets the real unsolved cliff (Risk 7) where durable value lives — but you're betting the next open-weight release won't close it for free (Risk 1). High risk/high reward. |
| **Vertical app in an incumbent-ignored niche** (regulated industry, on-prem/local-first, narrow workflow) | **Survivable with discipline** | Defensible only if too small/weird for Adobe/Google *and* you own data + customer relationship. Dies the moment your niche becomes a Firefly checkbox. |
| **General-purpose consumer/prosumer generator** ("AI image/video maker") | **Worst — avoid** | Head-on with Firefly's 30-model aggregator + free Nano Banana (Risk 2); zero-margin per-gen pricing (Risk 6); license + copyright exposure (Risks 3–4); *and* Sora proved even OpenAI can't fund consumer video gen. |

**Bottom line for the client:** the through-line of every survivable archetype is that **the generation model is an interchangeable input, not the product.** The defensible value is in the *workflow around* generation — provenance, orchestration, consistency, human-in-the-loop review, vertical depth — precisely the muscles the existing `clipper` design (swappable Detector/Transcriber protocols, operator-approval gate, provenance on export, local-first) already exercises. A pivot toward *generation-as-the-product* would walk straight into the buzzsaw of Risks 1, 2, and 6. A bet on a *consistency/orchestration/compliance layer* that treats generation as a commodity input is the only side of this trade with a defensible edge.
