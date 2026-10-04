"""Model karşılaştırma uçları (yalnızca yönetici, yalnızca okur, model çağrısı başlatmaz).

Deneyler geçici klasörde sentetik olarak kurulur; etiketler GERÇEK veri setinden (v1) gelir. Beklenen
sayılar testte elle yazılmış sabitlerdir (uygulamanın kendi hesaplayıcılarıyla yeniden hesaplanmaz);
ek olarak `build_report` çıktısıyla birebir aynılık ayrıca doğrulanır.
"""

import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import experiments
from app.deps import require_admin
from app.evaluation.dataset import dataset_sha256, load_samples
from app.evaluation.report import build_report
from app.routers.experiments import get_experiments_root, get_uncertainty_file

RUN_ID = "20261002T162249Z-v1-dev"
ALL_Q = [
    "category",
    "priority",
    "missing_location",
    "missing_detail",
    "missing_contact",
    "missing_timing",
]
JEV_COST = "0.000038000"
LLM_COST = "0.002900000"
STAGE_COST = "0.001250000"
PRICES = [
    {
        "provider": "jev",
        "model": "jev-1.13.0",
        "input_usd_per_mtok": "0.042",
        "output_usd_per_mtok": "0",
        "source_url": "https://docs.typesafe.ai/models",
        "checked_on": "2026-10-02",
    },
    {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "input_usd_per_mtok": "1",
        "output_usd_per_mtok": "5",
        "source_url": "https://platform.claude.com/docs/en/about-claude/pricing",
        "checked_on": "2026-10-02",
    },
]


def dev_samples(n: int):
    return [s for s in load_samples("v1") if s.split == "dev"][:n]


def _call(provider, model, questions, cost, inp, out, attempt=1, status="ok"):
    return {
        "provider": provider,
        "model": model,
        "attempt": attempt,
        "status": status,
        "duration_ms": 100,
        "input_tokens": inp,
        "output_tokens": out,
        "usage_estimated": False,
        "cost_usd": cost,
        "questions": questions,
        "is_mock": False,
        "request_id": "req_gizli_olmayan_kimlik",
    }


def _row(sample, strategy, idx, *, wrong_cat=(), wrong_pri=(), review=(), unknown_cost=False):
    gold = sample.gold
    category = gold.category
    if strategy in wrong_cat and idx in wrong_cat[strategy]:
        category = "cleaning" if gold.category != "cleaning" else "plumbing"
    priority = gold.priority
    if strategy in wrong_pri and idx in wrong_pri[strategy]:
        priority = "high" if gold.priority != "high" else "normal"
    if strategy == "jev_only":
        calls = [_call("jev", "jev-1.13.0", ALL_Q, JEV_COST, 900, 180)]
        latency = 300 + 10 * idx
    elif strategy == "llm_only":
        calls = [_call("anthropic", "claude-haiku-4-5-20251001", ALL_Q, LLM_COST, 1900, 190)]
        latency = 1500 + 20 * idx
    else:
        calls = [
            _call("jev", "jev-1.13.0", ALL_Q, JEV_COST, 900, 180),
            _call(
                "anthropic",
                "claude-haiku-4-5-20251001",
                ["missing_contact"],
                STAGE_COST,
                1000,
                46,
            ),
        ]
        latency = 1000 + 15 * idx
    if unknown_cost:
        calls[0]["cost_usd"] = None
    return {
        "sample_id": sample.id,
        "strategy": strategy,
        "split": sample.split,
        "failed": False,
        "error": None,
        "latency_ms": float(latency),
        "category": category,
        "priority": priority,
        "missing_info": [],
        "review_required": strategy == "jev_only" and idx in review,
        "review_reasons": ["category_unclear"]
        if (strategy == "jev_only" and idx in review)
        else [],
        "is_mock": False,
        "providers": ["jev"] if strategy == "jev_only" else ["anthropic"],
        "model_versions": ["jev-1.13.0"],
        "judgments": [
            {
                "question": "category",
                "answer": category,
                "probabilities": {"plumbing": 0.9},
                "confidence": 0.88,
                "confidence_kind": "jev_confidence" if strategy != "llm_only" else "self_reported",
                "n_options": 6,
                "source": "jev",
                "adopted": True,
                "ham_gizli_alan": "gizli-deger-yargi",
            },
            {
                "question": "missing_contact",
                "answer": True,
                "probabilities": {"yes": 0.63, "no": 0.37},
                "confidence": 0.26,
                "confidence_kind": "derived_margin",
                "n_options": 2,
                "source": "jev",
                "adopted": False,
                "ham_gizli_alan": "gizli-deger-yargi",
            },
        ],
        "calls": calls,
        # Beyaz liste dışı alanlar: yanıta SIZMAMALI
        "api_key": "sk-ant-ASLA-SIZMAMALI-123",
        "request_secret": "gizli-deger",
    }


