"""Versioned participant block-order generation shared by designer and runner."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Iterable


SEEDED_FACTORADIC_CYCLE = "seeded_factoradic_cycle.v1"
SUPPORTED_ORDER_ALGORITHMS = (
    SEEDED_FACTORADIC_CYCLE,
    "counterbalanced_rotation",
    "seeded_random_permutation",
    "fixed",
)


@dataclass(frozen=True)
class ParticipantOrder:
    participant_index: int
    cycle_index: int
    permutation_index: int
    algorithm: str
    seed: int
    block_order: tuple[str, ...]


def default_order_policy(*, seed: int, preview_count: int = 12) -> dict[str, object]:
    return {
        "schema": "pps-participant-order-policy.v1",
        "algorithm": SEEDED_FACTORADIC_CYCLE,
        "seed": int(seed),
        "preview_count": max(1, min(100, int(preview_count))),
    }


def _coprime_multiplier(modulus: int, digest: bytes) -> int:
    if modulus <= 1:
        return 0
    candidate = int.from_bytes(digest[:16], "big") % modulus
    candidate = candidate or 1
    while math.gcd(candidate, modulus) != 1:
        candidate = (candidate + 1) % modulus or 1
    return candidate


def _unrank_permutation(items: list[str], rank: int) -> tuple[str, ...]:
    available = list(items)
    result: list[str] = []
    for remaining in range(len(available), 0, -1):
        factor = math.factorial(remaining - 1)
        index, rank = divmod(rank, factor)
        result.append(available.pop(index))
    return tuple(result)


def seeded_factoradic_order(
    block_ids: Iterable[str], *, participant_index: int, seed: int
) -> ParticipantOrder:
    blocks = [str(value) for value in block_ids]
    if not blocks:
        raise ValueError("At least one block is required for participant ordering.")
    if len(set(blocks)) != len(blocks):
        raise ValueError("Participant-order block ids must be unique.")
    if participant_index < 1:
        raise ValueError("participant_index must be at least 1.")
    space = math.factorial(len(blocks))
    zero_index = participant_index - 1
    cycle_index, position = divmod(zero_index, space)
    material = f"{seed}|{'|'.join(blocks)}|{cycle_index}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    multiplier = _coprime_multiplier(space, digest)
    offset = int.from_bytes(digest[16:], "big") % space
    rank = 0 if space == 1 else (multiplier * position + offset) % space
    return ParticipantOrder(
        participant_index=participant_index,
        cycle_index=cycle_index,
        permutation_index=rank,
        algorithm=SEEDED_FACTORADIC_CYCLE,
        seed=int(seed),
        block_order=_unrank_permutation(blocks, rank),
    )


def participant_order(
    block_ids: Iterable[str],
    *,
    participant_index: int,
    policy: dict[str, object] | None = None,
    legacy_algorithm: str = "counterbalanced_rotation",
    legacy_seed: int = 20250604,
) -> ParticipantOrder:
    blocks = [str(value) for value in block_ids]
    if not blocks:
        raise ValueError("At least one block is required for participant ordering.")
    if len(set(blocks)) != len(blocks):
        raise ValueError("Participant-order block ids must be unique.")
    policy = dict(policy or {})
    algorithm = str(policy.get("algorithm") or legacy_algorithm)
    seed = int(policy.get("seed") if policy.get("seed") is not None else legacy_seed)
    if algorithm == SEEDED_FACTORADIC_CYCLE:
        return seeded_factoradic_order(blocks, participant_index=participant_index, seed=seed)
    if participant_index < 1:
        raise ValueError("participant_index must be at least 1.")
    if algorithm == "fixed":
        order = blocks
    elif algorithm == "seeded_random_permutation":
        order = list(blocks)
        random.Random(seed + participant_index * 7919).shuffle(order)
    elif algorithm == "counterbalanced_rotation":
        base = list(blocks)
        random.Random(seed).shuffle(base)
        count = len(base)
        shift = (participant_index - 1) % count
        order = base[shift:] + base[:shift]
        if ((participant_index - 1) // count) % 2 == 1:
            order.reverse()
    else:
        raise ValueError(f"Unsupported participant-order algorithm: {algorithm}")
    space = max(1, math.factorial(len(blocks)))
    return ParticipantOrder(
        participant_index=participant_index,
        cycle_index=(participant_index - 1) // space,
        permutation_index=(participant_index - 1) % space,
        algorithm=algorithm,
        seed=seed,
        block_order=tuple(order),
    )


def order_preview(
    block_ids: Iterable[str], *, policy: dict[str, object], count: int | None = None
) -> list[dict[str, object]]:
    preview_count = count if count is not None else int(policy.get("preview_count") or 12)
    return [
        {
            "participant_index": item.participant_index,
            "participant": f"P{item.participant_index:03d}",
            "cycle_index": item.cycle_index,
            "permutation_index": item.permutation_index,
            "algorithm": item.algorithm,
            "seed": item.seed,
            "block_order": list(item.block_order),
        }
        for item in (
            participant_order(block_ids, participant_index=index, policy=policy)
            for index in range(1, max(1, min(100, int(preview_count))) + 1)
        )
    ]
