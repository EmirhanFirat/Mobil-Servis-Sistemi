import { TicketListScreen, type StatusFilter } from '@/components/ticket-list';

// Sabit dizi: kimliği değişmezse süzgeç değişmedikçe liste gereksiz yeniden yüklenmez.
const FILTERS: StatusFilter[] = [
  { label: 'Açık işler', statuses: ['assigned', 'in_progress'] },
  { label: 'İnceleme', statuses: ['needs_review'] },
  { label: 'Çözüldü', statuses: ['resolved'] },
  { label: 'Tümü' },
];

export default function QueueScreen() {
  return (
    <TicketListScreen
      title="İş listesi"
      scope="queue"
      filters={FILTERS}
      showOwner
      emptyTitle="Bu görünümde iş yok"
      emptyMessage="Ekibine atanan talepler burada görünür."
    />
  );
}
