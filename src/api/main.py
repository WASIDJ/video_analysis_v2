"""FastAPI应用入口."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from .endpoints import router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期."""
    print(f"🚀 {settings.app_name} v{settings.app_version} 已启动")
    print(f"📊 姿态估计模型: {settings.pose.model_type}")
    print(f"🔧 调试模式: {settings.debug}")
    try:
        yield
    finally:
        print("👋 应用已关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于生物力学的视频姿态分析系统V2",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=settings.api.cors_credentials,
    allow_methods=settings.api.cors_methods,
    allow_headers=settings.api.cors_headers,
)

app.include_router(router, prefix="/api/v2")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        workers=settings.api.workers,
    )
