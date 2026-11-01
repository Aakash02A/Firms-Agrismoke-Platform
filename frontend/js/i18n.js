/* ==========================================================================
   i18n — lightweight English / हिन्दी toggle for public reach
   -------------------------------------------------------------------------
   Strategy: static UI chrome carries a data-i18n="key" (text),
   data-i18n-title="key" (title attr) or data-i18n-placeholder="key".
   applyLanguage() swaps strings from the dictionary, persists the choice to
   localStorage, and sets <html lang>. Dynamic, data-driven numbers stay in
   their native format; JS that builds sentences reads I18N.t(key) and
   dispatches 'agris:language' so live content can re-render in the new tongue.
   ========================================================================== */
(function () {
    'use strict';

    const STORAGE_KEY = 'agrismoke.lang';

    // Only citizen-facing surfaces (nav, dashboard, about, common labels) are
    // translated in this first pass. Expert tabs (methodology, policy detail)
    // stay English; untranslated keys simply keep their existing text.
    const DICT = {
        // ---- Navigation ----
        'nav.dashboard':        { en: 'Dashboard',                          hi: 'डैशबोर्ड' },
        'nav.map':              { en: 'Geospatial Plume Map',               hi: 'धुआँ मानचित्र' },
        'nav.calculator':       { en: 'AI Prediction Engine',               hi: 'पूर्वानुमान इंजन' },
        'nav.grap':             { en: 'GRAP Stages & Alerts',               hi: 'GRAP चरण और चेतावनियाँ' },
        'nav.mitigation':       { en: 'Policy Simulator',                   hi: 'नीति सिम्युलेटर' },
        'nav.transparency':     { en: 'Methodology & Standards',            hi: 'विधि और मानक' },
        'nav.about':            { en: 'About & Impact',                     hi: 'परिचय और प्रभाव' },

        // ---- Topbar ----
        'app.pageTitle':        { en: 'Indo-Gangetic Airshed Intelligence', hi: 'इंडो-गेंजिक वायु-सुधार जानकारी' },
        'topbar.printReport':   { en: 'Print Report',                       hi: 'रिपोर्ट प्रिंट करें' },
        'topbar.exportCsv':     { en: 'Export CSV',                         hi: 'CSV डाउनलोड करें' },

        // ---- Dashboard ----
        'dash.heroLabel':       { en: 'Delhi-NCR air quality right now',            hi: 'इस क्षण दिल्ली-NCR की वायु गुणवत्ता' },
        'dash.emergencyRules':  { en: 'Emergency rules:',                            hi: 'आपातकालीन नियम:' },
        'dash.riskScore':       { en: 'Health-risk score',                           hi: 'स्वास्थ्य जोखिम स्कोर' },
        'dash.lag':             { en: 'Farm smoke reaches the city in',             hi: 'खेतों का धुआँ शहर तक पहुँचता है' },
        'dash.tile1Label':      { en: 'Farm fires burning now',                      hi: 'अभी चल रही खेत की आग' },
        'dash.tile1Help':       { en: "Hotspots seen by satellite across Punjab & Haryana in the last 24 hours.", hi: "पिछले 24 घंटे में पंजाब और हरियाणा भर में उपग्रह ने जितनी भी आग देखी है।" },
        'dash.tile2Label':      { en: 'Of the pollution is farm smoke',              hi: 'प्रदूषण खेतों के धुएँ से है' },
        'dash.tile2Help':       { en: "How much of Delhi's fine-particle pollution comes from stubble burning.", hi: 'दिल्ली के सूक्ष्म-कण प्रदूषण का कितना हिस्सा पराली जलाने से है।' },
        'dash.tile3Label':      { en: 'Fine dust in the air (PM2.5)',                hi: 'हवा में सूक्ष्म धूल (PM2.5)' },
        'dash.tile3Help':       { en: 'PM10 is',                                     hi: 'PM10 है' },
        'dash.tile3HelpSuffix': { en: '. The safe WHO limit is 15.',                hi: '। WHO सुरक्षित सीमा 15 है।' },
        'dash.chart1Title':     { en: "How today's air will change",                 hi: 'आज वायु कैसे बदलेगी' },
        'dash.chart1Note':      { en: 'Air is usually worst in the early morning and late at night, and clears a little in the afternoon.', hi: 'सुबह जल्दी और रात देर में वायु सबसे खराब होती है, और दोपहर में थोड़ी साफ रहती है।' },
        'dash.chart2Title':     { en: 'Where the pollution comes from',              hi: 'प्रदूषण कहाँ से आता है' },
        'dash.adviceTitle':     { en: 'What should you do?',                         hi: 'आपको क्या करना चाहिए?' },
        'dash.adviceEveryone':  { en: 'Everyone',                                    hi: 'सभी लोग' },
        'dash.adviceSensitive': { en: 'Children, older adults & people with asthma or heart problems', hi: 'बच्चे, वरिष्ठ नागरिक और अस्थमा या हृदय रोगी' },
        'dash.adviceOutdoor':   { en: 'People who work outdoors',                    hi: 'खुले में काम करने वाले लोग' },

        // ---- About & Impact ----
        'about.badge':          { en: 'Built as an open public-good tool',           hi: 'एक खुला जन-हित साधन' },
        'about.title':          { en: 'Clean air, explained for everyone.',          hi: 'स्वच्छ हवा, सबके लिए आसान भाषा में।' },
        'about.text':           { en: 'AgriSmoke AI turns live satellite and weather data into simple, easy-to-understand air-quality forecasts for the Indo-Gangetic plain — so families can protect their health, officials can act earlier, and farmers can see how crop-residue burning affects the whole region.', hi: 'AgriSmoke AI उपग्रह और मौसम के लाइव डेटा को आसान भाषा की वायु-पूर्वानुमान में बदलता है — ताकि परिवार स्वास्थ्य की रक्षा करें, अधिकारी जल्दी कदम उठाएँ, और किसान देख सकें कि पराली जलाने का पूरे क्षेत्र पर क्या असर होता है।' },
        'about.whatTitle':      { en: 'What it does',                                hi: 'यह क्या करता है' },
        'about.whoTitle':       { en: "Who it's for",                                hi: 'यह किनके लिए है' },
        'about.dataTitle':      { en: 'Where the data comes from',                  hi: 'डेटा कहाँ से आता है' },
        'about.howTitle':       { en: 'How to read this dashboard',                  hi: 'डैशबोर्ड कैसे पढ़ें' },

        // ---- CPCB categories (used by dynamic, data-driven text) ----
        'cat.Satisfactory':     { en: 'satisfactory',   hi: 'संतोषजनक' },
        'cat.Moderate':         { en: 'moderate',       hi: 'मध्यम' },
        'cat.Poor':             { en: 'poor',           hi: 'खराब' },
        'cat.Very Poor':        { en: 'very poor',      hi: 'बहुत खराब' },
        'cat.Severe':           { en: 'severe',         hi: 'गंभीर' },
        'cat.Severe+ / Emergency': { en: 'an emergency', hi: 'आपात स्थिति' },

        // ---- Dynamic dashboard sentences (built by app.js) ----
        'summary.main':         { en: "Delhi-NCR's air quality is {cat} right now. {cause}", hi: 'इस समय दिल्ली-NCR की वायु गुणवत्ता {cat} है। {cause}' },
        'summary.causesHigh':   { en: 'About {pct}% of it is coming from farm-stubble smoke drifting in from Punjab and Haryana.', hi: 'इसका लगभग {pct}% हिस्सा पंजाब और हरियाणा से आ रहे पराली-धुएँ का है।' },
        'summary.causesLocal':  { en: 'Most of it is from local sources like traffic, dust and industry.', hi: 'अधिकांश हिस्सा स्थानीय स्रोतों — यातायात, धूल और उद्योग — से है।' }
    };

    function current() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved === 'hi' || saved === 'en') return saved;
        } catch (e) { /* localStorage may be blocked */ }
        return 'en';
    }

    function t(key) {
        const entry = DICT[key];
        if (!entry) return null;
        return entry[current()] || entry.en || null;
    }

    function applyLanguage(lang) {
        if (lang !== 'en' && lang !== 'hi') lang = 'en';
        try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) { /* ignore */ }

        document.documentElement.setAttribute('lang', lang === 'hi' ? 'hi' : 'en');

        document.querySelectorAll('[data-i18n]').forEach(el => {
            const val = t(el.getAttribute('data-i18n'));
            if (val != null) el.textContent = val;
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const val = t(el.getAttribute('data-i18n-title'));
            if (val != null) el.setAttribute('title', val);
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const val = t(el.getAttribute('data-i18n-placeholder'));
            if (val != null) el.setAttribute('placeholder', val);
        });

        syncToggleUI(lang);
        document.dispatchEvent(new CustomEvent('agris:language', { detail: { lang } }));
    }

    function syncToggleUI(lang) {
        document.querySelectorAll('[data-lang-btn]').forEach(btn => {
            const on = btn.getAttribute('data-lang-btn') === lang;
            btn.classList.toggle('active', on);
            btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }

    function init() {
        document.querySelectorAll('[data-lang-btn]').forEach(btn => {
            btn.addEventListener('click', () => applyLanguage(btn.getAttribute('data-lang-btn')));
        });
        applyLanguage(current());
    }

    // Expose a tiny API so app.js can build localized dynamic sentences.
    window.I18N = { t, current, applyLanguage };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
