export interface Cell {
  x: number
  y: number
}

const key = (c: Cell) => `${c.x},${c.y}`

/** 4-directional A* over a boolean blocked grid. Returns [] when unreachable. */
export function astar(
  start: Cell,
  goal: Cell,
  blocked: (c: Cell) => boolean,
  width: number,
  height: number,
): Cell[] {
  const h = (c: Cell) => Math.abs(c.x - goal.x) + Math.abs(c.y - goal.y)
  const open: Cell[] = [start]
  const cameFrom = new Map<string, Cell>()
  const g = new Map<string, number>([[key(start), 0]])

  while (open.length > 0) {
    let bestIndex = 0
    for (let i = 1; i < open.length; i++) {
      const a = open[i]
      const b = open[bestIndex]
      if ((g.get(key(a)) ?? Infinity) + h(a) < (g.get(key(b)) ?? Infinity) + h(b)) bestIndex = i
    }
    const current = open.splice(bestIndex, 1)[0]
    if (current.x === goal.x && current.y === goal.y) {
      const path = [current]
      let node = current
      while (cameFrom.has(key(node))) {
        node = cameFrom.get(key(node))!
        path.unshift(node)
      }
      return path
    }
    const neighbors: Cell[] = [
      { x: current.x + 1, y: current.y },
      { x: current.x - 1, y: current.y },
      { x: current.x, y: current.y + 1 },
      { x: current.x, y: current.y - 1 },
    ]
    for (const n of neighbors) {
      if (n.x < 0 || n.y < 0 || n.x >= width || n.y >= height) continue
      if (blocked(n) && !(n.x === goal.x && n.y === goal.y)) continue
      const tentative = (g.get(key(current)) ?? Infinity) + 1
      if (tentative < (g.get(key(n)) ?? Infinity)) {
        cameFrom.set(key(n), current)
        g.set(key(n), tentative)
        if (!open.some((o) => o.x === n.x && o.y === n.y)) open.push(n)
      }
    }
  }
  return []
}
