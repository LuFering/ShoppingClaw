from fastapi import APIRouter

from server.routers.chat_rounter import chat

router=APIRouter()

router.include_router(chat)  # /api/chat/*
