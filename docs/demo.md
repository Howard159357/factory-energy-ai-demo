# 30-second agent demo: storyboard and recording steps

One question, answered live: the plan, the tool calls as they happen, and the answer with
verified citations. All data is synthetic (fictional plant). The recording is made by hand
with the steps below.

## Before recording

1. Data and index exist:
   ```bash
   python -m factory_energy build-demo
   python -m factory_energy rag ingest
   ```
2. The model server is configured in `.env` (vLLM on the GPU host, on-premises):
   ```bash
   LLM_PROVIDER=openai_compatible
   LLM_BASE_URL=http://<gpu-host>:8000/v1
   LLM_MODEL=<served model name>
   ```
   If the demo is recorded with a stand-in backend instead (for example the Codex CLI one),
   say so in the caption: the project is on-premises by design.
3. Dry run the question once so the model and the index are warm, then clear the screen.
4. Terminal about 110 x 32 characters, a large font, a dark theme, nothing private on screen
   (no host names: the prompt and the window title should show only the project folder).

## The question

```text
What was the peak demand on 16 June 2025, why did it happen, and what would starting the machines 15 minutes apart have saved?
```

It exercises three kinds of tool (data, documents, simulation) and has a checkable answer:
1,324 kW at 08:15, ten machines started together, 1,142 kW with a 15-minute stagger,
NT$6,652 of exceedance penalty avoided.

## Storyboard (about 30 seconds)

| Time | On screen | Why |
|---|---|---|
| 0-3 s | The command is typed: `python -m factory_energy agent ask "<question>" --trace` | The whole interface is one command |
| 3-8 s | The plan appears (2-4 numbered steps) | Planning before acting |
| 8-18 s | Tool lines appear one by one: `get_demand`, `search_knowledge`, `whatif_staggered_start`, with timings | Tool use on real data, live |
| 18-26 s | The answer, with `[data: ...]` and `[source: docs/knowledge/...]` citations | Every figure is sourced and verified |
| 26-30 s | The summary line: model, steps, tools, model vs tool time, tokens; the log path | Observability |

Keep the cursor still while it runs; trim pauses longer than about 1.5 s.

## Recording with asciinema (Linux, macOS or WSL)

```bash
asciinema rec docs/assets/agent_demo.cast --cols 110 --rows 32 --idle-time-limit 1.5 --title "Energy agent"
# type the command, wait for the summary line, then press Ctrl-D
agg --font-size 20 docs/assets/agent_demo.cast docs/assets/agent_demo.gif   # GIF for the README
```

`agg` is asciinema's GIF generator. Check the GIF is under about 5 MB and 30 seconds.

## Recording on Windows without WSL

1. Open Windows Terminal, set the size and font as above.
2. Start a screen recording of that window (Win + Alt + R with the Xbox Game Bar, or OBS with a
   window capture).
3. Run the command, stop the recording after the summary line.
4. Trim to 30 seconds and convert to GIF or MP4 (for example with ffmpeg:
   `ffmpeg -i demo.mp4 -vf "fps=12,scale=1100:-1" docs/assets/agent_demo.gif`).

## Adding it to the README

Put the GIF under `docs/assets/agent_demo.gif` and add it to the "Demo video" section:

```markdown
<p align="center"><img src="docs/assets/agent_demo.gif" width="100%" alt="The energy agent answering a question with live tool calls and cited sources"></p>
```
