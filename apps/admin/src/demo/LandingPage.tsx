import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'

import heroWide from '../assets/anasayfa-2400.webp'
import heroMid from '../assets/anasayfa-1400.webp'
import heroMobile from '../assets/anasayfa-mobil.webp'
import type { DemoClient } from '../lib/demo-api'
import { TOPICS } from './portal-topics'

export const REQUEST_PATH = '/talep'

function Arrow() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d="M4 10h11m-4-4 4 4-4 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function StepIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="28"
      height="28"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

const STEPS = [
  {
    title: 'Bildir',
    text: 'Sorunu kendi cümlelerinle yaz: ne oldu, nerede, ne zamandan beri. Form üç alan, bir dakika.',
    icon: (
      <StepIcon>
        <path d="M5 4h10l4 4v12H5z" />
        <path d="M9 12h6M9 16h4" />
      </StepIcon>
    ),
  },
  {
    title: 'Ön değerlendirme',
    text: 'Talep okunur; kategori, öncelik ve eksik bilgi belirlenir. Belirsizse bir görevliye bırakılır.',
    icon: (
      <StepIcon>
        <circle cx="11" cy="11" r="6" />
        <path d="m20 20-4.5-4.5" />
      </StepIcon>
    ),
  },
  {
    title: 'Doğru ekibe',
    text: 'Atama sabit kurallarla yapılır: talep ilgili ekibin kuyruğuna düşer, sen numaranla takip edersin.',
    icon: (
      <StepIcon>
        <path d="M4 12h12m-4-5 5 5-5 5" />
        <path d="M20 5v14" />
      </StepIcon>
    ),
  },
]

/** Sistemin yapısına dair sabit gerçekler: performans iddiası DEĞİL (ölçümler "Sonuçlar"dadır). */
const FACTS = [
  { value: '5', label: 'bakım ekibi', note: 'Su/Tesisat, Elektrik, BT, Temizlik, Genel Bakım' },
  { value: '3', label: 'öncelik düzeyi', note: 'Düşük, normal, yüksek; acil durum 112' },
  { value: '4', label: 'karar stratejisi', note: 'Kurallar, Jev, LLM ve hibrit aynı sözleşmeyle' },
  { value: '72 sa', label: 'sonra silinir', note: 'Demo talepleri otomatik temizlenir' },
]

/**
 * Tanıtım sayfası (demo ana sayfası): tam genişlikte görsel, kısa vaat, nasıl çalıştığı ve talep
 * formuna giden çağrılar. Açılışta yalnızca ücretsiz hazırlık isteği gider (sunucuyu erkenden
 * uyandırır); model çağrısı ve oturum yoktur.
 */
