"""FastAPI application entry point for CERBERUS-X."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from backend.config import BackendSettings, get_settings
from backend.database import AnalysisRepository
from backend.schemas import (
    AnalysisDetailResponse,
    AnalysisListResponse,
    AskRequest,
    AskResponse,
    BriefResponse,
    ConflictsResponse,
    DeleteAnalysisResponse,
    DigitalTwinResponse,
    ForensicsResponse,
    GraphResponse,
    HealthResponse,
    UploadAnalysisResponse,
)
from backend.service import AnalysisNotFoundError, CerberusService, InvalidUploadError
from core import llm as core_llm
from core.extractor import EXTENSION_TYPES, ocr_status
from core.schemas import ConflictType, Severity


def create_app(settings: Optional[BackendSettings] = None) -> FastAPI:
    cfg = settings or get_settings()
    repo = AnalysisRepository(cfg.db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        repo.init_db()
        yield

    app = FastAPI(
        title="CERBERUS-X API",
        description="Offline Multimodal Evidence Intelligence & Conflict-Aware Reasoning API",
        version="0.3.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_service() -> CerberusService:
        return CerberusService(repo=repo, upload_dir=cfg.upload_dir)

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        repo.init_db()
        ocr_ok, ocr_msg = ocr_status()
        llm = core_llm.ollama_status()
        return HealthResponse(
            status="ok",
            service="cerberus-x",
            database="sqlite",
            ocr_available=ocr_ok,
            ocr_message=ocr_msg,
            ollama_available=llm.available,
            ollama_model=llm.model,
            ollama_model_installed=llm.model_installed,
            ollama_message=llm.message,
            supported_extensions=sorted(EXTENSION_TYPES.keys()),
        )

    @app.post(
        "/api/upload",
        response_model=UploadAnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["analysis"],
    )
    async def upload_evidence(
        files: list[UploadFile] = File(...),
        service: CerberusService = Depends(get_service),
    ) -> UploadAnalysisResponse:
        payloads: list[tuple[str, bytes]] = []
        for upload in files:
            content = await upload.read()
            payloads.append((upload.filename or "", content))
        try:
            return service.ingest_uploads(payloads)
        except InvalidUploadError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.post(
        "/api/demo",
        response_model=UploadAnalysisResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["analysis"],
    )
    def run_demo_analysis(
        service: CerberusService = Depends(get_service),
    ) -> UploadAnalysisResponse:
        try:
            return service.ingest_demo()
        except InvalidUploadError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/analyses",
        response_model=AnalysisListResponse,
        tags=["analysis"],
    )
    def list_analyses(
        service: CerberusService = Depends(get_service),
    ) -> AnalysisListResponse:
        return service.list_analyses()

    @app.get(
        "/api/analysis/{analysis_id}",
        response_model=AnalysisDetailResponse,
        tags=["analysis"],
    )
    def get_analysis(
        analysis_id: str,
        service: CerberusService = Depends(get_service),
    ) -> AnalysisDetailResponse:
        try:
            return service.get_analysis(analysis_id)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.delete(
        "/api/analysis/{analysis_id}",
        response_model=DeleteAnalysisResponse,
        tags=["analysis"],
    )
    def delete_analysis(
        analysis_id: str,
        service: CerberusService = Depends(get_service),
    ) -> DeleteAnalysisResponse:
        try:
            return service.delete_analysis(analysis_id)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get(
        "/api/analysis/{analysis_id}/graph",
        response_model=GraphResponse,
        tags=["analysis"],
    )
    def get_graph(
        analysis_id: str,
        service: CerberusService = Depends(get_service),
    ) -> GraphResponse:
        try:
            return service.get_graph(analysis_id)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get(
        "/api/analysis/{analysis_id}/conflicts",
        response_model=ConflictsResponse,
        tags=["analysis"],
    )
    def get_conflicts(
        analysis_id: str,
        conflict_type: Optional[ConflictType] = Query(default=None),
        severity: Optional[Severity] = Query(default=None),
        only_real_problems: bool = Query(default=False),
        service: CerberusService = Depends(get_service),
    ) -> ConflictsResponse:
        try:
            return service.get_conflicts(
                analysis_id,
                conflict_type=conflict_type,
                severity=severity,
                only_real_problems=only_real_problems,
            )
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get(
        "/api/analysis/{analysis_id}/digital-twin",
        response_model=DigitalTwinResponse,
        tags=["analysis"],
    )
    def get_digital_twin(
        analysis_id: str,
        entity_id: Optional[str] = Query(default=None),
        service: CerberusService = Depends(get_service),
    ) -> DigitalTwinResponse:
        try:
            return service.get_digital_twin(analysis_id, entity_id=entity_id)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post(
        "/api/analysis/{analysis_id}/ask",
        response_model=AskResponse,
        tags=["reasoning"],
    )
    def ask_analysis(
        analysis_id: str,
        body: AskRequest,
        service: CerberusService = Depends(get_service),
    ) -> AskResponse:
        try:
            return service.ask(analysis_id, body.question, use_llm=body.use_llm)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post(
        "/api/analysis/{analysis_id}/brief",
        response_model=BriefResponse,
        tags=["reasoning"],
    )
    def brief_analysis(
        analysis_id: str,
        service: CerberusService = Depends(get_service),
    ) -> BriefResponse:
        try:
            return service.generate_brief(analysis_id)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.get(
        "/api/analysis/{analysis_id}/forensics",
        response_model=ForensicsResponse,
        tags=["forensics"],
    )
    def get_forensics(
        analysis_id: str,
        service: CerberusService = Depends(get_service),
    ) -> ForensicsResponse:
        try:
            return service.get_forensics(analysis_id)
        except AnalysisNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return app


app = create_app()
