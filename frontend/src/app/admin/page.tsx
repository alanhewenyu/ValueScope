"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth-context";
import {
  getAdminStats,
  getAdminUsers,
  getAdminSystem,
  deleteAdminUser,
  type AdminStats,
  type AdminUser,
  type AdminSystem,
} from "@/lib/api";

export default function AdminPage() {
  const { t } = useI18n();
  const { user, loading: authLoading } = useAuth();

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [system, setSystem] = useState<AdminSystem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      // Load stats first — if this fails with 403, user is not admin
      const statsData = await getAdminStats();
      setStats(statsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
      setLoading(false);
      return;
    }
    // Load users and system independently — don't let one failure break the page
    try { const usersData = await getAdminUsers(); setUsers(usersData.users); } catch {}
    try { const systemData = await getAdminSystem(); setSystem(systemData); } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!authLoading && user) loadData();
    else if (!authLoading && !user) setLoading(false);
  }, [authLoading, user, loadData]);

  const handleDelete = async (u: AdminUser) => {
    if (!confirm(t.adminDeleteConfirm(u.email))) return;
    setDeleting(u.id);
    try {
      await deleteAdminUser(u.id);
      setUsers((prev) => prev.filter((x) => x.id !== u.id));
      // Refresh stats
      const newStats = await getAdminStats();
      setStats(newStats);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center text-gray-500">
        {t.loading}
      </div>
    );
  }

  if (!user || error) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          {t.adminNoAccess}
        </h1>
        <p className="text-gray-500 dark:text-gray-400">
          {error || t.adminNoAccessDesc}
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
        {t.adminTitle}
      </h1>

      {/* Stats Cards */}
      {stats && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">
            {t.adminStats}
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <StatCard label={t.adminTotalUsers} value={stats.total_users} />
            <StatCard label={t.adminTotalValuations} value={stats.total_valuations} />
            <StatCard label={t.adminTodaySignups} value={stats.today_signups} />
            <StatCard
              label={t.adminDbSize}
              value={`${(stats.db_size_mb.valuations + stats.db_size_mb.portfolio).toFixed(1)} MB`}
            />
            <StatCard
              label={t.adminDiskFree}
              value={stats.disk.free_gb != null ? `${stats.disk.free_gb} GB` : "N/A"}
            />
          </div>
        </section>
      )}

      {/* Users Table */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">
          {t.adminUsers}
        </h2>
        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900 text-gray-600 dark:text-gray-400">
              <tr>
                <th className="text-left px-4 py-3 font-medium">{t.adminEmail}</th>
                <th className="text-left px-4 py-3 font-medium">{t.adminCreatedAt}</th>
                <th className="text-right px-4 py-3 font-medium">{t.adminValuations}</th>
                <th className="text-right px-4 py-3 font-medium">{t.adminPortfolio}</th>
                <th className="text-right px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-gray-900/50">
                  <td className="px-4 py-3 text-gray-900 dark:text-white font-mono text-xs">
                    {u.email}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {u.created_at?.slice(0, 10) || "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">
                    {u.valuation_count}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">
                    {u.portfolio_count}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(u)}
                      disabled={deleting === u.id}
                      className="text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                    >
                      {deleting === u.id ? "..." : t.adminDelete}
                    </button>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    No users found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* System Info */}
      {system && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">
            {t.adminSystem}
          </h2>
          <div className="rounded-xl border border-gray-200 dark:border-gray-800 p-4 space-y-3">
            <div className="text-sm text-gray-600 dark:text-gray-400">
              Python {system.python_version}
            </div>
            <div className="flex flex-wrap gap-3">
              {Object.entries(system.api_keys).map(([key, configured]) => (
                <span
                  key={key}
                  className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full ${
                    configured
                      ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500"
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${configured ? "bg-green-500" : "bg-gray-400"}`} />
                  {key.replace(/_/g, " ").replace(/ API KEY/i, "").replace(/ KEY/i, "")}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-800 p-4">
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className="text-xl font-bold text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}
