from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median


EXPECTED_SAMPLE_RATE = 16000
SHORT_WINDOW_THRESHOLD_SECONDS = 1.5
TARGET_WINDOW_SECONDS = 3.0


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_manifest_path = (
        repo_root
        / "data"
        / "interim"
        / "iep1"
        / "asvspoof2019_la_cm_utterance_manifest.csv"
    )
    default_output_dir = repo_root / "data" / "interim" / "iep1"

    parser = argparse.ArgumentParser(
        description="Inspect ASVspoof 2019 LA FLAC metadata using the utterance manifest."
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=default_manifest_path,
        help="Path to the utterance-level manifest CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where metadata CSV and summary JSON will be written.",
    )
    parser.add_argument(
        "--limit-per-split",
        type=int,
        default=None,
        help="Optional cap on the number of manifest rows to inspect per split.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default=None,
        help="Optional filename prefix for the generated outputs.",
    )
    return parser.parse_args()


def relative_to_repo(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def parse_flac_streaminfo(audio_path: Path) -> dict[str, int | float]:
    with audio_path.open("rb") as handle:
        magic = handle.read(4)
        if magic != b"fLaC":
            raise ValueError(f"{audio_path} is not a valid FLAC file.")

        header = handle.read(4)
        if len(header) != 4:
            raise ValueError(f"{audio_path} is missing the FLAC metadata header.")

        block_type = header[0] & 0x7F
        block_length = int.from_bytes(header[1:], "big")
        if block_type != 0:
            raise ValueError(
                f"{audio_path} does not start with a STREAMINFO block (found type {block_type})."
            )
        if block_length != 34:
            raise ValueError(
                f"{audio_path} has unexpected STREAMINFO length {block_length}; expected 34."
            )

        streaminfo = handle.read(block_length)
        if len(streaminfo) != block_length:
            raise ValueError(f"{audio_path} has a truncated STREAMINFO block.")

    sample_fields = int.from_bytes(streaminfo[10:18], "big")
    sample_rate = (sample_fields >> 44) & 0xFFFFF
    num_channels = ((sample_fields >> 41) & 0x7) + 1
    bits_per_sample = ((sample_fields >> 36) & 0x1F) + 1
    total_samples = sample_fields & 0xFFFFFFFFF

    if sample_rate <= 0:
        raise ValueError(f"{audio_path} has invalid sample rate {sample_rate}.")

    duration_seconds = total_samples / sample_rate

    return {
        "sample_rate": sample_rate,
        "num_channels": num_channels,
        "bits_per_sample": bits_per_sample,
        "total_samples": total_samples,
        "duration_seconds": duration_seconds,
    }


def summarize_durations(values: list[float]) -> dict[str, float]:
    sorted_values = sorted(values)
    count = len(sorted_values)

    def percentile(fraction: float) -> float:
        if count == 1:
            return sorted_values[0]
        index = (count - 1) * fraction
        lower = math.floor(index)
        upper = math.ceil(index)
        if lower == upper:
            return sorted_values[lower]
        weight = index - lower
        return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight

    return {
        "min": round(sorted_values[0], 6),
        "max": round(sorted_values[-1], 6),
        "mean": round(mean(sorted_values), 6),
        "median": round(median(sorted_values), 6),
        "p05": round(percentile(0.05), 6),
        "p95": round(percentile(0.95), 6),
    }


def inspect_manifest(
    manifest_path: Path,
    repo_root: Path,
    limit_per_split: int | None = None,
) -> tuple[list[dict[str, str | int | float]], dict[str, object]]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    rows: list[dict[str, str | int | float]] = []
    errors: list[dict[str, str]] = []
    rows_by_split: Counter[str] = Counter()
    sample_rates_by_split: dict[str, Counter[int]] = defaultdict(Counter)
    channels_by_split: dict[str, Counter[int]] = defaultdict(Counter)
    bits_per_sample_by_split: dict[str, Counter[int]] = defaultdict(Counter)
    short_counts_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    durations_by_split: dict[str, list[float]] = defaultdict(list)
    seen_by_split: Counter[str] = Counter()

    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for manifest_row in reader:
            split = manifest_row["split"]
            if limit_per_split is not None and seen_by_split[split] >= limit_per_split:
                continue

            audio_path = repo_root / manifest_row["audio_path"]

            try:
                metadata = parse_flac_streaminfo(audio_path)
            except Exception as exc:
                errors.append(
                    {
                        "split": split,
                        "file_id": manifest_row["file_id"],
                        "audio_path": relative_to_repo(repo_root, audio_path),
                        "error": str(exc),
                    }
                )
                continue

            seen_by_split[split] += 1
            duration_seconds = float(metadata["duration_seconds"])
            sample_rate = int(metadata["sample_rate"])
            num_channels = int(metadata["num_channels"])
            bits_per_sample = int(metadata["bits_per_sample"])
            total_samples = int(metadata["total_samples"])

            short_lt_1_5 = duration_seconds < SHORT_WINDOW_THRESHOLD_SECONDS
            short_lt_3_0 = duration_seconds < TARGET_WINDOW_SECONDS

            row = {
                **manifest_row,
                "sample_rate": sample_rate,
                "num_channels": num_channels,
                "bits_per_sample": bits_per_sample,
                "total_samples": total_samples,
                "duration_seconds": round(duration_seconds, 6),
                "is_sample_rate_16k": int(sample_rate == EXPECTED_SAMPLE_RATE),
                "is_mono": int(num_channels == 1),
                "is_shorter_than_1_5s": int(short_lt_1_5),
                "is_shorter_than_3_0s": int(short_lt_3_0),
            }
            rows.append(row)

            rows_by_split[split] += 1
            sample_rates_by_split[split][sample_rate] += 1
            channels_by_split[split][num_channels] += 1
            bits_per_sample_by_split[split][bits_per_sample] += 1
            short_counts_by_split[split]["shorter_than_1_5s"] += int(short_lt_1_5)
            short_counts_by_split[split]["shorter_than_3_0s"] += int(short_lt_3_0)
            short_counts_by_split[split]["at_least_3_0s"] += int(not short_lt_3_0)
            durations_by_split[split].append(duration_seconds)

    if errors:
        preview = "\n".join(
            f"{error['file_id']}: {error['error']}" for error in errors[:10]
        )
        raise RuntimeError(
            f"Encountered {len(errors)} FLAC metadata parsing errors.\n{preview}"
        )

    duration_summary_by_split = {
        split: summarize_durations(values)
        for split, values in sorted(durations_by_split.items(), key=lambda item: item[0])
    }

    summary = {
        "manifest_path": relative_to_repo(repo_root, manifest_path),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_sample_rate": EXPECTED_SAMPLE_RATE,
        "short_window_threshold_seconds": SHORT_WINDOW_THRESHOLD_SECONDS,
        "target_window_seconds": TARGET_WINDOW_SECONDS,
        "limit_per_split": limit_per_split,
        "total_rows": len(rows),
        "rows_by_split": dict(sorted(rows_by_split.items(), key=lambda item: item[0])),
        "sample_rates_by_split": {
            split: dict(sorted(counts.items(), key=lambda item: item[0]))
            for split, counts in sorted(sample_rates_by_split.items(), key=lambda item: item[0])
        },
        "channels_by_split": {
            split: dict(sorted(counts.items(), key=lambda item: item[0]))
            for split, counts in sorted(channels_by_split.items(), key=lambda item: item[0])
        },
        "bits_per_sample_by_split": {
            split: dict(sorted(counts.items(), key=lambda item: item[0]))
            for split, counts in sorted(bits_per_sample_by_split.items(), key=lambda item: item[0])
        },
        "duration_summary_by_split": duration_summary_by_split,
        "windowing_eligibility_by_split": {
            split: dict(sorted(counts.items(), key=lambda item: item[0]))
            for split, counts in sorted(short_counts_by_split.items(), key=lambda item: item[0])
        },
    }

    return rows, summary


def write_csv(rows: list[dict[str, str | int | float]], output_path: Path) -> None:
    if not rows:
        raise ValueError("No rows available to write.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(summary: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = args.manifest_path.resolve()
    output_dir = args.output_dir.resolve()

    rows, summary = inspect_manifest(
        manifest_path=manifest_path,
        repo_root=repo_root,
        limit_per_split=args.limit_per_split,
    )

    if args.output_prefix:
        output_prefix = args.output_prefix
    elif args.limit_per_split is not None:
        output_prefix = f"asvspoof2019_la_audio_metadata_sample_{args.limit_per_split}_per_split"
    else:
        output_prefix = "asvspoof2019_la_audio_metadata"

    metadata_output_path = output_dir / f"{output_prefix}.csv"
    summary_output_path = output_dir / f"{output_prefix}.summary.json"

    write_csv(rows=rows, output_path=metadata_output_path)
    write_json(summary=summary, output_path=summary_output_path)

    print(f"Audio metadata written to: {metadata_output_path}")
    print(f"Summary written to: {summary_output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
