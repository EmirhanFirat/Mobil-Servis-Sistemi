import { useRouter } from 'expo-router';

import { TicketListScreen } from '@/components/ticket-list';

export default function MyTicketsScreen() {
  const router = useRouter();
  return (
    <TicketListScreen
      title="Taleplerim"
      scope="mine"
      emptyTitle="Henüz talebin yok"
      emptyMessage="Bir arıza veya sorun gördüğünde yeni talep açabilirsin."
      emptyActionLabel="Yeni talep aç"
      onEmptyAction={() => router.push('/new')}
    />
  );
}
