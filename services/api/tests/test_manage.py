"""Sunucu yönetim komutları: ilk yöneticiyi oluşturma ve parola sıfırlama (gerçek veritabanıyla)."""

import io
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import manage, security
from app.domain.vocabulary import Role
from app.models import Budget, User

STRONG = "cok-guclu-parola-123"


def test_yonetici_olusturulur_parola_ozetlenir(db):
    user = manage.create_admin(db, "Yonetici", "Ada Yönetici", STRONG)

    stored = db.scalar(select(User).where(User.username == "yonetici"))
    assert stored is not None and stored.id == user.id
    assert stored.role is Role.ADMIN and stored.is_active
    assert stored.password_hash != STRONG and STRONG not in stored.password_hash
    assert security.verify_password(stored.password_hash, STRONG)


def test_olusturulan_yonetici_giris_yapip_panel_uclarini_kullanir(api, db, auth):
    manage.create_admin(db, "yonetici", "Ada Yönetici", STRONG)

    token = api.post("/auth/login", json={"username": "yonetici", "password": STRONG}).json()[
        "access_token"
    ]

    response = api.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


@pytest.mark.parametrize("short", ["", "kisa", "a" * 11])
def test_kisa_yonetici_parolasi_reddedilir(db, short):
    with pytest.raises(manage.CommandError, match="en az 12"):
        manage.create_admin(db, "yonetici", "Ada", short)

    assert db.scalar(select(User)) is None  # hiçbir şey yazılmadı


def test_cok_uzun_parola_reddedilir(db):
    with pytest.raises(manage.CommandError, match="128"):
        manage.create_admin(db, "yonetici", "Ada", "a" * 129)


def test_ayni_kullanici_adi_iki_kez_olusturulamaz(db):
    manage.create_admin(db, "yonetici", "Ada", STRONG)

    with pytest.raises(manage.CommandError, match="zaten kullanılıyor"):
        manage.create_admin(db, "yonetici", "Baska", STRONG)


@pytest.mark.parametrize("username", ["a", "boşluk var", "geçersiz/karakter", "x" * 51])
def test_gecersiz_kullanici_adi_reddedilir(db, username):
    with pytest.raises(manage.CommandError, match="username"):
        manage.create_admin(db, username, "Ada", STRONG)


def test_parola_sifirlama_ozeti_degistirir_eski_oturumu_gecersiz_kilar(api, db):
    manage.create_admin(db, "yonetici", "Ada", STRONG)
    old = api.post("/auth/login", json={"username": "yonetici", "password": STRONG}).json()
    old_headers = {"Authorization": f"Bearer {old['access_token']}"}
    assert api.get("/auth/me", headers=old_headers).status_code == 200

    manage.reset_password(db, " YONETICI ", "bambaska-parola-456")

    assert api.get("/auth/me", headers=old_headers).status_code == 401
    assert (
        api.post("/auth/login", json={"username": "yonetici", "password": STRONG}).status_code
        == 401
    )
    ok = api.post("/auth/login", json={"username": "yonetici", "password": "bambaska-parola-456"})
    assert ok.status_code == 200


def test_olmayan_hesabin_parolasi_sifirlanamaz(db):
    with pytest.raises(manage.CommandError, match="hesap yok"):
        manage.reset_password(db, "yok.kimse", STRONG)


def test_sifirlama_kisa_parolayi_reddeder_ve_eskisini_korur(db):
    manage.create_admin(db, "yonetici", "Ada", STRONG)

    with pytest.raises(manage.CommandError):
        manage.reset_password(db, "yonetici", "kisa")

    stored = db.scalar(select(User).where(User.username == "yonetici"))
    assert security.verify_password(stored.password_hash, STRONG)


# --- Komut satırı ---


