from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from PIL import Image

from sitewatch_ml.audit import IMAGE_SUFFIXES, difference_hash
from sitewatch_ml.io import dataset_fingerprint, sha256_file, write_json
from sitewatch_ml.models import SplitConfig, SplitEntry, SplitManifest


def create_split_manifest(
    image_dir: Path,
    output_path: Path,
    split_config: SplitConfig,
    seed: int,
) -> SplitManifest:
    image_paths = sorted(
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    hashes = {path: sha256_file(path) for path in image_paths}
    perceptual = {}
    for path in image_paths:
        with Image.open(path) as image:
            perceptual[path] = difference_hash(image)

    groups = _duplicate_safe_groups(
        image_paths,
        perceptual,
        split_config.near_duplicate_hamming_distance,
        image_dir,
    )
    assignments = _assign_groups(groups, len(image_paths), split_config, seed)
    entries = [
        SplitEntry(
            relative_path=path.relative_to(image_dir).as_posix(),
            split=assignments[group_id],
            group_id=group_id,
            sha256=hashes[path],
        )
        for group_id, group_paths in sorted(groups.items())
        for path in sorted(group_paths)
    ]
    counts: defaultdict[str, int] = defaultdict(int)
    for entry in entries:
        counts[entry.split] += 1
    manifest = SplitManifest(
        dataset_fingerprint=dataset_fingerprint(
            (entry.relative_path, entry.sha256) for entry in entries
        ),
        seed=seed,
        entries=entries,
        counts={name: counts[name] for name in ("train", "validation", "test")},
    )
    write_json(output_path, manifest)
    return manifest


def _duplicate_safe_groups(
    paths: list[Path],
    perceptual: dict[Path, int],
    max_distance: int,
    image_dir: Path,
) -> dict[str, list[Path]]:
    parent = list(range(len(paths)))

    def find(index: int) -> int:
        if parent[index] != index:
            parent[index] = find(parent[index])
        return parent[index]

    for left in range(len(paths)):
        for right in range(left + 1, len(paths)):
            distance = (perceptual[paths[left]] ^ perceptual[paths[right]]).bit_count()
            if distance <= max_distance:
                parent[find(right)] = find(left)

    grouped: defaultdict[int, list[Path]] = defaultdict(list)
    for index, path in enumerate(paths):
        grouped[find(index)].append(path)
    result: dict[str, list[Path]] = {}
    for group_paths in grouped.values():
        identity = "\n".join(sorted(path.relative_to(image_dir).as_posix() for path in group_paths))
        group_id = hashlib.sha256(identity.encode()).hexdigest()[:16]
        result[group_id] = group_paths
    return result


def _assign_groups(
    groups: dict[str, list[Path]], total: int, config: SplitConfig, seed: int
) -> dict[str, str]:
    targets = {
        "train": total * config.train,
        "validation": total * config.validation,
        "test": total * config.test,
    }
    counts = {name: 0 for name in targets}
    assignments: dict[str, str] = {}
    ordered_groups = sorted(
        groups,
        key=lambda group_id: hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest(),
    )
    for group_id in ordered_groups:
        split = max(targets, key=lambda name: targets[name] - counts[name])
        assignments[group_id] = split
        counts[split] += len(groups[group_id])
    return assignments
