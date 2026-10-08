"""PostgreSQL'deki kalıcı ve atomik bütçe (gerçek veritabanıyla). Canlı demo ücretli çağrılarının
toplam sınırı buradan zorlanır; eşzamanlı istekler ve yeniden başlatmalar sınırı aşamaz."""

import threading
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.decision.budget import BudgetedProvider, Reservation
from app.decision.contract import ALL_QUESTIONS, BudgetExhausted, StrategyName
from app.decision.jev import JevProvider
from app.decision.pg_budget import (
    PgBudgetGuard,
    committed_usd,
    price_version_text,
    status,
)
from app.decision.pricing import JEV_1_13
from app.decision.providers import ProviderError
from app.models import Budget, BudgetEntry
from tests.decision.conftest import make_input
from tests.decision.test_jev import KEY, ok_response

BUDGET = "test-demo"
D = Decimal


@pytest.fixture
def session_factory(db_engine):
    return lambda: Session(db_engine)


@pytest.fixture
def budget(db, db_engine):
    """0,001 USD toplam sınırlı bütçe kapsamı. Testler arası temizlenir."""
    db.add(Budget(id=BUDGET, cap_usd=D("0.001"), purpose="test"))
    db.commit()
    yield BUDGET
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE budget_entries, budgets RESTART IDENTITY CASCADE"))


def guard(session_factory, budget_id=BUDGET, job_id=None) -> PgBudgetGuard:
    return PgBudgetGuard(session_factory, budget_id, job_id=job_id, price=JEV_1_13)


def entries(session_factory) -> list[BudgetEntry]:
    with session_factory() as db:
        return list(db.query(BudgetEntry).order_by(BudgetEntry.id))


class TestReserve:
    def test_rezervasyon_cagridan_once_kalici_ve_bekleyen_yazilir(self, budget, session_factory):
        reservation = guard(session_factory).reserve(D("0.0001"), provider="jev", model="m")

        rows = entries(session_factory)  # ayrı bir oturumdan görünür = commit edilmiş
        assert len(rows) == 1 and rows[0].id == reservation.seq
        assert rows[0].state == "pending" and rows[0].reserved_usd == D("0.0001")
        assert rows[0].charge_usd is None and rows[0].known is None
        assert "jev-1.13.0" in rows[0].price_version and "0.042" in rows[0].price_version

    def test_sinir_asilirsa_cagri_gonderilmez_ve_satir_yazilmaz(self, budget, session_factory):
        g = guard(session_factory)

        with pytest.raises(BudgetExhausted):
            g.reserve(D("0.0011"))

        assert entries(session_factory) == []

    def test_tam_sinirda_rezerve_edilir_bir_kurus_fazlasinda_edilmez(self, budget, session_factory):
        g = guard(session_factory)
        g.reserve(D("0.0009"))

        g.reserve(D("0.0001"))  # tam sınır: kabul
        with pytest.raises(BudgetExhausted):
            g.reserve(D("0.0000000001"))  # en küçük fazlalık: ret

    def test_tanimsiz_butce_kapsami_ucretli_cagriyi_engeller(self, budget, session_factory):
        with pytest.raises(BudgetExhausted, match="tanımlı değil"):
            guard(session_factory, budget_id="yok-boyle-bir-kapsam").reserve(D("0.0001"))

    @pytest.mark.parametrize("amount", [D("0"), D("-0.0001")])
    def test_sifir_veya_negatif_rezervasyon_reddedilir(self, budget, session_factory, amount):
        with pytest.raises(BudgetExhausted):
            guard(session_factory).reserve(amount)

    def test_kapsamlar_birbirinden_bagimsiz(self, budget, session_factory, db):
        db.add(Budget(id="baska", cap_usd=D("0.0002"), purpose="test"))
        db.commit()
        guard(session_factory).reserve(D("0.001"))  # test-demo doldu

        guard(session_factory, "baska").reserve(D("0.0002"))  # diğer kapsam etkilenmez

        with session_factory() as s:
            assert committed_usd(s, BUDGET) == D("0.001")
            assert committed_usd(s, "baska") == D("0.0002")

    def test_dosya_defteri_olusturulmaz_degerlendirme_defterinden_bagimsiz(
        self, budget, session_factory, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)

        guard(session_factory).reserve(D("0.0001"))

        assert list(tmp_path.iterdir()) == []  # hiçbir dosya yazılmadı


