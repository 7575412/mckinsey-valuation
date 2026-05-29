import type { SensitivityGrid } from "./api";

// Colors a cell from red (low) → green (high) relative to the grid range.
function color(value: number, min: number, max: number): string {
  if (max === min) return "hsl(120 60% 85%)";
  const t = (value - min) / (max - min); // 0..1
  const hue = 0 + t * 120; // red→green
  return `hsl(${hue} 70% 82%)`;
}

export default function Heatmap({ grid }: { grid: SensitivityGrid }) {
  const flat = grid.prices.flat().filter((v): v is number => v != null);
  const min = Math.min(...flat);
  const max = Math.max(...flat);

  return (
    <div className="card">
      <h3>민감도 분석 — 목표주가 (WACC × 영구성장률 g)</h3>
      <table className="heatmap">
        <thead>
          <tr>
            <th>WACC ＼ g</th>
            {grid.growth.map((g) => (
              <th key={g}>{(g * 100).toFixed(1)}%</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.wacc.map((w, i) => (
            <tr key={w}>
              <th>{(w * 100).toFixed(1)}%</th>
              {grid.prices[i].map((price, j) => (
                <td
                  key={j}
                  style={price != null ? { background: color(price, min, max) } : { color: "#aaa" }}
                >
                  {price != null ? price.toLocaleString() : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
