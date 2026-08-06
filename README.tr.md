<p align="center">
  <h1 align="center">⚡ MudaRemote: Discord için Mudae Otomasyonu</h1>
  <p align="center">
    <strong>Roll, claim, Kakera toplama ve çoklu hesap ayarlarını tek bir uygulamadan yönetin.</strong>
  </p>
  <p align="center">
    Sık kullanılan ayarlar için dosya düzenlemek gerekmez.<br>
    Zamanlama seçenekleri ban veya tespit edilmeme garantisi vermez.
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-Tek_Dosya_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.8.0-f97316?style=for-the-badge" alt="Version 4.8.0"></a>
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

MudaRemote ücretsiz ve açık kaynaklıdır. Düzenli kullanıyorsan ve bakım için harcanan zamana katkıda bulunmak istersen bağış yapabilirsin. Bağış tamamen isteğe bağlıdır.

Discord sunucusunda uygulamayı kullanan, sorun bildiren ve ayarlarını paylaşan **310'dan fazla üye** bulunuyor.

### Güncel hedef

**Hedefin %40'ı tamamlandı • İlk topluluk destekçileriyle $40 / $100 • Son güncelleme: Ağustos 2026**

Bağışlar şu işler için ayrılan zamanı destekler:

- Discord veya Mudae değiştiğinde gereken uyumluluk düzeltmeleri ve testler;
- Windows sürümleri, checksum kontrolleri ve güncelleme testleri;
- dokümantasyon, çeviriler ve topluluk desteği;
- açık hata kayıtları ve özellik istekleri.

Her miktar değerlidir. Bir referans istersen **$5**, **$15** veya **$30** karşılığı kripto düşünebilirsin. Alt sınır yoktur.

| Varlık | Ağ | Adres |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON (TRC20) | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> Göndermeden önce varlık ve ağı birlikte doğrula; kripto işlemleri geri alınamaz. İsteğe bağlı **Donator** rolünü almak için işlem kimliğini veya ekran görüntüsünü geliştiriciye Discord DM üzerinden gönder. İlgisiz cüzdan bilgilerini gizleyebilirsin. **Seed phrase veya private key'ini asla paylaşma.** Doğrulanan her bağış miktarı rol için yeterlidir.

Bağış dışında GitHub yıldızı vermek, tekrar üretilebilir bir hata bildirmek veya Discord'da bir soruyu yanıtlamak da yardımcı olur.

---

## ❓ Bu Ne İşe Yarar?

**MudaRemote**, Discord'daki Mudae oyununun tekrarlayan işlemlerini otomatikleştiren bir masaüstü aracıdır.

Başlıca özellikler:

- 🎲 **Otomatik roll**: `$wa`, `$ha` ve ayarladığınız diğer roll komutlarını gönderir.
- 💍 **Otomatik claim**: Karakterleri belirlediğiniz kurallarla karşılaştırıp uygun claim'i dener.
- 💎 **Kakera toplama**: Seçtiğiniz Kakera türlerine güç sınırlarını gözeterek tıklar.
- 🎯 **Wishlist takibi**: Ayarladığınız wishlist karakterlerini algılar ve uygun olduğunda hemen claim etmeyi dener.
- 🤖 **Mudae slash commands bot**: %10 daha fazla kakera bonusu için `/wa` komutlarını kullanabilir.
- 👥 **Çoklu hesap desteği**: Birden fazla preset çalıştırabilir ve claim işlemlerini koordine edebilir.
- 🕒 **Zamanlama kontrolleri**: Tekrarlayan zamanlamayı azaltmak için gecikme, pasif saat ve kanal aktivitesi seçenekleri sunar; güvenlik garantisi vermez.
- 🖥️ **Ayar arayüzü**: Sık kullanılan ve gelişmiş seçenekleri preset editöründen yönetir.

> **⚠️ UYARI:** Bu bir **self-bot** aracıdır. Self-bot kullanımı **Discord kurallarına aykırıdır**. **Banlanabilirsiniz**. Bu proje sadece **öğrenme amaçlıdır**. Kullanırsanız, bu **sizin tercihiniz ve riskinizdir**. Sorumluluk kabul etmiyoruz.

---

## 🏆 Neden MudaRemote?

| | Temel scriptler | **MudaRemote** |
| :--- | :---: | :---: |
| Roll | Genellikle yalnızca metin komutları | Metin ve desteklenen slash komutları |
| Claim | Temel filtreler | Wishlist, seri, değer, sıralama ve sahiplik filtreleri |
| Zamanlama | Sabit program | Ayarlanabilir gecikmeler ve pasif saatler |
| Hesaplar | Genellikle işlem başına tek hesap | Ortak koordinasyona sahip çoklu presetler |
| Kurulum | Python ve elle ayar | Windows uygulaması ve grafik arayüz |
| Güncellemeler | Dosyaları elle değiştirme | Onaylı ve doğrulanan uygulama içi güncellemeler |

---

## ✨ Özellikler

### 🎯 Karakter Eşleştirme ve Claim

Bot, ayarlanan kanallardaki uygun roll'ları izler ve claim denemeden önce belirlediğiniz kuralları uygular.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Wishlist Yakalama** | Wishlist'inizdeki karakterler için claim dener. |
| **Seri Yakalama** | Belirlediğiniz serilerdeki uygun karakterler için claim dener. |
| **Değer Yakalama** | Belirlediğiniz Kakera eşiğini aşan uygun karakterleri claim etmeyi deneyebilir. |
| **Anlık Yakalama** | Roll grubu tamamlanmadan eşleşen bir karakter için claim deneyebilir. |
| **Panik Yakalama** | Claim süresinin sonunda uygun seçenekler arasından en yüksek öncelikli olanı kullanabilir. |
| **Ücretsiz Kartlar** | Noel veya Yılbaşı etkinlik kartları ücretsizdir. Bot bunları otomatik alır. |
| **Auto $rt** | `$rt` size ekstra bir yakalama hakkı verir. Bot bunu gerektiğinde kullanır. |
| **Engelleme Listesi** | Listeye eklediğiniz karakterleri atlar. |

