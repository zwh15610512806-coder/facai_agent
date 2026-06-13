import os, re, json, logging
from datetime import datetime
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["search"])
SEARCH_ROOTS = [r"\\192.168.0.118法采共享盘2026"]
FILE_TYPE_MAP = {"document":[".doc",".docx",".pdf",".txt",".xls",".xlsx",".ppt",".pptx",".csv",".md",".json",".xml"],"image":[".jpg",".jpeg",".png",".gif",".bmp",".webp",".svg",".ico"],"video":[".mp4",".avi",".mov",".wmv",".flv",".mkv",".webm"],"audio":[".mp3",".wav",".aac",".flac",".ogg",".wma"],"archive":[".zip",".rar",".7z",".tar",".gz",".bz2"]}
EXT_TYPE_MAP = {}
for ft,exts in FILE_TYPE_MAP.items():
    for e in exts: EXT_TYPE_MAP[e] = ft