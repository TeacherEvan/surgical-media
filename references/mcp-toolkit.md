# MCP toolkit for content generation

Use these MCP servers to make the image-first video pipeline faster and better
verified. **Excluded deliberately:** `jpay-supabase`, `opencode-tools`.

The repo config `opencode.json` contains the sanitized server definitions. Secrets
must come from environment variables (`{env:HF_TOKEN}`, `{env:TINYFISH_API_KEY}`,
`{env:SUPABASE_PROJECT_REF}`) — never commit tokens or API keys.

## Servers and where they help

| MCP | Use it in this pipeline | Notes |
|---|---|---|
| **blender** | Optional hero 3D plate for one beat (structure a photo cannot show), e.g. exploded hardware or orbital diagram. | Start with `get_addon_status` + `get_scene_info`; look up shader nodes by **type**, not localized name; colours go on shader inputs, not `material.diffuse_color`; `look` to inspect. Never fill a whole video with procedural 3D. |
| **chrome-devtools** | Verify published/HTML artifacts: screenshot the page, read DOM/CSS, check safe zones and captions, confirm thumbnails render. | Use browser-feature-verification workflow; useful for auditing generated HTML storyboards/landing pages before export. |
| **firecrawl** | Step 2–3 research: current facts, source pages, licence text, spec/platform changes; `firecrawl_search`, `scrape`, `map`, `agent`, Alexandria providers for structured records. | Pass the `conversationId` on later calls. Prefer it over hand-written scraping. If credits run out, follow the provider's own message. |
| **GitKraken** | Repo hygiene while developing the skill: status, graph, diffs, commits, PRs, `compose_plan_status`. | `app_tool_box` is app-only for agents; prefer the GitKraken tools exposed by the host for actual work. Never commit user secrets. |
| **huggingface** | Find models/voices/datasets (Kokoro-82M ONNX, voice banks) and check model cards/licences before downloading. | Prefer `hf_fs` over web search for live Hub data. Anonymous rate limits apply; tell user to set `HF_TOKEN` for higher limits. |
| **supabase** | Optional content-ops: store script versions, claim/credit records, render job state and QC reports; query with `apply_migration` for schema work. | Inspect existing tables before schema changes; use RLS verification before exposing data. This is the standard `supabase` server, not `jpay-supabase`. |
| **tinyfish** | Free `search` + `fetch_content` for current web context (facts, images, product/people pages); `create_monitor` to watch a source; `run_web_automation` only for interactive browser tasks; datasets only for many-entity tables. | Default web/external-knowledge toolkit. Verify it works with search first, then fetch. Paid deep research only when the user explicitly asks. |

## Workflow mapping

1. **Intake + spec refresh** — local scripts; use `firecrawl`/`tinyfish` to confirm current platform limits or policy wording when `--fetch` is needed.
2. **Research & imagery** — `tinyfish.search` → `fetch_content` for claims; `firecrawl` for structured/multi-source research and licence pages; `huggingface` only if a model/voice is needed. Then `fetch_assets.py` / `media_harvester.py` for **real licensed photos** — visually curate every result.
3. **Voice** — local Kokoro. Verify pronunciation with its phonemiser and a short sample before rendering; see `lessons-learned.md`.
4. **Board + render** — local `render_engine.py`; `blender` only for an optional single hero beat.
5. **Verification** — local `qc_gate` / `style_lint` / `pipeline_preflight`; `chrome-devtools` for any HTML artifacts; `GitKraken` to review/commit the skill changes.
6. **Content ops** — `supabase` to persist credits, claim IDs, QC reports and render manifests if a project is configured.

## Config example (sanitized)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "blender": { "type": "local", "command": ["/home/leandi-duplessis/.local/bin/mcp-for-blender"], "enabled": true },
    "chrome-devtools": { "type": "local", "command": ["npx", "-y", "chrome-devtools-mcp@latest"], "enabled": true },
    "firecrawl": { "type": "remote", "url": "https://mcp.firecrawl.dev/v2/mcp-oauth", "enabled": true },
    "GitKraken": { "type": "local", "command": ["/home/leandi-duplessis/.config/Cursor/User/globalStorage/eamodio.gitlens/gk", "mcp", "--host=opencode", "--source=gitlens", "--scheme=cursor"], "enabled": true },
    "huggingface": { "type": "remote", "url": "https://huggingface.co/mcp", "headers": { "Authorization": "Bearer {env:HF_TOKEN}" }, "enabled": true },
    "supabase": { "type": "remote", "url": "https://mcp.supabase.com/mcp?project_ref={env:SUPABASE_PROJECT_REF}&features=docs,account,database", "enabled": true },
    "tinyfish": { "type": "remote", "url": "https://agent.tinyfish.ai/mcp?source=tinyfish_cli&client=opencode", "headers": { "X-API-Key": "{env:TINYFISH_API_KEY}" }, "enabled": true }
  }
}
```
