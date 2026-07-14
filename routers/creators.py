"""Creator-business CRUD, collaboration, and sample-order APIs."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from creator_schemas import (
    BdMemberCreate,
    BdMemberOut,
    BdMemberUpdate,
    CreatorAddressCreate,
    CreatorAddressOut,
    CreatorAddressUpdate,
    CreatorCollaborationCreate,
    CreatorCollaborationOut,
    CreatorCollaborationUpdate,
    CreatorCreate,
    CreatorDetailOut,
    CreatorFollowupCreate,
    CreatorFollowupOut,
    CreatorFollowupUpdate,
    CreatorPageOut,
    CreatorPortraitOut,
    CreatorPortraitUpdate,
    CreatorSampleOrderCreate,
    CreatorSampleOrderOut,
    CreatorSampleOrderUpdate,
    CreatorStage,
    CreatorUpdate,
    ImportMappingRequest,
    ImportResultOut,
    PrivateContactOut,
)
from config import MAX_UPLOAD_SIZE
from database import get_db
from services import creator_importer, creator_service
from services.upload_limits import read_upload_bytes
from services.bounded_executor import WorkQueueFull, run_blocking


router = APIRouter()


# Static routes are intentionally declared before /{creator_id} routes.
@router.get("/bd-members", response_model=list[BdMemberOut])
def get_bd_members(db: Session = Depends(get_db)):
    return creator_service.list_members(db)


@router.post("/bd-members", response_model=BdMemberOut, status_code=status.HTTP_201_CREATED)
def post_bd_member(payload: BdMemberCreate, db: Session = Depends(get_db)):
    return creator_service.create_member(db, payload)


@router.put("/bd-members/{member_id}", response_model=BdMemberOut)
def put_bd_member(member_id: int, payload: BdMemberUpdate, db: Session = Depends(get_db)):
    return creator_service.update_member(db, member_id, payload)


@router.get("/import/templates/{kind}")
def get_import_template(kind: str):
    content = creator_importer.build_template(kind)
    response = StreamingResponse(BytesIO(content), media_type=creator_importer.XLSX_MEDIA_TYPE)
    response.headers["Content-Disposition"] = f'attachment; filename="creator-{kind}-template.xlsx"'
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/import/preview")
async def post_import_preview(
    kind: str = Form(...),
    source_type: str = Form("facai_template"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="Excel 仅支持 .xlsx 文件")
    content = await read_upload_bytes(file, max_bytes=MAX_UPLOAD_SIZE)
    try:
        return await run_blocking(
            creator_importer.preview_upload,
            db,
            kind=kind,
            source_type=source_type,
            filename=filename,
            content=content,
        )
    except WorkQueueFull as exc:
        raise HTTPException(status_code=503, detail="文件解析任务繁忙，请稍后重试") from exc


@router.post("/import/{token}/validate", response_model=ImportResultOut)
def post_import_validate(
    token: str, payload: ImportMappingRequest, db: Session = Depends(get_db)
):
    return creator_importer.validate_import(db, token, payload.mapping)


@router.post("/import/{token}/commit", response_model=ImportResultOut)
def post_import_commit(token: str, db: Session = Depends(get_db)):
    return creator_importer.commit_import(db, token)


@router.get("/import/{token}/errors")
def get_import_errors(token: str, db: Session = Depends(get_db)):
    content = creator_importer.error_report(db, token)
    response = StreamingResponse(BytesIO(content), media_type=creator_importer.XLSX_MEDIA_TYPE)
    response.headers["Content-Disposition"] = 'attachment; filename="creator-import-errors.xlsx"'
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/export")
def get_export(
    entity: str,
    creator_id: int | None = Query(None, gt=0),
    stage: CreatorStage | None = None,
    owner_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, max_length=200),
    category: str | None = Query(None, max_length=100),
    follower_tier: str | None = Query(None, max_length=30),
    db: Session = Depends(get_db),
):
    content = creator_importer.export_workbook(
        db,
        entity=entity,
        creator_id=creator_id,
        stage=stage.value if stage else None,
        owner_id=owner_id,
        search=search,
        category=category,
        follower_tier=follower_tier,
    )
    response = StreamingResponse(BytesIO(content), media_type=creator_importer.XLSX_MEDIA_TYPE)
    response.headers["Content-Disposition"] = f'attachment; filename="creator-{entity}-export.xlsx"'
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("", response_model=CreatorPageOut)
def get_creators(
    search: str | None = Query(None, max_length=200),
    stage: CreatorStage | None = None,
    owner_id: int | None = Query(None, gt=0),
    category: str | None = Query(None, max_length=100),
    follower_tier: str | None = Query(None, max_length=30),
    sort: str = Query("updated_desc", max_length=30),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return creator_service.list_creators(
        db,
        search=search,
        stage=stage.value if stage else None,
        owner_id=owner_id,
        category=category,
        follower_tier=follower_tier,
        sort=sort,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=CreatorDetailOut, status_code=status.HTTP_201_CREATED)
def post_creator(payload: CreatorCreate, db: Session = Depends(get_db)):
    creator = creator_service.create_creator(db, payload)
    return creator_service.creator_detail(db, creator)


@router.get("/{creator_id}/private-contact", response_model=PrivateContactOut)
def get_private_contact(creator_id: int, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return creator_service.private_contact(db, creator_id)


@router.put("/{creator_id}/portrait", response_model=CreatorPortraitOut)
def put_portrait(
    creator_id: int, payload: CreatorPortraitUpdate, db: Session = Depends(get_db)
):
    return creator_service.update_portrait(db, creator_id, payload)


@router.post(
    "/{creator_id}/addresses",
    response_model=CreatorAddressOut,
    status_code=status.HTTP_201_CREATED,
)
def post_address(
    creator_id: int,
    payload: CreatorAddressCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return creator_service.create_address(db, creator_id, payload)


@router.put("/{creator_id}/addresses/{address_id}", response_model=CreatorAddressOut)
def put_address(
    creator_id: int,
    address_id: int,
    payload: CreatorAddressUpdate,
    response: Response,
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return creator_service.update_address(db, creator_id, address_id, payload)


@router.delete("/{creator_id}/addresses/{address_id}")
def delete_address(creator_id: int, address_id: int, db: Session = Depends(get_db)):
    creator_service.delete_address(db, creator_id, address_id)
    return {"success": True}


@router.get("/{creator_id}/followups", response_model=list[CreatorFollowupOut])
def get_followups(creator_id: int, db: Session = Depends(get_db)):
    return creator_service.list_followups(db, creator_id)


@router.post(
    "/{creator_id}/followups",
    response_model=CreatorFollowupOut,
    status_code=status.HTTP_201_CREATED,
)
def post_followup(
    creator_id: int, payload: CreatorFollowupCreate, db: Session = Depends(get_db)
):
    return creator_service.create_followup(db, creator_id, payload)


@router.put("/{creator_id}/followups/{followup_id}", response_model=CreatorFollowupOut)
def put_followup(
    creator_id: int,
    followup_id: int,
    payload: CreatorFollowupUpdate,
    db: Session = Depends(get_db),
):
    return creator_service.update_followup(db, creator_id, followup_id, payload)


@router.delete("/{creator_id}/followups/{followup_id}")
def delete_followup(creator_id: int, followup_id: int, db: Session = Depends(get_db)):
    creator_service.delete_followup(db, creator_id, followup_id)
    return {"success": True}


@router.get("/{creator_id}/collaborations", response_model=list[CreatorCollaborationOut])
def get_collaborations(creator_id: int, db: Session = Depends(get_db)):
    return creator_service.list_collaborations(db, creator_id)


@router.post(
    "/{creator_id}/collaborations",
    response_model=CreatorCollaborationOut,
    status_code=status.HTTP_201_CREATED,
)
def post_collaboration(
    creator_id: int,
    payload: CreatorCollaborationCreate,
    db: Session = Depends(get_db),
):
    item = creator_service.create_collaboration(db, creator_id, payload)
    return creator_service.collaboration_dict(item)


@router.put(
    "/{creator_id}/collaborations/{collaboration_id}",
    response_model=CreatorCollaborationOut,
)
def put_collaboration(
    creator_id: int,
    collaboration_id: int,
    payload: CreatorCollaborationUpdate,
    db: Session = Depends(get_db),
):
    item = creator_service.update_collaboration(db, creator_id, collaboration_id, payload)
    return creator_service.collaboration_dict(item)


@router.delete("/{creator_id}/collaborations/{collaboration_id}")
def delete_collaboration(
    creator_id: int, collaboration_id: int, db: Session = Depends(get_db)
):
    creator_service.cancel_collaboration(db, creator_id, collaboration_id)
    return {"success": True}


@router.get("/{creator_id}/sample-orders", response_model=list[CreatorSampleOrderOut])
def get_sample_orders(creator_id: int, db: Session = Depends(get_db)):
    return creator_service.list_sample_orders(db, creator_id)


@router.post("/{creator_id}/sample-orders", response_model=CreatorSampleOrderOut)
def post_sample_order(
    creator_id: int,
    payload: CreatorSampleOrderCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    order, created = creator_service.create_sample_order(db, creator_id, payload)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return creator_service.sample_order_dict(order)


@router.put("/{creator_id}/sample-orders/{order_id}", response_model=CreatorSampleOrderOut)
def put_sample_order(
    creator_id: int,
    order_id: int,
    payload: CreatorSampleOrderUpdate,
    db: Session = Depends(get_db),
):
    order = creator_service.update_sample_order(db, creator_id, order_id, payload)
    return creator_service.sample_order_dict(order)


@router.get("/{creator_id}", response_model=CreatorDetailOut)
def get_creator(creator_id: int, db: Session = Depends(get_db)):
    creator = creator_service._get_creator(db, creator_id)
    return creator_service.creator_detail(db, creator)


@router.put("/{creator_id}", response_model=CreatorDetailOut)
def put_creator(creator_id: int, payload: CreatorUpdate, db: Session = Depends(get_db)):
    creator = creator_service.update_creator(db, creator_id, payload)
    return creator_service.creator_detail(db, creator)


@router.delete("/{creator_id}")
def delete_creator(creator_id: int, db: Session = Depends(get_db)):
    creator_service.archive_creator(db, creator_id)
    return {"success": True}
