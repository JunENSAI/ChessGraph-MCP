/**
 * Chart colors as values, for code that cannot read CSS variables (Recharts props).
 * They mirror the tokens in index.css; change both together.
 * Win / draw / loss is a diverging scale: two poles and a neutral gray middle,
 * validated for color-blind separation on the dark surface.
 */
export const CHART = {
  win: '#199e70',
  draw: '#4a505b',
  loss: '#d95926',
  grid: '#232a35',
  axis: '#8d96a5',
  text: '#f3f5f7',
  surface: '#151922',
  border: '#343c49',
  accent: '#b8f05a',
} as const

export const CHART_TOOLTIP = {
  contentStyle: { background: CHART.surface, border: `1px solid ${CHART.border}`, borderRadius: 8, fontSize: 12 },
  labelStyle: { color: CHART.text },
  itemStyle: { color: CHART.text },
  cursor: { fill: 'rgba(255,255,255,0.04)' },
}
