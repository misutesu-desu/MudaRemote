# ⚡ MudaRemote: En İyi Mudae Otomasyon Aracı ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![Lisans](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Durum](https://img.shields.io/badge/Status-Aktif-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Katıl-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

> **⚠️ KRİTİK UYARI ⚠️**
> 
> **MudaRemote bir SELF-BOT'tur.** Kullanıcı hesaplarını otomatikleştirmek [Discord Hizmet Koşulları'na](https://discord.com/terms) aykırıdır. 
> Bu aracı kullanmak hesap askıya alınması veya yasaklanması riski taşır. **Kullanım riski size aittir.** Geliştiriciler herhangi bir sonuç için sorumluluk kabul etmez.

---

## 🚀 Genel Bakış

**MudaRemote**, özellikle Mudae Discord botu için tasarlanmış yüksek performanslı, zengin özelliklere sahip bir otomasyon motorudur. Basit bir otomatik yuvarlama (auto-roll) makrosunun çok ötesine geçerek, hesabınızı güvende tutarken harem verimliliğinizi en üst düzeye çıkarmak için akıllı durum yönetimi, cerrahi hassasiyette snipe yetenekleri ve gelişmiş insanlaştırma özellikleri sunar.

MudaRemote, ne zaman yuvarlayacağına, ne zaman uyuyacağına ve neyi talep edeceğine (claim) karar vermek için Mudae'nin yanıtlarını ($tu, mesajlar, embed'ler) gerçek zamanlı olarak ayrıştırır.

---

## ✨ Temel Özellikler

### 🎯 Gelişmiş Snipe Ekosistemi
*   **İstek Listesi (Wishlist) Snipe**: *Diğer kullanıcılar* tarafından düşürülen karakterleri `wishlist`'inizden anında kapar.
*   **Seri Snipe**: Tüm bir seriyi hedefleyin! Takip edilen bir seriden herhangi bir karakter düşerse, sizindir.
*   **Kakera Değeri Snipe**: Karakter istek listenizde olmasa bile, kakera değeri belirlediğiniz eşiği aşarsa otomatik olarak kapar.
*   **Global Kakera Çiftçiliği**: Bot, kakera reaksiyon butonları için **her** mesajı izler.
    *   *Yeni:* **Akıllı Filtreleme**: Sunucu dramalarından kaçınmak için sadece belirli kullanıcılardan (örn. yan hesaplarınız) kakera çalacak şekilde yapılandırın.
    *   *Yeni:* **Kaos Modu**: Kaos Anahtarları (Chaos Keys) ile Normal Kakera arasındaki farkı akıllıca yönetir.

### 🤖 Akıllı Otomasyon
*   **Akıllı Yuvarlama (Rolling)**: Saatlik yuvarlamaları ($wa, $hg, $ma, vb.) otomatik olarak halleder ve $daily sıfırlamanızı takip eder.
*   **Slash Komut Motoru**: İsteğe bağlı olarak yuvarlama için modern Discord `/komutlarını` kullanır; bu klasik metin komutlarından daha hızlıdır ve genellikle daha az hız sınırına (rate-limit) takılır.
*   **Optimize Edilmiş Talep (Claim)**:
    *   **$rt Entegrasyonu**: Refund Wish ($rt) avantajına sahip olup olmadığınızı otomatik olarak kontrol eder ve aynı sıfırlama döneminde ikinci bir yüksek değerli karakteri almak için kullanır.
    *   **Panik Modu**: Talep sıfırlamanıza 60 dakikadan az kaldıysa (`snipe_ignore_min_kakera_reset`), bot standartlarını düşürür ve hakkın boşa gitmesini önlemek için *herhangi bir şeyi* talep eder.
*   **DK Güç Yönetimi**: Mevcut reaksiyon gücünüzü ve stoğunuzu analiz eder. Sadece gücünüz reaksiyon vermek için gerçekten çok düşük olduğunda bir `$dk` (Günlük Kakera) yükü tüketir, böylece israfı önler.

