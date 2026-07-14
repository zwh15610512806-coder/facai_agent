"""Business rules for creator CRM, collaborations, and sample fulfilment."""
from __future__ import annotations

import math
import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from creator_models import (
    BdMember,
    Creator,
    CreatorAddress,
    CreatorCollaboration,
    CreatorCollaborationProduct,
    CreatorFollowup,
    CreatorPortrait,
    CreatorSampleOrder,
    CreatorSampleOrderItem,
    normalize_douyin_handle,
    normalize_platform_uid,
)
from creator_schemas import (
    BdMemberCreate,
    BdMemberUpdate,
    CreatorAddressCreate,
    CreatorAddressUpdate,
    CreatorCollaborationCreate,
    CreatorCollaborationUpdate,
    CreatorCreate,
    CreatorFollowupCreate,
    CreatorFollowupUpdate,
    CreatorPortraitUpdate,
    CreatorSampleOrderCreate,
    CreatorSampleOrderUpdate,
    CreatorUpdate,
)
from models import Product


COLLABORATION_TRANSITIONS = {
    "planned": {"planned", "in_progress", "completed", "cancelled"},
    "in_progress": {"in_progress", "completed", "cancelled"},
    "completed": {"completed"},
    "cancelled": {"cancelled"},
}
SAMPLE_TRANSITIONS = {
    "pending_shipment": {"shipped", "cancelled"},
    "shipped": {"received"},
    "received": set(),
    "cancelled": set(),
}


def _value(value):
    return value.value if isinstance(value, Enum) else value


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _commit(db: Session, *, conflict_detail: str):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail) from exc


def _get_creator(db: Session, creator_id: int, *, include_archived: bool = False) -> Creator:
    query = db.query(Creator).filter(Creator.id == creator_id)
    if not include_archived:
        query = query.filter(Creator.archived_at.is_(None))
    creator = query.first()
    if not creator:
        raise HTTPException(status_code=404, detail="达人不存在")
    return creator


def _get_member(db: Session, member_id: int | None) -> BdMember | None:
    if member_id is None:
        return None
    member = db.query(BdMember).filter(BdMember.id == member_id, BdMember.active.is_(True)).first()
    if not member:
        raise HTTPException(status_code=422, detail="BD 负责人不存在或已停用")
    return member


def mask_phone(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) == 1:
        return "***"
    if len(text) >= 11:
        return f"{text[:3]}****{text[-4:]}"
    if len(text) >= 7:
        return f"{text[:2]}***{text[-2:]}"
    return text[:1] + "*" * max(2, len(text) - 1)


def mask_wechat(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) == 1:
        return "****"
    visible = 1 if len(text) <= 4 else min(4, max(1, len(text) - 1))
    return text[:visible] + "*" * max(4, len(text) - visible)