def write_run(
    root: Path,
    run_id: str = RUN_ID,
    *,
    n: int = 5,
    routing: str | None = None,
    live: bool = True,
    mock: bool = False,
    stopped: dict | None = None,
    drop_hybrid_for: tuple[int, ...] = (),
    unknown_cost_for: tuple[int, ...] = (),
    sha: str | None = None,
    version: str = "v1",
    extra_run: dict | None = None,
    write_predictions: bool = True,
    n_completed: int | None = None,
) -> Path:
    samples = dev_samples(n)
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    strategies = [
        {
            "name": "jev_only",
            "is_mock": mock,
            "kind": "jev_only",
            "provider": "jev",
            "model": "jev-1.13.0",
            "prompt_version": "jev-sorular-v1-8c2683f3f49e",
        },
        {
            "name": "llm_only",
            "is_mock": mock,
            "kind": "llm_only",
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "prompt_version": "llm-istem-v1-e4fabd817c1e",
            "temperature": 0.0,
        },
        {
            "name": "hybrid",
            "is_mock": mock,
            "kind": "hybrid",
            "jev": {"provider": "jev", "model": "jev-1.13.0", "prompt_version": "jev-sorular-v1-x"},
            "llm": {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "prompt_version": "llm-istem-v1-x",
                "temperature": 0.0,
            },
            "thresholds": dict.fromkeys(ALL_Q, 0.6),
            "llm_min_self_reported": None,
        },
    ]
    if routing:
        strategies[2]["routing_version"] = routing
        strategies[2]["escalate_on"] = [
            "category",
            "priority",
            "missing_location",
            "missing_detail",
        ]
    spent = Decimal(0)
    rows = []
    wrong_cat = {"jev_only": {1}}
    wrong_pri = {"llm_only": {2}, "hybrid": {0}}
    for idx, sample in enumerate(samples):
        for name in ("jev_only", "llm_only", "hybrid"):
            if name == "hybrid" and idx in drop_hybrid_for:
                continue
            row = _row(
                sample,
                name,
                idx,
                wrong_cat=wrong_cat,
                wrong_pri=wrong_pri,
                review={3},
                unknown_cost=name == "jev_only" and idx in unknown_cost_for,
            )
            rows.append(row)
            spent += sum(
                (Decimal(c["cost_usd"]) for c in row["calls"] if c["cost_usd"] is not None),
                Decimal(0),
            )
    record = {
        "run_id": run_id,
        "created_at": "2026-10-02T16:22:49.891057+00:00",
        "source_commit": "09584e99f1614df2ec202b61dd1d422dbf4ff71d",
        "git_dirty": False,
        "dataset": {
            "version": version,
            "sha256": sha or dataset_sha256("v1"),
            "manifest_sha256": "x",
            "splits_used": ["dev"],
            "n_samples": n,
            "n_samples_completed": n if n_completed is None else n_completed,
            "limit": n,
            "source": "synthetic",
            "label_status": "single_annotator_unreviewed",
        },
        "strategies": strategies,
        "config": {
            "concurrency": 1,
            "cache": "yok",
            "retry": {"max_attempts": 3},
            "shuffle_seed": 4,
            "final": False,
        },
        "budget": {
            "live": live,
            "method": "yöntem metni",
            "budget_id": "ilk-deneme",
            "max_cost_usd": "0.10",
            "spent_usd": str(spent),
            "known_spent_usd": str(spent),
            "conservative_spent_usd": "0",
            "conservative_charges": 0,
            "bound_violations": 0,
            "calls": len([c for r in rows for c in r["calls"]]),
            "prior_spent_usd": "0",
            "prior_unresolved_reserved_usd": "0",
            "total_spent_usd": str(spent),
            "remaining_usd": str(Decimal("0.10") - spent),
            "ledger": "C:\\Users\\GIZLI-KULLANICI\\Desktop\\evaluation\\budget\\ilk-deneme.json",
        }
        if live
        else {"live": False},
        "stopped_early": stopped,
        "aborted_prediction": None,
        "prices": PRICES,
        "environment": {"python": "3.12.7", "platform": "Windows"},
        "gizli_alan": "sk-ant-RUNJSON-SIZMAMALI-456",
    }
    record.update(extra_run or {})
    (run_dir / "run.json").write_text(json.dumps(record), encoding="utf-8")
    if write_predictions:
        (run_dir / "predictions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
    return run_dir


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir()
    return root


@pytest.fixture
def uncertainty_file(tmp_path: Path) -> Path:
    path = tmp_path / "etiket_belirsizlikleri.json"
    first = dev_samples(5)[1].id
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "datasets": {"v1": {first: {"status": "gözden geçirme bekliyor", "note": "not"}}},
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def exp(app: FastAPI, runs_root: Path, uncertainty_file: Path) -> TestClient:
    """Yönetici girişi olmadan (DB'siz): yalnızca uç mantığını sınar. Yetki testleri `api` ile."""
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_experiments_root] = lambda: runs_root
    app.dependency_overrides[get_uncertainty_file] = lambda: uncertainty_file
    return TestClient(app, raise_server_exceptions=False)