### 🛡️ Gizlilik & Güvenlik
*   **İnsanlaştırılmış Aralıklar**: Artık robotik 60 dakikalık zamanlayıcılar yok. Bot, her bekleme süresine rastgele "sapmalar" (jitter) ekler.
*   **İnaktivite İzleyici**: Kanalın meşgul olduğunu algılar ve yuvarlamaları spamlamadan önce konuşmanın durulmasını bekler, böylece nazik bir insan kullanıcıyı taklit eder.
*   **Anahtar Limiti Algılama**: Mudae anahtar limitine ulaşırsanız yuvarlamayı otomatik olarak duraklatır.

---

## 🛠️ Kurulum

1.  **Ön Koşullar**:
    *   [Python 3.8](https://www.python.org/downloads/) veya üzerini yükleyin.
2.  **Bağımlılıkları Yükleyin**:
    ```bash
    pip install discord.py-self inquirer
    ```
3.  **Kurulum**:
    *   Bu depoyu indirin.
    *   Bir `presets.json` dosyası oluşturun (aşağıdaki yapılandırmaya bakın).

---

## ⚙️ Yapılandırma (`presets.json`)

Tüm ayarlar `presets.json` içinde yönetilir. Birden fazla bot profili (örn. "AnaHesap", "YanHesap") tanımlayabilir ve bunları aynı anda çalıştırabilirsiniz.

```json
{
  "BenimProMudaBotum": {
    "token": "DISCORD_TOKENINIZ_BURAYA",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- TEMEL AYARLAR ---": "",
    "rolling": true,                       // Sadece Snipe modu için false yapın (yuvarlama yok, sadece izleme)
    "min_kakera": 200,                     // Kendi yuvarlamalarınız sırasında bir karakteri almak için minimum değer
    "delay_seconds": 2,                    // Temel işlem gecikmesi
    "roll_speed": 1.5,                     // Yuvarlama komutları arasındaki saniye

    "// --- SNIPE YAPILANDIRMASI ---": "",
    "snipe_mode": true,                    // İstek listesi snipe için ana şalter
    "wishlist": ["Makima", "Rem"],         // Snipe yapılacak tam karakter isimleri listesi
    "snipe_delay": 0.5,                    // Ne kadar hızlı snipe yapılacak (saniye)
    
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // Snipe yapılacak seri isimleri
    "series_snipe_delay": 1.0,

    "// --- KAKERA ÇİFTÇİLİĞİ ---": "",
    "kakera_reaction_snipe_mode": true,    // HERHANGİ bir mesajdaki kakera butonlarına tıklansın mı?
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // İSTEĞE BAĞLI: Sadece bu kullanıcılardan çal (örn. yan hesapların)
        "yan_hesap_kullanici_adi"
    ],
    "only_chaos": false,                   // Eğer true ise, sadece Kaos Anahtarı (mor) kristallerine tepki verir.

    "// --- GELİŞMİŞ MANTIK ---": "",
    "use_slash_rolls": true,               // $wa yerine /wa kullan (Önerilen)
    "dk_power_management": true,           // $dk yüklerini gerçekten ihtiyaç duyduğunda kullanmak üzere sakla
    "snipe_ignore_min_kakera_reset": true, // Talep sıfırlamasına < 1 saat kaldıysa HERHANGİ bir karakteri al.
    "key_mode": false,                     // Talep hakkın olmasa bile anahtar için yuvarlamaya devam et?

    "// --- İNSANLAŞTIRMA ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // Sıfırlamadan sonra rastgele 0-30 dk fazladan bekle
    "humanization_inactivity_seconds": 10  // Yuvarlamadan önce kanalda 10 sn sessizlik bekle
  }
}
```

---

## 🎮 Kullanım

1.  Bot klasöründe terminalinizi açın.
2.  Komut dosyasını çalıştırın:
    ```bash
    python mudae_bot.py
    ```
3.  Menüden ön ayarınızı (preset) seçin.
4.  Arkanıza yaslanın ve haremin büyümesini izleyin. 📈

---

## 🔒 Tokeninizi Alma

1.  Tarayıcınızda (Chrome/Firefox) Discord'a giriş yapın.
2.  **F12** (Geliştirici Araçları) -> **Console** sekmesine basın.
3.  Tokeninizi görmek için bu kodu yapıştırın:
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *(Not: Bu tokeni asla kimseyle paylaşmayın. Hesabınıza tam erişim sağlar.)*

---

**İyi Avlar!** 💖