def mask_name(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "***"
    if len(text) == 1:
        return "**"
    return text[0] + "**"


def _masked_address(address: CreatorAddress) -> dict:
    return {
        "id": address.id,
        "creator_id": address.creator_id,
        "recipient_name": mask_name(address.recipient_name),
        "phone": mask_phone(address.phone) or "***",
        "province": address.province,
        "city": address.city,
        "district": address.district,
        "detail": "***",
        "is_default": bool(address.is_default),
        "created_at": address.created_at,
        "updated_at": address.updated_at,
    }


def _full_address(address: CreatorAddress) -> dict:
    return {
        "id": address.id,
        "creator_id": address.creator_id,
        "recipient_name": address.recipient_name,
        "phone": address.phone,
        "province": address.province,
        "city": address.city,
        "district": address.district,
        "detail": address.detail,
        "is_default": bool(address.is_default),
        "created_at": address.created_at,
        "updated_at": address.updated_at,
    }


def creator_metrics(db: Session, creator_id: int) -> dict:
    valid = [
        CreatorCollaboration.creator_id == creator_id,
        CreatorCollaboration.amount_status == "confirmed",
        CreatorCollaboration.status != "cancelled",
    ]
    total, count = db.query(
        func.coalesce(func.sum(CreatorCollaboration.actual_paid_cents), 0),
        func.count(CreatorCollaboration.id),
    ).filter(*valid).one()
    latest = db.query(func.max(CreatorCollaboration.collaboration_date)).filter(
        CreatorCollaboration.creator_id == creator_id,
        CreatorCollaboration.status != "cancelled",
    ).scalar()
    total = int(total or 0)
    count = int(count or 0)
    return {
        "confirmed_paid_cents": total,
        "confirmed_collaboration_count": count,
        "average_paid_cents": total // count if count else 0,
        "latest_collaboration_date": latest,
    }


def _followup_dates(db: Session, creator_id: int) -> tuple[datetime | None, datetime | None]:
    latest = db.query(CreatorFollowup).filter(CreatorFollowup.creator_id == creator_id).order_by(
        CreatorFollowup.followed_up_at.desc(), CreatorFollowup.id.desc()
    ).first()
    return (
        latest.followed_up_at if latest else None,
        latest.next_followup_at if latest else None,
    )


def portrait_summary(creator: Creator, metrics: dict) -> str:
    portrait = creator.portrait
    parts: list[str] = []
    if portrait:
        categories = portrait.primary_categories or []
        formats = portrait.content_formats or []
        if categories:
            parts.append("主营" + "、".join(categories[:3]))
        if formats:
            parts.append("内容以" + "、".join(formats[:3]) + "为主")
        if portrait.follower_count is not None:
            if portrait.follower_count >= 10000:
                parts.append(f"{portrait.follower_count / 10000:.1f}万粉")
            else:
                parts.append(f"{portrait.follower_count}粉")
        if portrait.fit_score:
            parts.append(f"合作匹配度{portrait.fit_score}/5")
    if metrics["confirmed_collaboration_count"]:
        paid = metrics["confirmed_paid_cents"] / 100
        parts.append(f"已确认合作{metrics['confirmed_collaboration_count']}次，累计实付¥{paid:,.2f}")
    return "；".join(parts) or "画像资料待完善"


def creator_list_item(
    db: Session,
    creator: Creator,
    *,
    metrics: dict | None = None,
    followup_dates: tuple[datetime | None, datetime | None] | None = None,
) -> dict:
    metrics = metrics if metrics is not None else creator_metrics(db, creator.id)
    last_followup_at, next_followup_at = (
        followup_dates if followup_dates is not None else _followup_dates(db, creator.id)
    )
    portrait = creator.portrait
    return {
        "id": creator.id,
        "platform": creator.platform,
        "platform_uid": creator.platform_uid,
        "douyin_handle": creator.douyin_handle,
        "nickname": creator.nickname,
        "avatar_url": creator.avatar_url,
        "mcn_name": creator.mcn_name,
        "owner_id": creator.owner_id,
        "owner_name": creator.owner.name if creator.owner else None,
        "stage": creator.stage,
        "tags": creator.tags or [],
        "follower_count": portrait.follower_count if portrait else None,
        "primary_categories": portrait.primary_categories if portrait else [],
        "masked_contact_phone": mask_phone(creator.contact_phone),
        "metrics": metrics,
        "last_followup_at": last_followup_at,
        "next_followup_at": next_followup_at,
        "archived_at": creator.archived_at,
    }


def creator_detail(db: Session, creator: Creator) -> dict:
    data = creator_list_item(db, creator)
    data.update(
        {
            "homepage_url": creator.homepage_url,
            "contact_name": mask_name(creator.contact_name) if creator.contact_name else None,
            "masked_wechat_id": mask_wechat(creator.wechat_id),
            "portrait": creator.portrait,
            "addresses": [_masked_address(item) for item in creator.addresses],
            "portrait_summary": portrait_summary(creator, data["metrics"]),
            "collaboration_count": len(creator.collaborations),
            "followup_count": len(creator.followups),
            "sample_order_count": len(creator.sample_orders),
            "created_at": creator.created_at,
            "updated_at": creator.updated_at,
        }
    )
    return data


def list_members(db: Session) -> list[BdMember]:
    return db.query(BdMember).order_by(BdMember.active.desc(), BdMember.name).all()


def create_member(db: Session, payload: BdMemberCreate) -> BdMember:
    member = BdMember(name=payload.name)
    db.add(member)
    _commit(db, conflict_detail="BD 成员名称已存在")
    db.refresh(member)
    return member


def update_member(db: Session, member_id: int, payload: BdMemberUpdate) -> BdMember:
    member = db.query(BdMember).filter(BdMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="BD 成员不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    _commit(db, conflict_detail="BD 成员名称已存在")
    db.refresh(member)
    return member


def _identity_conflict(
    db: Session,
    *,
    platform: str,
    platform_uid_normalized: str | None,
    douyin_handle_normalized: str | None,
    exclude_id: int | None = None,
) -> bool:
    conditions = []
    if platform_uid_normalized:
        conditions.append(Creator.platform_uid_normalized == platform_uid_normalized)
    if douyin_handle_normalized:
        conditions.append(Creator.douyin_handle_normalized == douyin_handle_normalized)
    if not conditions:
        return False
    query = db.query(Creator.id).filter(Creator.platform == platform, or_(*conditions))
    if exclude_id:
        query = query.filter(Creator.id != exclude_id)
    return query.first() is not None


def create_creator(db: Session, payload: CreatorCreate) -> Creator:
    _get_member(db, payload.owner_id)
    platform = payload.platform.strip().lower()
    uid_normalized = normalize_platform_uid(payload.platform_uid)
    handle = normalize_douyin_handle(payload.douyin_handle)
    handle_normalized = handle.casefold() if handle else None
    if _identity_conflict(
        db,
        platform=platform,
        platform_uid_normalized=uid_normalized,
        douyin_handle_normalized=handle_normalized,
    ):
        raise HTTPException(status_code=409, detail="达人身份已存在")
    creator = Creator(
        **payload.model_dump(exclude={"platform", "stage", "douyin_handle"}),
        platform=platform,
        douyin_handle=handle,
        platform_uid_normalized=uid_normalized,
        douyin_handle_normalized=handle_normalized,
        stage=_value(payload.stage),
    )
    db.add(creator)
    _commit(db, conflict_detail="达人身份已存在")
    db.refresh(creator)
    return creator


def update_creator(db: Session, creator_id: int, payload: CreatorUpdate) -> Creator:
    creator = _get_creator(db, creator_id)
    changes = payload.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        _get_member(db, changes["owner_id"])
    platform = (changes.get("platform") or creator.platform).strip().lower()
    raw_uid = changes.get("platform_uid", creator.platform_uid)
    raw_handle = changes.get("douyin_handle", creator.douyin_handle)
    uid_normalized = normalize_platform_uid(raw_uid)
    handle = normalize_douyin_handle(raw_handle)
    handle_normalized = handle.casefold() if handle else None
    if not uid_normalized and not handle_normalized:
        raise HTTPException(status_code=422, detail="官方达人 ID 和抖音号至少保留一项")
    if _identity_conflict(
        db,
        platform=platform,
        platform_uid_normalized=uid_normalized,
        douyin_handle_normalized=handle_normalized,
        exclude_id=creator.id,
    ):
        raise HTTPException(status_code=409, detail="达人身份已存在")
    for field, value in changes.items():
        setattr(creator, field, _value(value))
    creator.platform = platform
    creator.douyin_handle = handle
    creator.platform_uid_normalized = uid_normalized
    creator.douyin_handle_normalized = handle_normalized
    _commit(db, conflict_detail="达人身份已存在")
    db.refresh(creator)
    return creator


def archive_creator(db: Session, creator_id: int) -> Creator:
    creator = _get_creator(db, creator_id)
    creator.archived_at = _utcnow()
    db.commit()
    return creator


def list_creators(
    db: Session,
    *,
    search: str | None,
    stage: str | None,
    owner_id: int | None,
    category: str | None,
    follower_tier: str | None,
    sort: str,
    page: int,
    per_page: int,
) -> dict:
    query = (
        db.query(Creator)
        .options(joinedload(Creator.owner), joinedload(Creator.portrait))
        .filter(Creator.archived_at.is_(None))
    )
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Creator.nickname.ilike(term),
                Creator.douyin_handle.ilike(term),
                Creator.platform_uid.ilike(term),
                Creator.mcn_name.ilike(term),
            )
        )
    if stage:
        query = query.filter(Creator.stage == stage)
    if owner_id:
        query = query.filter(Creator.owner_id == owner_id)
    if category or follower_tier:
        query = query.join(CreatorPortrait)
    if category:
        category_values = func.json_each(CreatorPortrait.primary_categories).table_valued(
            "key", "value"
        ).alias("creator_category_values")
        query = query.filter(
            exists(
                select(1)
                .select_from(category_values)
                .where(category_values.c.value == category)
            )
        )
    if follower_tier:
        count = CreatorPortrait.follower_count
        ranges = {
            "under_10k": count < 10_000,
            "10k_100k": (count >= 10_000) & (count < 100_000),
            "100k_500k": (count >= 100_000) & (count < 500_000),
            "500k_1m": (count >= 500_000) & (count < 1_000_000),
            "1m_plus": count >= 1_000_000,
        }
        condition = ranges.get(follower_tier)
        if condition is None:
            raise HTTPException(status_code=422, detail="粉丝量级无效")
        query = query.filter(condition)

    total = query.count()
    if sort == "paid_desc":
        paid = db.query(func.coalesce(func.sum(CreatorCollaboration.actual_paid_cents), 0)).filter(
            CreatorCollaboration.creator_id == Creator.id,
            CreatorCollaboration.amount_status == "confirmed",
            CreatorCollaboration.status != "cancelled",
        ).correlate(Creator).scalar_subquery()
        query = query.order_by(paid.desc(), Creator.updated_at.desc())
    elif sort == "recent_followup":
        latest = db.query(func.max(CreatorFollowup.followed_up_at)).filter(
            CreatorFollowup.creator_id == Creator.id
        ).correlate(Creator).scalar_subquery()
        query = query.order_by(latest.desc(), Creator.updated_at.desc())
    elif sort == "updated_desc":
        query = query.order_by(Creator.updated_at.desc(), Creator.id.desc())
    else:
        raise HTTPException(status_code=422, detail="排序方式无效")

    creators = query.offset((page - 1) * per_page).limit(per_page).all()
    creator_ids = [creator.id for creator in creators]
    metrics_by_creator: dict[int, dict] = {}
    followups_by_creator: dict[int, tuple[datetime | None, datetime | None]] = {}
    if creator_ids:
        confirmed = (
            (CreatorCollaboration.amount_status == "confirmed")
            & (CreatorCollaboration.status != "cancelled")
        )
        metric_rows = (
            db.query(
                CreatorCollaboration.creator_id,
                func.coalesce(func.sum(case((confirmed, CreatorCollaboration.actual_paid_cents), else_=0)), 0),
                func.coalesce(func.sum(case((confirmed, 1), else_=0)), 0),
                func.max(case((CreatorCollaboration.status != "cancelled", CreatorCollaboration.collaboration_date))),
            )
            .filter(CreatorCollaboration.creator_id.in_(creator_ids))
            .group_by(CreatorCollaboration.creator_id)
            .all()
        )
        for creator_id, total_paid, collaboration_count, latest_date in metric_rows:
            total_paid = int(total_paid or 0)
            collaboration_count = int(collaboration_count or 0)
            metrics_by_creator[int(creator_id)] = {
                "confirmed_paid_cents": total_paid,
                "confirmed_collaboration_count": collaboration_count,
                "average_paid_cents": total_paid // collaboration_count if collaboration_count else 0,
                "latest_collaboration_date": latest_date,
            }

        ranked_followups = (
            db.query(
                CreatorFollowup.creator_id.label("creator_id"),
                CreatorFollowup.followed_up_at.label("followed_up_at"),
                CreatorFollowup.next_followup_at.label("next_followup_at"),
                func.row_number().over(
                    partition_by=CreatorFollowup.creator_id,
                    order_by=(CreatorFollowup.followed_up_at.desc(), CreatorFollowup.id.desc()),
                ).label("position"),
            )
            .filter(CreatorFollowup.creator_id.in_(creator_ids))
            .subquery()
        )
        followup_rows = db.query(
            ranked_followups.c.creator_id,
            ranked_followups.c.followed_up_at,
            ranked_followups.c.next_followup_at,
        ).filter(ranked_followups.c.position == 1).all()
        followups_by_creator = {
            int(creator_id): (followed_up_at, next_followup_at)
            for creator_id, followed_up_at, next_followup_at in followup_rows
        }

    empty_metrics = {
        "confirmed_paid_cents": 0,
        "confirmed_collaboration_count": 0,
        "average_paid_cents": 0,
        "latest_collaboration_date": None,
    }
    return {
        "items": [
            creator_list_item(
                db,
                creator,
                metrics=metrics_by_creator.get(creator.id, empty_metrics),
                followup_dates=followups_by_creator.get(creator.id, (None, None)),
            )
            for creator in creators
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": math.ceil(total / per_page) if total else 0,
    }


def private_contact(db: Session, creator_id: int) -> dict:
    creator = _get_creator(db, creator_id)
    return {
        "contact_name": creator.contact_name,
        "contact_phone": creator.contact_phone,
        "wechat_id": creator.wechat_id,
        "addresses": [_full_address(item) for item in creator.addresses],
    }


def update_portrait(db: Session, creator_id: int, payload: CreatorPortraitUpdate) -> CreatorPortrait:
    creator = _get_creator(db, creator_id)
    portrait = creator.portrait or CreatorPortrait(creator=creator)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(portrait, field, value)
    db.add(portrait)
    db.commit()
    db.refresh(portrait)
    return portrait


def create_address(db: Session, creator_id: int, payload: CreatorAddressCreate) -> CreatorAddress:
    creator = _get_creator(db, creator_id)
    if payload.is_default or not creator.addresses:
        db.query(CreatorAddress).filter(CreatorAddress.creator_id == creator_id).update(
            {CreatorAddress.is_default: False}, synchronize_session=False
        )
    address = CreatorAddress(creator_id=creator_id, **payload.model_dump())
    if not creator.addresses:
        address.is_default = True
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


def _get_address(db: Session, creator_id: int, address_id: int) -> CreatorAddress:
    address = db.query(CreatorAddress).filter(
        CreatorAddress.id == address_id, CreatorAddress.creator_id == creator_id
    ).first()
    if not address:
        raise HTTPException(status_code=404, detail="收件地址不存在")
    return address


def update_address(
    db: Session, creator_id: int, address_id: int, payload: CreatorAddressUpdate
) -> CreatorAddress:
    _get_creator(db, creator_id)
    address = _get_address(db, creator_id, address_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default"):
        db.query(CreatorAddress).filter(CreatorAddress.creator_id == creator_id).update(
            {CreatorAddress.is_default: False}, synchronize_session=False
        )
    for field, value in changes.items():
        setattr(address, field, value)
    db.commit()
    db.refresh(address)
    return address


def delete_address(db: Session, creator_id: int, address_id: int):
    address = _get_address(db, creator_id, address_id)
    was_default = address.is_default
    db.delete(address)
    db.flush()
    if was_default:
        replacement = db.query(CreatorAddress).filter(CreatorAddress.creator_id == creator_id).first()
        if replacement:
            replacement.is_default = True
    db.commit()


def create_followup(db: Session, creator_id: int, payload: CreatorFollowupCreate) -> CreatorFollowup:
    creator = _get_creator(db, creator_id)
    _get_member(db, payload.owner_id)
    values = payload.model_dump(exclude_unset=True)
    values["method"] = _value(payload.method)
    if payload.stage_after:
        values["stage_after"] = _value(payload.stage_after)
        creator.stage = _value(payload.stage_after)
    if not values.get("followed_up_at"):
        values["followed_up_at"] = _utcnow()
    followup = CreatorFollowup(creator_id=creator_id, **values)
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


def _get_followup(db: Session, creator_id: int, followup_id: int) -> CreatorFollowup:
    item = db.query(CreatorFollowup).filter(
        CreatorFollowup.id == followup_id, CreatorFollowup.creator_id == creator_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="跟进记录不存在")
    return item


def update_followup(
    db: Session, creator_id: int, followup_id: int, payload: CreatorFollowupUpdate
) -> CreatorFollowup:
    creator = _get_creator(db, creator_id)
    item = _get_followup(db, creator_id, followup_id)
    changes = payload.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        _get_member(db, changes["owner_id"])
    for field, value in changes.items():
        setattr(item, field, _value(value))
    if payload.stage_after:
        creator.stage = _value(payload.stage_after)
    db.commit()
    db.refresh(item)
    return item


def delete_followup(db: Session, creator_id: int, followup_id: int):
    item = _get_followup(db, creator_id, followup_id)
    db.delete(item)
    db.commit()


def list_followups(db: Session, creator_id: int) -> list[CreatorFollowup]:
    _get_creator(db, creator_id)
    return db.query(CreatorFollowup).filter(CreatorFollowup.creator_id == creator_id).order_by(
        CreatorFollowup.followed_up_at.desc(), CreatorFollowup.id.desc()
    ).all()


def _products(db: Session, product_ids: Iterable[int]) -> dict[int, Product]:
    ids = list(dict.fromkeys(product_ids))
    if not ids:
        return {}
    products = db.query(Product).filter(Product.id.in_(ids)).all()
    result = {product.id: product for product in products}
    missing = [product_id for product_id in ids if product_id not in result]
    if missing:
        raise HTTPException(status_code=422, detail=f"产品不存在：{missing[0]}")
    return result


def _replace_collaboration_products(
    db: Session, collaboration: CreatorCollaboration, payload_products
):
    ids = [item.product_id for item in payload_products]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="同一合作不能重复关联产品")
    products = _products(db, ids)
    collaboration.products.clear()
    if collaboration.id is not None:
        # Flush delete-orphans before re-inserting the same product IDs; otherwise
        # SQLite can see the new unique pair before the old row is deleted.
        db.flush()
    for item in payload_products:
        product = products[item.product_id]
        collaboration.products.append(
            CreatorCollaborationProduct(
                product_id=product.id,
                product_name_snapshot=product.name,
                note=item.note,
            )
        )


def create_collaboration(
    db: Session, creator_id: int, payload: CreatorCollaborationCreate
) -> CreatorCollaboration:
    _get_creator(db, creator_id)
    _get_member(db, payload.owner_id)
    values = payload.model_dump(exclude={"products"})
    for field in ("collaboration_type", "status", "amount_status"):
        values[field] = _value(values[field])
    collaboration = CreatorCollaboration(creator_id=creator_id, **values)
    _replace_collaboration_products(db, collaboration, payload.products)
    db.add(collaboration)
    _commit(db, conflict_detail="合作编号或平台记录 ID 已存在")
    db.refresh(collaboration)
    return collaboration


def _get_collaboration(db: Session, creator_id: int, collaboration_id: int) -> CreatorCollaboration:
    item = db.query(CreatorCollaboration).filter(
        CreatorCollaboration.id == collaboration_id,
        CreatorCollaboration.creator_id == creator_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="合作记录不存在")
    return item


def update_collaboration(
    db: Session,
    creator_id: int,
    collaboration_id: int,
    payload: CreatorCollaborationUpdate,
) -> CreatorCollaboration:
    item = _get_collaboration(db, creator_id, collaboration_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"products"})
    if "owner_id" in changes:
        _get_member(db, changes["owner_id"])
    new_status = _value(changes.get("status", item.status))
    if new_status not in COLLABORATION_TRANSITIONS[item.status]:
        raise HTTPException(status_code=422, detail="合作状态不能这样流转")
    for field, value in changes.items():
        setattr(item, field, _value(value))
    if payload.products is not None:
        _replace_collaboration_products(db, item, payload.products)
    _commit(db, conflict_detail="合作记录更新冲突")
    db.refresh(item)
    return item


