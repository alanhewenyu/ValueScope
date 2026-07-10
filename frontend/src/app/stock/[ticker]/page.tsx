import StockPageClient from "./StockPageClient";
import { prefetchStockData } from "./prefetch";

export default async function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const decoded = decodeURIComponent(ticker);

  const { profile, financials } = await prefetchStockData(decoded);

  return (
    <StockPageClient
      ticker={decoded}
      initialProfile={profile}
      initialFinancials={financials}
    />
  );
}
