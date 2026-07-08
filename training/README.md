# YOLOv26 training — parts detection & segmentation

Trains custom **YOLOv26** models (detection + segmentation) for the disassembly
parts on synthetic Isaac-Sim data, to feed the perception service and, via masks,
the 6DoF pose stage.

## Where things live

| | Path |
|---|---|
| Code (this dir, version-controlled) | `training/` in the repo |
| Server workspace (3.3 TB network drive) | `/mnt/vss-data/kip/` |
| Source renders (Isaac SDG output) | `~/output/` on `gpu-server` (16 GB, on root disk) |
| Converted YOLO datasets | `/mnt/vss-data/kip/datasets/{parts_det,parts_seg}/` |
| Training runs + checkpoints | `/mnt/vss-data/kip/runs/<name>/` |
| venv (ultralytics + yolo26) | `/mnt/vss-data/kip/venv/yolo/` |

**Compute:** `gpu-server` (`ssh gpu-server`), 8× RTX PRO 6000 Blackwell, shared with
other teams. Pin to an idle GPU (`--device N`; check `nvidia-smi` first) and keep
everything on `/mnt/vss-data` — the root disk sits at ~97%.

## One-time setup (on the server)

```bash
ssh gpu-server 'bash -s' < setup_server.sh      # builds /mnt/vss-data/kip/venv/yolo
```
Reuses the server's working Blackwell torch (`2.12.1+cu132`) via
`--system-site-packages`; only ultralytics is installed into the venv.

## 1. Convert Isaac renders → YOLO dataset

The converter reads the SDG pipeline's per-frame `bbox_2d` / `instance` /
`semantic` / `semantic_labels` files and emits an Ultralytics dataset (images are
**symlinked**, not copied). Run it inside the venv on the server.

```bash
source /mnt/vss-data/kip/venv/yolo/bin/activate
cd /mnt/vss-data/kip/code

# detection labels (boxes from bbox_2d)
python isaac_to_yolo.py --task det \
  --src /home/ubuntu/output/robot_subset_train \
  --out /mnt/vss-data/kip/datasets/parts_det

# segmentation labels (per-instance polygons via instance∩semantic)
python isaac_to_yolo.py --task seg \
  --src /home/ubuntu/output/robot_subset_train \
  --out /mnt/vss-data/kip/datasets/parts_seg
```

Useful flags: `--limit N` (smoke test on N frames), `--include a,b,c` (restrict
classes), `--class-map map.json` (merge/rename classes), `--val-frac 0.1`.
Class names are the sim's **native mesh names** (kept so pose can key meshes off
the class). Inspect the generated `data.yaml` for the discovered class list.

## 2. Train

Use the **supervisor** — it auto-resumes from `last.pt` if the run crashes
(CUDA hiccup, OOM, SSH drop). Wrap it in `screen` so it survives logout.

```bash
# detection (GPU 0)
screen -S det
bash /mnt/vss-data/kip/code/train_supervised.sh \
  --data /mnt/vss-data/kip/datasets/parts_det/data.yaml \
  --model yolo26m.pt --name parts_det_v1 --device 0 \
  --epochs 120 --imgsz 1536 --batch 16
# Ctrl-A D to detach

# segmentation (GPU 2) — in a second screen
screen -S seg
bash /mnt/vss-data/kip/code/train_supervised.sh \
  --data /mnt/vss-data/kip/datasets/parts_seg/data.yaml \
  --model yolo26m-seg.pt --name parts_seg_v1 --device 2 \
  --epochs 120 --imgsz 1536 --batch 16
```

`--epochs` is computed from a timing probe to fit the wall-clock budget (see
below). Reattach with `screen -r det` / `screen -r seg`.

### Resumability & checkpoints

- **`last.pt`** is written every epoch → a crash loses at most the current epoch.
- **Manual resume:** `python train.py … --name parts_det_v1 --resume` (or let the
  supervisor do it automatically).
- **Rolling last-5 epoch snapshots:** `--save-period 1 --keep-last 5` (defaults)
  keep `epoch{N}.pt` for the 5 newest epochs; `best.pt` and `last.pt` are never
  pruned. Tune with `--keep-last`.
- Weights: `/mnt/vss-data/kip/runs/<name>/weights/{best,last,epoch*}.pt`.

### Estimating epochs for a time budget (probe)

```bash
# short 4-epoch probe, read steady-state sec/epoch, compute epochs for N hours
python train.py --data <data.yaml> --model yolo26m.pt --name _probe \
  --epochs 4 --imgsz 1536 --batch 16 --device 0
# then: epochs = floor((hours*3600 - overhead) / sec_per_epoch)
```

## 3. Deploy to the perception service

Point the YOLO service at the trained weights:

```bash
export YOLO_WEIGHTS=/mnt/vss-data/kip/weights/parts_det_best.pt   # after copying best.pt here
```

(`perception/services/shared/config.py` → `YOLO_WEIGHTS`, default `yolo11n.pt`.)
The seg weights feed the perception→pose handoff — YOLO-seg masks become the
`mask_b64` instances the FoundationPose/GigaPose services consume.

## Data format reference (Isaac SDG per frame)

`rgb_NNNN.png` (2448×2048) · `bbox_2d_NNNN.json` `{"data":[[semId,x1,y1,x2,y2,occ]…]}` ·
`semantic_NNNN.png` (class-id map) · `instance_NNNN.png` (instance-id map) ·
`semantic_labels_NNNN.json` (`idToLabels`) · `pose_NNNN.json` (6DoF GT) ·
`obb_2d` · `depth`. `BACKGROUND`/`UNLABELLED` are dropped in conversion.
