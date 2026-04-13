from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


LABEL_MAP = {
    "bonafide": 0,
    "spoof": 1,
}


SPLIT_CONFIG = {
    "train": {
        "protocol": Path("ASVspoof2019_LA_cm_protocols/ASVspoof2019.LA.cm.train.trn.txt"),
        "audio_dir": Path("ASVspoof2019_LA_train/flac"),
    },
    "dev": {
        "protocol": Path("ASVspoof2019_LA_cm_protocols/ASVspoof2019.LA.cm.dev.trl.txt"),
        "audio_dir": Path("ASVspoof2019_LA_dev/flac"),
    },
    "eval": {
        "protocol": Path("ASVspoof2019_LA_cm_protocols/ASVspoof2019.LA.cm.eval.trl.txt"),
        "audio_dir": Path("ASVspoof2019_LA_eval/flac"),
    },
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_dataset_root = repo_root / "data" / "raw" / "asvspoof2019" / "LA"
    default_output_dir = repo_root / "data" / "interim" / "iep1"

    parser = argparse.ArgumentParser(
        description="Build a validated utterance-level manifest for ASVspoof 2019 LA CM."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=default_dataset_root,
        help="Root directory of the extracted ASVspoof 2019 LA dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where the manifest CSV and summary JSON will be written.",
    )
    return parser.parse_args()


def relative_to_repo(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def parse_protocol_line(split: str, line: str, line_number: int, audio_dir: Path, repo_root: Path) -> dict[str, str | int]:
    columns = line.strip().split()
    if len(columns) != 5:
        raise ValueError(
            f"{split} protocol line {line_number} has {len(columns)} columns; expected 5."
        )

    speaker_id, file_id, unused_meta, attack_id, label_text = columns
    if label_text not in LABEL_MAP:
        raise ValueError(
            f"{split} protocol line {line_number} has unknown label '{label_text}'."
        )

    if label_text == "bonafide" and attack_id != "-":
        raise ValueError(
            f"{split} protocol line {line_number} is bonafide but attack_id is '{attack_id}'."
        )

    if label_text == "spoof" and attack_id == "-":
        raise ValueError(
            f"{split} protocol line {line_number} is spoof but attack_id is '-'."
        )

    audio_path = audio_dir / f"{file_id}.flac"

    return {
        "split": split,
        "speaker_id": speaker_id,
        "file_id": file_id,
        "unused_meta": unused_meta,
        "attack_id": attack_id,
        "label_text": label_text,
        "label": LABEL_MAP[label_text],
        "audio_path": relative_to_repo(repo_root, audio_path),
    }


def build_manifest_rows(dataset_root: Path, repo_root: Path) -> tuple[list[dict[str, str | int]], list[str]]:
    rows: list[dict[str, str | int]] = []
    missing_audio: list[str] = []

    for split, config in SPLIT_CONFIG.items():
        protocol_path = dataset_root / config["protocol"]
        audio_dir = dataset_root / config["audio_dir"]

        if not protocol_path.is_file():
            raise FileNotFoundError(f"Missing protocol file: {protocol_path}")
        if not audio_dir.is_dir():
            raise FileNotFoundError(f"Missing audio directory: {audio_dir}")

        with protocol_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped_line = raw_line.strip()
                if not stripped_line:
                    continue

                row = parse_protocol_line(
                    split=split,
                    line=stripped_line,
                    line_number=line_number,
                    audio_dir=audio_dir,
                    repo_root=repo_root,
                )
                audio_path = repo_root / str(row["audio_path"])
                if not audio_path.is_file():
                    missing_audio.append(str(audio_path))
                rows.append(row)

    return rows, missing_audio


def build_summary(rows: list[dict[str, str | int]], dataset_root: Path, repo_root: Path) -> dict[str, object]:
    split_counts: dict[str, int] = Counter()
    label_counts: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    attack_counts: dict[str, dict[str, int]] = defaultdict(lambda: Counter())

    for row in rows:
        split = str(row["split"])
        label_text = str(row["label_text"])
        attack_id = str(row["attack_id"])

        split_counts[split] += 1
        label_counts[split][label_text] += 1
        attack_counts[split][attack_id] += 1

    ordered_attack_counts = {
        split: dict(sorted(counts.items(), key=lambda item: item[0]))
        for split, counts in attack_counts.items()
    }
    ordered_label_counts = {
        split: dict(sorted(counts.items(), key=lambda item: item[0]))
        for split, counts in label_counts.items()
    }

    return {
        "dataset_root": relative_to_repo(repo_root, dataset_root),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_rows": len(rows),
        "rows_by_split": dict(sorted(split_counts.items(), key=lambda item: item[0])),
        "labels_by_split": dict(sorted(ordered_label_counts.items(), key=lambda item: item[0])),
        "attack_ids_by_split": dict(sorted(ordered_attack_counts.items(), key=lambda item: item[0])),
    }


def write_manifest(rows: list[dict[str, str | int]], output_path: Path) -> None:
    fieldnames = [
        "split",
        "speaker_id",
        "file_id",
        "unused_meta",
        "attack_id",
        "label_text",
        "label",
        "audio_path",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(summary: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    dataset_root = args.dataset_root.resolve()
    output_dir = args.output_dir.resolve()

    rows, missing_audio = build_manifest_rows(dataset_root=dataset_root, repo_root=repo_root)
    if missing_audio:
        preview = "\n".join(missing_audio[:10])
        raise FileNotFoundError(
            f"Found {len(missing_audio)} missing audio files while building the manifest.\n{preview}"
        )

    manifest_path = output_dir / "asvspoof2019_la_cm_utterance_manifest.csv"
    summary_path = output_dir / "asvspoof2019_la_cm_utterance_manifest.summary.json"

    write_manifest(rows=rows, output_path=manifest_path)
    write_summary(
        summary=build_summary(rows=rows, dataset_root=dataset_root, repo_root=repo_root),
        output_path=summary_path,
    )

    print(f"Manifest written to: {manifest_path}")
    print(f"Summary written to: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
