import { ApiError, NetworkError, createApiClient, messageFromBody } from '../api';

type FetchCall = { url: string; init: RequestInit };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function setup(respond: (call: FetchCall) => Response | Promise<Response>, token: string | null = 'jeton') {
  const calls: FetchCall[] = [];
  const onUnauthorized = jest.fn();
  const fetchImpl = jest.fn(async (url: string, init: RequestInit) => {
    const call = { url, init };
    calls.push(call);
    return respond(call);
  }) as unknown as typeof fetch;
  const api = createApiClient({
    baseUrl: 'http://api.test',
    getToken: () => token,
    onUnauthorized,
    fetchImpl,
    timeoutMs: 50,
  });
  return { api, calls, onUnauthorized };
}

describe('istek biçimi', () => {
  it('kimlik gerektiren isteklerde Authorization başlığı gönderir', async () => {
    const { api, calls } = setup(() => jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));

    await api.listTickets();

    const headers = calls[0].init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer jeton');
  });

  it('girişte ve sözlükte Authorization göndermez', async () => {
    const { api, calls } = setup(() => jsonResponse(200, {}));

    await api.login('ayse', 'parola');
    await api.vocabulary();

    for (const call of calls) {
      expect((call.init.headers as Record<string, string>).Authorization).toBeUndefined();
    }
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ username: 'ayse', password: 'parola' });
  });

  it('sorgu dizesini kurar: tekrarlı durumlar, tanımsızları atlar, kodlar', async () => {
    const { api, calls } = setup(() => jsonResponse(200, { items: [], total: 0, limit: 100, offset: 0 }));

    await api.listTickets({ scope: 'queue', status: ['assigned', 'in_progress'], limit: 100 });

    expect(calls[0].url).toBe(
      'http://api.test/tickets?scope=queue&status=assigned&status=in_progress&limit=100',
    );
  });

  it('parametre yoksa sorgu dizesi eklemez', async () => {
    const { api, calls } = setup(() => jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));

    await api.listTickets();

    expect(calls[0].url).toBe('http://api.test/tickets');
  });

  it('geçiş isteğinde not yalnızca doluysa gönderilir', async () => {
    const { api, calls } = setup(() => jsonResponse(200, {}));

    await api.transition('abc', 'resolved');
    await api.transition('abc', 'resolved', 'Düzeltildi');

    expect(JSON.parse(calls[0].init.body as string)).toEqual({ to: 'resolved' });
    expect(JSON.parse(calls[1].init.body as string)).toEqual({ to: 'resolved', note: 'Düzeltildi' });
    expect(calls[0].url).toBe('http://api.test/tickets/abc/transitions');
  });

  it('talep kimliğini adrese eklerken kodlar', async () => {
    const { api, calls } = setup(() => jsonResponse(200, {}));

    await api.getTicket('a/b?c');

    expect(calls[0].url).toBe('http://api.test/tickets/a%2Fb%3Fc');
  });
});

describe('hata dönüşümü', () => {
  it('sunucunun Türkçe mesajını ve kodunu korur', async () => {
    const { api } = setup(() =>
      jsonResponse(409, { detail: "'Yeni' durumundan 'Çözüldü' durumuna geçilemez.", code: 'invalid_transition' }),
    );

    const error = await api.transition('x', 'resolved').catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.code).toBe('invalid_transition');
    expect(error.message).toContain('geçilemez');
  });

  it('doğrulama hatasında (liste) genel Türkçe mesaj verir', () => {
    const result = messageFromBody(422, { detail: [{ loc: ['body', 'title'], msg: 'x' }] });

    expect(result.message).toBe('Girilen bilgiler geçersiz. Alanları kontrol et.');
    expect(result.code).toBeNull();
  });

  it('5xx için sunucu metnini göstermez', () => {
    expect(messageFromBody(500, { detail: 'Traceback ...' }).message).toBe(
      'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.',
    );
  });

  it('veritabanı yok (503 database_unavailable) yanıtını açıkça söyler; metni sunucudan almaz', () => {
    const result = messageFromBody(503, {
      detail: 'Traceback ... password=hunter2',
      code: 'database_unavailable',
    });

    expect(result).toEqual({
      code: 'database_unavailable',
      message: 'Sunucu şu anda veritabanına ulaşamıyor. Biraz sonra tekrar dene.',
    });
    expect(result.message).not.toContain('hunter2');
  });

  it('başka 503 (ve başka kodlu 5xx) genel mesaj verir', () => {
    const generic = 'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.';

    expect(messageFromBody(503, { detail: 'x', code: 'baska_kod' }).message).toBe(generic);
    expect(messageFromBody(503, null).message).toBe(generic);
    expect(messageFromBody(500, { code: 'database_unavailable' }).message).toBe(generic);
  });

  it('JSON olmayan hata gövdesinde de durum koduna göre mesaj üretir', async () => {
    const { api } = setup(() => new Response('<html>Bad Gateway</html>', { status: 502 }));

    const error = await api.me().catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.message).toContain('Sunucuda bir sorun');
  });

  it('bilinmeyen durum kodunda kodu mesaja koyar', () => {
    expect(messageFromBody(418, null).message).toBe('İstek başarısız oldu (418).');
  });
});

describe('oturum süresi (401)', () => {
  it('kimlik gerektiren istekte onUnauthorized çağrılır', async () => {
    const { api, onUnauthorized } = setup(() => jsonResponse(401, { detail: 'Oturum geçersiz', code: 'unauthorized' }));

    await expect(api.me()).rejects.toBeInstanceOf(ApiError);

    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('yanlış parolayla giriş (401) oturum sonlandırma sayılmaz', async () => {
    const { api, onUnauthorized } = setup(() =>
      jsonResponse(401, { detail: 'Kullanıcı adı veya parola hatalı.', code: 'unauthorized' }),
    );

    const error = await api.login('ayse', 'yanlış').catch((e) => e);

    expect(error.message).toBe('Kullanıcı adı veya parola hatalı.');
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});

describe('ağ hataları', () => {
  it('bağlantı yoksa NetworkError fırlatır (ApiError değil)', async () => {
    const { api } = setup(() => {
      throw new TypeError('Network request failed');
    });

    const error = await api.me().catch((e) => e);

    expect(error).toBeInstanceOf(NetworkError);
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error.timedOut).toBe(false);
    expect(error.message).toContain('Sunucuya ulaşılamıyor');
  });

  it('zaman aşımında isteği iptal eder ve timedOut işaretler', async () => {
    const { api } = setup(
      ({ init }) =>
        new Promise<Response>((_, reject) => {
          init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
        }),
    );

    const error = await api.me().catch((e) => e);

    expect(error).toBeInstanceOf(NetworkError);
    expect(error.timedOut).toBe(true);
    expect(error.message).toContain('zamanında yanıt vermedi');
  });
});