export default function LandingPage({ client }: { client: DemoClient }) {
  const navigate = useNavigate()
  const [quick, setQuick] = useState('')

  useEffect(() => {
    // Ücretsiz barındırmada sunucu uyuyor olabilir: ziyaretçi formu açana dek uyansın.
    void client.status().catch(() => undefined)
  }, [client])

  function onQuickStart(event: FormEvent) {
    event.preventDefault()
    navigate(REQUEST_PATH, { state: { title: quick.trim() } })
  }

  return (
    <div className="landing">
      <section className="lp-hero" aria-labelledby="lp-heading">
        <picture>
          <source media="(max-width: 640px)" srcSet={heroMobile} />
          <img
            className="lp-hero-img"
            src={heroMid}
            srcSet={`${heroMid} 1400w, ${heroWide} 2400w`}
            sizes="100vw"
            alt="Bir bakım görevlisi kafa lambasıyla yurt odasındaki eski bir radyatörü onarıyor."
            fetchPriority="high"
          />
        </picture>
        <div className="lp-hero-inner">
          <p className="lp-eyebrow">Kampüs ve yurt bakım ekipleri için</p>
          <h1 id="lp-heading">
            Arıza bildirimi,
            <br />
            <span>doğru ekibe tek adımda.</span>
          </h1>
          <p className="lp-lead">
            TalepAkış Türkçe yazılan servis taleplerini okur; kategori, öncelik ve eksik bilgiyi belirler, talebi ilgili
            ekibin kuyruğuna yönlendirir.
          </p>
          <form className="lp-quick" onSubmit={onQuickStart} aria-label="Hızlı başlangıç">
            <label className="visually-hidden" htmlFor="lp-quick-input">
              Sorunu bir cümleyle yaz
            </label>
            <input
              id="lp-quick-input"
              value={quick}
              maxLength={120}
              placeholder="Sorunu bir cümleyle yaz: ör. Lavabo akıtıyor"
              onChange={(e) => setQuick(e.target.value)}
            />
            <button type="submit" className="lp-btn lp-btn-accent">
              Talep oluştur <Arrow />
            </button>
          </form>
          <p className="lp-hero-note">
            Portföy demosudur: talepler gerçek bir ekibe iletilmez. Acil durumda <strong>112</strong>.
          </p>
        </div>
      </section>

      <section className="lp-strip" aria-label="Hizmet verilen konular">
        <div className="lp-container lp-strip-inner">
          {TOPICS.filter((topic) => topic.category).map((topic) => (
            <span key={topic.id} className="lp-strip-item">
              {topic.icon}
              {topic.label}
            </span>
          ))}
          <span className="lp-strip-item lp-strip-more">+ Genel bakım</span>
        </div>
      </section>

      <section className="lp-section" aria-labelledby="lp-how">
        <div className="lp-container">
          <p className="lp-kicker">Nasıl çalışır</p>
          <h2 id="lp-how">Talebin kaybolmaz, sırası beklenmez.</h2>
          <ol className="lp-steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="lp-step">
                <span className="lp-step-icon">{step.icon}</span>
                <span className="lp-step-no">0{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="lp-band" aria-labelledby="lp-facts">
        <div className="lp-container">
          <h2 id="lp-facts">Küçük bir ekip için, açık kurallarla.</h2>
          <dl className="lp-facts">
            {FACTS.map((fact) => (
              <div key={fact.label}>
                <dt>
                  <span className="lp-fact-value">{fact.value}</span> {fact.label}
                </dt>
                <dd>{fact.note}</dd>
              </div>
            ))}
          </dl>
          <p className="lp-band-note">
            Bu rakamlar sistemin yapısını anlatır; doğruluk veya hız iddiası değildir. Ölçülen sonuçlar{' '}
            <Link to="/sonuclar">Sonuçlar</Link> sayfasındadır.
          </p>
        </div>
      </section>

      <section className="lp-section" aria-labelledby="lp-who">
        <div className="lp-container">
          <p className="lp-kicker">Kimin için</p>
          <h2 id="lp-who">İki taraf, tek akış.</h2>
          <div className="lp-cards">
            <article className="lp-card">
              <span className="lp-card-tag">Öğrenci ve personel</span>
              <h3>Bildir, numaranı al, takip et.</h3>
              <p>
                Konu seç ya da doğrudan yaz. Gönderdiğin anda talep numaran, önceliğin ve talebin hangi ekibe gittiği
                fişte görünür.
              </p>
              <Link className="lp-link" to={REQUEST_PATH}>
                Talep oluştur <Arrow />
              </Link>
            </article>
            <article className="lp-card lp-card-dark">
              <span className="lp-card-tag">Bakım ekibi</span>
              <h3>Kuyruk düzenli, karar izlenebilir.</h3>
              <p>
                Mobil uygulama ve yönetici paneliyle çalışır. Atama ve yetki kodla yönetilir; model çıktısı hiçbir yetki
                vermez, ilk tahmin ve insan düzeltmesi ayrı kaydedilir.
              </p>
              <Link className="lp-link" to="/hakkinda">
                Projeyi tanı <Arrow />
              </Link>
            </article>
          </div>
        </div>
      </section>

      <section className="lp-section lp-split-wrap" aria-labelledby="lp-research">
        <div className="lp-container lp-split">
          <div>
            <p className="lp-kicker">Araştırma</p>
            <h2 id="lp-research">Jev mi, dil modeli mi, ikisi birden mi?</h2>
            <p>
              Aynı Türkçe taleplerde Jev, ekonomik bir dil modeli ve ikisini birleştiren hibrit yaklaşım doğruluk, süre
              ve ücret açısından karşılaştırılıyor. Hangisinin kazanacağı baştan varsayılmıyor; sonuçlar küçük
              örneklemle ve uyarılarıyla yayımlanıyor.
            </p>
            <Link className="lp-btn lp-btn-navy" to="/sonuclar">
              Ölçüm sonuçları <Arrow />
            </Link>
          </div>
          <figure className="lp-preview" aria-label="Örnek fiş görünümü">
            <figcaption>Örnek fiş görünümü</figcaption>
            <div className="lp-preview-card">
              <div className="lp-preview-head">
                <span className="lp-preview-check" aria-hidden="true">
                  ✓
                </span>
                <div>
                  <strong>Talebin alındı</strong>
                  <span>Talep numaran TA-0042</span>
                </div>
              </div>
              <div className="lp-preview-grid">
                <span>
                  Kategori<b>Su/Tesisat</b>
                </span>
                <span>
                  Öncelik<b className="lp-preview-high">Yüksek</b>
                </span>
                <span className="lp-preview-wide">
                  Yönlendirilen ekip<b>Su/Tesisat Ekibi</b>
                </span>
              </div>
            </div>
            <p>Arayüz örneğidir; gerçek bir talep veya ölçüm değildir.</p>
          </figure>
        </div>
      </section>

      <section className="lp-cta" aria-labelledby="lp-cta-heading">
        <div className="lp-container lp-cta-inner">
          <h2 id="lp-cta-heading">Kampüste bir sorun mu var?</h2>
          <Link className="lp-btn lp-btn-accent" to={REQUEST_PATH}>
            Talep oluştur <Arrow />
          </Link>
        </div>
      </section>
    </div>
  )
}
