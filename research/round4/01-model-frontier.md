# Round 4 — Stream 1: OSS Image/Video Model Capability Frontier (mid-2026)

*Skeptical-analyst scan of what open/open-weight generative models can actually do as of June 2026, what it costs, and what crossed the "build a product on it" line. Confidence tags: [Verified] = primary source / official repo, [High] = multiple consistent secondary sources, [Med] = single decent source or reasoned inference, [Low]/[Speculative] = thin or extrapolated.*

> **Caveat on sources:** Much of the 2026 web is SEO/affiliate content (GPU-rental blogs, model aggregators). Benchmark claims like "beats Kling 2.1" almost always come from vendor or affiliate pages, not neutral evals. I downgrade those to [Med] and flag direction-of-travel rather than precise rankings. Release dates and licenses are pulled from official repos where possible ([Verified]).

---

## TL;DR (read this first)

1. **Open-weight IMAGE generation is genuinely solved for production.** Flux, Qwen-Image, and the SDXL ecosystem produce commercial-quality stills today. The remaining gap to closed leaders (Nano Banana Pro / Seedream 5 / GPT-Image-2) is **multi-turn conversational editing and instruction-following**, not raw fidelity. [High]
2. **The big license trap: the *good* open models are mostly *non-commercial*.** FLUX.2 [dev] (32B, Nov 25 2025) and Klein-9B are **non-commercial**; only **FLUX.2 [klein] 4B is Apache-2.0** (Jan 15 2026). The truly commercial-safe, high-quality open image models are **Qwen-Image / Qwen-Image-2.0 (Apache-2.0)** and **SDXL/Wan-Image**. Build commercially on Apache models or buy a BFL license. [Verified]
3. **Open-weight VIDEO is "good enough to build on" for the first time — at the 5–10s clip level.** Wan 2.2 (Apache-2.0, Jul 2025), HunyuanVideo-1.5 (8.3B, Nov 20 2025, runs in 8GB), and LTX-2 (Apache-2.0, Jan 6 2026, native 4K + audio) are real production tools, not demos. [High]
4. **But open video is ~6–12 months behind closed**, and the gap is widening at the top. Sora 2 / Veo 3.1 / Kling 2.6–3.0 lead on physics, long-shot coherence, prompt adherence, and especially **native synchronized audio + dialogue**. LTX-2 is the only open model with native A/V; everyone else is silent video + bolt-on lip-sync. [High]
5. **Alibaba split its Wan line: open vs API.** The Apache-2.0 downloadable lineage tops out at **Wan 2.2** (with 2.6-Image variants); **Wan 2.5 / 2.7 are API-first / closed-weight** "platform" releases. Don't assume the next Wan number is downloadable. [Med→High]
6. **The control/edit layer is the real moat-builder and it's mature on the image side, flaky on video.** LoRA training, ControlNet, IP-Adapter/PuLID, inpainting, Qwen-Image-Edit = reliable. Character consistency *across a video clip* and *across many clips* is still the hardest unsolved problem. [High]
7. **Cost is not the blocker.** On rented GPUs, a Flux/Qwen image is ~**$0.001–0.01**, and a second of 720p open-source video is ~**$0.02–0.08**; managed APIs (fal/Replicate) charge ~**$0.01–0.04/image** and ~**$0.04–0.10/s** for open video. Closed video (Veo/Sora) is **$0.15–0.40/s**. [High]
8. **The buildable edge is in the gaps closed models leave:** commercial-safe customization (LoRA/character IP you own), controllable/deterministic pipelines, batch+orchestration, and stitching silent open video to open audio/lip-sync — things the closed APIs deliberately don't let you do. [Med]

---

## 1. IMAGE — open / open-weight state

### The Flux family (Black Forest Labs) — fidelity leader, license minefield
[Verified unless noted]