class TestSettle:
    def test_bilinen_ucret_gercek_bedelle_kesinlesir(self, budget, session_factory):
        g = guard(session_factory)
        reservation = g.reserve(D("0.0001"))

        g.settle(reservation, D("0.00004"), input_tokens=900, output_tokens=170)

        row = entries(session_factory)[0]
        assert row.state == "settled" and row.known is True
        assert row.charge_usd == D("0.00004") and row.exceeded_reservation is False
        assert (row.input_tokens, row.output_tokens) == (900, 170)
        assert row.settled_at is not None

    def test_bilinmeyen_ucret_rezervasyon_bedeliyle_muhafazakar_sayilir(
        self, budget, session_factory
    ):
        g = guard(session_factory)
        reservation = g.reserve(D("0.0001"))

        g.settle(reservation, None)

        row = entries(session_factory)[0]
        assert row.state == "settled" and row.known is False
        assert row.charge_usd == D("0.0001")  # sıfır DEĞİL: en kötü durum

    def test_gercek_ucret_rezervasyonu_asarsa_isaretlenir(self, budget, session_factory):
        g = guard(session_factory)
        reservation = g.reserve(D("0.0001"))

        g.settle(reservation, D("0.0002"))

        row = entries(session_factory)[0]
        assert row.exceeded_reservation is True and row.charge_usd == D("0.0002")

    def test_ikinci_kesinlestirme_sonucu_degistirmez(self, budget, session_factory):
        g = guard(session_factory)
        reservation = g.reserve(D("0.0001"))
        g.settle(reservation, D("0.00003"))

        g.settle(reservation, None)  # çift çağrı: ilk kayıt korunur

        row = entries(session_factory)[0]
        assert row.known is True and row.charge_usd == D("0.00003")

    def test_veritabani_hatasinda_satir_bekleyen_kalir_ve_istisna_firlatmaz(
        self, budget, session_factory
    ):
        g = guard(session_factory)
        reservation = g.reserve(D("0.0001"))

        def broken():
            raise SQLAlchemyError("bağlantı koptu")

        g._session_factory = broken

        g.settle(reservation, D("0.00003"))  # sonuç kullanıcıya dönebilsin: istisna yok

        row = entries(session_factory)[0]
        assert row.state == "pending"  # en kötü bedelle sayılmaya devam eder
        with session_factory() as s:
            assert committed_usd(s, BUDGET) == D("0.0001")


class TestStatus:
    def test_bilinen_muhafazakar_ve_cozulmemis_ayri_raporlanir(self, budget, session_factory):
        g = guard(session_factory)
        g.settle(g.reserve(D("0.00010")), D("0.00004"))  # bilinen gerçek
        g.settle(g.reserve(D("0.00020")), None)  # bilinemeyen: en kötü bedel
        g.reserve(D("0.00030"))  # çözülmemiş (çağrı sürüyor veya süreç öldü)

        with session_factory() as s:
            st = status(s, BUDGET)

        assert st.cap_usd == D("0.001")
        assert st.known_usd == D("0.00004")
        assert st.conservative_usd == D("0.00020")
        assert st.unresolved_usd == D("0.00030")
        assert st.remaining_usd == D("0.001") - D("0.00004") - D("0.0002") - D("0.0003")
        assert (st.entries, st.pending_entries) == (3, 1)
        assert len(st.price_versions) == 1 and "jev-1.13.0" in st.price_versions[0]

    def test_tanimsiz_kapsam_none(self, budget, session_factory):
        with session_factory() as s:
            assert status(s, "yok") is None

    def test_sinir_asimi_sayaci(self, budget, session_factory):
        g = guard(session_factory)
        g.settle(g.reserve(D("0.0001")), D("0.0005"))

        with session_factory() as s:
            assert status(s, BUDGET).bound_violations == 1

    def test_cozulmemis_rezervasyon_cokmeden_sonra_da_butceden_dusulur(
        self, budget, session_factory
    ):
        """Süreç çağrı sırasında ölür (settle hiç çağrılmaz); yeniden başlayan süreç (yeni guard)
        o rezervasyonu SIFIR harcama saymaz."""
        guard(session_factory).reserve(D("0.0009"))  # süreç 1: çağrıdan sonra öldü

        restarted = guard(session_factory)  # süreç 2
        with pytest.raises(BudgetExhausted):
            restarted.reserve(D("0.0002"))  # 0,0009 hâlâ taahhütte: 0,0002 sığmaz
        restarted.reserve(D("0.0001"))  # kalan 0,0001 sığar


