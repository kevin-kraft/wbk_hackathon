# perception deploy — gpu-server

The perception services run in Docker on the **gpu-server**, reached from the
dashboard host over the `ssh gpu-server` LocalForward (18001 yolo, 18002 sam3,
18003 locateanything, 18007 yoloseg). Containers:

| Container | Serves | Host port | Source |
|---|---|---|---|
| `wbk-perception` | yolo `:8001`, locateanything `:8003` | 6767, 6769 | bind-mount `/mnt/vss-data/kip/perception` |
| `wbk-sam3` | sam3 `:8002` | — | (own image) |
| `wbk-yoloseg` | yoloseg `:8007` | 6770 | bind-mount `/mnt/vss-data/kip/perception` |

Canonical source-of-truth on the box: **`/mnt/vss-data/kip/perception`**
(rsync target). Weights: `/mnt/vss-data/kip/weights/{parts_detmask,parts_seg}.pt`.

## `redeploy-wbk-perception.sh` — make the container durable

The original `wbk-perception` baked its code into the image and ran with
`restart=no`, so hot-fixes (`docker cp`) and the container itself were lost on a
reboot. This script recreates it **durably**: canonical source bind-mounted,
`--restart unless-stopped`, a supervisord config that runs **only** yolo +
locateanything (sam3/yoloseg have their own containers — no double GPU load),
and a supervisorctl control socket.

```bash
scp deploy/perception/redeploy-wbk-perception.sh gpu-server:/tmp/
ssh gpu-server 'bash /tmp/redeploy-wbk-perception.sh'   # bounces yolo+locate briefly
```

Run it in a quiet moment — it reloads both models (the LocateAnything-3B VLM
takes ~a minute). Idempotent; safe to re-run.

## Updating perception code afterwards (no rebuild)

Source is bind-mounted, so:

```bash
# edit /mnt/vss-data/kip/perception/... on the box (or rsync perception/ to it), then:
docker exec wbk-perception supervisorctl \
  -c /app/perception/supervisord.wbk-perception.conf restart locateanything   # or: yolo
```

## Teardown (after the competition)

```bash
docker rm -f wbk-perception wbk-sam3 wbk-yoloseg
```
