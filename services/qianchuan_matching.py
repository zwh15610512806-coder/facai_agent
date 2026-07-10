"""Core planning algorithm for deterministic Qianchuan material matching."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def plan_auto_match(
    db,
    *,
    viral_script_model,
    binding_model,
    latest_materials: Callable[[Any], list],
    structured_candidate: Callable[[Any, Any], dict | None],
    min_score: int,
    min_margin: int,
) -> dict:
    materials = latest_materials(db)
    scripts = db.query(viral_script_model).order_by(viral_script_model.id.asc()).all()
    existing_rows = db.query(binding_model.script_id, binding_model.material_id).all()
    bound_by_script: dict[int, set[str]] = {}
    globally_bound_materials: set[str] = set()
    for script_id, material_id in existing_rows:
        bound_by_script.setdefault(script_id, set()).add(material_id)
        globally_bound_materials.add(material_id)

    matches = []
    ambiguous = []
    candidates = []
    no_candidate = 0
    skipped_existing = 0
    for script in scripts:
        bound_ids = bound_by_script.get(script.id, set())
        if bound_ids:
            skipped_existing += len(bound_ids)
            continue

        script_candidates = []
        for material in materials:
            if material.material_id in globally_bound_materials:
                continue
            item = structured_candidate(script, material)
            if item:
                script_candidates.append(item)
        script_candidates.sort(
            key=lambda item: (item["score"], item["transaction_amount"]),
            reverse=True,
        )
        if not script_candidates:
            no_candidate += 1
            continue

        high_confidence = [
            item for item in script_candidates
            if int(item.get("score") or 0) >= min_score
        ]
        if len(high_confidence) == 1:
            matches.append(high_confidence[0])
        elif len(high_confidence) > 1:
            top_score = int(high_confidence[0].get("score") or 0)
            close = [
                item for item in high_confidence
                if top_score - int(item.get("score") or 0) <= 3
            ]
            if len(close) > 1:
                ambiguous.append({
                    "script_id": script.id,
                    "script_title": script.title,
                    "candidates": close[:5],
                })
            else:
                matches.append(high_confidence[0])
        else:
            candidates.append({
                "script_id": script.id,
                "script_title": script.title,
                "candidates": script_candidates[:5],
            })

    resolved_matches = []
    matches_by_material: dict[str, list[dict]] = {}
    for item in matches:
        material_id = str(item.get("material_id") or "")
        matches_by_material.setdefault(material_id, []).append(item)
    for material_id, items in matches_by_material.items():
        if len(items) == 1:
            resolved_matches.append(items[0])
            continue
        items.sort(
            key=lambda item: (
                int(item.get("score") or 0),
                float(item.get("transaction_amount") or 0),
            ),
            reverse=True,
        )
        top_score = int(items[0].get("score") or 0)
        second_score = int(items[1].get("score") or 0)
        if top_score - second_score >= min_margin:
            resolved_matches.append(items[0])
            continue
        ambiguous.append({
            "material_id": material_id,
            "material_name": items[0].get("material_name") or "",
            "script_id": items[0].get("script_id"),
            "script_title": items[0].get("script_title") or "",
            "candidates": items[:5],
        })

    return {
        "total_scripts": len(scripts),
        "processed": len(scripts),
        "material_count": len(materials),
        "planned": len(resolved_matches),
        "would_create": len(resolved_matches),
        "created": 0,
        "created_bindings": 0,
        "skipped_existing": skipped_existing,
        "already_bound": skipped_existing,
        "no_candidate": no_candidate,
        "review_count": len(candidates),
        "ambiguous_count": len(ambiguous),
        "matches": resolved_matches,
        "ambiguous": ambiguous,
        "candidates": candidates,
        "candidates_preview": (ambiguous + candidates)[:20],
    }
