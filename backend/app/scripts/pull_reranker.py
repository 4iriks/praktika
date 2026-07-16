from __future__ import annotations

import json
from importlib import import_module
from typing import Protocol, cast

from app.core.config import get_settings


class SnapshotDownload(Protocol):
    def __call__(self, *, repo_id: str, revision: str, local_files_only: bool = False) -> str: ...


class HuggingFaceHubModule(Protocol):
    snapshot_download: SnapshotDownload


def main() -> None:
    settings = get_settings()
    module = cast(HuggingFaceHubModule, import_module("huggingface_hub"))
    download = module.snapshot_download
    path = download(
        repo_id=settings.reranker_model,
        revision=settings.reranker_model_revision,
        local_files_only=False,
    )
    print(
        json.dumps(
            {
                "model": settings.reranker_model,
                "revision": settings.reranker_model_revision,
                "path": path,
                "status": "installed",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
