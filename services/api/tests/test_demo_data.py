"""Demo verisi: süresi dolan ziyaretçilerin temizlenmesi ve deney sonuçlarının statik dışa aktarımı."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import export_demo, manage, worker
from app.config import Settings
from app.domain.vocabulary import Role
from app.models import (
    Budget,
    BudgetEntry,
    Decision,
    DecisionJob,
    DemoRequest,
    ModelCall,
    Ticket,
    TicketEvent,
    User,
)
from app.services import demo
from tests.test_experiments import RUN_ID, write_run

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def exists(db: Session, model, row_id) -> bool:
    """Satır veritabanında var mı (kimlik haritasındaki eski nesneye değil, gerçek duruma bakar)."""
    return bool(db.scalar(select(func.count()).select_from(model).where(model.id == row_id)))


def make_visitor(db: Session, name: str, age_hours: float) -> User:
    user = User(
        username=name,
        display_name="Ziyaretçi",
        password_hash="!demo",
        role=Role.REQUESTER,
        is_demo=True,
        created_at=NOW - timedelta(hours=age_hours),
    )
    db.add(user)
    db.commit()
    return user


def decided_ticket(db_engine, make_ticket, owner: User) -> Ticket:
    """Karar işi işlenmiş (karar + model çağrısı yazılmış) talep."""
    ticket = make_ticket(owner, decision_strategy="mock_jev")
    worker.drain(
        lambda: Session(db_engine), worker_id="test", lease=timedelta(seconds=60), max_jobs=1
    )
    return ticket


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, demo_retention_hours=72)


class TestPurge:
    def test_suresi_dolan_ziyaretci_ve_tum_verisi_silinir(
        self, db, db_engine, make_ticket, settings
    ):
        old = make_visitor(db, "ziyaretci-eski", age_hours=80)
        ticket = decided_ticket(db_engine, make_ticket, old)
        db.add(DemoRequest(user_id=old.id, ticket_id=ticket.id, request_key="k" * 64))
        db.commit()
        assert count(db, Decision) == 1 and count(db, ModelCall) >= 1

        removed = demo.purge_expired(db, settings, NOW)

        assert removed == 1
        for model in (User, Ticket, TicketEvent, DecisionJob, Decision, ModelCall, DemoRequest):
            assert count(db, model) == 0, model.__name__

    def test_suresi_dolmayan_ziyaretci_ve_talepleri_korunur(
        self, db, db_engine, make_ticket, settings
    ):
        fresh = make_visitor(db, "ziyaretci-yeni", age_hours=71.9)
        decided_ticket(db_engine, make_ticket, fresh)

        assert demo.purge_expired(db, settings, NOW) == 0

        assert count(db, User) == 1 and count(db, Ticket) == 1 and count(db, Decision) == 1

    def test_gercek_kullanicilar_ve_yerel_kayitlar_asla_silinmez(
        self, db, db_engine, make_user, make_ticket, settings
    ):
        """Çok eski olsalar bile `is_demo` olmayan hesaplar (seed, E2E, gerçek kullanıcı) kalır."""
        real = make_user("gercek.eski")
        real.created_at = NOW - timedelta(days=400)
        db.add(real)
        db.commit()
        kept = decided_ticket(db_engine, make_ticket, real)
        make_visitor(db, "ziyaretci-eski", age_hours=500)

        removed = demo.purge_expired(db, settings, NOW)

        assert removed == 1
        assert exists(db, User, real.id)
        assert exists(db, Ticket, kept.id)
        assert count(db, Decision) == 1  # gerçek kullanıcının kararı duruyor

    def test_yalnizca_ziyaretcinin_talepleri_silinir_digerininki_degil(
        self, db, db_engine, make_user, make_ticket, settings
    ):
        real = make_user("gercek")
        keep_id = make_ticket(real).id
        old = make_visitor(db, "ziyaretci-eski", age_hours=100)
        gone_id = make_ticket(old).id  # silinmeden ÖNCE okunur (silinince nesne süresi dolar)

        demo.purge_expired(db, settings, NOW)

        assert exists(db, Ticket, keep_id) and not exists(db, Ticket, gone_id)

    def test_butce_kayitlari_silinmez_yalnizca_is_baglantisi_bosalir(
        self, db, db_engine, make_ticket, settings
    ):
        db.add(Budget(id="canli-demo", cap_usd=Decimal("0.25")))
        db.commit()
        old = make_visitor(db, "ziyaretci-eski", age_hours=100)
        ticket = decided_ticket(db_engine, make_ticket, old)
        job = db.scalar(select(DecisionJob).where(DecisionJob.ticket_id == ticket.id))
        db.add(
            BudgetEntry(
                budget_id="canli-demo",
                job_id=job.id,
                provider="jev",
                model="jev-1.13.0",
                price_version="v",
                reserved_usd=Decimal("0.0001"),
                state="settled",
                charge_usd=Decimal("0.00004"),
                known=True,
            )
        )
        db.commit()

        demo.purge_expired(db, settings, NOW)

        entry = db.scalar(select(BudgetEntry))
        assert entry is not None and entry.charge_usd == Decimal("0.00004")  # harcama kaydı kalır
        assert entry.job_id is None  # iş silindi; bağlantı boşaldı, kayıt silinmedi

    def test_saklama_suresi_ayardan_gelir(self, db):
        make_visitor(db, "ziyaretci-a", age_hours=2)
        short = Settings(_env_file=None, demo_retention_hours=1)

        assert demo.purge_expired(db, short, NOW) == 1

    def test_sinirli_partilerle_silinir(self, db, settings):
        total = demo.PURGE_BATCH + 7
        for i in range(total):
            make_visitor(db, f"ziyaretci-{i:04d}", age_hours=100 + i)

        first = demo.purge_expired(db, settings, NOW)
        second = demo.purge_expired(db, settings, NOW)

        assert (first, second) == (demo.PURGE_BATCH, 7)
        assert count(db, User) == 0

    def test_silinecek_yoksa_sifir(self, db, settings):
        assert demo.purge_expired(db, settings, NOW) == 0

    def test_cli_purge_demo_komutu(self, db, db_engine, monkeypatch, capsys):
        monkeypatch.setattr(manage, "get_engine", lambda: db_engine)
        monkeypatch.setattr(manage, "get_settings", lambda: Settings(_env_file=None))
        make_visitor(db, "ziyaretci-eski", age_hours=24 * 30)
        make_visitor(db, "ziyaretci-yeni", age_hours=1)

        assert manage.main(["purge-demo"]) == 0

        assert "1 süresi dolmuş ziyaretçi hesabı" in capsys.readouterr().out
        assert [u.username for u in db.scalars(select(User))] == ["ziyaretci-yeni"]


# --- Statik dışa aktarım ---


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir()
    return root


class TestExport:
    def test_gercek_deney_listesi_ayrintisi_ve_ornekleri_yazilir(self, runs, tmp_path):
        write_run(runs, RUN_ID, n=5, live=True)
        out = tmp_path / "demo-data"

        written = export_demo.export_demo_data(runs, out)

        assert {p.name for p in written} == {"experiments.json", "vocabulary.json"}
        data = json.loads((out / "experiments.json").read_text(encoding="utf-8"))
        assert [r["id"] for r in data["list"]["runs"]] == [RUN_ID]
        detail = data["details"][RUN_ID]
        assert detail["run"]["id"] == RUN_ID and len(detail["samples"]) == 5
        assert set(data["samples"][RUN_ID]) == {row["id"] for row in detail["samples"]}
        vocab = json.loads((out / "vocabulary.json").read_text(encoding="utf-8"))
        assert {"categories", "priorities", "statuses"} <= set(vocab)

    def test_ciktida_defter_yolu_anahtar_veya_yerel_yol_yoktur(self, runs, tmp_path):
        write_run(
            runs,
            RUN_ID,
            live=True,
            extra_run={"secret": "sk-ant-GIZLI-OLMALI-DEGIL", "api_key": "sk-ant-XYZ"},
        )
        out = tmp_path / "demo-data"

        export_demo.export_demo_data(runs, out)

        blob = (out / "experiments.json").read_text(encoding="utf-8")
        for forbidden in ("sk-ant", "ledger", "GIZLI", str(tmp_path), "api_key"):
            assert forbidden not in blob, forbidden

    def test_mock_ve_ucretsiz_calistirmalar_varsayilan_olarak_yayimlanmaz(self, runs, tmp_path):
        write_run(runs, "20261001T100000Z-mock", live=False, mock=True)
        write_run(runs, RUN_ID, live=True)

        export_demo.export_demo_data(runs, tmp_path / "o")

        data = json.loads((tmp_path / "o" / "experiments.json").read_text(encoding="utf-8"))
        assert [r["id"] for r in data["list"]["runs"]] == [RUN_ID]
        assert "20261001T100000Z-mock" not in data["details"]

    def test_mock_bayragiyla_dahil_edilir(self, runs, tmp_path):
        write_run(runs, "20261001T100000Z-mock", live=False, mock=True)

        export_demo.export_demo_data(runs, tmp_path / "o", include_mock=True)

        data = json.loads((tmp_path / "o" / "experiments.json").read_text(encoding="utf-8"))
        assert [r["id"] for r in data["list"]["runs"]] == ["20261001T100000Z-mock"]

    def test_eksik_dosyali_ve_bozuk_deneyler_rakam_uretilmeden_disarida_kalir(self, runs, tmp_path):
        (runs / "20261002T000000Z-bos").mkdir()  # run.json yok
        write_run(runs, RUN_ID, live=True)

        export_demo.export_demo_data(runs, tmp_path / "o")

        data = json.loads((tmp_path / "o" / "experiments.json").read_text(encoding="utf-8"))
        assert [r["id"] for r in data["list"]["runs"]] == [RUN_ID]

    def test_deney_klasoru_yoksa_bos_liste(self, tmp_path):
        export_demo.export_demo_data(tmp_path / "yok", tmp_path / "o")

        data = json.loads((tmp_path / "o" / "experiments.json").read_text(encoding="utf-8"))
        assert data["list"] == {"runs_dir_found": False, "runs": []}
        assert data["details"] == {} and data["samples"] == {}

    def test_cikti_belirleyici_ayni_kayitlardan_ayni_bayt(self, runs, tmp_path):
        write_run(runs, RUN_ID, live=True)

        export_demo.export_demo_data(runs, tmp_path / "a")
        export_demo.export_demo_data(runs, tmp_path / "b")

        for name in ("experiments.json", "vocabulary.json"):
            assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()

    def test_kaynak_kayitlar_degismez(self, runs, tmp_path):
        run_dir = write_run(runs, RUN_ID, live=True)
        before = {p.name: p.read_bytes() for p in run_dir.iterdir()}

        export_demo.export_demo_data(runs, tmp_path / "o")

        assert {p.name: p.read_bytes() for p in run_dir.iterdir()} == before

    def test_cli_komutu_dosyalari_yazar(self, runs, tmp_path, capsys):
        write_run(runs, RUN_ID, live=True)

        code = manage.main(
            ["export-demo-data", "--runs-dir", str(runs), "--out", str(tmp_path / "o")]
        )

        assert code == 0
        assert "2 dosya yazıldı" in capsys.readouterr().out
        assert (tmp_path / "o" / "experiments.json").is_file()


def test_vt_temizligi_butce_tablosuna_dokunmaz(db_engine):
    """Test verisi temizliği (conftest) bütçe kapsamlarını da boşaltır: testler arası sızıntı yok."""
    with db_engine.connect() as conn:
        assert conn.scalar(text("select count(*) from budgets")) == 0