| Model | Params | Released | License | Practical hardware |
|---|---|---|---|---|
| FLUX.1 [schnell] | 12B | Aug 2024 | **Apache-2.0** | 12–24GB |
| FLUX.1 [dev] | 12B | Aug 2024 | **Non-commercial** (BFL license; commercial license sold separately) | 12–24GB (Q4 ~8GB) |
| FLUX.1 [pro] / Kontext | — | 2024–25 | Proprietary, API-only | — |
| **FLUX.2 [dev]** | **32B** | **Nov 25 2025** | **FLUX Non-Commercial License** | **H100-class**: FP16 ~64GB, FP8 ~32GB, Q4 GGUF ~19GB (4090 only with text-encoder offloaded) |
| **FLUX.2 [klein] 4B** | 4B | **Jan 15 2026** | **Apache-2.0** | ~13GB FP16, runs 12GB / ~8GB quantized; sub-second on consumer GPUs |
| FLUX.2 [klein] 9B | 9B | Jan 15 2026 | **Non-commercial** | ~29GB FP16, 16GB quantized |
| FLUX.2 [flex] / [pro] | — | 2026 | Proprietary, API-only | — |

Reading: FLUX.2 [dev] is the open *quality* peak but it's **(a) non-commercial and (b) H100-sized** — not a local pick and not commercially usable without buying a license. The commercially free Flux is **klein-4B (Apache)**, which is fast and decent but a tier below dev on fidelity. "Flux.1 Krea [dev]" exists as another non-commercial dev variant (aesthetic-tuned). **Net: Flux gives you the best open fidelity, but the commercial-safe Flux is the smallest one.** [Verified — BFL repo + licensing page]

### Qwen-Image / Qwen-Image-2.0 (Alibaba) — the commercial-safe workhorse
[High]

- Original **Qwen-Image**: 20B MMDiT, **Apache-2.0**, strong **text rendering** (its headline capability) and editing via **Qwen-Image-Edit**. [Verified — QwenLM repo + HF]
- **Qwen-Image-2.0** (Feb 10 2026): leaner **7B**, native **2K**, unified generation+editing in one model, up to ~1000-token prompts, strong typography/infographics/posters. Claims higher benchmarks than the 20B predecessor at a fraction of the size. [Med — vendor/blog sourced; treat benchmark claims skeptically]
- **Why it matters for a builder:** Apache-2.0 + best-in-open **text-in-image** + a real **editing** model. This is the model you build a *commercial* image product on. The Qwen-Image-Edit line (incl. "2509" revisions) is also the community's favorite **dataset-generation tool** for building character LoRAs. [High]

### SDXL ecosystem — old but unkillable
[High]

SDXL (2023) is ancient by 2026 standards but remains the **deepest tooling ecosystem**: every ControlNet, every IP-Adapter, the most LoRAs, fastest to fine-tune, runs on 8GB. For controllable, customized, cheap image pipelines it's still a rational default — you trade peak fidelity for unmatched control surface and resource frugality. [High]

### Open vs closed image leaders (the honest gap)
Closed leaders in 2026: **Nano Banana / Nano Banana Pro (Google Gemini-image), Seedream 4.0→5.0 (ByteDance), GPT-Image-2 (OpenAI)**. [High]
- **Raw single-image fidelity:** open (Flux.2/Qwen) is competitive; a normal viewer can't reliably tell. [Med]
- **Where closed still wins:** *conversational multi-turn editing*, prompt-adherence on complex compositional instructions, world-knowledge ("draw an accurate diagram of X"), and consistency of identity across edits. Nano Banana Pro / Seedream 5 are noticeably ahead on "do exactly what I described across 5 edits." [High]
- **Cost of closed image is already trivial** (~$0.03–0.04/image), so for one-off images the open advantage is *control/ownership*, not price. [High]

**Verdict (image):** Production-quality open image generation is **here and commercial-safe via Qwen/SDXL**. Flux gives the fidelity ceiling but with license/hardware strings. The only durable closed advantage is high-end instruction-following + multi-turn edit UX. [High]

---

## 2. VIDEO — open / open-weight state

### The current open lineup
[Verified releases; quality claims [Med]]

