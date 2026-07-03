import Navbar from "@/components/Navbar";

/** Streams instantly while the server page prefetches data. */
export default function Loading() {
  return (
    <>
      <Navbar />
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="mb-6 animate-pulse">
          <div className="flex items-center gap-4 mb-3">
            <div className="w-12 h-12 rounded-xl bg-gray-200 dark:bg-gray-800" />
            <div>
              <div className="h-6 w-48 bg-gray-200 dark:bg-gray-800 rounded mb-2" />
              <div className="h-4 w-32 bg-gray-200 dark:bg-gray-800 rounded" />
            </div>
          </div>
          <div className="flex gap-6 mt-3">
            <div className="h-8 w-24 bg-gray-200 dark:bg-gray-800 rounded" />
            <div className="h-8 w-20 bg-gray-200 dark:bg-gray-800 rounded" />
            <div className="h-8 w-28 bg-gray-200 dark:bg-gray-800 rounded" />
          </div>
        </div>
      </div>
    </>
  );
}
