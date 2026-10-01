import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';

interface State<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}

/**
 * Bir ekranın verisini yükler; ekran her öne geldiğinde sessizce yeniler (ör. talep açıldıktan
 * sonra liste güncellenir). `load` çağıranda `useCallback` ile sabitlenmelidir.
 *
 * - loading: ilk yükleme sürüyor (tam ekran spinner)
 * - error + data: yenileme başarısız ama eski veri hâlâ gösterilebilir
 */
export function useResource<T>(load: () => Promise<T>) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  const [refreshing, setRefreshing] = useState(false);
  const latest = useRef(0);
  const hasData = useRef(false);

  const run = useCallback(
    async (mode: 'initial' | 'silent' | 'pull') => {
      const id = ++latest.current;
      if (mode === 'initial') setState((s) => ({ ...s, loading: true, error: null }));
      if (mode === 'pull') setRefreshing(true);
      try {
        const data = await load();
        if (id !== latest.current) return; // daha yeni bir istek var; bunu yok say
        hasData.current = true;
        setState({ data, error: null, loading: false });
      } catch (failure) {
        if (id !== latest.current) return;
        const error = failure instanceof Error ? failure : new Error(String(failure));
        setState((s) => ({ data: s.data, error, loading: false }));
      } finally {
        if (mode === 'pull' && id === latest.current) setRefreshing(false);
      }
    },
    [load],
  );

  const lastLoad = useRef(load);

  useFocusEffect(
    useCallback(() => {
      // Süzgeç değişti (yeni `load`): eski sonuç yanıltıcı olur, baştan yükle. Aksi halde sessiz yenile.
      const changed = lastLoad.current !== load;
      lastLoad.current = load;
      void run(changed || !hasData.current ? 'initial' : 'silent');
    }, [run, load]),
  );

  return {
    ...state,
    refreshing,
    /** İlk yükleme hatasından sonra "Tekrar dene". */
    retry: useCallback(() => run('initial'), [run]),
    /** Aşağı çekerek yenile. */
    refresh: useCallback(() => run('pull'), [run]),
    /** Bir işlemden sonra veriyi spinner göstermeden yenile. */
    reload: useCallback(() => run('silent'), [run]),
  };
}
