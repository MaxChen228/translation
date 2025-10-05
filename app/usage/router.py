from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates

from .models import LLMUsageQueryResponse
from .recorder import get_usage, query_usage, summarize_usage

router = APIRouter(prefix="/usage", tags=["usage"])
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/llm", response_model=LLMUsageQueryResponse)
def get_llm_usage(
    device_id: Optional[str] = Query(default=None),
    route: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    since: Optional[float] = Query(default=None, description="Filter records newer than this Unix timestamp"),
    until: Optional[float] = Query(default=None, description="Filter records older than this Unix timestamp"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> LLMUsageQueryResponse:
    query_kwargs = {
        "device_id": device_id,
        "route": route,
        "model": model,
        "provider": provider,
        "since": since,
        "until": until,
        "limit": limit,
        "offset": offset,
    }
    records = query_usage(**query_kwargs)
    summary = summarize_usage(
        device_id=device_id,
        route=route,
        model=model,
        provider=provider,
        since=since,
        until=until,
    )
    return LLMUsageQueryResponse(summary=summary, items=records)


@router.get("/llm/view")
def llm_usage_view(request: Request):
    return _TEMPLATES.TemplateResponse("admin/usage_dashboard.html", {"request": request})

@router.get("/llm/{usage_id}/view")
def llm_usage_detail_view(request: Request, usage_id: int):
    record = get_usage(usage_id)
    if record is None:
        raise HTTPException(status_code=404, detail="usage_not_found")

    import json
    try:
        import yaml
    except Exception:
        yaml = None

    def _normalize_newlines(obj):
        if isinstance(obj, str):
            return obj.replace('\\n', '\n')
        if isinstance(obj, list):
            return [_normalize_newlines(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _normalize_newlines(v) for k, v in obj.items()}
        return obj

    def _dump_yaml(obj) -> str:
        class _LiteralDumper(yaml.SafeDumper):
            pass

        def _str_representer(dumper, data):
            style = '|' if '\n' in data else None
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=style)

        _LiteralDumper.add_representer(str, _str_representer)
        return yaml.dump(obj, Dumper=_LiteralDumper, allow_unicode=True, sort_keys=False)

    def _to_yaml(data: str) -> str:
        try:
            obj = json.loads(data)
            obj = _normalize_newlines(obj)
        except Exception:
            return data.replace('\\n', '\n')
        if yaml is None:
            return json.dumps(obj, ensure_ascii=False, indent=2).replace('\\n', '\n')
        return _dump_yaml(obj)

    request_pretty = _to_yaml(record.request_payload)
    response_pretty = _to_yaml(record.response_payload)

    context = {
        "request": request,
        "record": record,
        "request_pretty": request_pretty,
        "response_pretty": response_pretty,
    }
    return _TEMPLATES.TemplateResponse("admin/usage_detail.html", context)
