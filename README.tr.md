<p align="center">
  <h1 align="center">⚡ MudaRemote — Discord İçin Gelişmiş Mudae Otomasyonu</h1>
  <p align="center">
    <strong>Mudae Auto Claim • Discord Mudae Sniper • Auto Roll Mudae • Mudae Auto Kakera • Mudae Slash Commands Bot</strong>
  </p>
  <p align="center">
    Roll, claim, Kakera toplama ve çoklu hesap presetlerini tek bir masaüstü uygulamasından yönetin.<br>
    Zamanlama seçenekleri ban veya tespit edilmeme garantisi vermez.
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-Tek_Dosya_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.7.9-f97316?style=for-the-badge" alt="Version 4.7.9"></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active_2026-10b981?style=for-the-badge" alt="Active 2026"></a>
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/Discord-Join_Server-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server"></a>
</p>

<p align="center">
  <a href="README.md">English</a> •
  <a href="README.fr.md">Français</a> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.zh-CN.md">简体中文</a> •
  <a href="README.pt-BR.md">Português Brasileiro</a>
</p>

## 💖 MudaRemote'u Destekle

MudaRemote **ücretsiz ve açık kaynaklı** kalacak. Sana zaman kazandırdıysa, koleksiyonunu oluşturmana yardımcı olduysa veya Kakera farming'i kolaylaştırdıysa geliştirme çalışmalarına gönüllü olarak destek olabilirsin.

Projeyi birlikte kullanan, test eden ve geliştiren **310+ üyelik** büyüyen Discord topluluğunun bir parçasısın.

### İlk topluluk hedefimiz

**Hedefin %40'ı tamamlandı • İlk topluluk destekçileriyle $40 / $100 • Son güncelleme: Ağustos 2026**

Desteğin bağımsız geliştiriciye şu işler için daha fazla zaman sağlar:

- Discord veya Mudae değiştiğinde uyumluluk düzeltmeleri ve regresyon testleri;
- doğrulanmış Windows sürümleri, checksum'lar ve daha güvenli güncellemeler;
- dokümantasyon, çeviriler ve doğrudan topluluk desteği;
- özellik ve hata listesinde bekleyen işlerin tamamlanması.

Her miktar değerlidir. Bir referans istersen **$5**, **$15** veya **$30+** karşılığı kripto düşünebilirsin. Bunlar seviye veya alt sınır değil, yalnızca öneridir; senin için doğru olan miktarı seç.

| Varlık | Ağ | Adres |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON — TRC20 | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> Göndermeden önce varlık ve ağı birlikte doğrula; kripto işlemleri geri alınamaz. İsteğe bağlı **Donator** rolünü almak için işlem kimliğini veya ekran görüntüsünü geliştiriciye Discord DM üzerinden gönder. İlgisiz cüzdan bilgilerini gizleyebilirsin. **Seed phrase veya private key'ini asla paylaşma.** Doğrulanan her bağış miktarı rol için yeterlidir.

Şu anda bağış yapmak istemiyorsan GitHub yıldızı vermek, faydalı bir hata bildirimi göndermek veya topluluktaki başka bir kullanıcıya yardım etmek de projeyi destekler.

## 🆕 Son Sürüm — v4.7.9

- Chaos ve Perk 8 Kakera seçimleri artık normal Kakera tercihlerini doğru biçimde devralıyor.
- Tekrarlanan dört butonlu Perk 8 roll'ları Discord mesajı yenilense bile güvenilir şekilde eşleştiriliyor.
- `sp` ve `spR` kırmızı küre adları aynı hedef olarak algılanıyor.
- Preset geçişleri seçim ve eksik taslakları kaybetmeden çok daha hızlı çalışıyor.
- Quick Setup artık `wx`, `hx` ve `mx` roll havuzlarını da destekliyor.

## 🔐 Termux Token Saklama — v4.6.2

