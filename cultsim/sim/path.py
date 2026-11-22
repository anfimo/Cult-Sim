"""A*-Wegfindung auf dem Kachelgitter (8 Richtungen, kein Schneiden von Ecken)."""
from __future__ import annotations

import heapq

_DIRS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
         (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))


def astar(cost: list[float], size: int, sx: int, sy: int, goals: set[int], max_iter: int = 9000):
    """cost[idx] == 0 → blockiert. Liefert Liste von (x, y) ohne Startfeld oder None."""
    if not goals:
        return None
    start = sx + sy * size
    if start in goals:
        return []
    gl = [(g % size, g // size) for g in goals]
    if len(gl) > 6:
        gl = gl[:6]

    def h(x, y):
        best = 1e9
        for gx, gy in gl:
            dx, dy = abs(gx - x), abs(gy - y)
            d = (dx + dy) - 0.586 * (dx if dx < dy else dy)
            if d < best:
                best = d
        return best

    open_heap = [(h(sx, sy), 0.0, start)]
    g_cost = {start: 0.0}
    came: dict[int, int] = {}
    it = 0
    while open_heap:
        _, g, cur = heapq.heappop(open_heap)
        if cur in goals:
            out = []
            while cur != start:
                out.append((cur % size, cur // size))
                cur = came[cur]
            out.reverse()
            return out
        if g > g_cost.get(cur, 1e9):
            continue
        it += 1
        if it > max_iter:
            return None
        cx, cy = cur % size, cur // size
        for dx, dy, dc in _DIRS:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= size or ny >= size:
                continue
            ni = nx + ny * size
            c = cost[ni]
            if c == 0 and ni not in goals:
                continue
            if dx and dy and (cost[cx + dx + cy * size] == 0 or cost[cx + (cy + dy) * size] == 0):
                continue
            ng = g + dc * (c or 1.0)
            if ng < g_cost.get(ni, 1e9):
                g_cost[ni] = ng
                came[ni] = cur
                heapq.heappush(open_heap, (ng + h(nx, ny), ng, ni))
    return None


def label_components(cost: list[float], size: int) -> list[int]:
    """Zusammenhangskomponenten (4er-Nachbarschaft) für schnelle Erreichbarkeitsprüfung."""
    n = size * size
    comp = [-1] * n
    cid = 0
    for s in range(n):
        if comp[s] != -1 or cost[s] == 0:
            continue
        comp[s] = cid
        stack = [s]
        while stack:
            i = stack.pop()
            x = i % size
            if x > 0 and comp[i - 1] == -1 and cost[i - 1]:
                comp[i - 1] = cid; stack.append(i - 1)
            if x < size - 1 and comp[i + 1] == -1 and cost[i + 1]:
                comp[i + 1] = cid; stack.append(i + 1)
            if i >= size and comp[i - size] == -1 and cost[i - size]:
                comp[i - size] = cid; stack.append(i - size)
            if i < n - size and comp[i + size] == -1 and cost[i + size]:
                comp[i + size] = cid; stack.append(i + size)
        cid += 1
    return comp
