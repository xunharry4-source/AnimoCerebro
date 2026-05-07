import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import zhCN from './locales/zh-CN.json';
import enUS from './locales/en-US.json';

export const SUPPORTED_LANGUAGES = ['zh-CN', 'en-US'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
export const DEFAULT_LANGUAGE: SupportedLanguage = 'zh-CN';

type I18nRuntimeConfig = {
  language?: unknown;
  supported_languages?: unknown;
};

export function normalizeSupportedLanguage(value: unknown): SupportedLanguage {
  const raw = String(value || DEFAULT_LANGUAGE).trim();
  const normalized = raw.toLowerCase().replace('_', '-');
  if (normalized === 'en' || normalized === 'en-us') {
    return 'en-US';
  }
  if (normalized === 'zh' || normalized === 'zh-cn' || normalized === 'cn') {
    return 'zh-CN';
  }
  return DEFAULT_LANGUAGE;
}

async function fetchConfiguredLanguage(): Promise<SupportedLanguage> {
  try {
    const response = await fetch('/api/web/i18n/config', {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      return DEFAULT_LANGUAGE;
    }
    const config = (await response.json()) as I18nRuntimeConfig;
    return normalizeSupportedLanguage(config.language);
  } catch {
    return DEFAULT_LANGUAGE;
  }
}

export async function initI18n(): Promise<typeof i18n> {
  if (i18n.isInitialized) {
    return i18n;
  }

  const configuredLanguage = await fetchConfiguredLanguage();

  await i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: {
        'zh-CN': { translation: zhCN },
        'en-US': { translation: enUS },
      },
      lng: configuredLanguage,
      fallbackLng: 'zh-CN',
      supportedLngs: [...SUPPORTED_LANGUAGES],
      interpolation: {
        escapeValue: false,
      },
      detection: {
        order: ['localStorage'],
        caches: ['localStorage'],
      },
    });
  return i18n;
}

export default i18n;
