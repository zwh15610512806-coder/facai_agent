---
name: seedance-2-0-prompt
description: Create Seedance 2.0 video-generation prompts. Use when Codex needs to turn scripts, shot notes, ecommerce products, bakery products, product demos, or short-video scenes into vertical video prompts for Seedance 2.0.
---

# Seedance 2.0 Prompt

## Output Goal

Create short vertical-video prompts that Seedance 2.0 can follow. Prompts should describe the visible scene, motion, camera, product proof, and quality controls without adding unsupported claims.

## Scene Prompt Recipe

For each scene, include:

1. Format: vertical 9:16, short commercial video.
2. Subject: product, person, hand action, food, packaging, or environment.
3. Action: what moves in the shot, such as opening, pouring, cutting, packing, pointing, comparing, or showing texture.
4. Camera: close-up, medium shot, handheld, push-in, overhead, pan, macro detail, rack focus.
5. Setting: bakery counter, cake shop, clean studio tabletop, delivery packing area, display shelf, or realistic workbench.
6. Proof: product detail, texture, packaging, usage result, finished dessert, cost/efficiency scene, before-after comparison.
7. Style: realistic, bright, clean, commercial, natural light, product in focus.
8. Constraints: no captions, no subtitles, no watermark, no distorted packaging, no fake text, no extra logos.

## Facai Bakery Defaults

When product context is from the Facai app:

- Use Chinese output by default.
- Mention `法采` only when the product/brand context supports it.
- Keep the product inspectable: packaging, texture, portion, usage action, and finished result should be visible.
- Prefer real bakery-business scenes over generic lifestyle scenes.
- Do not invent prices, discounts, certifications, or data.
- Keep each prompt independent so it can be copied scene by scene.

## Transforming Scripts

If the input script already has shot notes like `（镜头展示产品）口播文案`:

1. Use the parenthesized shot note as the scene anchor.
2. Use the spoken line only for action/context, not as literal subtitles.
3. Split into one prompt per meaningful scene.
4. Limit to the most useful 6-12 prompts unless the user asks for all scenes.

If the script has no shot notes:

1. Split by sentence or beat.
2. Infer scenes from product, pain point, proof, price mechanism, and CTA.
3. Add camera language that makes the product and action visible.

## Output Format

```text
画面1：[ready-to-copy Seedance 2.0 prompt]

画面2：[ready-to-copy Seedance 2.0 prompt]
```

Keep prompts concise but specific. Do not include analysis unless the user asks for reasoning.