- **Shell komutu gerektirmez:** Termux kullanıcıları tokenı editöre bir kez girip normal şekilde kaydeder.
- **Kalıcı özel depolama:** Token, `presets.json` veya paylaşılan depolama yerine Android'in Termux'a özel uygulama dizininde yeniden başlatmalar arasında korunur.
- **Kısıtlı erişim:** Depolama dizini ve token dosyası yalnızca sahibinin erişebileceği izinlerle (`0700`/`0600`) kilitlenir.
- **Otomatik taşıma:** `presets.json` içinde kalmış eski tokenlar bir sonraki editör açılışında özel depoya taşınır.
- **Güvenilir forcedivorce onayı:** Kakera farming artık gerekli `y` onayını aynı aralıklı komut kuyruğundan gönderir.
- **Gizli `$rt` kullanımı yok:** Forcedivorce tek başına `$rt` açmaz; farm claim'lerinde yalnızca **Auto $rt After Claim** açıksa kullanılır.

## 🚀 Komut Aralığı ve Farming Kontrolleri — v4.6.1

- **Güvenilir claim ve pause:** Claim sonucu canlı Discord kanıtlarıyla doğrulanır, reset zamanları saniye hassasiyetinde korunur ve pause tüm hesaplardaki aktif roll, gecikme, reaction ve buton işlemlerini durdurur.
- **Çok daha az `$tu`:** Kesin cooldown, tamamlanmış roll döngüsü ve miktarı belli bonus roll mesajları yalnızca ilgili yerel durumu günceller; taze yanıt eşleştirme, sınırlı tekrar ve backoff sorgu spam'ini önler.
- **Daha güvenli ayarlar ve güncellemeler:** Token'lar Windows DPAPI, sistem keyring'i veya Termux'un uygulamaya özel depolaması ile saklanır; JSON yazımları atomiktir ve modüler updater indirdiği her dosyayı uygulamadan önce doğrular.
- **Daha dayanıklı otomasyon:** Çoklu hesap claim koordinasyonu, zamanlanmış roll'lar, Kakera maliyetleri, boş embed'ler, sıfır değerli eşikler ve sonsuz tekrar yolları düzeltildi.
- **Esnek Kakera farming:** Bağımsız roll öncesi ve claim sonrası forcedivorce seçenekleri ayrı ayrı veya birlikte açılabilir; ortak sunucu, solo key farming ve başlangıçta zaten sahip olunan karakter senaryolarını kapsar.
- **Doğru birleşik güç indirimleri:** 10+ key indirimi ile görünen `💎/2` Perk 8 indirimi artık bağımsız şekilde üst üste uygulanır; 7.5% gibi kesirli maliyetler doğru izlenir.
- **Geliştirilmiş preset editörü ve tanılama:** Preset doğrulama ve kayıt akışları tutarlı hale getirildi; dinamik değerler korunur, alt süreç durumu görünür, log'lar döndürülür ve kritik akışlar otomatik testlerle korunur.

---

## ❓ Bu Ne İşe Yarar?

**MudaRemote** bir **Mudae botudur** — Discord'daki Mudae oyununu sizin yerinize otomatik olarak oynayan bir programdır.

Neler yapabilir:

- 🎲 **Auto roll Mudae** — Sizin yerinize karakter çıkartma komutlarını (`$wa`, `$ha`, vb.) gönderir.
- 💍 **Mudae auto claim** — İyi bir karakter mi gördü? Hemen yakalar. Anında.
- 💎 **Mudae auto kakera** — Size para kazandırmak için çıkartılan karakterlerdeki kakera kristallerine tıklar.
- 🎯 **Wishlist takibi** — Ayarladığınız wishlist karakterlerini algılar ve uygun olduğunda hemen claim etmeyi dener.
- 🤖 **Mudae slash commands bot** — %10 daha fazla kakera bonusu için `/wa` komutlarını kullanabilir.
- 👥 **Mudae multi-account sync** — Yan hesaplarınız mı var? Birlikte çalışabilirler.
- 🕒 **Zamanlama kontrolleri** — Tekrarlayan zamanlamayı azaltmak için gecikme, pasif saat ve kanal aktivitesi seçenekleri sunar; güvenlik garantisi vermez.
- 🖥️ **Kolay Arayüz** — Kod düzenleme yok. Ayarlamak için sadece düğmelere tıklayın.

> **⚠️ UYARI:** Bu bir **self-bot** aracıdır. Self-bot kullanımı **Discord kurallarına aykırıdır**. **Banlanabilirsiniz**. Bu proje sadece **öğrenme amaçlıdır**. Kullanırsanız, bu **sizin tercihiniz ve riskinizdir**. Sorumluluk kabul etmiyoruz.

