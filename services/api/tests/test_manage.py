"""Sunucu yönetim komutları: ilk yöneticiyi oluşturma ve parola sıfırlama (gerçek veritabanıyla)."""

import io

import pytest
from sqlalchemy import select

from app import manage, security
from app.domain.vocabulary import Role
from app.models import User

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
