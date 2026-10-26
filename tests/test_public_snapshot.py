"""Offline checks for the reviewed, asset-free public snapshot."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from config import DEFAULT_ROLE_ID
from memory.embedder import HashingEmbedder
from roleplay.evidence import index
from roleplay.evidence.loader import load_evidence
from roleplay.evidence.retriever import retrieval_text, retrieve_indexed
from roleplay.sticker_llm_selector import _family_candidates, select_sticker_for_text
from roles.registry import get_role, list_roles
from roles.stickers.registry import StickerRegistry
from roles.stickers.schema import StickerAffect, StickerDefinition
from tools.export_public_kei import export, public_files


def test_source_audit_matches_public_files() -> None:
    root = Path(__file__).resolve().parents[1]
    audit = json.loads((root / "docs/SOURCE_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["frozen_kei_v1_1"]["status"] == "source unverified"
    assert audit["current_worktree"]["evidence_rows"] == 78
    for entry in audit["public_derivative"]["source_entries"]:
        path = root / entry.get("public_path", entry["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["public_sha256"]


def test_default_kei_profile_is_discoverable() -> None:
    assert DEFAULT_ROLE_ID == "tendou_kei"
    role = get_role(DEFAULT_ROLE_ID)
    assert role.id in {item.id for item in list_roles()}
    assert role.runtime_identity is not None
    assert role.runtime_identity.name == "天童凯伊"
    assert role.roleplay.message_split.enabled


def test_synthetic_scene_contract_and_retrieval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    role_id = "test_role"
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    rows = [
        {
            "schema_version": 4,
            "id": f"synthetic_{number}",
            "role_id": role_id,
            "scene": scene,
            "relationship_context": "普通朋友",
            "source_refs": [{"source_id": f"synthetic/example_{number}.txt"}],
            "lines": [
                {"speaker": "friend", "kind": "dialogue", "source": "raw", "text": question},
                {"speaker": role_id, "kind": "dialogue", "source": "raw", "text": answer},
            ],
            "sticker_ids": [],
            "review_status": "reviewed",
            "trajectory_id": f"synthetic_{number}",
            "trajectory_order": 1,
            "trajectory_mode": "independent",
            "relation_floor": 0.0,
            "affection_expression": 0.0,
        }
        for number, scene, question, answer in [
            (1, "整理图书馆书架", "今天忙吗？", "刚忙完，怎么啦？"),
            (2, "计划公园散步", "周末散步吗？", "好啊，先看看天气。"),
        ]
    ]
    (evidence_dir / f"{role_id}.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    cards = load_evidence(role_id, evidence_directory=evidence_dir)
    assert len(cards) == 2
    assert "普通朋友" in retrieval_text(cards[0])
    monkeypatch.setattr(index, "INDEX_DIR", tmp_path / "indexes")
    embedder = HashingEmbedder()
    embedder.model_id = "offline-hash-test"
    results = retrieve_indexed(role_id, "周末散步吗？", cards, embedder=embedder, limit=2, min_score=0)
    assert len(results) == 2
    assert results[0].card.id == "synthetic_2"
    assert index.index_path(role_id).is_file()


def test_reviewed_stickers_and_family_boundary() -> None:
    assert len(StickerRegistry.from_directory().list_available("tendou_kei")) == 34
    called = False

    def model_call(*args, **kwargs):
        nonlocal called
        called = True
        return '{"sticker_id":"smile"}'

    assert select_sticker_for_text(
        user_text="你好", reply_text="你好。", stickers=[], model_call=model_call,
        affect_family="gentle",
    ) is None
    assert not called
    angry = StickerDefinition(
        id="angry", file="assets/stickers/test/angry.png", label="生气",
        description="生气", emotion_tags=(), enabled=True,
        affect=StickerAffect("angry"),
    )
    assert _family_candidates([angry], "gentle") == ((), True)


def test_api_import_with_reviewed_assets() -> None:
    from fastapi.testclient import TestClient
    from web.server import create_app

    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 200
        assert "no frontend" in client.get("/").json()["detail"]
        assert client.get("/api/roles").status_code == 200
        assert client.get("/api/modes").status_code == 200
        assert client.get("/local-assets/avatars/tendou_kei.png").status_code == 200
        assert client.get("/local-assets/stickers/tendou_kei/CH0335_noweapon_spr_01.png").status_code == 200


def test_allowlist_export_excludes_private_trees(tmp_path: Path) -> None:
    target = tmp_path / "public"
    files = public_files()
    assert Path("roles/profiles/tendou_kei.yaml") in files
    assert Path("roles/stickers/packs/tendou_kei.yaml") in files
    assert Path("docs/SOURCE_AUDIT.json") in files
    assert all("sample_character" not in str(path) for path in files)
    manifest = export(target)
    assert manifest["snapshot_id"] == "kei-v1.1-public"
    assert (target / "PUBLIC_MANIFEST.json").is_file()
    assert (target / "checksums.sha256").is_file()
    assert not (target / ".git").exists()
    assert len(list(target.rglob("*.png"))) == 35
    assert len(list((target / "local_data/roleplay_cards/tendou_kei").glob("*.md"))) == 7
    assert not list(target.rglob(".env"))
    with pytest.raises(FileExistsError):
        export(target)
