import { resolveApiUrl } from '../config';

describe('resolveApiUrl', () => {
  it('açık adres her şeyden önce gelir ve sondaki eğik çizgiyi atar', () => {
    expect(resolveApiUrl({ explicitUrl: 'https://api.ornek.com/', hostUri: '192.168.1.5:8081', os: 'ios' })).toBe(
      'https://api.ornek.com',
    );
  });

  it('telefonda Expo sunucusunun bilgisayar adresini kullanır (localhost telefonun kendisidir)', () => {
    expect(resolveApiUrl({ hostUri: '192.168.1.20:8081', os: 'ios' })).toBe('http://192.168.1.20:8000');
    expect(resolveApiUrl({ hostUri: '10.7.222.223:8081', os: 'android' })).toBe('http://10.7.222.223:8000');
  });

  it('geri döngü adresini telefon için kullanmaz', () => {
    expect(resolveApiUrl({ hostUri: 'localhost:8081', os: 'ios' })).toBe('http://127.0.0.1:8000');
    expect(resolveApiUrl({ hostUri: '127.0.0.1:8081', os: 'web' })).toBe('http://127.0.0.1:8000');
  });

  it('Android emülatöründe bilgisayar 10.0.2.2 olarak görünür', () => {
    expect(resolveApiUrl({ hostUri: 'localhost:8081', os: 'android' })).toBe('http://10.0.2.2:8000');
    expect(resolveApiUrl({ os: 'android' })).toBe('http://10.0.2.2:8000');
  });

  it('hiçbir ipucu yoksa 127.0.0.1 kullanır', () => {
    expect(resolveApiUrl({ os: 'web' })).toBe('http://127.0.0.1:8000');
    expect(resolveApiUrl({ hostUri: null, os: 'ios' })).toBe('http://127.0.0.1:8000');
  });
});
