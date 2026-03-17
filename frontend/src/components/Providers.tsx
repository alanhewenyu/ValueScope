"use client";

import { I18nProvider } from "@/lib/i18n";
import { SettingsProvider } from "@/lib/settings";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <SettingsProvider>{children}</SettingsProvider>
    </I18nProvider>
  );
}
