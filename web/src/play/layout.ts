/** Deterministic spread of object tags around the frame, biased to the lower half. */
export function tagPosition(i: number, n: number) {
  const side = i % 2 === 0 ? 8 : 64
  const x = side + ((i * 61.8 + 12) % 20)
  const row = n > 1 ? Math.floor(i / 2) / Math.max(1, Math.ceil(n / 2) - 1) : 0.5
  const y = 26 + row * 50 + ((i * 37) % 7)
  return { left: `${x}%`, top: `${y}%` }
}
