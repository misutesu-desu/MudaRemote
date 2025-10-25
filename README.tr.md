# ✨ MudaRemote: Gelişmiş Mudae Otomasyonu ✨

[![Discord TOS İhlali - **DİKKATLİ KULLANIN**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **HESAP YASAĞI RİSKİ!** ⚠️

**🛑🛑🛑 UYARI: SELF-BOT - POTANSİYEL DİSCORD TOS İHLALİ! HESAP YASAĞI RİSKİ! 🛑🛑🛑**
**🔥 KENDİ RİSKİNİZDE KULLANIN! 🔥 HESABINIZA KARŞI ALINAN HİÇBİR EYLEMDEN SORUMLU DEĞİLİZ. 😱**

---

[Discord sunucumuza](https://discord.gg/4WHXkDzuZx) katılın

## 🚀 MudaRemote: Mudae Deneyiminizi Geliştirin (Sorumlu Kullanın!)

MudaRemote, Discord botu Mudae için çeşitli görevleri otomatikleştirmek üzere tasarlanmış Python tabanlı bir self-bottur. Gerçek zamanlı snipe etme ve akıllı talep etme gibi özellikler sunar. **Ancak, self-bot kullanmak Discord'un Hizmet Şartları'na (TOS) aykırıdır ve hesabın askıya alınmasına veya yasaklanmasına yol açabilir.** Lütfen son derece dikkatli kullanın ve ilgili riskleri anlayın.

### ✨ Temel Özellikler:

*   **🎯 Harici Snipe Etme (İstek Listesi, Seri ve Kakera Değeri):** *Başkaları* tarafından çekilen karakterleri talep eder.
*   **🟡 Harici Kakera Reaksiyon Snipe Etme:** *Herhangi bir* Mudae mesajındaki kakera reaksiyon butonlarına otomatik olarak tıklar.
*   **😴 Yalnızca Snipe Modu:** Bot örneklerini, roll komutları göndermeden, *yalnızca* harici snipe'ları dinlemek ve yürütmek üzere yapılandırın.
*   **⚡ Reaktif Kendi Roll Snipe Etme:** *Kendi* roll'lerinizden gelen karakterler kriterlere uyuyorsa anında talep eder.
*   **🤖 Otomatik Roll ve Genel Talep Etme:** Roll komutlarını yönetir ve minimum kakeraya göre talep eder.
*   **🥇 Akıllı Talep Mantığı:** `$tu`'yu ayrıştırarak `$rt` kullanılabilirliğini kontrol eder ve yüksek değerli roll'lerde potansiyel ikinci talep için kullanır.
*   **🔄 Otomatik Sıfırlama Algılama:** Mudae'nin talep ve roll sıfırlama sayaçlarını izler ve bekler.
*   **🚶‍♂️ İnsanlaştırılmış Bekleme (YENİ!):** Sıfırlamadan sonra eylemlere devam etmeden önce rastgele bir süre ve kanalın hareketsizliğini bekleyerek insan davranışını simüle eder, böylece tahmin edilebilirliği önemli ölçüde azaltır.
*   **💡 DK Güç Yönetimi (YENİ!):** `$tu` aracılığıyla kakera reaksiyon gücünüzü akıllıca kontrol eder ve yalnızca bir reaksiyon için güç yetersiz olduğunda `$dk` kullanır, böylece şarjları korur.
*   **🔑 Anahtar Modu:** Karakter talepleri beklemedeyken bile kakera toplamak için sürekli roll atmayı sağlar.
*   **⏩ Slash Roll Gönderimi (YENİ!):** Metin komutları yerine Discord'un Slash Komut altyapısını kullanarak roll komutlarını (`wa`, `h`, `m`, vb.) göndermek için isteğe bağlı özellik.
*   **👯 Çoklu Hesap Desteği:** Birden fazla bot örneğini aynı anda çalıştırın.
*   **⏱️ Özelleştirilebilir Gecikmeler ve Roll Hızı:** Tüm eylem gecikmelerini ve roll komutlarının hızını ince ayar yapın.
*   **🗂️ Kolay Ön Ayar Yapılandırması:** Tüm ayarları tek bir `presets.json` dosyasında yönetin.
*   **📊 Konsol Kaydı:** Net, renk kodlu gerçek zamanlı çıktı.
*   **🌐 Yerelleştirme Desteği:** Hem İngilizce hem de Portekizce (PT-BR) Mudae yanıtları için iyileştirilmiş ayrıştırma.

---

## 🛠️ Kurulum Kılavuzu

1.  **🐍 Python:** Python 3.8+ kurulu olduğundan emin olun. ([Python İndir](https://www.python.org/downloads/))
2.  **📦 Bağımlılıklar:** Terminalinizi veya komut isteminizi açın ve çalıştırın:
    ```bash
    pip install discord.py-self inquirer
    ```
    *Not: `use_slash_rolls: true` kullanmayı planlıyorsanız, `discord.py-self` sürümünüzün `Route` nesnesini içerdiğinden emin olun (genellikle yeni sürümler içerir).*
3.  **📝 `presets.json`:** Komut dosyasının dizininde bir `presets.json` dosyası oluşturun. Bot yapılandırmalarınızı buraya ekleyin. Mevcut tüm seçenekler için aşağıdaki örneğe bakın.
4.  **🚀 Çalıştırın:** Komut dosyasını terminalinizden yürütün:
    ```bash
    python mudae_bot.py
    ```
5.  **🕹️ Ön Ayarları Seçin:** Etkileşimli menüden çalıştırılacak yapılandırılmış bot(lar)ı seçin.

---

### `presets.json` Yapılandırma Örneği:

*(Teknik yapılandırma için JSON içeriği orijinaliyle aynı kalır.)*

```json
{
  "YourBotAccountName": {
    // --- REQUIRED SETTINGS ---
    "token": "YOUR_DISCORD_ACCOUNT_TOKEN", 
    "channel_id": 123456789012345678,     
    "roll_command": "wa",                  
    "delay_seconds": 1,                    
    "mudae_prefix": "$",                   
    "min_kakera": 50,                      

    // --- CORE OPERATIONAL MODE ---
    "rolling": true,                       

    // --- ADVANCED ROLLING / CLAIMING ---
    "roll_speed": 0.4,                     
    "key_mode": false,                     
    "skip_initial_commands": false,        // (Varsayılan: false) True ise, başlangıçta $limroul, $dk ve $daily'yi atlar, doğrudan $tu'ya gider.
    "use_slash_rolls": false,              // (Varsayılan: false) True ise, Discord'un slash komut API'sini kullanarak roll komutlarını göndermeye çalışır.
    "dk_power_management": true,           // (Varsayılan: false) True ise, $tu'da kakera gücünü kontrol eder ve yalnızca gerekirse $dk kullanır.

    // YENİ: Sadece Chaos Anahtarları Filtresi
    "only_chaos": false,                   // (Varsayılan: false) True ise, sadece 10+ anahtarlı (chaos keys) karakterlerde kakera butonlarına tıklar.           

    // --- HUMANIZATION (Recommended for high-risk accounts) ---
    "humanization_enabled": true,          
    "humanization_window_minutes": 40,     
    "humanization_inactivity_seconds": 5,  

    // --- EXTERNAL SNIPING (For characters rolled by OTHERS) ---
    "snipe_mode": true,                    
    "wishlist": ["Character Name 1", "Character Name 2"],
    "snipe_delay": 2,                      

    "series_snipe_mode": true,             
    "series_wishlist": ["Series Name 1"],
    "series_snipe_delay": 3,               

    "kakera_reaction_snipe_mode": false,   
    "kakera_reaction_snipe_delay": 0.75,   

    // --- KAKERA THRESHOLD (Used for both External and Reactive Sniping) ---
    "kakera_snipe_mode": true,             
    "kakera_snipe_threshold": 100,         

    // --- REAKTİF SNİPE (KENDİ rolllerinizden gelen karakterler için) ---
    "reactive_snipe_on_own_rolls": true,   // (Varsayılan: true) Kendi rollleriniz sırasında ANINDA talepleri etkinleştirir/devre dışı bırakır (WL, Seri WL veya Kakera Eşiğine göre).
    "reactive_snipe_delay": 0,             // (Varsayılan: 0) Kendi rolllerinizde reaktif snipe sırasında talep etmeden önce gecikme (saniye). Daha doğal görünmek için kullanışlıdır.   

    // --- OTHER ---
    "start_delay": 0,                      
    "snipe_ignore_min_kakera_reset": false 
  }
}
```

---

## 🎮 Discord Jetonunuzu Alma 🔑

Self-bot'lar Discord hesap jetonunuzu gerektirir. **Bu jeton hesabınıza tam erişim sağlar – son derece gizli tutun! Paylaşmak şifrenizi vermek gibidir.** Bu botu alternatif bir hesapta kullanmanız önerilir.

1.  **Discord'u web tarayıcınızda açın** (örneğin Chrome, Firefox). *Masaüstü uygulaması değil.*
2.  Geliştirici Araçları'nı açmak için **F12** tuşuna basın.
3.  **`Console`** sekmesine gidin.
4.  Aşağıdaki kod parçasını konsola yapıştırın ve Enter tuşuna basın:

    ```javascript
    // [Aynı Javascript kod parçası buraya eklenir]
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
5.  Jetonunuz panonuza kopyalanacaktır. Bunu dikkatlice `presets.json` dosyanızdaki `"token"` alanına yapıştırın.

---

## 🤝 Katkıda Bulunma

Katkılar memnuniyetle karşılanır! Hata bildirmekten, özellik önermekten veya proje deposuna çekme istekleri (pull request) göndermekten çekinmeyin.

**🙏 Lütfen bu aracı, Discord hesabınız için potansiyel risklerin tam bilincinde olarak sorumlu ve etik bir şekilde kullanın. 🙏**

**Mutlu (ve Dikkatli!) Mudae-leme!** 😉

---
**Lisans:** [MIT Lisansı](LICENSE)