def _all_keys(value) -> set[str]:
    """İç içe yapıdaki tüm sözlük anahtarları."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _all_keys(v)}
    return set()


def strat(detail: dict, name: str) -> dict:
    return next(s for s in detail["strategies"] if s["name"] == name)


# --------------------------------------------------------------------------- liste


class TestListRuns:
    def test_klasor_yoksa_bos_durum_ve_uydurma_rakam_yok(self, exp, runs_root):
        runs_root.rmdir()

        body = exp.get("/admin/experiments").json()

        assert body == {"runs_dir_found": False, "runs": []}

    def test_klasor_bos_ise_bos_liste(self, exp):
        assert exp.get("/admin/experiments").json() == {"runs_dir_found": True, "runs": []}

    def test_secici_alanlari_tarih_ornek_strateji_durum_surum(self, exp, runs_root):
        write_run(runs_root)

        run = exp.get("/admin/experiments").json()["runs"][0]

        assert run["id"] == RUN_ID
        assert run["created_at"] == "2026-10-02T16:22:49.891057+00:00"
        assert run["dataset"]["n_samples"] == 5 and run["dataset"]["n_completed"] == 5
        assert run["dataset"]["version"] == "v1" and run["dataset"]["splits"] == ["dev"]
        assert run["dataset"]["matches_current"] is True
        assert [s["name"] for s in run["strategies"]] == ["jev_only", "llm_only", "hybrid"]
        assert run["status"] == "complete" and run["status_detail"] is None
        assert run["live"] is True
        assert run["scope_label"] == "5 sentetik geliştirme örneği — bağlantı denemesi"
        assert run["source_commit"].startswith("09584e9")

    def test_eski_hibrit_v1_etiketlenir_guncel_kodla_alinmis_gibi_degil(self, exp, runs_root):
        write_run(runs_root)

        routing = exp.get("/admin/experiments").json()["runs"][0]["hybrid_routing"]

        assert routing["version"] == "hibrit-yonlendirme-v1" and routing["recorded"] is False

    def test_kayitli_v2_surumu_gosterilir(self, exp, runs_root):
        write_run(runs_root, routing="hibrit-yonlendirme-v2")

        routing = exp.get("/admin/experiments").json()["runs"][0]["hybrid_routing"]

        assert routing["version"] == "hibrit-yonlendirme-v2" and routing["recorded"] is True
        assert "karar" in routing["description"]

    def test_yeniden_eskiye_siralanir_ve_gecersiz_klasor_adlari_yok_sayilir(self, exp, runs_root):
        write_run(
            runs_root,
            "20261001T100000Z-v1-dev",
            extra_run={"created_at": "2026-10-01T10:00:00+00:00"},
        )
        write_run(runs_root, RUN_ID)
        (runs_root / "rastgele-klasor").mkdir()
        (runs_root / "not-a-run.txt").write_text("x", encoding="utf-8")

        ids = [r["id"] for r in exp.get("/admin/experiments").json()["runs"]]

        assert ids == [RUN_ID, "20261001T100000Z-v1-dev"]

    def test_yarim_kalan_deney_nedeniyle_isaretlenir(self, exp, runs_root):
        write_run(
            runs_root,
            n=5,
            n_completed=3,
            stopped={"reason": "budget", "samples_completed": 3, "samples_planned": 5},
        )

        run = exp.get("/admin/experiments").json()["runs"][0]

        assert run["status"] == "partial"
        assert "3/5" in run["status_detail"] and "harcama sınırını" in run["status_detail"]

    def test_tahmin_dosyasi_yoksa_eksik_dosya_durumu(self, exp, runs_root):
        write_run(runs_root, write_predictions=False)

        run = exp.get("/admin/experiments").json()["runs"][0]

        assert run["status"] == "missing_files" and run["files"]["predictions"] is False

    def test_bozuk_run_json_listelenir_ama_bozuk_gorunur(self, exp, runs_root):
        run_dir = runs_root / RUN_ID
        run_dir.mkdir()
        (run_dir / "run.json").write_text("{bozuk", encoding="utf-8")

        run = exp.get("/admin/experiments").json()["runs"][0]

        assert run["status"] == "corrupt" and "run.json" in run["status_detail"]
        assert run["dataset"] is None and run["strategies"] == []

    def test_run_json_olmayan_klasor_eksik_dosya(self, exp, runs_root):
        (runs_root / RUN_ID).mkdir()

        assert exp.get("/admin/experiments").json()["runs"][0]["status"] == "missing_files"

    def test_veri_seti_degismisse_sha_uyusmuyor_isaretlenir(self, exp, runs_root):
        write_run(runs_root, sha="0" * 64)

        run = exp.get("/admin/experiments").json()["runs"][0]
        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert run["dataset"]["matches_current"] is False
        assert "dataset_changed" in [w["code"] for w in detail["warnings"]]


# --------------------------------------------------------------------------- ayrıntı ve sayılar


class TestDetailNumbers:
    @pytest.fixture
    def detail(self, exp, runs_root):
        write_run(runs_root)
        return exp.get(f"/admin/experiments/{RUN_ID}").json()

    def test_ortak_ornekler_ve_uyarilar(self, detail):
        assert detail["metrics_available"] is True
        assert detail["common"]["n"] == 5 and detail["common"]["excluded"] == []
        codes = [w["code"] for w in detail["warnings"]]
        assert "small_sample" in codes and "hybrid_v1" in codes and "disputed_labels" in codes
        assert (
            "Güncel kod (v2)"
            in next(w for w in detail["warnings"] if w["code"] == "hybrid_v1")["text"]
        )

    def test_kategori_ve_oncelik_dogrulugu(self, detail):
        jev, llm, hyb = (strat(detail, n) for n in ("jev_only", "llm_only", "hybrid"))

        # jev_only: 1 kategori hatası; llm_only: 1 öncelik hatası; hybrid: 1 öncelik hatası
        assert (
            jev["metrics"]["category_accuracy"]["successes"],
            jev["metrics"]["category_accuracy"]["n"],
        ) == (4, 5)
        assert jev["metrics"]["priority_accuracy"]["successes"] == 5
        assert llm["metrics"]["category_accuracy"]["successes"] == 5
        assert llm["metrics"]["priority_accuracy"]["successes"] == 4
        assert hyb["metrics"]["priority_accuracy"]["successes"] == 4
        assert jev["metrics"]["category_accuracy"]["value"] == pytest.approx(0.8)

    def test_inceleme_ve_otomatik_karar_orani(self, detail):
        jev = strat(detail, "jev_only")["metrics"]
        llm = strat(detail, "llm_only")["metrics"]

        assert (jev["review_rate"]["successes"], jev["review_rate"]["n"]) == (1, 5)
        assert (jev["automated_rate"]["successes"], jev["automated_rate"]["n"]) == (4, 5)
        assert (llm["review_rate"]["successes"], llm["automated_rate"]["successes"]) == (0, 5)

    def test_gecikme_p50_p95_ortak_orneklerden(self, detail):
        jev = strat(detail, "jev_only")["metrics"]

        # 300, 310, 320, 330, 340 → p50 320
        assert jev["latency_p50_ms"] == pytest.approx(320.0)
        assert jev["latency_p95_ms"] == pytest.approx(338.0)  # doğrusal enterpolasyon

    def test_ucret_olculen_toplam_ve_talep_basi(self, detail):
        jev, llm, hyb = (strat(detail, n)["cost"] for n in ("jev_only", "llm_only", "hybrid"))

        assert Decimal(jev["known_usd"]) == Decimal("0.00019")  # 5 × 0.000038
        assert Decimal(llm["known_usd"]) == Decimal("0.0145")  # 5 × 0.0029
        assert Decimal(hyb["known_usd"]) == Decimal("0.00019") + Decimal(
            "0.00625"
        )  # Jev + 5 × 0.00125
        assert Decimal(jev["per_completed_usd"]) == Decimal("0.000038")
        assert Decimal(llm["per_completed_usd"]) == Decimal("0.0029")
        assert jev["calls_with_unknown_cost"] == 0 and jev["total_usd"] is not None

    def test_1000_talep_tahmini_olculen_toplamdan_ayri_alan(self, detail):
        llm = strat(detail, "llm_only")["cost"]

        assert Decimal(llm["estimate_per_1000_usd"]) == Decimal("2.9")  # 0.0029 × 1000 (tahmin)
        assert llm["known_usd"] != llm["estimate_per_1000_usd"]

    def test_tokenlar_girdi_cikti_ayri_ve_saglayici_bazinda(self, detail):
        hyb = strat(detail, "hybrid")["usage"]
        by_provider = {p["provider"]: p for p in hyb["providers"]}

        assert (
            by_provider["jev"]["input_tokens"] == 4500
            and by_provider["jev"]["output_tokens"] == 900
        )
        assert by_provider["anthropic"]["input_tokens"] == 5000
        assert by_provider["anthropic"]["output_tokens"] == 230
        assert hyb["input_tokens"] == 9500 and hyb["output_tokens"] == 1130

    def test_ucretsiz_cikti_tokeni_sifir_gosterilmez_ama_ucretsiz_diye_isaretlenir(self, detail):
        jev = strat(detail, "jev_only")["usage"]["providers"][0]
        llm = strat(detail, "llm_only")["usage"]["providers"][0]

        assert jev["output_tokens"] == 900 and jev["output_tokens_free"] is True
        assert llm["output_tokens"] == 950 and llm["output_tokens_free"] is False

    def test_cagri_retry_ve_hata_sayilari(self, detail):
        usage = strat(detail, "hybrid")["usage"]

        assert usage["calls"] == 10 and usage["retries"] == 0 and usage["call_errors"] == 0

    def test_hibrit_llm_e_gecis_orani_ve_tetikleyen_sorular(self, detail):
        hybrid = strat(detail, "hybrid")["hybrid"]

        assert (hybrid["escalated"]["successes"], hybrid["escalated"]["n"]) == (5, 5)
        assert hybrid["trigger_questions"] == {"missing_contact": 5}
        assert hybrid["jev_stage_calls"] == 5 and hybrid["llm_stage_calls"] == 5
        assert strat(detail, "jev_only")["hybrid"] is None

    def test_butce_ozeti_defter_yolu_olmadan(self, detail):
        budget = detail["budget"]

        assert budget["budget_id"] == "ilk-deneme" and budget["max_cost_usd"] == "0.10"
        assert "ledger" not in budget and "method" not in budget

    def test_karsilastirma_disi_harcama_toplamdan_gizlenmez(self, exp, runs_root):
        # 2. örnekte hibrit satırı yok: bu örnek karşılaştırma dışı, ama çağrı harcaması defterde var.
        write_run(runs_root, drop_hybrid_for=(2,))

        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert detail["common"]["n"] == 4
        assert detail["common"]["excluded"] == [
            {"sample_id": dev_samples(5)[2].id, "missing_strategies": ["hybrid"]}
        ]
        rec = detail["reconciliation"]
        # Karşılaştırma dışı: o örneğin jev_only + llm_only harcaması
        assert Decimal(rec["outside_comparison_usd"]) == Decimal(JEV_COST) + Decimal(LLM_COST)
        assert Decimal(rec["run_known_spent_usd"]) == Decimal(rec["compared_known_usd"]) + Decimal(
            rec["outside_comparison_usd"]
        )
        assert "excluded_samples" in [w["code"] for w in detail["warnings"]]

    def test_bilinmeyen_ucret_sifir_gosterilmez(self, exp, runs_root):
        write_run(runs_root, unknown_cost_for=(0, 1))

        cost = strat(exp.get(f"/admin/experiments/{RUN_ID}").json(), "jev_only")["cost"]

        assert cost["calls_with_unknown_cost"] == 2
        assert cost["total_usd"] is None and cost["per_completed_usd"] is None
        # Sağlayıcı bazında döküm de bilinmeyeni sıfır saymaz ve ayrıca bildirir.
        provider = strat(exp.get(f"/admin/experiments/{RUN_ID}").json(), "jev_only")["usage"][
            "providers"
        ][0]
        assert provider["calls_with_unknown_cost"] == 2
        assert Decimal(provider["cost_known_usd"]) == Decimal("0.000114")
        sample = exp.get(f"/admin/experiments/{RUN_ID}/samples/{dev_samples(5)[0].id}").json()
        first = next(x for x in sample["strategies"] if x["name"] == "jev_only")
        assert (
            first["calls_with_unknown_cost"] == 1
            and first["usage"][0]["calls_with_unknown_cost"] == 1
        )
        assert first["calls"][0]["cost_usd"] is None  # kayıtlı değer: bilinmiyor, "0" değil
        assert cost["estimate_per_1000_usd"] is None  # bilinmeyenden tahmin üretilmez
        assert Decimal(cost["known_usd"]) == Decimal("0.000114")  # yalnızca bilinen kısım, ayrıca

    def test_mock_deney_uyari_ve_etiket(self, exp, runs_root):
        write_run(runs_root, mock=True, live=False)

        run = exp.get("/admin/experiments").json()["runs"][0]
        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert "MOCK" in run["scope_label"] and "mock" in [w["code"] for w in detail["warnings"]]
        assert detail["budget"] is None and detail["reconciliation"] is None

    def test_sayilar_build_report_ile_birebir_ayni(self, exp, runs_root):
        run_dir = write_run(runs_root, n=5)
        _, metrics = build_report(run_dir)
        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        for name in ("jev_only", "llm_only", "hybrid"):
            ref = metrics["splits"]["dev"][name]
            got = strat(detail, name)
            assert (
                got["metrics"]["category_accuracy"]["successes"]
                == ref["category_accuracy"]["successes"]
            )
            assert got["metrics"]["category_macro_f1"] == pytest.approx(ref["category_macro_f1"])
            assert (
                got["metrics"]["priority_accuracy"]["successes"]
                == ref["priority_accuracy"]["successes"]
            )
            assert got["metrics"]["high_priority_missed"] == ref["high_priority_missed"]
            assert got["metrics"]["review_rate"]["successes"] == ref["review_rate"]["successes"]
            assert got["metrics"]["latency_p50_ms"] == pytest.approx(ref["latency_p50_ms"])
            assert got["metrics"]["latency_p95_ms"] == pytest.approx(ref["latency_p95_ms"])
            assert Decimal(got["cost"]["known_usd"]) == Decimal(ref["cost_known_usd"])
            assert got["usage"]["input_tokens"] == ref["input_tokens_known"]
            assert got["usage"]["output_tokens"] == ref["output_tokens_known"]
            assert got["usage"]["calls"] == ref["calls_total"]

    def test_veri_seti_bulunamazsa_rakam_uretilmez(self, exp, runs_root):
        write_run(runs_root, version="v999")

        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert detail["metrics_available"] is False and detail["strategies"] == []
        assert "v999" in detail["unavailable_reason"]

    def test_tahmin_dosyasi_yoksa_rakam_uretilmez(self, exp, runs_root):
        write_run(runs_root, write_predictions=False)

        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert detail["metrics_available"] is False and detail["samples"] == []
        assert detail["unavailable_reason"]

    def test_bozuk_tahmin_satiri_rakam_uretmez_ve_icerigi_gostermez(self, exp, runs_root):
        run_dir = write_run(runs_root)
        with (run_dir / "predictions.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('{"gizli": "sk-ant-BOZUK-SATIR"\n')

        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert detail["metrics_available"] is False
        assert "satır" in detail["unavailable_reason"]
        assert "sk-ant" not in json.dumps(detail)

    def test_yarim_deney_yalniz_tamamlananlari_kapsar_ve_bunu_soyler(self, exp, runs_root):
        write_run(
            runs_root,
            n=5,
            n_completed=3,
            drop_hybrid_for=(3, 4),
            stopped={
                "reason": "provider_unavailable",
                "samples_completed": 3,
                "samples_planned": 5,
            },
        )

        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert detail["run"]["status"] == "partial" and detail["common"]["n"] == 3
        assert "partial" in [w["code"] for w in detail["warnings"]]
        assert strat(detail, "jev_only")["n"] == 3  # yalnızca ortak örnekler


class TestSamples:
    def test_ornek_satirlari_etiket_tahmin_ve_tartismali_isaret(self, exp, runs_root):
        write_run(runs_root)

        rows = {r["id"]: r for r in exp.get(f"/admin/experiments/{RUN_ID}").json()["samples"]}
        first_id, second_id = dev_samples(5)[0].id, dev_samples(5)[1].id

        second = rows[second_id]
        assert second["disputed"] == {"status": "gözden geçirme bekliyor", "note": "not"}
        assert rows[first_id]["disputed"] is None
        assert second["strategies"]["jev_only"]["category_ok"] is False  # jev 1. indekste yanlış
        assert second["strategies"]["llm_only"]["category_ok"] is True
        assert second["in_common"] is True

    def test_ornek_ayrintisi_tam_metin_beklenen_etiket_ve_uc_strateji(self, exp, runs_root):
        write_run(runs_root)
        sample = dev_samples(5)[1]

        body = exp.get(f"/admin/experiments/{RUN_ID}/samples/{sample.id}").json()

        assert body["sample"]["description"] == sample.description
        assert (
            body["sample"]["title"] == sample.title
            and body["sample"]["location"] == sample.location
        )
        assert body["sample"]["gold"]["category"] == sample.gold.category
        assert body["sample"]["disputed"]["status"] == "gözden geçirme bekliyor"
        names = [s["name"] for s in body["strategies"]]
        assert names == ["jev_only", "llm_only", "hybrid"]
        hybrid = body["strategies"][2]
        assert hybrid["escalated_questions"] == ["missing_contact"]
        assert hybrid["calls"][1]["questions"] == ["missing_contact"]
        assert Decimal(hybrid["cost_known_usd"]) == Decimal(JEV_COST) + Decimal(STAGE_COST)
        assert hybrid["latency_ms"] > 0 and hybrid["review_required"] is False

    def test_guven_turleri_ayri_kavram_olarak_aynen_tasinir(self, exp, runs_root):
        write_run(runs_root)
        sample = dev_samples(5)[0]

        body = exp.get(f"/admin/experiments/{RUN_ID}/samples/{sample.id}").json()
        kinds = {
            s["name"]: {j["question"]: j["confidence_kind"] for j in s["judgments"]}
            for s in body["strategies"]
        }

        assert kinds["jev_only"]["category"] == "jev_confidence"
        assert kinds["llm_only"]["category"] == "self_reported"
        assert kinds["jev_only"]["missing_contact"] == "derived_margin"
        contact = next(
            j for j in body["strategies"][0]["judgments"] if j["question"] == "missing_contact"
        )
        assert contact["adopted"] is False and contact["probabilities"] == {"yes": 0.63, "no": 0.37}
        # Modelin üretmediği gerekçe uydurulmaz: yanıtta gerekçe alanı yoktur.
        keys = _all_keys(body)
        assert not keys & {"reason", "rationale", "explanation", "gerekce", "aciklama", "why"}

    def test_bilinmeyen_ornek_404(self, exp, runs_root):
        write_run(runs_root)

        assert exp.get(f"/admin/experiments/{RUN_ID}/samples/s999").status_code == 404
        assert exp.get(f"/admin/experiments/{RUN_ID}/samples/..%2Frun").status_code == 404


# --------------------------------------------------------------------------- güvenlik


class TestSafety:
    @pytest.mark.parametrize(
        "run_id",
        [
            "..",
            "../runs",
            "..%2F..%2Fetc",
            "%2e%2e",
            "C:\\Windows",
            "/etc/passwd",
            "20261002T162249Z-v1-dev/../..",
            "20261002T162249Z-v1-dev%00",
            "20261002T162249Z-" + "a" * 200,
        ],
    )
    def test_dosya_yolu_ve_gezinti_denemeleri_404(self, exp, runs_root, run_id):
        write_run(runs_root)

        response = exp.get(f"/admin/experiments/{run_id}")

        assert response.status_code in (404, 405)
        assert "run.json" not in response.text and "predictions" not in response.text

    def test_olmayan_gecerli_desenli_kimlik_404(self, exp, runs_root):
        write_run(runs_root)

        assert exp.get("/admin/experiments/20250101T000000Z-v1-dev").status_code == 404

    def test_sembolik_baglanti_kok_disina_cikamaz(self, exp, runs_root, tmp_path):
        outside = tmp_path / "disarida"
        outside.mkdir()
        link = runs_root / "20260101T000000Z-v1-dev"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            # Windows'ta yetki gerektirmeyen "junction" ile aynı durumu dene.
            made = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True
            )
            if os.name != "nt" or made.returncode != 0:
                pytest.skip("Bu ortamda sembolik bağ oluşturulamıyor.")

        assert exp.get("/admin/experiments/20260101T000000Z-v1-dev").status_code == 404
        assert [r["id"] for r in exp.get("/admin/experiments").json()["runs"]] == []

    def test_yanit_gizli_alan_yerel_yol_veya_anahtar_sizdirmaz(self, exp, runs_root):
        write_run(runs_root)
        sample = dev_samples(5)[0]

        everything = (
            exp.get("/admin/experiments").text
            + exp.get(f"/admin/experiments/{RUN_ID}").text
            + exp.get(f"/admin/experiments/{RUN_ID}/samples/{sample.id}").text
        )

        for forbidden in (
            "sk-ant",
            "ASLA-SIZMAMALI",
            "RUNJSON-SIZMAMALI",
            "gizli-deger",
            "GIZLI-KULLANICI",
            "ledger",
            "req_gizli_olmayan_kimlik",
            "api_key",
        ):
            assert forbidden not in everything, forbidden

    def test_servis_katmani_beyaz_listeyi_kendisi_uygular_yanit_sablonuna_guvenmez(self, runs_root):
        # response_model ikinci savunma hattıdır; sızıntı önce servis katmanında kesilir.
        write_run(runs_root)

        detail = experiments.load_run_detail(runs_root, RUN_ID)
        sample = experiments.load_sample_detail(runs_root, RUN_ID, dev_samples(5)[0].id)

        assert set(detail["budget"]) == {
            "budget_id",
            "max_cost_usd",
            "known_spent_usd",
            "conservative_spent_usd",
            "conservative_charges",
            "calls",
            "prior_spent_usd",
            "prior_unresolved_reserved_usd",
            "total_spent_usd",
            "remaining_usd",
        }
        for strategy in sample["strategies"]:
            for call in strategy["calls"]:
                assert set(call) == {
                    "provider",
                    "model",
                    "attempt",
                    "status",
                    "duration_ms",
                    "input_tokens",
                    "output_tokens",
                    "usage_estimated",
                    "cost_usd",
                    "questions",
                    "is_mock",
                }
            for judgment in strategy["judgments"]:
                assert set(judgment) == {
                    "question",
                    "answer",
                    "probabilities",
                    "confidence",
                    "confidence_kind",
                    "n_options",
                    "source",
                    "adopted",
                }
        assert "gizli" not in json.dumps(detail) and "sk-ant" not in json.dumps(sample)

    def test_yalniz_okuma_dosya_butce_defteri_ve_klasor_degismez(self, exp, runs_root, tmp_path):
        run_dir = write_run(runs_root)
        budget = tmp_path / "budget"
        budget.mkdir()
        (budget / "ilk-deneme.json").write_text('{"entries": []}', encoding="utf-8")
        sample = dev_samples(5)[0]

        def snapshot():
            return {
                str(p): (p.stat().st_size, p.stat().st_mtime_ns)
                for root in (runs_root, budget)
                for p in root.rglob("*")
                if p.is_file()
            }

        before = snapshot()
        exp.get("/admin/experiments")
        exp.get(f"/admin/experiments/{RUN_ID}")
        exp.get(f"/admin/experiments/{RUN_ID}/samples/{sample.id}")

        assert snapshot() == before
        assert not (run_dir / "report.md").exists() and not (run_dir / "metrics.json").exists()

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_yazma_yontemleri_kabul_edilmez(self, exp, runs_root, method):
        write_run(runs_root)

        for path in ("/admin/experiments", f"/admin/experiments/{RUN_ID}"):
            assert getattr(exp, method)(path).status_code == 405

    def test_sayfayi_acmak_hicbir_model_cagrisi_baslatmaz(self, exp, runs_root, monkeypatch):
        import http.client

        import httpx

        from app.decision import factory

        write_run(runs_root)
        sample = dev_samples(5)[0]

        def forbidden(*_args, **_kwargs):
            raise AssertionError("Model/ağ çağrısı yapılmamalı")

        # Gerçek HTTP katmanları kapatılır (TestClient kendi taşıyıcısını kullanır, etkilenmez).
        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
        monkeypatch.setattr(http.client.HTTPConnection, "connect", forbidden)
        monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)
        monkeypatch.setattr(factory, "jev_provider_from_settings", forbidden)
        monkeypatch.setattr(factory, "anthropic_provider_from_settings", forbidden)

        for path in (
            "/admin/experiments",
            f"/admin/experiments/{RUN_ID}",
            f"/admin/experiments/{RUN_ID}/samples/{sample.id}",
        ):
            assert exp.get(path).status_code == 200


class TestUncertainties:
    def test_depodaki_gercek_dosya_s023u_tartismali_isaretler(self):
        marks, error = experiments.load_uncertainties("v1")

        assert error is None
        assert marks["s023"]["status"] == "gözden geçirme bekliyor"
        assert "etiket" in marks["s023"]["note"]

    def test_depodaki_dosya_bomsuz_yazilmistir(self):
        # BOM'lu JSON bazı okuyucularda reddedilir ve işaretler sessizce kaybolurdu.
        raw = experiments.default_uncertainty_file().read_bytes()

        assert not raw.startswith(b"\xef\xbb\xbf")

    def test_bomlu_dosya_da_okunur(self, tmp_path):
        path = tmp_path / "b.json"
        path.write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"datasets": {"v1": {"s001": {"status": "x"}}}}).encode()
        )

        marks, error = experiments.load_uncertainties("v1", path)

        assert error is None and marks["s001"]["status"] == "x"

    def test_dosya_yoksa_hata_degil_isaret_yok(self, tmp_path):
        assert experiments.load_uncertainties("v1", tmp_path / "yok.json") == ({}, None)

    def test_bozuk_dosya_sessizce_yutulmaz_uyari_gosterilir(self, exp, runs_root, uncertainty_file):
        write_run(runs_root)
        uncertainty_file.write_text("{bozuk", encoding="utf-8")

        detail = exp.get(f"/admin/experiments/{RUN_ID}").json()

        assert detail["metrics_available"] is True  # ölçümler yine gösterilir
        assert "uncertainty_unreadable" in [w["code"] for w in detail["warnings"]]
        assert all(row["disputed"] is None for row in detail["samples"])


# --------------------------------------------------------------------------- yetki (DB'siz)


class TestAdminOnlyWithoutDatabase:
    """Gerçek `require_admin` çalışır; yalnızca oturumdaki kullanıcının kaynağı (veritabanı) yapaydır."""

    PATHS = [
        "/admin/experiments",
        f"/admin/experiments/{RUN_ID}",
        f"/admin/experiments/{RUN_ID}/samples/s001",
    ]

    @pytest.fixture
    def guarded(self, app: FastAPI, runs_root: Path, uncertainty_file: Path):
        write_run(runs_root)
        app.dependency_overrides[get_experiments_root] = lambda: runs_root
        app.dependency_overrides[get_uncertainty_file] = lambda: uncertainty_file
        return app

    def as_role(self, app: FastAPI, role) -> TestClient:
        from types import SimpleNamespace

        from app.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role)
        return TestClient(app, raise_server_exceptions=False)

    def test_oturumsuz_istek_401(self, guarded):
        client = TestClient(guarded, raise_server_exceptions=False)

        for path in self.PATHS:
            assert client.get(path).status_code == 401, path

    def test_gecersiz_belirtec_401(self, guarded):
        client = TestClient(guarded, raise_server_exceptions=False)

        for path in self.PATHS:
            response = client.get(path, headers={"Authorization": "Bearer sahte.belirtec.degeri"})
            assert response.status_code == 401, path
            assert RUN_ID not in response.text

    @pytest.mark.parametrize("role_name", ["REQUESTER", "TECHNICIAN"])
    def test_talep_sahibi_ve_teknik_gorevli_403_ve_icerik_sizmaz(self, guarded, role_name):
        from app.domain.vocabulary import Role

        client = self.as_role(guarded, Role[role_name])

        for path in self.PATHS:
            response = client.get(path)
            assert response.status_code == 403, (role_name, path)
            assert RUN_ID not in response.text and "predictions" not in response.text
            assert "runs" not in response.json()

    def test_yonetici_200(self, guarded):
        from app.domain.vocabulary import Role

        client = self.as_role(guarded, Role.ADMIN)

        response = client.get("/admin/experiments")

        assert response.status_code == 200 and response.json()["runs"][0]["id"] == RUN_ID
        assert client.get(f"/admin/experiments/{RUN_ID}").status_code == 200

    def test_yetkisiz_istek_dosya_sistemine_hic_dokunmaz(self, guarded, monkeypatch):
        from app.domain.vocabulary import Role

        touched = []
        monkeypatch.setattr(experiments, "list_runs", lambda *a, **k: touched.append("list"))
        monkeypatch.setattr(
            experiments, "load_run_detail", lambda *a, **k: touched.append("detail")
        )
        client = self.as_role(guarded, Role.REQUESTER)

        for path in self.PATHS:
            client.get(path)

        assert touched == []  # yetki, dosya okumadan ÖNCE reddeder


# --------------------------------------------------------------------------- yetki (DB'li)


class TestAccessControl:
    PATHS = [
        "/admin/experiments",
        f"/admin/experiments/{RUN_ID}",
        f"/admin/experiments/{RUN_ID}/samples/s001",
    ]

    @pytest.fixture
    def secured(self, api, app, runs_root):
        write_run(runs_root)
        app.dependency_overrides[get_experiments_root] = lambda: runs_root
        return api

    def test_oturumsuz_401(self, secured):
        for path in self.PATHS:
            assert secured.get(path).status_code == 401

    def test_talep_sahibi_ve_teknik_gorevli_403(self, secured, make_user, auth):
        from app.domain.vocabulary import Role

        requester = make_user("ayse", Role.REQUESTER)
        technician = make_user("usta", Role.TECHNICIAN, team="plumbing")

        for user in (requester, technician):
            for path in self.PATHS:
                response = secured.get(path, headers=auth(user))
                assert response.status_code == 403, (user.username, path)
                assert RUN_ID not in response.text and "predictions" not in response.text

    def test_yonetici_200(self, secured, make_user, auth):
        from app.domain.vocabulary import Role

        admin = make_user("yonetici", Role.ADMIN)

        response = secured.get("/admin/experiments", headers=auth(admin))

        assert response.status_code == 200 and response.json()["runs"][0]["id"] == RUN_ID


# --------------------------------------------------------------------------- gerçek ilk deneme


REAL_RUN = experiments.default_runs_dir() / "20261002T162249Z-v1-dev"


@pytest.mark.skipif(not (REAL_RUN / "metrics.json").exists(), reason="Yerel ilk deney kaydı yok")
def test_gercek_ilk_deneme_panel_sayilari_metrics_json_ile_ayni(app):
    saved = json.loads((REAL_RUN / "metrics.json").read_text(encoding="utf-8"))["splits"]["dev"]

    detail = experiments.load_run_detail(REAL_RUN.parent, REAL_RUN.name)

    assert detail["metrics_available"] is True and detail["common"]["n"] == 5
    for result in detail["strategies"]:
        ref = saved[result["name"]]
        assert (
            result["metrics"]["category_accuracy"]["successes"]
            == ref["category_accuracy"]["successes"]
        )
        assert (
            result["metrics"]["priority_accuracy"]["successes"]
            == ref["priority_accuracy"]["successes"]
        )
        assert result["metrics"]["latency_p50_ms"] == pytest.approx(ref["latency_p50_ms"])
        assert Decimal(result["cost"]["known_usd"]) == Decimal(ref["cost_known_usd"])
        assert result["usage"]["calls"] == ref["calls_total"]
        assert result["usage"]["input_tokens"] == ref["input_tokens_known"]
    assert detail["run"]["hybrid_routing"]["recorded"] is False
    # Gerçek dosyayla tartışmalı etiket (s023) işaretlenir; etiket ve sonuç değişmez.
    disputed = {row["id"] for row in detail["samples"] if row["disputed"]}
    assert disputed == {"s023"}
    assert "disputed_labels" in [w["code"] for w in detail["warnings"]]
    assert detail["run"]["scope_label"] == "5 sentetik geliştirme örneği — bağlantı denemesi"
