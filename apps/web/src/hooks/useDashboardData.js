import { useEffect, useState } from "react";

import { fetchJson } from "../lib/api";
import { dashboardStats } from "../data/mock";

export function useDashboardData() {
  const [summary, setSummary] = useState({
    products: null,
    warehouses: null,
    low_stock_alerts: null,
  });

  useEffect(() => {
    let mounted = true;

    fetchJson("/inventory/summary", {
      products: 1,
      warehouses: 1,
      low_stock_alerts: 0,
    }).then((data) => {
      if (mounted) {
        setSummary(data);
      }
    });

    return () => {
      mounted = false;
    };
  }, []);

  const mergedStats = dashboardStats.map((item) => {
    if (item.title === "Alertas criticas" && summary.low_stock_alerts !== null) {
      return { ...item, value: String(summary.low_stock_alerts) };
    }
    return item;
  });

  return {
    summary,
    stats: mergedStats,
  };
}

