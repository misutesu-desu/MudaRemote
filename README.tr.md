[English](README.md) | [Français](README.fr.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

# ✨ MudaRemote: Gelişmiş Mudae Otomasyonu ✨

[![Discord TOS Violation - **DİKKATLİ KULLANIN**](https://img.shields.io/badge/Discord%20TOS-İHLALİ-red)](https://discord.com/terms) ⚠️ **HESAP YASAĞI RİSKİ!** ⚠️

**🛑🛑🛑 UYARI: SELF-BOT - POTANSİYEL DİSCORD HİZMET ŞARTLARI İHLALİ! HESAP YASAĞI RİSKİ! 🛑🛑🛑**
**🔥 KENDİ RİSKİNİZDE KULLANIN! 🔥 HESABINIZA KARŞI ALINAN HİÇBİR EYLEMDEN SORUMLU DEĞİLİZ. 😱**

---

## 🚀 MudaRemote: Mudae Deneyiminizi Geliştirin (Sorumlu Kullanın!) 🚀

MudaRemote, Discord botu Mudae için çeşitli görevleri otomatikleştirmek üzere tasarlanmış Python tabanlı bir self-bottur. Gerçek zamanlı snipe ve akıllı talep gibi özellikler sunar. **Ancak, self-bot kullanmak Discord'un Hizmet Şartları'na aykırıdır ve hesap askıya alınmasına veya yasaklanmasına yol açabilir.** Lütfen son derece dikkatli kullanın ve ilgili riskleri anlayın.

### ✨ Temel Özellikler:

*   **🎯 Harici Snipe (İstek Listesi, Seri ve Kakera Değeri):**
    *   **İstek Listesi Snipe:** *Başkaları* tarafından çekilen karakterleri istek listenizden talep eder (yapılandırılabilir gecikme).
    *   **Seri Snipe:** *Başkaları* tarafından çekilen karakterleri seri istek listenizden talep eder (yapılandırılabilir gecikme).
    *   **Kakera Değeri Snipe:** *Başkaları* tarafından çekilen karakterleri sadece kakera değerlerine göre (eşik üzerindeyse) talep eder.
*   **🟡 Harici Kakera Reaksiyon Snipe (Yeni!):** *Herhangi bir* Mudae mesajındaki kakera reaksiyon butonlarına otomatik olarak tıklar.
*   **😴 Sadece Snipe Modu:** Bot örneklerini, roll komutları göndermeden, *sadece* harici snipe'ları dinlemek ve yürütmek üzere yapılandırın.
*   **⚡ Reaktif Kendi Roll Snipe:** Kendi roll'larınızdan gelen karakterleri, kriterlere (istek listesi, seri, kakera değeri) uyuyorsa anında talep eder. Mevcut roll grubunu kesintiye uğratır.
*   **👯 Çoklu Hesap Desteği:** Her biri kendi yapılandırmasına sahip birden fazla bot örneğini aynı anda çalıştırın.
*   **🤖 Otomatik Roll ve Genel Talep:** Roll komutlarınızı yönetir ve roll'lar tamamlandıktan sonra minimum kakeraya göre genel taleplerde bulunur.
*   **🥇 Akıllı Talep Mantığı:** Başarılı bir birincil talepten sonra veya Anahtar Modu'ndayken potansiyel bir ikinci talep için `$rt` kullanır.
*   **🔄 Otomatik Roll ve Talep Sıfırlama Algılama:** Mudae'nin sıfırlama zamanlayıcılarını izler ve eylemleri optimize etmek için bekler.
*   **🔑 Anahtar Modu:** Ana karakter talep haklarınız beklemedeyken bile kakera toplamak için sürekli roll yapmayı sağlar.
*   **⏱️ Özelleştirilebilir Gecikmeler ve Roll Hızı:** Genel eylem gecikmelerini ve roll komutlarının hızını ayarlayın.
*   **🗂️ Kolay Ön Ayar Yapılandırması:** Tüm ayarları farklı hesaplar/senaryolar için `presets.json` dosyası aracılığıyla yönetin.
*   **📊 Konsol Günlüğü:** Bot eylemlerinin ve durumunun net, renk kodlu gerçek zamanlı çıktısı.

---

## 🛠️ Kurulum Kılavuzu

1.  **🐍 Python:** Python 3.8+ yüklü olduğundan emin olun. ([Python İndir](https://www.python.org/downloads/))
2.  **📦 Bağımlılıklar:** Terminalinizi veya komut istemcinizi açın ve çalıştırın:
    ```bash
    pip install discord.py-self inquirer
    ```
3.  **📝 `presets.json`:** Komut dosyasının bulunduğu dizinde `presets.json` adında bir dosya oluşturun. Bot yapılandırmalarınızı buraya ekleyin. Tüm mevcut seçenekler için aşağıdaki örneğe bakın.
4.  **🚀 Çalıştır:** Komut dosyasını terminalinizden yürütün:
    ```bash
    python mudae_bot.py
    ```
    (Farklıysa `mudae_bot.py` yerine komut dosyanızın gerçek adını kullanın).
5.  **🕹️ Ön Ayarları Seçin:** Görünen etkileşimli menüden hangi yapılandırılmış bot(lar)ı çalıştıracağınızı seçin.

---

### `presets.json` Yapılandırma Örneği:

```json
{
  "YourBotAccountName": {
    // --- ZORUNLU AYARLAR ---
    "token": "YOUR_DISCORD_ACCOUNT_TOKEN", // Discord hesap token'ınız. BUNU SON DERECE GİZLİ TUTUN!
    "channel_id": 123456789012345678,     // Mudae komutları için Discord kanalının ID'si.
    "roll_command": "wa",                  // Tercih ettiğiniz Mudae roll komutu (örn. wa, hg, w, ma). Sadece "rolling" true ise kullanılır.
    "delay_seconds": 1,                    // Bazı bot eylemleri arasındaki genel gecikme (saniye) (örn. $tu'dan sonra ayrıştırmadan önce). Sadece "rolling" true ise kullanılır.
    "mudae_prefix": "$",                   // Mudae'nin sunucunuzda kullandığı önek (genellikle "$").
    "min_kakera": 50,                      // Genel (roll sonrası toplu) karakter talepleri için minimum kakera değeri. Sadece "rolling" true ise kullanılır.

    // --- TEMEL ÇALIŞMA MODU ---
    "rolling": true,                       // (Varsayılan: true) True ise, bot roll yapma, talep etme, $tu kontrolleri vb. işlemleri gerçekleştirir.
                                           // False ise, bot SADECE SNIPE moduna girer: roll yapmaz, $tu kontrolü yapmaz, sadece harici snipe'ları dinler.

    // --- İSTEĞE BAĞLI AYARLAR (Bazıları "rolling: true" değerine bağlıdır) ---
    "key_mode": false,                     // (Varsayılan: false) True VE "rolling" true ise, ana karakter talep hakkı mevcut olmasa bile kakera toplamak için roll yapar.
    "start_delay": 0,                      // (Varsayılan: 0) Menüde seçildikten sonra botun başlamadan önceki gecikmesi (saniye).
    "roll_speed": 0.4,                     // (Varsayılan: 0.4) Bireysel roll komutları arasındaki gecikme (saniye). Sadece "rolling" true ise kullanılır.

    // Harici Snipe Ayarları (BAŞKALARI tarafından çekilen karakterler/kakera için - "rolling" durumundan bağımsız olarak yapılandırılmışsa her zaman aktiftir)
    "snipe_mode": true,                    // (Varsayılan: false) Harici istek listesi snipe'ını (kalp talepleri) etkinleştirir.
    "wishlist": ["Character Name 1", "Character Name 2"], // Kalp snipe'ı için karakter adları listesi.
    "snipe_delay": 2,                      // (Varsayılan: 2) Harici istek listesi snipe'ı VE harici kakera değeri snipe'ı talep etmeden önceki gecikme (saniye).

    "series_snipe_mode": true,             // (Varsayılan: false) Harici seri snipe'ını (kalp talepleri) etkinleştirir.
    "series_wishlist": ["Series Name 1"],  // Kalp snipe'ı için seri adları listesi.
    "series_snipe_delay": 3,               // (Varsayılan: 3) Harici seri snipe'ı talep etmeden önceki gecikme (saniye).

    "kakera_reaction_snipe_mode": false,   // (Varsayılan: false) Harici kakera REAKSİYON snipe'ını (kakera butonlarına tıklar) etkinleştirir.
    "kakera_reaction_snipe_delay": 0.75,   // (Varsayılan: 0.75) Harici kakera reaksiyonuna tıklamadan önceki gecikme (saniye).

    // Reaktif Snipe Ayarları (KENDİ roll'larınızdan gelen karakterler/kakera için - Sadece "rolling: true" ise aktiftir)
    "reactive_snipe_on_own_rolls": true,   // (Varsayılan: true) KENDİ roll'larınız sırasında ANINDA reaktif kalp taleplerini VE kakera tıklamalarını etkinleştirir/devre dışı bırakır.
                                           // True ise, kalp talepleri için kriter olarak istek listesi, seri_istek_listesi ve kakera_snipe_eşik (kakera_snipe_mode true ise) kullanılır.
                                           // Bu reaktif olarak talep edilen karakterlerdeki kakera da tıklanacaktır.
                                           // False ise, kendi roll'larınız için tüm talepler/kakera tıklamaları roll grubu tamamlandıktan sonra gerçekleşir.

    // Kakera Eşik Ayarları (HEM reaktif kendi roll KALBİ talepleri HEM DE harici kakera değeri KALBİ snipe'ları için kullanılır)
    "kakera_snipe_mode": true,             // (Varsayılan: false) True ise, `kakera_snipe_threshold`'u aşağıdaki KALBİ talepler için bir kriter olarak etkinleştirir:
                                           //    1. Kendi roll'larınız sırasında ANINDA reaktif kalp talepleri ("rolling" VE reactive_snipe_on_own_rolls true ise).
                                           //    2. GECİKMELİ harici kakera değeri-sadece kalp snipe'ları (`snipe_delay` kullanır).
    "kakera_snipe_threshold": 100,         // (Varsayılan: 0) Yukarıda belirtilen kalp taleplerini tetiklemek için minimum kakera değeri (`kakera_snipe_mode` true ise).

    // Diğer (Sadece "rolling: true" ise aktiftir)
    "snipe_ignore_min_kakera_reset": false // (Varsayılan: false) True ise, roll sonrası genel talepler için, talep sıfırlamanız 1 saatten az kalmışsa min_kakera etkili bir şekilde 0 olur.
                                           // Bu, reaktif snipe'ı veya harici kakera değeri snipe eşiklerini ETKİLEMEZ.
  }
  // Buraya diğer hesaplar için virgülle ayrılmış daha fazla ön ayar ekleyin.
}
```

---

## 🎮 Discord Token'ınızı Alma 🔑

Self-bot'lar Discord hesap token'ınızı gerektirir. **Bu token, hesabınıza tam erişim sağlar – bunu son derece gizli tutun! Paylaşmak, şifrenizi vermek gibidir.** Bu botu alternatif bir hesapta kullanmanız önerilir.

1.  **Discord'u web tarayıcınızda açın** (örn. Chrome, Firefox). *Masaüstü uygulamasını değil.*
2.  Geliştirici Araçları'nı açmak için **F12** tuşuna basın.
3.  **`Console`** sekmesine gidin.
4.  Aşağıdaki kod parçasını konsola yapıştırın ve Enter tuşuna basın:
    ```javascript
    window.webpackChunkdiscord_app.push([
    	[Symbol()],
    	{},
    	req => {
    		if (!req.c) return;
    		for (let m of Object.values(req.c)) {
    			try {
    				if (!m.exports || m.exports === window) continue;
    				if (m.exports?.getToken) return copy(m.exports.getToken());
    				for (let ex in m.exports) {
    					if (m.exports?.[ex]?.getToken && m.exports[ex][Symbol.toStringTag] !== 'IntlMessagesProxy') return copy(m.exports[ex].getToken());
    				}
    			} catch {}
    		}
    	},
    ]);

    window.webpackChunkdiscord_app.pop();
    console.log('%cWorked!', 'font-size: 50px');
    console.log(`%cYou now have your token in the clipboard!`, 'font-size: 16px');
    ```
5.  Token'ınız panonuza kopyalanacaktır. Dikkatlice `presets.json` dosyanızdaki `"token"` alanına yapıştırın.

---

## 🤝 Katkıda Bulunma

Katkılar memnuniyetle karşılanır! Sorunları bildirmekten, özellik önermekten veya proje deposuna çekme istekleri göndermekten çekinmeyin.

**🙏 Lütfen bu aracı sorumlu ve etik bir şekilde, Discord hesabınıza yönelik potansiyel risklerin tam bilincinde olarak kullanın. 🙏**

**Mutlu (ve Dikkatli!) Mudae'lemeler!** 😉

---
**Lisans:** [MIT Lisansı](LICENSE)