def cancel_collaboration(db: Session, creator_id: int, collaboration_id: int) -> CreatorCollaboration:
    item = _get_collaboration(db, creator_id, collaboration_id)
    if "cancelled" not in COLLABORATION_TRANSITIONS[item.status]:
        raise HTTPException(status_code=422, detail="当前合作状态不能取消")
    item.status = "cancelled"
    db.commit()
    return item


def collaboration_dict(item: CreatorCollaboration) -> dict:
    return {
        "id": item.id,
        "creator_id": item.creator_id,
        "owner_id": item.owner_id,
        "source_type": item.source_type,
        "external_record_id": item.external_record_id,
        "internal_code": item.internal_code,
        "collaboration_type": item.collaboration_type,
        "collaboration_date": item.collaboration_date,
        "status": item.status,
        "actual_paid_cents": item.actual_paid_cents,
        "amount_status": item.amount_status,
        "notes": item.notes,
        "products": [
            {
                "id": product.id,
                "product_id": product.product_id,
                "product_name_snapshot": product.product_name_snapshot,
                "note": product.note,
            }
            for product in item.products
        ],
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def list_collaborations(db: Session, creator_id: int) -> list[dict]:
    _get_creator(db, creator_id)
    rows = db.query(CreatorCollaboration).filter(
        CreatorCollaboration.creator_id == creator_id
    ).order_by(CreatorCollaboration.collaboration_date.desc(), CreatorCollaboration.id.desc()).all()
    return [collaboration_dict(item) for item in rows]


def _sample_fingerprint_value(
    *,
    address_id: int | None,
    collaboration_id: int | None,
    notes: str | None,
    items: list[dict],
) -> str | None:
    if address_id is None:
        return None
    canonical_items = sorted(
        (
            {
                "product_id": item.get("product_id"),
                "specification": item.get("specification"),
                "quantity": item.get("quantity"),
                "note": item.get("note"),
            }
            for item in items
        ),
        key=lambda item: (
            item["product_id"] or 0,
            item["specification"] or "",
            item["quantity"] or 0,
            item["note"] or "",
        ),
    )
    canonical = {
        "address_id": address_id,
        "collaboration_id": collaboration_id,
        "notes": notes,
        "items": canonical_items,
    }
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sample_request_fingerprint(payload: CreatorSampleOrderCreate) -> str:
    return _sample_fingerprint_value(
        address_id=payload.address_id,
        collaboration_id=payload.collaboration_id,
        notes=payload.notes,
        items=[item.model_dump() for item in payload.items],
    )


def _sample_order_fingerprint(order: CreatorSampleOrder) -> str | None:
    return _sample_fingerprint_value(
        address_id=getattr(order, "address_id", None),
        collaboration_id=getattr(order, "collaboration_id", None),
        notes=getattr(order, "notes", None),
        items=[
            {
                "product_id": item.product_id,
                "specification": item.specification,
                "quantity": item.quantity,
                "note": item.note,
            }
            for item in getattr(order, "items", [])
        ],
    )


def create_sample_order(
    db: Session, creator_id: int, payload: CreatorSampleOrderCreate
) -> tuple[CreatorSampleOrder, bool]:
    creator = _get_creator(db, creator_id)
    request_fingerprint = _sample_request_fingerprint(payload)
    existing = db.query(CreatorSampleOrder).filter(
        CreatorSampleOrder.idempotency_key == payload.idempotency_key
    ).first()
    if existing:
        if existing.creator_id != creator_id:
            raise HTTPException(status_code=409, detail="寄样幂等键已被其他达人使用")
        existing_fingerprint = existing.request_fingerprint or _sample_order_fingerprint(existing)
        if not existing_fingerprint or existing_fingerprint != request_fingerprint:
            raise HTTPException(status_code=409, detail="寄样幂等键与原请求内容不一致")
        if not existing.request_fingerprint:
            existing.request_fingerprint = request_fingerprint
            db.commit()
            db.refresh(existing)
        return existing, False
    address = _get_address(db, creator_id, payload.address_id)
    if payload.collaboration_id:
        _get_collaboration(db, creator_id, payload.collaboration_id)
    products = _products(db, [item.product_id for item in payload.items])
    order = CreatorSampleOrder(
        creator_id=creator.id,
        address_id=address.id,
        collaboration_id=payload.collaboration_id,
        idempotency_key=payload.idempotency_key,
        request_fingerprint=request_fingerprint,
        status="pending_shipment",
        recipient_name_snapshot=address.recipient_name,
        phone_snapshot=address.phone,
        province_snapshot=address.province,
        city_snapshot=address.city,
        district_snapshot=address.district,
        address_detail_snapshot=address.detail,
        notes=payload.notes,
    )
    for item in payload.items:
        product = products[item.product_id]
        order.items.append(
            CreatorSampleOrderItem(
                product_id=product.id,
                product_name_snapshot=product.name,
                specification=item.specification,
                quantity=item.quantity,
                note=item.note,
            )
        )
    db.add(order)
    return _commit_sample_order(db, order)


def _commit_sample_order(
    db: Session, order: CreatorSampleOrder
) -> tuple[CreatorSampleOrder, bool]:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.query(CreatorSampleOrder).filter(
            CreatorSampleOrder.idempotency_key == order.idempotency_key
        ).first()
        if existing and existing.creator_id == order.creator_id:
            existing_fingerprint = getattr(existing, "request_fingerprint", None) or _sample_order_fingerprint(existing)
            if existing_fingerprint != getattr(order, "request_fingerprint", None):
                raise HTTPException(status_code=409, detail="寄样幂等键与原请求内容不一致") from exc
            return existing, False
        raise HTTPException(status_code=409, detail="寄样单重复提交") from exc
    db.refresh(order)
    return order, True


def _get_sample_order(db: Session, creator_id: int, order_id: int) -> CreatorSampleOrder:
    order = db.query(CreatorSampleOrder).filter(
        CreatorSampleOrder.id == order_id,
        CreatorSampleOrder.creator_id == creator_id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="寄样单不存在")
    return order


def update_sample_order(
    db: Session, creator_id: int, order_id: int, payload: CreatorSampleOrderUpdate
) -> CreatorSampleOrder:
    order = _get_sample_order(db, creator_id, order_id)
    if order.status in {"received", "cancelled"}:
        raise HTTPException(status_code=422, detail="寄样终态不可修改")
    new_status = _value(payload.status)
    if new_status not in SAMPLE_TRANSITIONS[order.status]:
        raise HTTPException(status_code=422, detail="寄样状态不能这样流转")
    updates = {"status": new_status}
    if new_status == "shipped":
        shipping_company = payload.shipping_company or order.shipping_company
        tracking_number = payload.tracking_number or order.tracking_number
        if not shipping_company or not tracking_number:
            raise HTTPException(status_code=422, detail="发货必须填写快递公司和运单号")
        updates["shipping_company"] = shipping_company
        updates["tracking_number"] = tracking_number
        if not order.shipped_at:
            updates["shipped_at"] = _utcnow()
    if new_status == "received" and not order.received_at:
        updates["received_at"] = _utcnow()
    if payload.notes is not None:
        updates["notes"] = payload.notes
    updated = db.query(CreatorSampleOrder).filter(
        CreatorSampleOrder.id == order_id,
        CreatorSampleOrder.creator_id == creator_id,
        CreatorSampleOrder.status == order.status,
    ).update(updates, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="寄样单状态已被更新，请刷新后重试")
    db.commit()
    db.refresh(order)
    return order


def sample_order_dict(order: CreatorSampleOrder, *, private: bool = False) -> dict:
    address_detail = order.address_detail_snapshot if private else (
        " ".join(
            value
            for value in (
                order.province_snapshot,
                order.city_snapshot,
                order.district_snapshot,
                "***",
            )
            if value
        )
    )
    return {
        "id": order.id,
        "creator_id": order.creator_id,
        "address_id": order.address_id,
        "collaboration_id": order.collaboration_id,
        "idempotency_key": order.idempotency_key,
        "status": order.status,
        "recipient_name_snapshot": order.recipient_name_snapshot if private else mask_name(order.recipient_name_snapshot),
        "phone_snapshot": order.phone_snapshot if private else mask_phone(order.phone_snapshot),
        "province_snapshot": order.province_snapshot,
        "city_snapshot": order.city_snapshot,
        "district_snapshot": order.district_snapshot,
        "address_detail_snapshot": address_detail,
        "shipping_company": order.shipping_company,
        "tracking_number": order.tracking_number,
        "shipped_at": order.shipped_at,
        "received_at": order.received_at,
        "notes": order.notes,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name_snapshot": item.product_name_snapshot,
                "specification": item.specification,
                "quantity": item.quantity,
                "note": item.note,
            }
            for item in order.items
        ],
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def list_sample_orders(db: Session, creator_id: int) -> list[dict]:
    _get_creator(db, creator_id)
    rows = db.query(CreatorSampleOrder).filter(CreatorSampleOrder.creator_id == creator_id).order_by(
        CreatorSampleOrder.created_at.desc(), CreatorSampleOrder.id.desc()
    ).all()
    return [sample_order_dict(item) for item in rows]
