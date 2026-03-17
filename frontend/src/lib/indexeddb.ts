/**
 * IndexedDB helper for saving DCF valuation results client-side.
 */

const DB_NAME = "valuescope";
const DB_VERSION = 2;
const STORE_NAME = "valuations";

/** Cached DB connection (singleton) */
let _dbInstance: IDBDatabase | null = null;

export interface SavedValuation {
  id?: number;
  ticker: string;
  company_name: string;
  date: string;           // ISO string, set on first save
  updated_at: string;     // ISO string, updated on each save
  mode: string;           // "manual" | "copilot"
  ai_engine?: string;
  // DCF core
  dcf_price: number;
  market_price: number;
  diff_pct: number;
  currency: string;
  reported_currency?: string;
  // Parameters (flat, matching SQLite)
  revenue_growth_1: number;
  revenue_growth_2: number;
  ebit_margin: number;
  convergence: number;
  rev_ic_1: number;
  rev_ic_2: number;
  rev_ic_3: number;
  tax_rate: number;
  wacc: number;
  ronic_match_wacc: boolean;
  // Bridge
  bridge: Record<string, number>;
  // Gap analysis (optional, added later)
  gap_analysis?: { analysis_text: string; adjusted_price: number | null; gap_pct?: number };
  // AI data (optional)
  ai_reasoning?: string;
}

function openDB(): Promise<IDBDatabase> {
  // Return cached connection if still open
  if (_dbInstance) return Promise.resolve(_dbInstance);

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = (event) => {
      const db = request.result;
      const oldVersion = (event as IDBVersionChangeEvent).oldVersion;
      // If upgrading from v1, delete old store (v1 data is minimal, not worth migrating)
      if (oldVersion < 2 && db.objectStoreNames.contains(STORE_NAME)) {
        db.deleteObjectStore(STORE_NAME);
      }
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, {
          keyPath: "id",
          autoIncrement: true,
        });
        store.createIndex("ticker", "ticker", { unique: false });
        store.createIndex("date", "date", { unique: false });
      }
    };
    request.onsuccess = () => {
      _dbInstance = request.result;
      // Clear cache if DB is unexpectedly closed
      _dbInstance.onclose = () => { _dbInstance = null; };
      _dbInstance.onversionchange = () => { _dbInstance?.close(); _dbInstance = null; };
      resolve(_dbInstance);
    };
    request.onerror = () => reject(request.error);
  });
}

export async function saveValuation(data: Omit<SavedValuation, "id">, existingId?: number): Promise<number> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const record = existingId ? { ...data, id: existingId } : data;
    const req = existingId ? store.put(record) : store.add(data);
    req.onsuccess = () => resolve(req.result as number);
    req.onerror = () => reject(req.error);
  });
}

export async function getValuationHistory(
  ticker: string,
  limit = 20
): Promise<SavedValuation[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const index = store.index("ticker");
    const results: SavedValuation[] = [];
    const req = index.openCursor(IDBKeyRange.only(ticker), "prev");
    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor && results.length < limit) {
        results.push(cursor.value);
        cursor.continue();
      } else {
        resolve(results);
      }
    };
    req.onerror = () => reject(req.error);
  });
}

export async function getAllValuationHistory(
  limit = 50
): Promise<SavedValuation[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const results: SavedValuation[] = [];
    const req = store.openCursor(null, "prev");
    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor && results.length < limit) {
        results.push(cursor.value);
        cursor.continue();
      } else {
        resolve(results);
      }
    };
    req.onerror = () => reject(req.error);
  });
}

export async function deleteValuation(id: number): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const req = store.delete(id);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}
