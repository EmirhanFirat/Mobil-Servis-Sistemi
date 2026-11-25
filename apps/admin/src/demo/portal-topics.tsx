import type { ReactNode } from 'react'

/**
 * Portalda ziyaretçinin isteğe bağlı seçtiği konu. Seçim YALNIZCA yazmayı kolaylaştırır (örnek
 * ipuçları) ve fişte sistemin belirlediği kategoriyle yan yana gösterilir; karar motoruna girdi
 * olarak GİTMEZ (karar yalnızca metinden verilir, D37).
 */
export interface Topic {
  /** Sözlükteki kategori kodu; "Emin değilim" için null. */
  category: string | null
  id: string
  label: string
  hint: string
  titlePlaceholder: string
  descriptionPlaceholder: string
  icon: ReactNode
}

/** Konu ikonu çerçevesi (bileşen değil, düz yardımcı: dosya yalnızca veri dışa aktarır). */
function icon(children: ReactNode) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="26"
      height="26"
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

export const TOPICS: Topic[] = [
  {
    id: 'su',
    category: 'plumbing',
    label: 'Su / Tesisat',
    hint: 'Sızıntı, tıkanıklık, sıcak su',
    titlePlaceholder: 'ör. Lavabo akıtıyor',
    descriptionPlaceholder: 'Ne zamandır sürüyor? Su yayılıyor mu? Kullanılamayan bir yer var mı?',
    icon: icon(
      <>
        <path d="M12 3.5c3.2 4 5.5 7.1 5.5 10a5.5 5.5 0 0 1-11 0c0-2.9 2.3-6 5.5-10z" />
      </>,
    ),
  },
  {
    id: 'elektrik',
    category: 'electrical',
    label: 'Elektrik',
    hint: 'Aydınlatma, priz, sigorta',
    titlePlaceholder: 'ör. Koridor lambası yanmıyor',
    descriptionPlaceholder: 'Hangi lamba ya da priz? Kıvılcım, yanık kokusu veya ısınma var mı?',
    icon: icon(
      <>
        <path d="M13 2.5 5 13.5h6l-1 8 8-11h-6l1-8z" />
      </>,
    ),
  },
  {
    id: 'internet',
    category: 'it_network',
    label: 'İnternet / BT',
    hint: 'Wi-Fi, ağ, laboratuvar',
    titlePlaceholder: 'ör. Wi-Fi sürekli kopuyor',
    descriptionPlaceholder: 'Hangi ağ ya da cihaz? Ne zamandan beri? Herkeste mi oluyor?',
    icon: icon(
      <>
        <path d="M2.5 9a14 14 0 0 1 19 0" />
        <path d="M5.5 12.5a9.5 9.5 0 0 1 13 0" />
        <path d="M8.7 16a5 5 0 0 1 6.6 0" />
        <circle cx="12" cy="19.2" r="0.6" fill="currentColor" />
      </>,
    ),
  },
  {
    id: 'temizlik',
    category: 'cleaning',
    label: 'Temizlik',
    hint: 'Ortak alan, çöp, hijyen',
    titlePlaceholder: 'ör. Ortak mutfak temizlenmemiş',
    descriptionPlaceholder: 'Hangi alan? Koku, haşere veya kayma tehlikesi var mı?',
    icon: icon(
      <>
        <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
        <path d="m6 6 2.2 2.2M15.8 15.8 18 18M6 18l2.2-2.2M15.8 8.2 18 6" />
      </>,
    ),
  },
  {
    id: 'emin-degilim',
    category: null,
    label: 'Emin değilim',
    hint: 'Sistem metinden belirlesin',
    titlePlaceholder: 'ör. Asansör kapısı kapanmıyor',
    descriptionPlaceholder: 'Sorunu kendi cümlelerinle anlat; ne gördüğünü ve ne zaman başladığını yaz.',
    icon: icon(
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.4" />
        <circle cx="12" cy="16.8" r="0.6" fill="currentColor" />
      </>,
    ),
  },
]

/** Konu seçilmemişken gösterilen genel ipuçları. */
export const DEFAULT_PLACEHOLDERS = {
  title: 'ör. Lavabo akıtıyor',
  description: 'Sorunu kısaca anlat: ne oldu, ne zamandan beri, kullanılamayan bir şey var mı?',
  location: 'ör. B Blok, 2. kat ortak banyo',
}
