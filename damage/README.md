# Damage-inspection stage

The final quality gate. After the arm disassembles a part, it holds the part up
to a dedicated **inspection webcam** which captures it from several angles. Those
images are POSTed here; a **VLM (via OpenRouter)** compares them against
known-good and known-damaged reference examples and returns an **OK / damaged**
verdict. The arm then sorts the part into the **working bin** or a separate
**reject bin**.

No GPU — this service is a thin OpenRouter client (`python:3.11-slim`).

## Endpoint

`POST /inspect`

```jsonc
{
  "images_b64": ["<angle 1>", "<angle 2>", "..."],   // required: the target part
  "part_class": "housing",                            // optional: loads disk refs + labels prompt
  "reference_ok_b64":      ["<known-good example>"],  // optional inline references
  "reference_damaged_b64": ["<known-damaged example>"],
  "notes": "check the mating flange for hairline cracks"
}
```

Response:

```jsonc
{
  "verdict": "damaged",           // ok | damaged | uncertain
  "damaged": true,
  "confidence": 0.86,
  "bin": "reject_bin",            // ok_bin | reject_bin  ← where the arm places it
  "issues": ["hairline crack on flange", "corrosion"],
  "reasoning": "…",
  "model": "anthropic/claude-sonnet-5",
  "part_class": "housing"
}
```

**Sorting policy:** only a clean `ok` goes to `ok_bin`; both `damaged` and
`uncertain` route to `reject_bin`, so a bad part never reaches the working bin.

Also `GET /health` → `{status, service, model, api_key_present, reference_dir}`.

## References (few-shot examples)

Give the model examples of good and bad parts two ways (they combine):

1. **Inline** — `reference_ok_b64` / `reference_damaged_b64` in the request.
2. **On disk** — mount a reference dir and pass `part_class`:
   ```
   <REFERENCE_DIR>/<part_class>/ok/*.{jpg,png}
   <REFERENCE_DIR>/<part_class>/damaged/*.{jpg,png}
   ```

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | **required** — your OpenRouter key |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-5` | OpenRouter model slug (must match their catalog; any vision model works) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API base |
| `REFERENCE_DIR` | `/reference` | disk-backed reference images root |
| `DAMAGE_TIMEOUT_S` | `60` | per-request timeout |

## Run

```bash
export OPENROUTER_API_KEY=sk-or-...
docker compose up --build damage
# then:
curl -s localhost:8006/inspect -H 'content-type: application/json' \
  -d '{"images_b64":["'"$(base64 -w0 part.jpg)"'"],"part_class":"housing"}' | jq
```

## Layout

```
schemas.py    request/verdict contract
config.py     env settings (OpenRouter + reference dir)
prompts.py    system prompt + message builder (references then target images)
reference.py  disk-backed per-class reference loader
client.py     OpenRouter /chat/completions call + JSON extraction
app.py        FastAPI service (:8006)
```
