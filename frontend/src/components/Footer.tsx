"use client";

import { useState } from "react";
import Image from "next/image";
import { useI18n } from "@/lib/i18n";

export default function Footer() {
  const { t } = useI18n();
  const [showQR, setShowQR] = useState(false);

  return (
    <>
      <footer className="border-t border-gray-200 dark:border-gray-800 mt-16">
        <div className="max-w-7xl mx-auto px-4 py-8 space-y-4">
          {/* Disclaimer */}
          <p className="text-xs text-gray-400 dark:text-gray-500 leading-relaxed">
            <strong className="text-gray-500 dark:text-gray-400">{t.disclaimerTitle}:</strong>{" "}
            {t.disclaimerBody}
          </p>

          {/* Divider */}
          <div className="border-t border-gray-100 dark:border-gray-800/50" />

          {/* Copyright + Contact */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-gray-400 dark:text-gray-500">
            <span>{t.copyright(new Date().getFullYear())}</span>
            <div className="flex items-center gap-3">
              <a
                href="https://jianshan.co"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                {t.contactBlog}
              </a>
              <span className="text-gray-300 dark:text-gray-700">·</span>
              <a
                href="https://github.com/alanhe/valuescope"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                {t.contactGitHub}
              </a>
              <span className="text-gray-300 dark:text-gray-700">·</span>
              <button
                type="button"
                onClick={() => setShowQR(true)}
                className="hover:text-gray-600 dark:hover:text-gray-300 transition-colors cursor-pointer"
              >
                {t.contactWeChat}
              </button>
              <span className="text-gray-300 dark:text-gray-700">·</span>
              <a
                href="mailto:alanhe@icloud.com"
                className="hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                {t.contactEmail}
              </a>
            </div>
          </div>
        </div>
      </footer>

      {/* WeChat QR Code Modal */}
      {showQR && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => setShowQR(false)}
        >
          <div
            className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl p-6 max-w-xs w-full mx-4 text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
              {t.wechatScanToFollow}
            </p>
            <div className="bg-white rounded-xl p-3 inline-block">
              <Image
                src="https://jianshan.co/images/wechat-qrcode.jpg"
                alt="WeChat QR Code"
                width={220}
                height={220}
                className="rounded-lg"
                unoptimized
              />
            </div>
            <button
              type="button"
              onClick={() => setShowQR(false)}
              className="mt-4 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </>
  );
}
