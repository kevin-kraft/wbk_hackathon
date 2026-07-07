# Proposed contract — grip (grab-detection) sensor endpoint

*Draft for the hardware/grip teammate (basic pressure sensors, binary 0/1) —
adjust freely; the orchestrator's `HttpGrip` client will follow.*

Base URL via `GRIP_URL` (default `http://jetson.local:9001`).

## `GET /grip`
Return whether the gripper is currently holding something, from the closed-circuit
pressure sensor(s).

```jsonc
// response — either form is accepted by the client
{ "grasped": true }        // preferred
{ "raw": 1 }               // or the raw 0/1 also works
```

- `grasped: true` (or `raw: 1`) = circuit closed = something is gripped.
- The orchestrator polls this **right after closing the gripper**. A `false`
  triggers the rectify path: release, re-plan the grasp, retry (up to
  `MAX_GRASP_ATTEMPTS`).

## Optional extras (only if easy)
- `GET /grip/raw` → per-sensor array `{ "sensors": [0,1,0] }` if there are several
  pads — lets us reason about partial/edge grips later.
- A streaming/websocket form if polling latency matters; polling is fine for now.

## Notes
- Keep it dead simple: one boolean is enough for the current loop.
- Debounce on the hardware side if the raw signal is noisy — the orchestrator
  takes the reading at face value.
- Future: a **VLM-based visual grip check** will run *alongside* this sensor as a
  second opinion (see orchestrator README, "Future"). The sensor stays the fast,
  authoritative signal; the VLM catches wrong-part / partial grips the binary
  sensor can't distinguish.
