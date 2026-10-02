import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../lib/api'
import { fakeApi, makeTicket, teams, vocab } from '../test-utils'
import { AssignPanel, CorrectionPanel, TransitionPanel } from './ticket-panels'

describe('AssignPanel', () => {
  function setup(ticket = makeTicket(), api = fakeApi()) {
    const onChanged = vi.fn()
    render(<AssignPanel ticket={ticket} teams={teams} vocab={vocab} api={api} onChanged={onChanged} />)
    return { api, onChanged, user: userEvent.setup() }
  }

  it('kategorinin varsayılan ekibini ön seçer ve görevliler yalnızca o ekibin üyeleridir', () => {
    setup(makeTicket({ category: 'plumbing' }))

    expect(screen.getByLabelText('Ekip')).toHaveValue('team-p')
    expect(screen.getByRole('option', { name: 'Mehmet Tesisat' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Ahmet Elektrik' })).not.toBeInTheDocument()
  })

  it('ekip seçilmeden gönderilemez; kategori yoksa ön seçim de yoktur', () => {
    setup()

    expect(screen.getByLabelText('Ekip')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Ata' })).toBeDisabled()
    expect(screen.getByLabelText('Görevli')).toBeDisabled()
  })

  it('ekip + görevli seçip gönderir ve başarıyı üst bileşene bildirir', async () => {
    const { api, onChanged, user } = setup()

    await user.selectOptions(screen.getByLabelText('Ekip'), 'team-e')
    await user.selectOptions(screen.getByLabelText('Görevli'), 'u-ahmet')
    await user.click(screen.getByRole('button', { name: 'Ata' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith('Atama kaydedildi.'))
    expect(api.assign).toHaveBeenCalledWith('ticket-1', {
      team_id: 'team-e',
      assignee_id: 'u-ahmet',
      note: undefined,
    })
  })

  it('görevli seçilmezse ekip kuyruğuna bırakır (assignee_id: null)', async () => {
    const { api, user } = setup(makeTicket({ category: 'electrical' }))

    await user.click(screen.getByRole('button', { name: 'Ata' }))

    await waitFor(() => expect(api.assign).toHaveBeenCalled())
    expect(api.assign).toHaveBeenCalledWith('ticket-1', {
      team_id: 'team-e',
      assignee_id: null,
      note: undefined,
    })
  })

  it('ekip değişince seçili görevli sıfırlanır: eski ekibin görevlisi yeni ekibe gönderilmez', async () => {
    const { api, user } = setup(makeTicket({ category: 'plumbing' }))
    await user.selectOptions(screen.getByLabelText('Görevli'), 'u-mehmet')

    await user.selectOptions(screen.getByLabelText('Ekip'), 'team-e')
    await user.click(screen.getByRole('button', { name: 'Ata' }))

    // DOM'da seçili görünmemesi yetmez; asıl önemli olan sunucuya giden değerdir.
    await waitFor(() => expect(api.assign).toHaveBeenCalled())
    expect(api.assign).toHaveBeenCalledWith('ticket-1', {
      team_id: 'team-e',
      assignee_id: null,
      note: undefined,
    })
  })

  it('seçili ekip kategorinin ekibinden farklıysa öneriyi gösterir ve tek tıkla uygular', async () => {
    const { user } = setup(makeTicket({ category: 'plumbing' }))
    await user.selectOptions(screen.getByLabelText('Ekip'), 'team-e')

    await user.click(screen.getByRole('button', { name: 'Su/Tesisat Ekibi' }))

    expect(screen.getByLabelText('Ekip')).toHaveValue('team-p')
  })

  it('sunucu hatasını (Türkçe mesaj) gösterir ve başarı bildirmez', async () => {
    const api = fakeApi({
      assign: vi.fn().mockRejectedValue(new ApiError(422, 'invalid_assignee', 'Görevli, seçilen ekibin görevlisi olmalı.')),
    })
    const { onChanged, user } = setup(makeTicket({ category: 'plumbing' }), api)

    await user.click(screen.getByRole('button', { name: 'Ata' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Görevli, seçilen ekibin görevlisi olmalı.')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('atanamayan (çözülmüş/kapalı) talepte form yerine açıklama gösterir', () => {
    setup(makeTicket({ can_assign: false, status: 'resolved' }))

    expect(screen.getByText(/yeniden atanamaz/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Ekip')).not.toBeInTheDocument()
  })

  it('atanmış talepte düğme "Yeniden ata" olur', () => {
    setup(makeTicket({ team: { id: 'team-p', code: 'plumbing', name: 'Su/Tesisat Ekibi' }, status: 'assigned' }))

    expect(screen.getByRole('button', { name: 'Yeniden ata' })).toBeEnabled()
  })
})

describe('CorrectionPanel', () => {
  function setup(ticket = makeTicket(), api = fakeApi()) {
    const onChanged = vi.fn()
    render(<CorrectionPanel ticket={ticket} vocab={vocab} api={api} onChanged={onChanged} />)
    return { api, onChanged, user: userEvent.setup() }
  }

  it('değişiklik yapılmadan kaydet düğmesi kapalıdır', () => {
    setup()

    expect(screen.getByRole('button', { name: 'Düzeltmeyi kaydet' })).toBeDisabled()
  })

  it('yalnızca değişen alanı gönderir', async () => {
    const { api, onChanged, user } = setup()

    await user.selectOptions(screen.getByLabelText('Öncelik'), 'high')
    await user.click(screen.getByRole('button', { name: 'Düzeltmeyi kaydet' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith('Düzeltme kaydedildi.'))
    expect(api.patchTicket).toHaveBeenCalledWith('ticket-1', { priority: 'high' })
  })

  it('kategori ve eksik bilgi birlikte, notla gönderilir', async () => {
    const { api, user } = setup()

    await user.selectOptions(screen.getByLabelText('Kategori'), 'electrical')
    await user.click(screen.getByRole('checkbox', { name: 'İletişim bilgisi eksik' }))
    await user.type(screen.getByLabelText('Düzeltme notu (isteğe bağlı)'), 'Telefon yok')
    await user.click(screen.getByRole('button', { name: 'Düzeltmeyi kaydet' }))

    await waitFor(() => expect(api.patchTicket).toHaveBeenCalled())
    expect(api.patchTicket).toHaveBeenCalledWith('ticket-1', {
      category: 'electrical',
      missing_info: ['contact'],
      note: 'Telefon yok',
    })
  })

  it('kategoriyi "Belirtilmemiş"e çevirmek null gönderir', async () => {
    const { api, user } = setup(makeTicket({ category: 'plumbing' }))

    await user.selectOptions(screen.getByLabelText('Kategori'), '')
    await user.click(screen.getByRole('button', { name: 'Düzeltmeyi kaydet' }))

    await waitFor(() => expect(api.patchTicket).toHaveBeenCalled())
    expect(api.patchTicket).toHaveBeenCalledWith('ticket-1', { category: null })
  })

  it('kapalı talepte form yerine açıklama gösterir', () => {
    setup(makeTicket({ can_edit: false, status: 'closed' }))

    expect(screen.getByText('Kapatılmış talep düzeltilemez.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Öncelik')).not.toBeInTheDocument()
  })
})

describe('TransitionPanel', () => {
  function setup(ticket = makeTicket({ status: 'assigned', allowed_transitions: ['in_progress', 'closed'] }), api = fakeApi()) {
    const onChanged = vi.fn()
    render(<TransitionPanel ticket={ticket} api={api} onChanged={onChanged} />)
    return { api, onChanged, user: userEvent.setup() }
  }

  it('yalnızca sunucunun izin verdiği geçişleri düğme olarak gösterir', () => {
    setup()

    expect(screen.getByRole('button', { name: 'İşleme al' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Talebi kapat' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Çözüldü olarak işaretle' })).not.toBeInTheDocument()
  })

  it('izinli geçiş yoksa açıklama gösterir', () => {
    setup(makeTicket({ status: 'closed', allowed_transitions: [] }))

    expect(screen.getByText('Bu talepte yapılabilecek bir durum işlemi yok.')).toBeInTheDocument()
  })

  it('önce onay adımı açılır; onaylayınca notla gönderilir', async () => {
    const { api, onChanged, user } = setup()

    await user.click(screen.getByRole('button', { name: 'İşleme al' }))
    expect(api.transition).not.toHaveBeenCalled() // tek tıkla gitmez
    await user.type(screen.getByLabelText('Not (isteğe bağlı)'), 'Yola çıktı')
    await user.click(screen.getByRole('button', { name: 'Onayla' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith('Durum güncellendi.'))
    expect(api.transition).toHaveBeenCalledTimes(1) // tek onay, tek istek
    expect(api.transition).toHaveBeenCalledWith('ticket-1', 'in_progress', 'Yola çıktı')
  })

  it('Vazgeç onay adımını kapatır, istek göndermez', async () => {
    const { api, user } = setup()

    await user.click(screen.getByRole('button', { name: 'Talebi kapat' }))
    await user.click(screen.getByRole('button', { name: 'Vazgeç' }))

    expect(api.transition).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'İşleme al' })).toBeInTheDocument()
  })

  it('durum başkası tarafından değişmişse (409) hatayı gösterir ve ayrıntıyı yeniletir', async () => {
    const api = fakeApi({
      transition: vi.fn().mockRejectedValue(new ApiError(409, 'invalid_transition', "'Atandı' durumundan geçilemez.")),
    })
    const { onChanged, user } = setup(undefined, api)

    await user.click(screen.getByRole('button', { name: 'İşleme al' }))
    await user.click(screen.getByRole('button', { name: 'Onayla' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("'Atandı' durumundan geçilemez.")
    expect(onChanged).toHaveBeenCalledWith() // mesajsız: yalnızca yenile
  })
})
