/**
 * MudaRemote - GitHub Primer Styled Web Application
 * Handles: Repo Tabs, Multi-Language Engine, FAQ Accordion & Clipboard Toast Helpers
 */

// ==========================================================================
// 1. Multi-Language Translations Dictionary
// ==========================================================================
const translations = {
  en: {
    downloadExe: "Download MudaRemote.exe",
    heroDesc: "⚡ Advanced desktop & mobile Discord self-bot for Mudae. Sniping, intelligent Kakera collection, heuristic sphere solvers, and multi-account sync.",
    goalText: "Goal: $40 of $100",
    copiedToast: "Copied to clipboard!"
  },
  tr: {
    downloadExe: "MudaRemote.exe İndir",
    heroDesc: "⚡ Discord Mudae için gelişmiş masaüstü ve mobil self-bot. Otomatik roll, karakter snipe, akıllı Kakera toplama, küre çözücü ve çoklu hesap desteği.",
    goalText: "Hedef: $100 üzerinden $40",
    copiedToast: "Panoya kopyalandı!"
  },
  fr: {
    downloadExe: "Télécharger MudaRemote.exe",
    heroDesc: "⚡ Outil d'automatisation Discord de pointe pour Mudae. Sniping, collecte intelligente de Kakera et synchronisation multi-comptes.",
    goalText: "Objectif: 40$ / 100$",
    copiedToast: "Copié dans le presse-papiers !"
  },
  ja: {
    downloadExe: "MudaRemote.exe をダウンロード",
    heroDesc: "⚡ 次世代 Discord Mudae 自動化ツール。自動取得、Kakera高速回収、球体パズル自動解析、マルチアカウント同期。",
    goalText: "目標: $100中 $40",
    copiedToast: "クリップボードにコピーしました！"
  },
  ko: {
    downloadExe: "MudaRemote.exe 다운로드",
    heroDesc: "⚡ 차세대 Discord Mudae 자동화 봇. 자동 롤, 위시리스트 스나이핑, 지능형 카케라 수집 및 다중 계정 동기화 지원.",
    goalText: "목표: $100 중 $40",
    copiedToast: "클립보드에 복사되었습니다!"
  },
  zh: {
    downloadExe: "下载 MudaRemote.exe",
    heroDesc: "⚡ 新一代 Discord Mudae 自动化神器。自动掷骰、心愿单狙击、智能 Kakera 收集与多账号协作管理工具。",
    goalText: "赞助目标: $100 已筹 $40",
    copiedToast: "已复制到剪贴板！"
  },
  pt: {
    downloadExe: "Baixar MudaRemote.exe",
    heroDesc: "⚡ Ferramenta definitiva para automação Mudae no Discord. Sniping, coleta inteligente de Kakera e sincronização multi-contas.",
    goalText: "Meta: $40 de $100",
    copiedToast: "Copiado para a área de transferência!"
  }
};

let currentLang = 'en';

function setLanguage(lang) {
  if (!translations[lang]) lang = 'en';
  currentLang = lang;
  
  const dict = translations[lang];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) {
      el.textContent = dict[key];
    }
  });

  const langBtnText = document.getElementById('currentLangLabel');
  if (langBtnText) {
    langBtnText.textContent = lang.toUpperCase();
  }

  document.querySelectorAll('.lang-dropdown-item').forEach(opt => {
    opt.classList.toggle('active', opt.getAttribute('data-lang') === lang);
  });
}

// ==========================================================================
// 2. Toast & Clipboard Helper
// ==========================================================================
function showToast(message) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 16 16" fill="#3fb950"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"></path></svg>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, 2200);
}

function copyText(text, successMsg = "Copied to clipboard!") {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(translations[currentLang]?.copiedToast || successMsg);
    });
  } else {
    const input = document.createElement('textarea');
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    showToast(translations[currentLang]?.copiedToast || successMsg);
  }
}

// ==========================================================================
// 3. Initialization & Event Bindings
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
  // Setup language dropdown
  const langBtn = document.getElementById('langBtn');
  const langDropdown = document.getElementById('langDropdown');
  if (langBtn && langDropdown) {
    langBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      langDropdown.classList.toggle('show');
    });

    document.querySelectorAll('.lang-dropdown-item').forEach(opt => {
      opt.addEventListener('click', () => {
        const lang = opt.getAttribute('data-lang');
        setLanguage(lang);
        langDropdown.classList.remove('show');
      });
    });

    document.addEventListener('click', () => {
      langDropdown.classList.remove('show');
    });
  }

  // Repository Navigation Tabs
  document.querySelectorAll('.repo-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = tab.getAttribute('data-tab');
      document.querySelectorAll('.repo-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      
      tab.classList.add('active');
      document.getElementById(targetId)?.classList.add('active');
    });
  });

  // Copy buttons on cards & code boxes
  document.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.getAttribute('data-copy');
      if (val) copyText(val);
    });
  });

  // FAQ Accordion
  document.querySelectorAll('.gh-faq-question').forEach(q => {
    q.addEventListener('click', () => {
      const item = q.closest('.gh-faq-item');
      item.classList.toggle('active');
    });
  });
});