---

## 🏆 Neden Diğer Mudae Scriptlerinden Daha İyi?

| | Eski Mudae Botları | **MudaRemote** |
| :--- | :---: | :---: |
| Karakter Çıkarma | Sadece yazı (`$wa`) | ✅ Slash komutları (`/wa`) — %10 daha fazla kakera |
| Yakalama | Her şeyi yakalar | ✅ Sadece SİZİN istediğinizi yakalar |
| Zamanlama | Her saat aynı zamanda | ✅ En mükemmel anı bekler |
| Güvenlik | Kolayca fark edilir | ✅ Gerçek bir insan gibi davranır |
| Hesaplar | Sadece tek hesap | ✅ Aynı anda birçok hesap |
| Kurulum | Kod dosyalarını düzenle | ✅ Kolay grafiksel pencere |
| Güncellemeler | Tekrar indir | ✅ Kendini otomatik olarak günceller |
| Dil | Sadece İngilizce | ✅ İngilizce, Portekizce, İspanyolca, Fransızca |

---

## ✨ Tüm Özellikler (Basit Açıklama)

### 🎯 Karakter Yakalama — Mudae Auto Claim

Bot çıkartılan her karakteri (sizinkini ve başkalarınınkini) izler ve sizin için en iyi karakterleri yakalar.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Wishlist Yakalama** | İstediğiniz karakterlerin listesini yaparsınız. Bot çıktıkları an yakalar. |
| **Seri Yakalama** | "Naruto"yu mu seviyorsunuz? Bot her Naruto karakterini yakalar. |
| **Değer Yakalama** | Belirlediğiniz Kakera eşiğini aşan uygun karakterleri claim etmeyi deneyebilir. |
| **Anlık Yakalama** | Bot karakter çıkartırken iyi bir şey çıkarsa, BEKLEMEDEN hemen yakalar. |
| **Panik Yakalama** | Yakalama süreniz mi bitiyor? Bot hiçbir şeyi boşa harcamamak için HER ŞEYİ yakalar. |
| **Ücretsiz Kartlar** | Noel veya Yılbaşı etkinlik kartları ücretsizdir. Bot bunları otomatik alır. |
| **Auto $rt** | `$rt` size ekstra bir yakalama hakkı verir. Bot bunu gerektiğinde kullanır. |
| **Engelleme Listesi** | ASLA istemediğiniz karakterler mi var? Listeye ekleyin, bot onları görmezden gelir. |

---

### 💎 Kakera — Mudae Auto Kakera

Para kazanmak için kristal butonlara tıklar. Bot akıllıdır.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Otomatik Tıklama** | Bot, sizin ve başkalarının rulolarındaki kakera butonlarına tıklar. |
| **Öncelik Sırası** | Çok fazla buton mu var? Bot en iyisine önce tıklar. |
| **Güç Takibi** | Tıklamak güç harcar. Bot gücünüzü takip eder, yetmiyorsa tıklamaz. |
| **Auto $dk** | Güç düşük mü? Bot gücü doldurmak için `$dk` kullanır. |
| **Chaos Modu** | 10+ anahtarlı karakterler %50 daha az güç harcar. Bot bunları hedefleyebilir. |
| **Sadece MK Modu** | Sadece `$mk` rulolarındakilere tıklar. Çok fazla güç tasarrufu sağlar. |
| **Küre Algılama** | Küreler SIFIR güç harcar. Bot bunlara HER ZAMAN tıklar. |

---

### 🎲 Karakter Çıkarma — Auto Roll Mudae

Bot sizin yerinize ve en akıllı zamanda karakter çıkartır.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Auto Roll** | `$wa`, `$ha` vb. komutları otomatik gönderir. |
| **Slash Komutları** | %10 daha fazla kakera veren `/wa` komutlarını kullanır. |
| **Akıllı Zamanlama** | Yakalama hakkınızın yenilendiği an karakter çıkartma işlemini bitirecek şekilde ayarlar. |
| **Planlanmış Zamanlar** | "Her gün 14:00 ve 18:30'da karakter çıkart" diyebilirsiniz. |
| **Lurker Modu** | Ayarlanan kanalları izler ve kendi roll'larını claim penceresinin sonuna yakın kullanır. |