class TestConcurrency:
    def _race(self, session_factory, n_threads: int, amount: Decimal):
        barrier = threading.Barrier(n_threads)
        results: list[object] = []
        lock = threading.Lock()

        def worker():
            g = guard(session_factory)
            barrier.wait()  # hepsi aynı anda başlasın
            try:
                outcome: object = g.reserve(amount)
            except BudgetExhausted as exc:
                outcome = exc
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        return results

    def test_esanli_istekler_toplam_siniri_asamaz(self, budget, session_factory):
        """Sınır tam 10 rezervasyona yetiyor; 40 iş parçacığı (her biri kendi bağlantısı =
        birden çok süreçteki gibi) aynı anda 10'a istiyor: tam 10 tanesi kabul edilir."""
        results = self._race(session_factory, n_threads=40, amount=D("0.0001"))

        accepted = [r for r in results if isinstance(r, Reservation)]
        refused = [r for r in results if isinstance(r, BudgetExhausted)]
        assert len(results) == 40
        assert len(accepted) == 10 and len(refused) == 30
        with session_factory() as s:
            assert committed_usd(s, BUDGET) == D("0.001")  # asla aşılmadı, tam dolu
        assert len(entries(session_factory)) == 10  # reddedilenler satır bırakmadı

    def test_farkli_tutarlarda_da_toplam_siniri_asmaz(self, budget, session_factory):
        for _ in range(3):  # yarışı birkaç tur tekrarla
            with session_factory() as db:
                db.execute(text("TRUNCATE budget_entries RESTART IDENTITY"))
                db.commit()
            results = self._race(session_factory, n_threads=30, amount=D("0.00033"))

            accepted = [r for r in results if isinstance(r, Reservation)]
            assert len(accepted) == 3  # 3 × 0,00033 = 0,00099 ≤ 0,001 < 4 × 0,00033
            with session_factory() as s:
                assert committed_usd(s, BUDGET) <= D("0.001")

    def test_rezervasyon_ve_kesinlestirme_karisik_calisirken_taahhut_hep_sinirin_altinda(
        self, budget, session_factory
    ):
        stop = threading.Event()
        violations: list[Decimal] = []

        def monitor():
            while not stop.is_set():
                with session_factory() as s:
                    total = committed_usd(s, BUDGET)
                if total > D("0.001"):
                    violations.append(total)

        def worker():
            g = guard(session_factory)
            for _ in range(8):
                try:
                    reservation = g.reserve(D("0.00015"))
                except BudgetExhausted:
                    continue
                g.settle(reservation, D("0.00004"))  # gerçek ücret rezervasyondan küçük

        watcher = threading.Thread(target=monitor)
        watcher.start()
        workers = [threading.Thread(target=worker) for _ in range(12)]
        for t in workers:
            t.start()
        for t in workers:
            t.join(timeout=120)
        stop.set()
        watcher.join(timeout=10)

        assert violations == []
        with session_factory() as s:
            assert committed_usd(s, BUDGET) <= D("0.001")


class TestDatabaseConstraints:
    def test_kesinlesmis_satir_tutarsiz_olamaz(self, budget, db_engine):
        with pytest.raises(IntegrityError), db_engine.begin() as conn:
            conn.execute(
                text(
                    "insert into budget_entries (budget_id, provider, model, price_version, "
                    "reserved_usd, state) values (:b, 'jev', 'm', 'v', 0.0001, 'settled')"
                ),
                {"b": BUDGET},
            )

    def test_pozitif_olmayan_rezervasyon_ve_gecersiz_durum_reddedilir(self, budget, db_engine):
        for reserved, state in ((0, "pending"), (0.0001, "bilinmeyen")):
            with pytest.raises(IntegrityError), db_engine.begin() as conn:
                conn.execute(
                    text(
                        "insert into budget_entries (budget_id, provider, model, price_version, "
                        "reserved_usd, state) values (:b, 'jev', 'm', 'v', :r, :s)"
                    ),
                    {"b": BUDGET, "r": reserved, "s": state},
                )

    def test_butce_siniri_pozitif_olmali(self, db, db_engine):
        with pytest.raises(IntegrityError), db_engine.begin() as conn:
            conn.execute(text("insert into budgets (id, cap_usd) values ('sifir', 0)"))


