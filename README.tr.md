# ⚡ MudaRemote: Nihai Mudae Bot Otomasyon Aracı

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.3.8-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Active_2026-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Join%20Server-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Português Brasileiro](README.pt-BR.md)

**MudaRemote**, **Mudae Discord Botu** için özel olarak tasarlanmış en sofistike, özellik açısından zengin otomasyon motorudur. Basit makroların çok ötesine geçerek, harem verimliliğini en üst düzeye çıkarırken insan benzeri davranışı simüle etmek için gerçek zamanlı verileri ($tu, embedler, bileşenler) analiz eder.

> **⚠️ KRİTİK UYARI:** MudaRemote bir **SELF-BOT**'tur. Self-bot kullanımı Discord'un Hizmet Şartlarını (ToS) ihlal eder ve kalıcı yasaklanma riski taşır. **Kullanım sorumluluğu tamamen size aittir.**

---

## 🏆 Neden MudaRemote? (Karşılaştırma)

2021 model scriptlerle yetinmeyin. 2025 standardına yükseltin.

| Özellik | Sıradan Mudae Botları | **MudaRemote v3.3.8** |
| :--- | :--- | :--- |
| **Roll Zamanlaması** | Sabit/Rastgele Zamanlayıcılar | **Stratejik Sınır Senkronizasyonu (Mükemmel claimleme)** |
| **Komut Motoru** | Sadece Metin | **Slash Komutları (Modern API Desteği)** |
| **$rt Yönetimi** | Yok / Manuel | **Tam Otomatik Zeka** |
| **Güncellemeler** | Manuel Yeniden İndirme | **Entegre Otomatik Güncelleme Sistemi** |
| **Gizlilik** | Statik Gecikmeler | **İnsan Benzeri Jitter (Sapma) & İnaktivite İzleyici** |
| **Yerelleştirme** | Sadece İngilizce | **4 Dil Destekleniyor** |

---

## ✨ Öne Çıkan Yüksek Etkili Özellikler

### 🎨 Yepyeni: Grafiksel Preset Editörü
*   **Görsel Yapılandırma:** Artık manuel JSON düzenlemeye son! Tüm presetlerinizi şık ve koyu temalı bir GUI üzerinden yönetmek için `mudae_preset_editor.py` dosyasını kullanın.
*   **Kolay Özelleştirme:** Akıllı geri dönüş mantığı ile bireysel claim ve kakera emojilerini kolayca açıp kapatın.
*   **Tek Tıkla Başlat:** Botu doğrudan editör üzerinden başlatın.

### 🎯 Gelişmiş Sniping (Kapma) Ekosistemi
*   **Wishlist (İstek Listesi) & Seri Sniping:** Başkaları tarafından rollenen karakterleri veya tüm anime serilerini anında claimler.
*   **Akıllı Kakera Sniper:** Bir eşik değeri belirleyin (örneğin 200+) ve botun değeri otomatik olarak güvence altına almasına izin verin.
*   **Küresel Kakera Farming:** Tüm mesajları kristaller için tarar. Radara yakalanmamak için sadece belirli kullanıcılardan (yan hesaplarınız gibi) alım yapacak **Akıllı Filtreleme** içerir.
*   **Kaos Modu:** Chaos Key (10+ anahtarlı karakterler) için özelleşmiş mantık.
*   **Minimize Edilmiş $tu İzleri:** Claim ve evlilik mesajlarını (Married) chat üzerinden otomatik takip eder. Böylece sürekli `$tu` yazarak dikkat çekmez ve hesabınızı korur.
*   **Akıllı Snipe Doğrulayıcı:** Karakterin size mi yoksa başkasına mı gittiğini mesajlardan okuyarak doğrular.

### 🤖 Akıllı Otomasyon ("Beyin")
*   **Stratejik Roll Zamanlaması:** Bot, claim sıfırlamanızdan hemen öncesine kadar rolleri tutar; böylece claim hakkınız bekleme süresindeyken asla roll israf etmezsiniz.
*   **Slash Komut Motoru:** İsteğe bağlı olarak `/wa`, `/ha` vb. kullanır; bunlar daha hızlıdır ve Discord'un tespit sistemine karşı önemli ölçüde daha güvenlidir.
*   **Akıllı $rt Kullanımı:** `$rt` komutunun kullanılabilir olup olmadığını otomatik olarak algılar ve bunu yalnızca yüksek öncelikli wishlist hedefleri için kullanır.
*   **DK Güç Yönetimi:** Yüksek değerli tepkiler (react) için her zaman yeterli gücünüzün olduğundan emin olmak için Kakera gücü kullanımınızı optimize eder.

### 🛡️ Gizlilik & Ban Karşıtı Teknoloji
*   **İnsanileştirilmiş Aralıklar:** Rastgele "jitter" (sapma) uygular, böylece aktiviteniz asla 60 dakikalık bir döngü gibi görünmez.
*   **İnaktivite İzleyici:** Bir kanalın meşgul olduğunu algılar ve roll yapmadan önce sohbette bir duraksama bekler; nazik bir kullanıcı gibi davranır.
*   **Key Limiti Koruması:** Bayraklanmayı önlemek için günlük 1.000 key limitine ulaştığınızda otomatik olarak duraklar.

---

## 🛠️ Hızlı Başlangıç

1.  **Gereksinimler**: [Python 3.8+](https://www.python.org/downloads/)
2.  **Kurulum**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **Çalıştır**:
    ```bash
    python mudae_preset_editor.py
    ```
    *Presetleri yönetmek için şık yeni GUI'yi kullanın, ardından **Run Bot**'a tıklayın!*

    *(Alternatif olarak, klasik konsol menüsü için `python mudae_bot.py` komutunu çalıştırın)*

---

## ⚙️ Yapılandırma (`presets.json`)

Farklı hesaplar veya sunucular için birden fazla profil tanımlayın.

```json
{
  "AnaHesap": {
    "token": "TOKENINIZ_BURAYA",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // Önerilen
    "time_rolls_to_claim_reset": true, // Benzersiz Özellik
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"],
    "claim_interval": 180,              // Sunucu claim sıfırlama süresi (dakika)
    "roll_interval": 60 
  }
}
```
📖 **Ayarlar için yardıma mı ihtiyacınız var?** Ayrıntılı [Yapılandırma Kılavuzumuza (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide) göz atın.

---

## 🔒 Tokeninizi Alma
1. Discord'u Tarayıcınızda açın.
2. `F12` -> `Console` (Konsol) sekmesine basın.
3. Şunu yapıştırın:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **Bu tokeni asla kimseyle paylaşmayın!**

---

**⭐ Eğer bu araç hareminizi büyütmenize yardımcı olduysa, lütfen bir Yıldız verin! Bu, projenin büyümesine ve güncel kalmasına yardımcı olur.**
