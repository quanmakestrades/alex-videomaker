Minimalist stick-figure educational illustration in the style of popular explainer YouTube channels (Primer, MinutePhysics, Kurzgesagt-lite). Clean black line art on a warm cream or parchment background. Simple, expressive stick-figure characters with dot eyes and mouths that convey emotion through posture. Occasional detailed hand-drawn props, labeled diagrams, maps, charts, or scrolls in a woodcut/etching aesthetic. Muted accent colors — ochre, terracotta, dusty blue, forest green — used sparingly. Soft textured paper background. Wide 16:9 composition. No photorealism, no 3D rendering, no gradients, no glossy effects. The feeling is a scholarly sketchbook come to life.

---

## Notes for humans (not appended to prompts)

This style prefix is designed around the five reference images provided:

1. Nile scene — warm dusk palette, mud-brick villages, palm trees, subtle pyramids
2. Babylonian zodiac — stick figure lecturer pointing at a hand-drawn star chart with constellation labels
3. Hieroglyph examination — stick figure explorer with detailed carved wall art
4. Equation scene — stick figure lecturer + chalkboard covered in math
5. Detective scene — stick figure at desk with magnifying glass, ancient scroll, tablet

The key tension in the style is: **simple expressive characters** + **detailed environmental illustrations**. Stick figures carry the action and emotion. The world around them carries the information.

The pipeline only uses the first paragraph above as the actual style prefix — everything after the `---` is for humans reading this file. See `scene_manager.apply_style()` for where this gets prepended.

## Tuning the style

If the generated images drift too illustrated (too Primer, not enough stick figure):
- Add "simplified geometry" and "flat colors only" to the prefix.
- Remove "hand-drawn props" language.

If the images drift too minimal (too XKCD, not enough atmosphere):
- Add "richly detailed backgrounds" and "textured shading" to the prefix.
- Add specific environmental cues in per-scene `image_prompt`s.

Edit this file and the changes apply to the next run — no code changes needed.