@pytest.fixture
def cli(monkeypatch, db_engine):
    """`main` gerçek (geliştirme) veritabanına değil test veritabanına bağlanır."""
    monkeypatch.setattr(manage, "get_engine", lambda: db_engine)

    def run(*argv: str, stdin: str = ""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        return manage.main(list(argv))

    return run


def test_cli_parolayi_stdin_den_okuyup_yonetici_olusturur(cli, db, capsys):
    code = cli(
        "create-admin", "--username", "yonetici", "--display-name", "Ada", "--password-stdin",
        stdin=STRONG + "\n",
    )  # fmt: skip

    out = capsys.readouterr()
    assert code == 0
    assert "Yönetici oluşturuldu: yonetici" in out.out
    assert STRONG not in out.out and STRONG not in out.err  # parola hiçbir yere yazdırılmaz
    assert db.scalar(select(User).where(User.username == "yonetici")) is not None


def test_cli_interaktif_parola_ikisi_ayni_degilse_hata(cli, monkeypatch, db, capsys):
    answers = iter([STRONG, "baska-bir-parola-1"])
    monkeypatch.setattr(manage.getpass, "getpass", lambda prompt="": next(answers))

    code = cli("create-admin", "--username", "yonetici", "--display-name", "Ada")

    assert code == 1
    assert "aynı değil" in capsys.readouterr().err
    assert db.scalar(select(User)) is None


def test_cli_interaktif_parola_ile_olusturur(cli, monkeypatch, db):
    monkeypatch.setattr(manage.getpass, "getpass", lambda prompt="": STRONG)

    assert cli("create-admin", "--username", "yonetici", "--display-name", "Ada") == 0


def test_cli_hata_mesajini_yigin_izi_olmadan_verir(cli, db, capsys):
    code = cli(
        "create-admin", "--username", "yonetici", "--display-name", "Ada", "--password-stdin",
        stdin="kisa\n",
    )  # fmt: skip

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("Hata: Parola en az 12")
    assert "Traceback" not in err


def test_cli_parola_sifirlar(cli, db, api):
    manage.create_admin(db, "yonetici", "Ada", STRONG)

    code = cli(
        "reset-password", "--username", "yonetici", "--password-stdin", stdin="yepyeni-parola-789\n"
    )

    assert code == 0
    ok = api.post("/auth/login", json={"username": "yonetici", "password": "yepyeni-parola-789"})
    assert ok.status_code == 200


def test_cli_veritabani_yoksa_anlasilir_hata(monkeypatch, capsys):
    from sqlalchemy import create_engine

    dead = create_engine(
        "postgresql+psycopg://u:p@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )
    monkeypatch.setattr(manage, "get_engine", lambda: dead)
    monkeypatch.setattr("sys.stdin", io.StringIO(STRONG + "\n"))

    code = manage.main(
        ["create-admin", "--username", "yonetici", "--display-name", "Ada", "--password-stdin"]
    )

    err = capsys.readouterr().err
    assert code == 1
    assert "Veritabanına ulaşılamadı" in err
    assert STRONG not in err


def test_cli_alt_komut_zorunlu(cli):
    with pytest.raises(SystemExit):
        cli()


# --- Bütçe komutları ---


class TestBudgetCommands:
    def test_butce_olusturulur_ve_sinir_saklanir(self, db):
        budget, created = manage.create_budget(db, "canli-demo", Decimal("0.25"), "Canlı demo")

        assert created is True
        assert (budget.id, budget.cap_usd, budget.purpose) == (
            "canli-demo",
            Decimal("0.25"),
            "Canlı demo",
        )

    def test_ayni_sinirla_tekrar_degisiklik_yapmaz(self, db):
        manage.create_budget(db, "canli-demo", Decimal("0.25"), "a")

        budget, created = manage.create_budget(db, "canli-demo", Decimal("0.25"), "b")

        assert created is False and budget.purpose == "a"

    def test_farkli_sinirla_yeniden_tanimlanamaz_kendiliginden_artirma_yok(self, db):
        manage.create_budget(db, "canli-demo", Decimal("0.25"), "")

        with pytest.raises(manage.CommandError, match="değiştirilmez"):
            manage.create_budget(db, "canli-demo", Decimal("5"), "")

        assert db.get(Budget, "canli-demo").cap_usd == Decimal("0.25")  # değişmedi

    @pytest.mark.parametrize("cap", ["0", "-1", "NaN", "Infinity"])
    def test_gecersiz_tutarlar_reddedilir(self, db, cap):
        with pytest.raises(manage.CommandError, match="pozitif"):
            manage.create_budget(db, "canli-demo", Decimal(cap), "")

        assert db.get(Budget, "canli-demo") is None

    def test_yazim_hatasi_gibi_asiri_yuksek_tutar_reddedilir(self, db):
        with pytest.raises(manage.CommandError, match="aşıyor"):
            manage.create_budget(db, "canli-demo", Decimal("1000"), "")

    @pytest.mark.parametrize("budget_id", ["", "A", "Büyük", "bosluk var", "-x", "x" * 70])
    def test_gecersiz_kimlik_reddedilir(self, db, budget_id):
        with pytest.raises(manage.CommandError, match="kimliği"):
            manage.create_budget(db, budget_id, Decimal("0.25"), "")

    def test_durum_raporu_ayrimlari_gosterir(self, db, db_engine):
        from app.decision.pg_budget import PgBudgetGuard
        from app.decision.pricing import JEV_1_13

        manage.create_budget(db, "canli-demo", Decimal("0.001"), "")
        guard = PgBudgetGuard(lambda: Session(db_engine), "canli-demo", job_id=None, price=JEV_1_13)
        guard.settle(guard.reserve(Decimal("0.0001")), Decimal("0.00004"))
        guard.settle(guard.reserve(Decimal("0.0002")), None)
        guard.reserve(Decimal("0.0003"))

        report = manage.budget_report(db, "canli-demo")

        assert "toplam sınır (onaylı):          0.001 USD" in report
        assert "bilinen gerçek harcama:          0.00004 USD" in report
        assert "muhafazakâr (bilinemeyen):       0.0002 USD" in report
        assert "çözülmemiş rezervasyon:          0.0003 USD" in report
        assert "kalan:                           0.00046 USD" in report
        assert "kayıt: 3 (bekleyen 1)" in report and "jev-1.13.0" in report

    def test_tanimsiz_butce_durumu_hata(self, db):
        with pytest.raises(manage.CommandError, match="tanımlı değil"):
            manage.budget_report(db, "yok")

    def test_cli_butce_olusturur_ve_durumu_gosterir(self, cli, db, capsys):
        assert (
            cli("create-budget", "--id", "canli-demo", "--cap-usd", "0.25", "--purpose", "demo")
            == 0
        )
        out = capsys.readouterr().out
        assert "Bütçe oluşturuldu: canli-demo · toplam sınır 0.25 USD" in out

        assert cli("create-budget", "--id", "canli-demo", "--cap-usd", "0.25") == 0
        assert "zaten tanımlı (değişiklik yok)" in capsys.readouterr().out

        assert cli("budget-status", "--id", "canli-demo") == 0
        assert "bütçe: canli-demo" in capsys.readouterr().out

    def test_cli_farkli_sinirda_hata_kodu_1(self, cli, db, capsys):
        cli("create-budget", "--id", "canli-demo", "--cap-usd", "0.25")
        capsys.readouterr()

        assert cli("create-budget", "--id", "canli-demo", "--cap-usd", "9") == 1
        assert "değiştirilmez" in capsys.readouterr().err

    def test_cli_gecersiz_tutar_metni(self, cli, db, capsys):
        assert cli("create-budget", "--id", "canli-demo", "--cap-usd", "çok") == 1
        assert "Geçersiz tutar" in capsys.readouterr().err
