# DeepSeek 冲击日 — a 3D documentary short, rendered on GitHub Actions

A faceless, Chinese-narrated documentary episode built the way
[this tweet](https://x.com/HeLi8866/status/2118501801813234127) describes:
Claude writes the script, builds every scene in the free
[Tesseract](https://github.com/mirage-hq/Tesseract) engine (path-traced, no Blender,
no video model), aligns the picture to the narration, and a GitHub runner renders the MP4.

Nothing renders on a PC. No API keys are needed for the render path.

## Layout

| path | what |
|---|---|
| `script/` | topics list + per-scene script (the 10-topic pick and the full narration) |
| `project/` | the editable `.tsrct` document(s) and narration audio |
| `skills/` | Tesseract skills, vendored by the bootstrap workflow |
| `docs/cli/` | `tsrct --help` dumps and the project schema, produced by the bootstrap run |
| `.github/workflows/bootstrap.yml` | install the CLI on a runner, dump docs, vendor skills |
| `.github/workflows/render.yml` | render `project/*.tsrct` to MP4, publish as a Release |

## Pipeline (the tweet's five steps)

1. Ten documentary topics for the channel's field, strongest hook picked.
2. Full script, split by scene.
3. Each scene built as a Tesseract 3D scene: camera move, lighting, animated text.
4. Narration recorded (placeholder: edge-tts), picture aligned to it.
5. One-sentence revisions ("slower camera", "warmer light", "bigger title") touch only what they name.
