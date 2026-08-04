"use client";

import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";

export function Grafico({ opcion, alto = 280 }: { opcion: EChartsOption; alto?: number }) {
  return <ReactECharts option={opcion} style={{ height: alto, width: "100%" }} notMerge />;
}