class TestWithBudgetedProvider:
    """Gerçek JevProvider (sahte HTTP) + BudgetedProvider + PostgreSQL bütçesi."""

    DATA = make_input("Lavabo akıtıyor", "B blok ikinci kattaki lavabo akıtıyor.")

    def _provider(self, session_factory, handler, **guard_kwargs):
        jev = JevProvider(KEY, transport=httpx.MockTransport(handler))
        return BudgetedProvider(jev, guard(session_factory, **guard_kwargs))

    def test_basarili_cagri_bildirilen_kullanimdan_gercek_ucreti_yazar(
        self, budget, session_factory
    ):
        provider = self._provider(session_factory, lambda r: ok_response())

        provider.classify(self.DATA, ALL_QUESTIONS, StrategyName.JEV_ONLY)

        row = entries(session_factory)[0]
        assert row.state == "settled" and row.known is True
        assert row.charge_usd == D("392") / D(1_000_000) * D("0.042")  # 392 girdi token'ı
        assert (row.input_tokens, row.output_tokens) == (392, 65)
        assert row.charge_usd < row.reserved_usd  # üst sınır gerçek ücretten büyük

    def test_zaman_asimi_ucreti_bilinmez_en_kotu_bedelle_sayilir(self, budget, session_factory):
        def timeout(request):
            raise httpx.ReadTimeout("zaman aşımı", request=request)

        provider = self._provider(session_factory, timeout)

        with pytest.raises(ProviderError):
            provider.classify(self.DATA, ALL_QUESTIONS, StrategyName.JEV_ONLY)

        row = entries(session_factory)[0]
        assert row.state == "settled" and row.known is False
        assert row.charge_usd == row.reserved_usd  # sıfır değil

    def test_kullanim_bilgisi_eksikse_maliyet_bilinmez(self, budget, session_factory):
        provider = self._provider(session_factory, lambda r: ok_response(usage={}))

        provider.classify(self.DATA, ALL_QUESTIONS, StrategyName.JEV_ONLY)

        row = entries(session_factory)[0]
        assert row.known is False and row.charge_usd == row.reserved_usd
        assert (row.input_tokens, row.output_tokens) == (None, None)  # uydurulmadı

    def test_butce_yetmezse_istek_hic_gonderilmez(self, budget, session_factory, db):
        sent = []
        provider = self._provider(session_factory, lambda r: sent.append(r) or ok_response())
        db.query(Budget).filter_by(id=BUDGET).update({"cap_usd": D("0.0000001")})
        db.commit()

        with pytest.raises(BudgetExhausted):
            provider.classify(self.DATA, ALL_QUESTIONS, StrategyName.JEV_ONLY)

        assert sent == [] and entries(session_factory) == []

    def test_farkli_model_surumunde_ucret_bilinmez(self, budget, session_factory):
        provider = self._provider(session_factory, lambda r: ok_response(model="jev-9.9.9"))

        provider.classify(self.DATA, ALL_QUESTIONS, StrategyName.JEV_ONLY)

        assert entries(session_factory)[0].known is False  # doğrulanmamış fiyat uygulanmaz


def test_fiyat_surumu_metni_fiyati_kaynagi_tarihi_ve_varsayimi_icerir():
    text_ = price_version_text(JEV_1_13, max_attempts=1)

    for part in ("jev-1.13.0", "0.042 USD/1M girdi", "0 USD/1M çıktı", "2026-10-08", "bayt"):
        assert part in text_
    assert "deneme hakkı 1" in text_
    assert price_version_text(None) == "fiyat bilinmiyor"