---

### 💎 Kakera: Mudae Auto Kakera

Bot, seçilen Kakera butonlarına tıklayabilir ve harcanan gücü takip eder.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Otomatik Tıklama** | Bot, sizin ve başkalarının rulolarındaki kakera butonlarına tıklar. |
| **Öncelik Sırası** | Birden fazla buton varsa belirlediğiniz sırayı kullanır. |
| **Güç Takibi** | Tıklamak güç harcar. Bot gücünüzü takip eder, yetmiyorsa tıklamaz. |
| **Auto $dk** | Güç düşük mü? Bot gücü doldurmak için `$dk` kullanır. |
| **Chaos Modu** | 10+ anahtarlı karakterler %50 daha az güç harcar. Bot bunları hedefleyebilir. |
| **Sadece MK Modu** | Kakera toplamayı `$mk` roll'larıyla sınırlar. |
| **Küre Algılama** | Kakera gücü harcamayan desteklenen küre butonlarını algılar. |
| **Küre Mini Oyunları** | Otomatik `$oh` ve `$oc` küre tahtalarını oynar; `$oh` kullanımları çarpanlı toplu veya ayrı tahtalar halinde çalıştırılabilir. |

---

### 🎲 Karakter Çıkarma: Auto Roll Mudae

Roll'lar hemen, belirli saatlerde veya bir sonraki claim yenilenmesine göre çalıştırılabilir.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Auto Roll** | `$wa`, `$ha` vb. komutları otomatik gönderir. |
| **Slash Komutları** | %10 daha fazla kakera veren `/wa` komutlarını kullanır. |
| **Akıllı Zamanlama** | Yakalama hakkınızın yenilendiği an karakter çıkartma işlemini bitirecek şekilde ayarlar. |
| **Planlanmış Zamanlar** | 14:00 ve 18:30 gibi belirli saatlerde çalışır. |
| **Lurker Modu** | Ayarlanan kanalları izler ve kendi roll'larını claim penceresinin sonuna yakın kullanır. |

---

### 🕒 Zamanlama ve Etkinlik Kontrolleri

Bu ayarlar yalnızca tekrar eden zamanlamayı azaltır. Bir self-botu görünmez veya Discord kurallarına uygun hâle getirmez.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Rastgele Gecikmeler** | Her döngüden sonra rastgele süre bekler (0-40 dk). |
| **Kanal İzleyici** | Ayarlanan kanalda yakın zamanda konuşma varsa bekleyebilir. |
| **Rastgele Reaksiyonlar** | Karakter yakalarken her seferinde farklı bir kalp emojisi seçer. |
| **Uyku Düzeni** | "Gece 1 ile sabah 7 arası uyu" diyebilirsiniz. Bot tamamen sessiz kalır. |
| **Bakım Algılama** | Mudae bakıma mı girdi? Bot bunu algılar ve durur. |

---

### 👥 Çoklu Hesap: Mudae Multi-Account Sync

Aynı anda birçok hesapta çalıştırın.

| Özellik | Ne Yapar |
| :--- | :--- |
| **Ana Hesap Senkronizasyonu** | Ayarlanan hesaplar arasında claim rezervasyonlarını koordine eder. |
| **Ayrı Profiller** | Her hesabın kendi tokeni, kanalı ve ayarları vardır. |
| **Otomatik Yeniden Başlatma** | Bot çökerse, 60 saniye sonra kendini yeniden açar. |

---

### 🖥️ Kolay Kurulum Penceresi (GUI)

`mudae_preset_editor.py` üzerinden token, kanal ve otomasyon ayarlarını yönetebilirsiniz:

- Token ve kanal kimliğini girin.
- Kullanmak istediğiniz özellikleri seçin.
- Ayarları kaydedip botu başlatın.

---

## 🛠️ Nasıl Kurulur? (Adım Adım)

### Gerekli Olanlar
- **[Python 3.8 veya daha yenisi](https://www.python.org/downloads/)**: Kurarken ✅ **"Add to PATH"** işaretleyin
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
Penceredeki **▶ Launch Bot** butonuna tıklayın.

---

## 🔑 Discord Tokeni Nasıl Alınır?
1. **Tarayıcıdan** Discord'u açın (Uygulamadan olmaz).
2. Klavyenizden **F12** tuşuna basın.
3. **Console** sekmesine tıklayın.
4. Şunu yapıştırın ve Enter'a basın:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
5. Konsolda gösterilen tokeni MudaRemote'a kopyalayın. **Tokeninizi kimseyle paylaşmayın.**

---

## ⚠️ Uyarı (Okuyun!)
> **Bu program sadece eğitim amaçlıdır.**
> Self-bot kullanmak Discord kurallarına aykırıdır.
> Hesabınızın kalıcı olarak kapatılma riski vardır. Sorumluluk kabul etmiyoruz. Sadece kaybetmeyi göze aldığınız hesaplarda kullanın.

---

<p align="center">
  <strong>⭐ Projeyi faydalı buluyorsanız GitHub'da yıldız verebilirsiniz. ⭐</strong>
</p>
