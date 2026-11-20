# 新聯華假期 XO Tours — 關於我們 (about-us ad)

A ~68 s brand ad built the same way as the DeepSeek film in this repo: Claude writes the
script, every scene is a Tesseract 3D scene, a GitHub runner renders it. No API keys.

| scene | picture | narration |
|---|---|---|
| S1 hook | fly through a corridor of real XO tour photos, "32 年，帶華人看世界" | 三十二年來… |
| S2 origin | 1994, one gold coin standing on a table, "1994" behind it | the tip that started the company |
| S3 name | a lotus opens on dark water, its heart lights up | 新聯華 = 心中有蓮花 |
| S4 reach | gold-lined globe, routes grow from Vancouver to Toronto / LA / Taipei / Beijing | branches + ticketing for 100+ agencies |
| S5 trips | carousel of tour photos around a glowing core | 專業世界通，服務通世界 |
| S6 close | gold arch (the bridge) over water at dawn, then logo + xotours.net + 1.800.978.1788 | 用旅遊搭起世界和平的橋樑 |

Facts come from the site's 品牌理念 / About Us page (includes/category_content/1592.html).
Photos are XO's own brochure photos (tours 7617, 7620, 7622, 7627); the logo is the gold
brochure medallion. The music bed is synthesised by `make_bgm.py` (nothing sampled).

## Files

- `script.json` — narration lines per scene, voice (edge-tts zh-TW-HsiaoChenNeural), pacing.
- `tts.py` — makes `project/narration/*.mp3`, `narration.wav`, `script_timed.json`.
  A real recording wins: drop `<line id>.wav` into `project/narration/`.
- `build.py` — the six scenes as Tesseract action batches; `ONLY=S1,S3` builds a subset.
- `make_bgm.py` — music bed, ducked under the voice at the stitch step.
- `previews/` — one raster filmstrip per scene + build.log, committed by each push run.

## Running

Push anything under `xotours/` → `.github/workflows/xotours.yml` builds and commits previews.
Final video: run the workflow manually (`gh workflow run xotours.yml -f renderer=raster`);
it renders in 20 chunks and publishes `xotours_about_us.mp4` as Release `xotours-run-<n>`.
