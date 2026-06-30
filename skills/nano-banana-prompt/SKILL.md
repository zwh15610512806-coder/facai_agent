---
name: nano-banana-prompt
description: Create image-generation prompts for Nano Banana / image models. Use when Codex needs to write or improve prompts for product images, ecommerce visuals, social media images, food photography, commercial scene images, or reference-image-based image generation.
---

# Nano Banana Prompt

## Output Goal

Create image prompts that are direct, visual, and production-ready. Prefer a single polished prompt unless the user asks for multiple options.

## Prompt Recipe

Build prompts in this order:

1. Subject: product, food, person, object, or scene.
2. Commercial purpose: ecommerce hero, social post, product-in-use, close-up, menu image, ad visual, comparison image, etc.
3. Composition: camera angle, crop, framing, foreground/background, negative space.
4. Materials and details: packaging, texture, color, surface, food state, hands, props, scale references.
5. Lighting and style: natural daylight, soft studio light, realistic commercial photography, clean tabletop, warm bakery workspace.
6. Brand constraints: exact visible text if supplied, logo placement if supplied, avoid inventing unsupported claims.
7. Quality controls: sharp focus, realistic proportions, no distorted text, no watermark, no extra logos, no messy background.

## Defaults

- Use realistic commercial photography unless the user asks for illustration or a stylized look.
- For food and bakery products, make the product inspectable: clear texture, packaging, usage state, and scale.
- For ecommerce images, keep the background clean and leave room for later copy if useful.
- For social images, make the first visual read obvious at mobile size.
- If a reference image is provided, preserve the product identity and change only the requested scene, angle, lighting, or styling.

## Negative Prompt Guidance

Add a compact avoid list when useful:

`Avoid distorted text, fake logos, extra fingers, warped packaging, unreadable labels, watermarks, low resolution, cluttered background, unrealistic food texture.`

## Output Format

For one prompt:

```text
[Final prompt]

Avoid: [negative controls]
```

For multiple prompts, number them and make each visually distinct by angle, setting, or purpose. Keep each prompt ready to paste into an image model.