| Model | Org | Params | Released | License | Notable |
|---|---|---|---|---|---|
| **Wan 2.2** (T2V/I2V A14B, TI2V-5B) | Alibaba | 14B (MoE) / 5B | **Jul 2025** | **Apache-2.0** | Unified T2V+I2V+edit; best open photoreal humans; deep LoRA ecosystem |
| **HunyuanVideo-1.5** | Tencent | **8.3B** | **Nov 20 2025** | Open weights (HF) | Runs in **8GB** (Q4 GGUF); step-distilled I2V → ~75s/clip on a 4090; strong motion/physics |
| **LTX-2** | Lightricks | 19B (14B video + 5B audio) | **Jan 6 2026** | **Apache-2.0** | **First open model with native synced 4K video+audio**, ~20s clips @ 50fps, lip-sync; fastest open model |
| HunyuanVideo (orig) | Tencent | 13B | Dec 2024 | Open weights | The 2024 baseline; superseded by 1.5 |
| CogVideoX (2B/5B) | Zhipu | 2–5B | 2024–25 | Open | Best prompt/semantic adherence per-param; small; older quality |
| Mochi 1 | Genmo | 10B | 2024 | Apache-2.0 | Early open T2V; now mid-pack |
| SkyReels V2 | Skywork | — | 2025 | Open | Built for **longer** clips (>6–8s) with extended temporal consistency |

**The Wan version trap (important):** The downloadable Apache-2.0 lineage is **Wan 2.1 → 2.2** (+ a 2.6-**Image** variant). **Wan 2.5 and Wan 2.7 launched as cloud/API products with open weights *not* confirmed/released** — a deliberate shift to "platform-first" for the newest, best models. Affiliate blogs loosely call them "open source" because Wan *historically* open-sourced; that is pattern-matching, not a commitment. **For a builder: assume Wan 2.2 is your open ceiling unless/until 2.5+ weights actually drop on HF/ModelScope.** [Med→High]

### Capability reality (open video, mid-2026)
[High on direction; [Med] on exact figures]

- **Max usable clip length:** ~**5–8s** is the reliable zone for most open models; LTX-2 ~20s; SkyReels pushes longer but with quality cost. Beyond ~8s, **temporal drift** (identity/scene morphing) sets in for everyone. [High]
- **Resolution:** 720p is the comfortable open default; 1080p achievable; **LTX-2 does native 4K**. [High]
- **Motion/physics:** Wan strong on aggressive physical motion; Hunyuan-1.5 strong on fluid/cloth/physics. Still below Sora 2's physics. [Med]
- **Faces under motion:** holds "better than 2025" but degrades on fast motion / long clips. [Med]
- **Hands & text-in-video:** **still the classic failure modes.** Readable on-screen text is unreliable across nearly all open models; hands improved but not solved. [High]
- **Audio:** **only LTX-2 generates native synced audio/dialogue.** Wan/Hunyuan/Cog are silent → you bolt on TTS + lip-sync in post. [High]
- **First-take success rate:** open models need **more re-rolls** than closed for a usable clip (e.g., reported ~50–60% for talking-head UGC vs ~65–75% for Kling). Budget 2–4× generations per keeper. [Med]

### How close to closed (Sora 2 / Veo 3.1 / Kling 2.6–3.0)?
[High]

