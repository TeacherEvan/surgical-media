#!/usr/bin/env python3
"""Stage 3: decorate the timed board with licensed imagery + 3D coil scenes."""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPO = Path("/home/leandi-duplessis/github/workspaces/Agent-Surgery-Skills/surgical-media")
sys.path.insert(0, str(REPO / "scripts"))

from storyboard import assign_start_times  # noqa: E402

MANIFESTS = {
    "a": BASE / "assets2" / "manifest.json",
    "b": BASE / "assets" / "manifest.json",
}
ASSETS = {}
for key, path in MANIFESTS.items():
    for item in json.loads(path.read_text(encoding="utf-8"))["assets"]:
        ASSETS[f"{key}:{item['file'][:2]}"] = (path.parent / item["file"], item["attribution"])

# beat -> (photo key, HUD badge text, accent)
PHOTOS = {
    "hook_friends": ("a:02", "FRIENDS, NOT FOOD", "#7EE787"),
    "look_closer": ("a:03", "LOOK CLOSER", "#38BDF8"),
    "mostly_harmless": ("a:01", "85–90% NON-VENOMOUS", "#7EE787"),
    "defence_only": ("a:10", "BITE = DEFENCE", "#FACC15"),
    "guard_harvest": ("b:02", "CROP GUARD", "#34D399"),
    "rodents_grain": ("a:07", "RODENTS → GRAIN LOSS", "#F59E0B"),
    "rodents_checked": ("b:01", "FREE PEST CONTROL", "#7EE787"),
    "free_control": ("a:04", "NO CHEMICALS NEEDED", "#34D399"),
    "rodent_disease": ("a:09", "RODENTS CARRY DISEASE", "#F472B6"),
    "fewer_outbreaks": ("a:08", "FEWER RATS, FEWER RISKS", "#38BDF8"),
    "prey_too": ("b:06", "PREDATOR & PREY", "#FACC15"),
    "raptors_need": ("a:05", "HAWKS NEED SNAKES", "#38BDF8"),
    "snakes_hunt": ("a:06", "SNAKE EATS SNAKE", "#F59E0B"),
    "forests_spread": ("b:04", "FOREST ENGINEERS", "#7EE787"),
    "seeds_sprout": ("a:04", "SEEDS TRAVEL FARTHER", "#34D399"),
    "venom_medicine": ("a:10", "VENOM → MEDICINE", "#FACC15"),
    "heart_drugs": ("a:06", "CAPTOPRIL FROM VIPERS", "#F472B6"),
    "numbers_falling": ("a:01", "SNAKES IN DECLINE", "#F59E0B"),
    "give_space": ("a:07", "SPACE, NOT FEAR", "#38BDF8"),
    "let_live": ("a:02", "LET THEM LIVE", "#7EE787"),
}

# Three abstract 3D "coil" interludes (standard torus backend; no false anatomy claim).
COIL = {
    "rodents_checked": ("PEST CONTROL // A NATURAL SERVICE", [("anchor_coil_a", "RODENT PRESSURE", "LOWER", [1.55, 0.25, 0.15], "#7EE787")]),
    "prey_too": ("FOOD WEB // PREDATOR AND PREY", [("anchor_coil_a", "IN THE WEB", "BOTH ENDS", [1.55, 0.25, 0.15], "#FACC15"), ("anchor_coil_b", "POPULATION", "BALANCED", [-1.45, -0.65, 0.35], "#38BDF8")]),
    "numbers_falling": ("COIL MOTIF // A POPULATION IN DECLINE", [("anchor_coil_a", "WORLDWIDE", "DECLINING", [1.55, 0.25, 0.15], "#F59E0B"), ("anchor_coil_b", "HABITAT", "SHRINKING", [-1.45, -0.65, 0.35], "#F472B6")]),
}


def coil_spec(title, anchors):
    return {
        "category": "orbital_or_field_3d",
        "hud_title": title,
        "blender_engine": "AUTO_EEVEE",
        "camera_3d": {
            "mode": "orbit",
            "focal_length_mm": 45.0,
            "fstop": 2.4,
            "radius_start": 6.8,
            "radius_end": 5.6,
            "azimuth_start_deg": 12.0,
            "azimuth_end_deg": 68.0,
            "elevation_deg": 26.0,
        },
        "anchors_3d": [
            {
                "anchor_id": aid,
                "label": label,
                "metric": metric,
                "local_pos": pos,
                "accent_hex": accent,
            }
            for aid, label, metric, pos, accent in anchors
        ],
    }


board = json.loads((BASE / "board_timed.json").read_text(encoding="utf-8"))
for scene in board["scenes"]:
    sid = scene["scene_id"]
    accent = PHOTOS[sid][2] if sid in PHOTOS else "#38BDF8"
    elements = []
    if sid in COIL:
        title, anchors = COIL[sid]
        scene["scene_spec"] = coil_spec(title, anchors)
        # No `background` element here: the canvas is already #050811 and a
        # full-frame background painter would cover the 3D+HUD pass.
    else:
        key, badge, _ = PHOTOS[sid]
        path, attribution = ASSETS[key]
        assert path.is_file(), path
        elements.append(
            {
                "type": "image",
                "src": str(path),
                "box": [84, 180, 996, 1500],
                "fit": "cover",
                "kb_zoom": 1.09,
                "fade_in_sec": 0.28,
                "radius": 18,
                "attribution": attribution,
                "attribution_y": 1452,
            }
        )
        elements.append({"type": "hud_badge", "text": badge, "corner": "tl"})
    elements.append({"type": "kinetic_captions", "accent": accent, "size": 34})
    scene["elements"] = elements
    scene["fade_in_sec"] = 0.2
    scene["fade_out_sec"] = 0.2
    dur = float(scene["duration_sec"])
    scene["sfx_events"] = [
        {"t_sec": 0.1, "sfx": "whoosh", "intensity": 0.5},
        {"t_sec": max(0.3, dur - 0.35), "sfx": "chime", "intensity": 0.45},
    ]

# 4.5 s silent close to bring the master to ~60 s.
board["scenes"].append(
    {
        "scene_id": "end_card",
        "archetype": "mixed",
        "narration": "",
        "duration_sec": round(60.0 - sum(float(s["duration_sec"]) for s in board["scenes"]), 3),
        "silent_beat": True,
        "fade_in_sec": 0.5,
        "fade_out_sec": 0.6,
        "scene_spec": coil_spec("SNAKES ARE FRIENDS, NOT FOOD", []),
        "elements": [
            {
                "type": "quote_card",
                "quote": "LET THEM LIVE.",
                "attribution": "Respect the coil",
                "box": [120, 540, 960, 1010],
            }
        ],
        "words": [],
        "sfx_events": [{"t_sec": 0.1, "sfx": "chime", "intensity": 0.9}],
    }
)
board = assign_start_times(board)
out = BASE / "board_final.json"
out.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
print(
    f"wrote {out} — {len(board['scenes'])} scenes, "
    f"{sum(float(s['duration_sec']) for s in board['scenes']):.3f}s, "
    f"{sum(bool(s.get('vo_wav')) for s in board['scenes'])} voiced"
)
