import json
import os
from decimal import Decimal

import pytest

from app.decision.budget import BudgetGuard
from app.decision.budget_ledger import (
    BudgetLedger,
    LedgerCapMismatch,
    LedgerError,
    LedgerLocked,
)
from app.decision.contract import BudgetExhausted

CAP = Decimal("0.10")


@pytest.fixture
def path(tmp_path):
    return tmp_path / "defter" / "deneme.json"


def open_ledger(path, cap=CAP, budget_id="deneme"):
    return BudgetLedger.open(path, budget_id=budget_id, cap=cap)


def on_disk(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestLedgerFile:
    def test_ilk_acilista_sinirla_olusturulur_ve_kilit_alinir(self, path):
        ledger = open_ledger(path)

        assert on_disk(path)["cap_usd"] == "0.10" and on_disk(path)["entries"] == []
        assert path.with_suffix(".lock").exists()
        ledger.release()
        assert not path.with_suffix(".lock").exists()

    def test_yeni_defter_icin_sinir_zorunlu(self, path):
        with pytest.raises(LedgerError, match="pozitif"):
            open_ledger(path, cap=None)

        assert not path.with_suffix(".lock").exists()  # başarısız açılış kilit bırakmaz

    def test_rezervasyon_cagridan_once_diske_yazilir(self, path):
        ledger = open_ledger(path)

        seq = ledger.begin("kosu-1", "anthropic", "claude-haiku-4-5-20251001", Decimal("0.0094"))

        entry = on_disk(path)["entries"][0]  # başka bir okuyucu da görür: kalıcı
        assert seq == 1 and entry["state"] == "pending" and entry["reserved_usd"] == "0.0094"
        assert entry["provider"] == "anthropic" and entry["run_id"] == "kosu-1"
        ledger.release()

    def test_kesinlesme_diske_yazilir_gercek_ve_en_kotu_bedel_ayri_isaretlenir(self, path):
        ledger = open_ledger(path)
        a = ledger.begin("k", "anthropic", "m", Decimal("0.01"))
        b = ledger.begin("k", "jev", "m", Decimal("0.02"))

        ledger.settle(a, Decimal("0.002"), known=True)
        ledger.settle(b, Decimal("0.02"), known=False)  # bilinemedi → en kötü bedel

        rows = on_disk(path)["entries"]
        assert [r["state"] for r in rows] == ["settled", "settled"]
        assert [r["known"] for r in rows] == [True, False]
        status = ledger.status()
        assert status["settled_known_usd"] == "0.002"
        assert status["settled_conservative_usd"] == "0.020"
        assert status["settled_total_usd"] == "0.022"
        assert status["unresolved_reserved_usd"] == "0"
        ledger.release()

    def test_diske_yazma_basarisizsa_rezervasyon_verilmez_istek_gonderilmez(
        self, path, monkeypatch
    ):
        ledger = open_ledger(path)

        def broken(*args, **kwargs):
            raise OSError("disk dolu")

        monkeypatch.setattr(os, "replace", broken)
        with pytest.raises(OSError):
            ledger.begin("k", "anthropic", "m", Decimal("0.01"))

        assert ledger.entries == []  # bellekte de kalmadı: sayaç ile disk ayrışmaz
        monkeypatch.undo()
        ledger.release()

    def test_defterde_anahtar_istek_veya_yanit_metni_yok(self, path):
        ledger = open_ledger(path)
        seq = ledger.begin("kosu", "anthropic", "claude-haiku-4-5-20251001", Decimal("0.01"))
        ledger.settle(seq, Decimal("0.002"), known=True)
        ledger.release()

        text = path.read_text(encoding="utf-8")

        assert "sk-" not in text and "Bearer" not in text and "x-api-key" not in text
        assert set(on_disk(path)["entries"][0]) == {
            "seq",
            "run_id",
            "provider",
            "model",
            "reserved_usd",
            "state",
            "reserved_at",
            "charge_usd",
            "known",
            "settled_at",
        }


class TestLedgerLockAndCap:
    def test_ikinci_surec_ayni_defteri_acamaz(self, path):
        first = open_ledger(path)

        with pytest.raises(LedgerLocked) as caught:
            open_ledger(path)

        assert "kilit" in str(caught.value).lower() and str(path.with_suffix(".lock")) in str(
            caught.value
        )
        assert path.with_suffix(".lock").exists()  # kilit AÇAN süreçte kaldı, silinmedi
        first.release()
        open_ledger(path).release()  # bırakılınca açılır

    def test_cokmus_surecin_biraktigi_kilit_otomatik_silinmez_kullaniciya_bildirilir(self, path):
        open_ledger(path)  # release çağrılmadan "çöktü"

        with pytest.raises(LedgerLocked, match="SİLME"):
            open_ledger(path)

        assert path.with_suffix(".lock").exists()

    @pytest.mark.parametrize("other", [Decimal("0.20"), Decimal("0.05"), Decimal("1")])
    def test_farkli_sinirla_acmak_reddedilir_kendiliginden_artirilmaz(self, path, other):
        open_ledger(path).release()

        with pytest.raises(LedgerCapMismatch, match="kendiliğinden değiştirilmez"):
            open_ledger(path, cap=other)

        assert on_disk(path)["cap_usd"] == "0.10"
        assert not path.with_suffix(".lock").exists()  # reddedilen açılış kilidi bırakmaz

    def test_ayni_sinir_veya_sinir_verilmemesi_kabul_edilir(self, path):
        open_ledger(path).release()

        open_ledger(path, cap=CAP).release()
        ledger = open_ledger(path, cap=None)
        assert ledger.cap == CAP
        ledger.release()

    def test_farkli_kimlikle_acilamaz(self, path):
        open_ledger(path).release()

        with pytest.raises(LedgerError, match="kimliği"):
            open_ledger(path, budget_id="baska")

    def test_salt_okunur_acilis_kilit_almaz(self, path):
        held = open_ledger(path)

        status = BudgetLedger.read(path).status()

        assert status["cap_usd"] == "0.10"
        held.release()

    def test_olmayan_defter_okunamaz(self, tmp_path):
        with pytest.raises(LedgerError, match="yok"):
            BudgetLedger.read(tmp_path / "yok.json")


class TestGuardWithLedger:
    def test_sinir_ve_onceki_harcama_defterden_gelir(self, path):
        first = open_ledger(path)
        guard = BudgetGuard(
            Decimal("999"), ledger=first, run_id="kosu-1"
        )  # verilen sınır yok sayılır
        reservation = guard.reserve(Decimal("0.03"), provider="anthropic", model="m")
        guard.settle(reservation, Decimal("0.03"))
        first.release()

        second = open_ledger(path)
        restarted = BudgetGuard(Decimal("999"), ledger=second, run_id="kosu-2")

        assert restarted.cap == CAP  # defter tek kaynak
        assert restarted.prior_spent == Decimal("0.03")
        assert restarted.remaining() == Decimal("0.07")  # YENİ 0,10 açılmadı
        second.release()

    def test_yeniden_baslatmada_kalan_butceyi_asan_rezervasyon_reddedilir(self, path):
        first = open_ledger(path)
        guard = BudgetGuard(CAP, ledger=first)
        reservation = guard.reserve(Decimal("0.08"))
        guard.settle(reservation, Decimal("0.08"))
        first.release()

        second = open_ledger(path)
        restarted = BudgetGuard(CAP, ledger=second)

        with pytest.raises(BudgetExhausted):
            restarted.reserve(Decimal("0.03"))  # 0,08 + 0,03 > 0,10
        assert restarted.reserve(Decimal("0.02")).amount == Decimal("0.02")  # tam kalan sığar
        second.release()

    def test_cokmeden_kalan_cozulmemis_rezervasyon_en_kotu_bedelle_dusulur(self, path):
        first = open_ledger(path)
        guard = BudgetGuard(CAP, ledger=first)
        guard.reserve(Decimal("0.04"))  # istek gitti, süreç ÇÖKTÜ: settle çağrılmadı
        path.with_suffix(".lock").unlink()  # çökmeyi benzet (kilit kalmış olsaydı reddedilirdi)

        second = open_ledger(path)
        restarted = BudgetGuard(CAP, ledger=second)

        assert restarted.prior_unresolved == Decimal("0.04")
        assert restarted.remaining() == Decimal("0.06")  # belirsiz rezervasyon düşüldü
        summary = restarted.summary()
        assert summary["prior_unresolved_reserved_usd"] == "0.04"
        assert summary["prior_spent_usd"] == "0"  # çözülmemiş, gerçek harcamadan AYRI raporlanır
        assert summary["remaining_usd"] == "0.06"
        second.release()

    def test_rezervasyon_defterde_pending_olarak_yazilmadan_guard_izin_vermez(self, path):
        ledger = open_ledger(path)
        guard = BudgetGuard(CAP, ledger=ledger, run_id="kosu")

        guard.reserve(Decimal("0.01"), provider="jev", model="jev-1.13.0")

        entry = on_disk(path)["entries"][0]
        assert entry["state"] == "pending" and entry["provider"] == "jev"
        assert entry["model"] == "jev-1.13.0" and entry["run_id"] == "kosu"
        ledger.release()

    def test_ozet_gercek_en_kotu_onceki_ve_cozulmemis_kalemleri_ayri_verir(self, path):
        first = open_ledger(path)
        g1 = BudgetGuard(CAP, ledger=first)
        r = g1.reserve(Decimal("0.02"))
        g1.settle(r, Decimal("0.005"))
        g1.reserve(Decimal("0.01"))  # çözülmemiş
        path.with_suffix(".lock").unlink()

        second = open_ledger(path)
        g2 = BudgetGuard(CAP, ledger=second, run_id="kosu-2")
        known = g2.reserve(Decimal("0.02"))
        g2.settle(known, Decimal("0.004"))  # gerçek
        unknown = g2.reserve(Decimal("0.03"))
        g2.settle(unknown, None)  # bilinemedi → en kötü bedel

        summary = g2.summary()
        assert summary["prior_spent_usd"] == "0.005"
        assert summary["prior_unresolved_reserved_usd"] == "0.01"
        assert summary["known_spent_usd"] == "0.004"
        assert summary["conservative_spent_usd"] == "0.03"
        assert summary["spent_usd"] == "0.034"
        assert summary["total_spent_usd"] == "0.039"  # önceki + bu çalıştırma
        assert summary["remaining_usd"] == "0.051"  # 0,10 − 0,039 − 0,01 çözülmemiş
        assert summary["budget_id"] == "deneme"
        second.release()

    def test_defter_toplami_hicbir_zaman_siniri_asmaz_birden_cok_yeniden_baslatmada(self, path):
        import random

        rng = random.Random(3)
        for run in range(6):  # 6 ayrı "süreç"
            ledger = open_ledger(path)
            guard = BudgetGuard(CAP, ledger=ledger, run_id=f"kosu-{run}")
            for _ in range(20):
                amount = Decimal(rng.randint(1, 15)) / 1000
                try:
                    reservation = guard.reserve(amount)
                except BudgetExhausted:
                    continue
                guard.settle(reservation, None if rng.random() < 0.4 else amount / 3)
            ledger.release()
            status = BudgetLedger.read(path).status()
            assert (
                Decimal(status["settled_total_usd"]) + Decimal(status["unresolved_reserved_usd"])
                <= CAP
            )
        assert Decimal(BudgetLedger.read(path).status()["remaining_usd"]) >= 0
