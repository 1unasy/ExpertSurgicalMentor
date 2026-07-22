# Syringe/Pill object detector dataset

Classes must use these exact indices:

```text
0 syringe
1 pill
```

Extract candidate images:

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
PYTHONPATH=src/lerobot/src python scripts/extract_object_yolo_frames.py
```

Label every visible syringe and pill bounding box. Images containing neither class remain valid
negative samples with empty label files. Export the labeled result to this layout:

```text
labeled/
├── train/images
├── train/labels
├── valid/images
└── valid/labels
```

Keep frames from the same episode in only one split to avoid video-frame leakage. Recommended split
is 64 train episodes and 16 validation episodes. After labeling, train with:

```bash
DEVICE=0 BATCH=8 ./scripts/train_object_yolo.sh
```