- **Consensus gap: ~6–12 months.** Open Wan 2.2 ≈ closed models from mid/late-2025; it does **not** match current Sora 2 / Veo 3.1 on physics, long-shot coherence, prompt adherence, or audio. [High]
- **Veo 3.1** is the audio leader (synced dialogue + ambient + SFX matched to lip movement). [High]
- **Sora 2** leads cinematic physics/camera. (One 2026 source claims Sora 2 is silent — this contradicts Sora 2's launch feature set of synchronized audio; **treat that source as wrong** and assume Sora 2 has audio. [Low on that single claim])
- **Kling 2.6/3.0** = the speed/affordability leader for social, cheap closed option (~$0.04–0.06/s tiers). [Med]
- **Market is multi-polar**, unlike LLMs — no single winner, and the smart move is mixing models per pipeline stage. [High]

**Verdict (video):** Open video **crossed into "buildable" for short clips** in the last ~12 months (Wan 2.2 → Hunyuan-1.5 → LTX-2 + audio). It is **still clearly behind closed** at the frontier (long, audio-synced, physics-perfect, high first-take yield). The open edge is **cost, control, customization, and no content gatekeeping** — not beating Veo on quality. [High]

---

## 3. CONTROL / EDIT layer — the part that actually differentiates a product

### Reliable today [High]
- **LoRA training (character/style):** mature. 15–50 images, 1–3k steps, 1–4h on a rented GPU via Kohya / ai-toolkit / OneTrainer. Works for SDXL, Flux, Qwen, and **Wan video LoRAs**. This is the single most important "make it yours" lever. [High]
- **ControlNet** (pose/depth/canny/edge): rock-solid on SDXL; available and good for Flux and **Qwen-Image-Edit + ControlNet Union**. Deterministic structure control. [High]
- **IP-Adapter / PuLID / InstantID** (identity transfer from a reference): reliable for face/style locking; the pro stack is **low-strength LoRA (body/vibe) + PuLID (face) + ControlNet/OpenPose (pose)**. [High]
- **Inpainting / outpainting:** solved on SDXL/Flux/Qwen. [High]
- **Image editing (instruction-based):** **Qwen-Image-Edit** (open, Apache) and **Flux Kontext** (closed/API) are both strong; Qwen-Edit is the open default and doubles as a **synthetic-dataset generator** for consistent characters. [High]
- **Img2Vid (I2V):** first-class in Wan, Hunyuan-1.5, LTX-2 — the most reliable way to get controllable open video (generate a perfect still, animate it). [High]
- **Lip-sync:** **LatentSync** (ByteDance, open) is the open SOTA for video; MuseTalk / Wav2Lip older fallbacks. Good but lighting/extreme-angle cases still flaky. [High]
- **Upscaling:** mature (Real-ESRGAN, SUPIR, topaz-style open pipelines; video upscalers exist). [High]

### Flaky / unsolved [Med→High]
- **Character consistency *within* a video clip** and **across many clips**: the hardest open problem. LoRA + I2V + reference helps but drift over time and across shots is unsolved at "studio identical" quality without heavy operator effort. [High]
- **Video-to-video / restyle** with temporal stability: improving (Wan edit, AnimateDiff lineage) but flicker/coherence remain failure modes. [Med]
- **Long-form coherence** (>10–20s, multi-scene): not reliable open. [High]
- **Multi-character interaction + consistent identities** in one shot: flaky. [Med]

**Takeaway:** On **images**, the control layer is mature enough to build deterministic, customized, commercial pipelines today. On **video**, control is good for *single short shots from a controlled still*, but **consistency across a real piece of content is the open frontier** — and therefore the most valuable thing to engineer well. [High]

---

## 4. HARDWARE & COST (rented GPU vs API)

### GPU rental, mid-2026 (on-demand; spot lower) [High]
- **RTX 4090 (24GB):** ~**$0.31–0.40/hr** (Vast.ai / RunPod community). Workhorse for SDXL, Flux Q4/klein, Hunyuan-1.5, Wan 2.2 (quantized), LTX-2.
- **A100 80GB:** ~**$0.60–1.10/hr** spot, ~$1.07–1.99/hr on-demand.
- **H100 80GB:** ~**$1.03–1.50/hr** spot/community, up to ~$3.29 premium. Needed for FLUX.2 [dev] FP16 and fastest video batches.
- **B200** appearing from ~$2.12/hr. [Med]
- *Marketplace prices (Vast) move in real time — verify at deploy.* [Verified caveat]

### VRAM floor by task [High]
- **Images:** SDXL/Flux-klein/Qwen 8–16GB; FLUX.2 [dev] needs 24GB (Q4, offloaded) to 64GB (FP16) → **rent, don't buy**.
- **Video:** Hunyuan-1.5 from **8GB** (Q4); Wan 2.2 / Cog / Mochi comfortable at 24GB; LTX-2 scales from RTX up to datacenter; FP16 video and 4K want 48–80GB.
- **The client's 8GB M1 Air cannot run any of the good video models locally** — it's strictly the orchestrator. All generation = rented GPU. [Verified vs project constraint]

### Realistic unit economics
**Self-hosted on rented GPU** (amortizing GPU/hr over throughput) [Med, back-of-envelope]:
- **Image:** a 4090 does many images/min → **~$0.001–0.01 / image** all-in.
- **Video:** Hunyuan-1.5 distilled ~75s wall-clock for a clip on a 4090 (~$0.35/hr → ~$0.007 of GPU per clip), but realistically **~$0.02–0.08 / second of finished 720p** once you include re-rolls, cold starts, and orchestration overhead. [Med]

**Managed APIs (fal.ai / Replicate)** [High]:
- **Images:** Qwen ~$0.02/MP; FLUX Kontext Pro ~$0.04/img; Seedream V4 ~$0.03/img; **FLUX.2 klein as low as ~$0.01/img**.
- **Open video:** ~**$0.04–0.10/s** (Wan tiers ~$0.04–0.06/s).
- **Closed video:** **Veo 3 ~$0.40/s**, Sora/Kling Pro tiers ~$0.15–0.40/s.
- **fal vs Replicate:** fal generally 30–50% cheaper (up to ~80% on video) and faster; fal bills per output/MP, Replicate per GPU-second. fal also rents raw GPU-seconds (H100 ~$1.89/hr, A100 ~$0.99/hr). [High]

**Cost conclusion:** Self-hosting open models on rented GPUs is **3–10× cheaper per unit than managed APIs** and **5–40× cheaper than closed video APIs** — *but only at volume*, because you pay for engineering, cold starts, idle GPU, and re-rolls. **Low volume → just use fal/Replicate. High volume or need-control → self-host open.** This crossover point is the core build/buy decision. [Med]

---

## 5. THRESHOLD CALL — what crossed "good enough to build on"

### Crossed the line in the last ~12 months (Jul 2025 → Jun 2026) [High]
1. **Open IMAGE at commercial quality + commercial license** — Qwen-Image (Apache) + Qwen-Image-Edit, FLUX.2 klein-4B (Apache), mature SDXL control stack. You can ship a real image product on open weights legally. [High]
2. **Open VIDEO for short clips became production-usable** — Wan 2.2 (Jul 2025), HunyuanVideo-1.5 running in **8GB** (Nov 2025), and **LTX-2 with native 4K + audio** (Jan 2026). The "demo-only" label no longer fits 5–8s clips. [High]
3. **Open lip-sync (LatentSync) + I2V + LoRA** matured enough to assemble a controllable talking-character pipeline entirely from open parts. [High]
4. **GPU rental got cheap and granular** (4090 ~$0.35/hr, per-second billing) so the *infra* objection is gone. [High]

### Still research-grade / demo-only / clearly behind closed [High]
1. **Long-form coherent video** (>10–20s, multi-scene, persistent identity) — open is not there; even closed is shaky past a shot. [High]
2. **Native synchronized audio + dialogue at quality** — closed (Veo 3.1) wins decisively; open has only LTX-2 as a single entrant. [High]
3. **Character identity locked *across* a full video / many clips** — the open frontier; needs real engineering, no turnkey solution. [High]
4. **High-end instruction-following / multi-turn image edit UX** — Nano Banana Pro / Seedream 5 / GPT-Image-2 still ahead of open. [High]
5. **Frontier video physics & first-take yield** — Sora 2 / Veo 3.1 lead; open needs more re-rolls. [High]
6. **Readable text and reliable hands *in video*** — broadly unsolved open. [High]
7. **The newest/best Wan models are going closed** — don't bank on open weights for Wan 2.5/2.7. [Med]

### Where open is genuinely competitive (not just "cheaper")
- **Customization/ownership:** train a LoRA on IP *you own*, run it forever, no per-image gatekeeping. Closed APIs can't give you this. [High]
- **Determinism/control:** ControlNet/pose/depth/inpaint pipelines closed models won't expose. [High]
- **No content policy chokepoint / data stays yours:** matters for some B2B/regulated buyers. [Med]
- **Per-unit cost at volume.** [High]

---

## What this means for a builder

**The frontier (raw quality) is the wrong place to compete.** Closed models (Sora 2, Veo 3.1, Nano Banana Pro) are ahead on fidelity, audio, and instruction-following, and they're cheap per call. A solo builder will not out-quality them, and a thin "generate a clip" wrapper has no moat. [High]

**The buildable edge is everything closed APIs deliberately *don't* let you do**, all of which open weights make possible:
1. **Commercial-safe customization** — products built around **LoRA/character/style assets the customer owns**, trained on Qwen/SDXL/Flux-klein/Wan (watch licenses: build commercial on **Apache** models or buy a BFL license). [High]
2. **Controllable / deterministic pipelines** — ControlNet + IP-Adapter/PuLID + I2V + inpaint stacks for reproducible, art-directed output, exposed as a real tool, not a chat box. [High]
3. **Assembly/orchestration of open parts** — silent open video (Wan/Hunyuan) + open TTS + **LatentSync** lip-sync + upscale, glued into one pipeline the closed APIs can't replicate because they're black boxes. [Med]
4. **The hard problem as the product:** **character/scene consistency across a multi-shot video.** It's unsolved open, valuable, and exactly the kind of engineering a strong Python builder can attack (orchestration, reference management, automated re-roll/selection, LoRA-per-character). [Med]
5. **Cost arbitrage at volume** via self-hosting on rented 4090/A100/H100 — but only once volume justifies the ops; below that, ride fal/Replicate. [Med]

**Architecture fit to the client:** 8GB M1 Air = orchestrator only; all generation on rented GPUs. This is *the* right shape for an open-gen product: a Python control plane (queueing, model selection, re-roll logic, provenance, consistency engineering) that drives ephemeral GPU workers running open weights. The differentiation lives in the **control plane and the consistency/customization layer**, not the model. [Med]

**One-line synthesis:** Open *image* gen is production-ready and commercial-safe **today**; open *video* is production-ready for **short clips** but trails closed by 6–12 months and lacks good native audio. The defensible build is not "generate," it's **"control, customize, and make consistent"** — the deterministic, ownership-respecting, multi-shot-coherent layer the closed APIs won't sell you. [High]

---

### Key open releases referenced (dates/licenses)
- FLUX.2 [dev] — Nov 25 2025, 32B, **non-commercial** [Verified]
- FLUX.2 [klein] 4B Apache / 9B non-commercial — Jan 15 2026 [Verified]
- Qwen-Image (20B, Apache) / Qwen-Image-2.0 (7B) — orig 2025 / 2.0 Feb 10 2026 [Verified / Med]
- Wan 2.2 (A14B + TI2V-5B, **Apache-2.0**) — Jul 2025; Wan 2.5/2.7 **API-first, weights unconfirmed** [Verified / Med]
- HunyuanVideo-1.5 (8.3B, 8GB-capable, distilled I2V) — Nov 20 2025 [Verified]
- LTX-2 (19B, **Apache-2.0**, native 4K + synced audio, ~20s) — Jan 6 2026 [Verified]
- LatentSync (ByteDance, open lip-sync SOTA) [High]
- Closed reference points: Sora 2, Veo 3.1, Kling 2.6/3.0, Nano Banana Pro, Seedream 4→5, GPT-Image-2 [High]

*Confidence on the overall thesis (open image = ready/commercial; open video = ready-for-short-clips but behind closed; edge = control/customization/consistency): **High.** Specific per-model benchmark rankings: **Med** — vendor/affiliate sourced, not neutral evals.*
