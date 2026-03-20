"use client";

import { I18nProvider } from "@/lib/i18n";
import { SettingsProvider } from "@/lib/settings";
import { AuthProvider } from "@/lib/auth-context";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <SettingsProvider>
        <AuthProvider>{children}</AuthProvider>
      </SettingsProvider>
    </I18nProvider>
  );
}
