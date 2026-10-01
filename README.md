# TalepAkış

Kampüs veya yurt bakım ekipleri için mobil servis talebi ve iş yönlendirme uygulaması. Kullanıcı metinle talep açar; sistem kategori, öncelik ve eksik bilgiyi önerir ve talebi ilgili ekip kuyruğuna yönlendirir.

Projenin araştırma sorusu: **Türkçe servis taleplerinde Jev, ekonomik bir LLM ve hibrit yaklaşım arasında doğruluk, işlem süresi ve maliyet nasıl değişiyor?** Sonuçlar ölçülmeden hiçbir tasarruf veya başarı iddiası yapılmaz.

> **Durum:** Aşama 0 (iskelet). Şu an yalnızca API iskeleti ve `/health` uç noktası vardır. Giriş, talepler, karar motoru, mobil uygulama ve yönetici paneli planlandı ama henüz yok. Ayrıntı için [docs/STATUS.md](docs/STATUS.md) ve [docs/PLAN.md](docs/PLAN.md).

## Yapı

```
services/api   FastAPI sunucusu (Python 3.12)
apps/mobile    Expo + React Native + TypeScript   (Aşama 1)
apps/admin     Yönetici paneli, React web         (Aşama 1)
evaluation     Benchmark ve değerlendirme         (Aşama 4)
docs           Plan, durum ve mimari kararlar
```

## Gereksinimler

- Windows 11 + PowerShell (diğer sistemlerde komutlar benzerdir)
- Python 3.12
- Docker Desktop (PostgreSQL için)
- Node.js 24 (mobil ve yönetici paneli geldiğinde)

## API'yi çalıştırma

Komutlar proje kökünden başlar. Klasör adında boşluk olduğu için yolları tırnak içine al.

```powershell
cd services\api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Sunucu `http://127.0.0.1:8000` adresinde açılır. Kontrol: `http://127.0.0.1:8000/health`. Otomatik API belgeleri: `http://127.0.0.1:8000/docs`.

## Testler ve lint

```powershell
cd services\api
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

## PostgreSQL (Docker)

Docker Desktop açıkken proje kökünden:

```powershell
docker compose up -d db
docker compose ps
```

Veritabanı yalnızca bu bilgisayardan (`127.0.0.1:5432`) erişilebilir. Kapatmak için `docker compose down`; kayıtlı veriyi de silmek için `docker compose down -v`. Docker kapalıysa `docker info` bağlantı hatası verir; önce Docker Desktop'ı başlat.

## Telefondan API'ye erişim (localhost ve bilgisayarın IP'si)

Telefondaki uygulamada `localhost` veya `127.0.0.1`, **telefonun kendisi** demektir; bilgisayardaki API'ye ulaşmaz. Telefondan erişmek için:

1. Bilgisayar ve telefon aynı Wi-Fi ağında olsun.
2. Bilgisayarın yerel IP'sini bul: `ipconfig` çıktısında Wi-Fi bağdaştırıcısındaki "IPv4 Address" (genelde `192.168.x.x` veya `10.x.x.x`).
3. API'yi tüm ağ arayüzlerinde dinleyecek şekilde başlat (`services\api` içinde): `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --reload`.
4. Telefonda API adresi olarak `http://<bilgisayar-IP'si>:8000` kullan. Windows Güvenlik Duvarı ilk seferde izin sorabilir; yalnızca özel (ev/ofis) ağlar için izin ver.

`--host 0.0.0.0` sunucuyu o ağdaki herkese açar; ortak veya halka açık Wi-Fi'da kullanma. Emülatör kullanıyorsan adres farklıdır (ör. Android emülatöründe bilgisayar `10.0.2.2` olarak görünür).

## Güvenlik notları

- API anahtarları yalnızca backend ortam değişkenlerinden okunur; mobil uygulamaya hiçbir zaman konmaz.
- `.env` dosyaları commitlenmez; yalnızca sahte değerli `.env.example` depoda durur.
- Ücretli model çağrıları varsayılan olarak kapalıdır; bütçe onayı olmadan gerçek model çağrısı yapılmaz.