---

### 🕒 Zamanlama ve Etkinlik Kontrolleri

Bu ayarlar yalnızca tekrar eden zamanlamayı azaltır. Bir self-botu görünmez veya Discord kurallarına uygun hâle getirmez.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Rastgele Gecikmeler** | Her döngüden sonra rastgele süre bekler (0–40 dk). |
| **Kanal İzleyici** | İnsanlar chatte konuşuyorsa bot bekler. Gerçek bir insan gibi. |
| **Rastgele Reaksiyonlar** | Karakter yakalarken her seferinde farklı bir kalp emojisi seçer. |
| **Uyku Düzeni** | "Gece 1 ile sabah 7 arası uyu" diyebilirsiniz. Bot tamamen sessiz kalır. |
| **Bakım Algılama** | Mudae bakıma mı girdi? Bot bunu algılar ve durur. |

---

### 👥 Çoklu Hesap — Mudae Multi-Account Sync

Aynı anda birçok hesapta çalıştırın.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Ana Hesap Senkronizasyonu** | Yan hesabınız, ana hesabınızın istediği bir karakteri görürse ANINDA yakalar. |
| **Ayrı Profiller** | Her hesabın kendi tokeni, kanalı ve ayarları vardır. |
| **Otomatik Yeniden Başlatma** | Bot çökerse, 60 saniye sonra kendini yeniden açar. |

---

### 🖥️ Kolay Kurulum Penceresi (GUI)

Kodlarla uğraşmanıza gerek yok. `mudae_preset_editor.py` size güzel bir pencere açar:
- ✅ Tokeninizi ve kanal ID'nizi girin
- ✅ Özellikleri kutucukları işaretleyerek açın/kapatın
- ✅ Tek tıkla kaydedin ve başlatın

---

## 🛠️ Nasıl Kurulur? (Adım Adım)

### Gerekli Olanlar
- **[Python 3.8 veya daha yenisi](https://www.python.org/downloads/)** — Kurarken ✅ **"Add to PATH"** işaretleyin
- Discord Tokeni ([aşağıya bakın](#-discord-tokeni-nasıl-alınır))

### Adım 1: Botu İndirin
GitHub'dan ZIP olarak indirin ve klasöre çıkarın.

### Adım 2: Gerekli Kütüphaneleri Kurun
Klasörün içinde terminal (CMD) açın ve şunu yazın:
```bash
pip install -r requirements.txt
```

### Adım 3: Ayarlar Penceresini Açın
```bash
python mudae_preset_editor.py
```
**Token** ve **Kanal ID** girin, **💾 Save Changes** butonuna basın.

### Adım 4: Botu Başlatın
Penceredeki **▶ Launch Bot** butonuna tıklayın. İşte bu kadar! 🎉

---

## 🔑 Discord Tokeni Nasıl Alınır?
1. **Tarayıcıdan** Discord'u açın (Uygulamadan olmaz).
2. Klavyenizden **F12** tuşuna basın.
3. **Console** sekmesine tıklayın.
4. Şunu yapıştırın ve Enter'a basın:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
5. Çıkan uzun yazı tokeninizdir. **🚨 BU TOKENİ ASLA KİMSEYLE PAYLAŞMAYIN.**

---

## ⚠️ Uyarı (Okuyun!)
> **Bu program sadece eğitim amaçlıdır.**
> Self-bot kullanmak Discord kurallarına aykırıdır.
> Hesabınızın kalıcı olarak kapatılma riski vardır. Sorumluluk kabul etmiyoruz. Sadece kaybetmeyi göze aldığınız hesaplarda kullanın.

---

<p align="center">
  <strong>⭐ Beğendiyseniz Star (Yıldız) vermeyi unutmayın! ⭐</strong>
</p>

<p align="center">
  <sub>MudaRemote — Mudae bot, Mudae auto claim, Discord Mudae sniper, Mudae auto kakera, Mudae slash commands bot, auto roll Mudae, Mudae macro, Mudae script, Mudae multi-account sync, Mudae automation, Mudae selfbot, Mudae helper, Mudae tool, Mudae farming bot, Mudae key farming, Mudae power management, Mudae wishlist bot, Mudae Discord tool 2026</sub>
</p>
