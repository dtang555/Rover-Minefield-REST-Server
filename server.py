"""
COE892 Lab 4-5: FastAPI Ground Control Server
Simulates rover navigation, mine management, and dispatch.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import hashlib
import os

app = FastAPI(title="COE892 Ground Control", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------

MAP_FILE   = "map.txt"
MINES_FILE = os.path.join("mines.txt")

# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------

def load_map_file(path: str) -> dict:
    """Load map.txt -> {rows, cols, grid}"""
    with open(path, 'r') as f:
        rows, cols = map(int, f.readline().split())
        grid = []
        for line in f:
            line = line.strip()
            if line:
                grid.append([int(x) for x in line.split()])
    print(f"[server] Map loaded from '{path}': {rows}x{cols}")
    return {"rows": rows, "cols": cols, "grid": grid}

def load_mines_file(path: str) -> tuple[dict, int]:
    """Load mines.txt -> (mines dict, next_id counter)"""
    result = {}
    counter = 1
    if not os.path.exists(path):
        print(f"[server] Warning: mines file '{path}' not found — starting with no mines")
        return result, counter
    with open(path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 3:
                row, col, serial = int(parts[0]), int(parts[1]), parts[2]
                result[counter] = {"id": counter, "row": row, "col": col, "serial": serial}
                counter += 1
    print(f"[server] Mines loaded from '{path}': {len(result)} mines")
    return result, counter

# ---------------------------------------------------------------------------
# State — loaded from files at startup
# ---------------------------------------------------------------------------

map_state = load_map_file(MAP_FILE)

mines, _mine_id_counter = load_mines_file(MINES_FILE)

# rovers: id -> {id, status, row, col, direction, commands, path}
rovers: dict = {}
_rover_id_counter = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_pin(serial: str) -> str:
    i = 0
    while True:
        pin = str(i)
        h = hashlib.sha256((serial + pin).encode()).hexdigest()
        if h.startswith("000000"):
            return pin
        i += 1

def get_mine_at(row: int, col: int) -> Optional[dict]:
    for m in mines.values():
        if m["row"] == row and m["col"] == col:
            return m
    return None

def rebuild_grid():
    """Rebuild grid from current mines (all cells 0 except mine positions)."""
    rows, cols = map_state["rows"], map_state["cols"]
    grid = [[0] * cols for _ in range(rows)]
    for m in mines.values():
        r, c = m["row"], m["col"]
        if 0 <= r < rows and 0 <= c < cols:
            grid[r][c] = 1
    map_state["grid"] = grid

def simulate_rover(rover: dict) -> dict:
    """
    Run rover commands on the current map.
    Returns updated rover dict with status, position, path, and executed_commands.
    """
    rows, cols = map_state["rows"], map_state["cols"]
    grid = map_state["grid"]

    row, col = 0, 0
    direction = 2  # 0=N,1=E,2=S,3=W
    dx = [-1, 0, 1, 0]
    dy = [0, 1, 0, -1]
    path = [[0] * cols for _ in range(rows)]
    path[row][col] = 1
    commands = rover["commands"]
    executed = []
    disarmed_mines = []

    for cmd in commands:
        # Check mine BEFORE executing non-D commands
        if grid[row][col] == 1 and cmd != 'D':
            rover["status"] = "Eliminated"
            rover["row"] = row
            rover["col"] = col
            rover["path"] = path
            rover["executed_commands"] = ''.join(executed)
            rover["disarmed_mines"] = disarmed_mines
            return rover

        if cmd == 'L':
            direction = (direction - 1) % 4
            executed.append(cmd)
        elif cmd == 'R':
            direction = (direction + 1) % 4
            executed.append(cmd)
        elif cmd == 'M':
            nr, nc = row + dx[direction], col + dy[direction]
            if 0 <= nr < rows and 0 <= nc < cols:
                row, col = nr, nc
                path[row][col] = 1
            executed.append(cmd)
        elif cmd == 'D':
            mine = get_mine_at(row, col)
            if mine:
                pin = find_pin(mine["serial"])
                disarmed_mines.append({
                    "row": row, "col": col,
                    "serial": mine["serial"], "pin": pin
                })
            executed.append(cmd)

    rover["status"] = "Finished"
    rover["row"] = row
    rover["col"] = col
    rover["path"] = path
    rover["executed_commands"] = ''.join(executed)
    rover["disarmed_mines"] = disarmed_mines
    return rover


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class MapUpdate(BaseModel):
    rows: int
    cols: int

class MineCreate(BaseModel):
    row: int
    col: int
    serial: str

class MineUpdate(BaseModel):
    row: Optional[int] = None
    col: Optional[int] = None
    serial: Optional[str] = None

class RoverCreate(BaseModel):
    commands: str

class RoverCommandUpdate(BaseModel):
    commands: str


# ---------------------------------------------------------------------------
# Map Routes
# ---------------------------------------------------------------------------

@app.get("/map")
def get_map():
    return {
        "rows": map_state["rows"],
        "cols": map_state["cols"],
        "grid": map_state["grid"],
    }

@app.put("/map")
def update_map(body: MapUpdate):
    if body.rows < 1 or body.cols < 1:
        raise HTTPException(status_code=400, detail="Rows and cols must be >= 1")
    map_state["rows"] = body.rows
    map_state["cols"] = body.cols
    rebuild_grid()
    return {"message": "Map updated", "rows": body.rows, "cols": body.cols}


# ---------------------------------------------------------------------------
# Mine Routes
# ---------------------------------------------------------------------------

@app.get("/mines")
def get_mines():
    return list(mines.values())

@app.get("/mines/{mine_id}")
def get_mine(mine_id: int):
    if mine_id not in mines:
        raise HTTPException(status_code=404, detail=f"Mine {mine_id} not found")
    return mines[mine_id]

@app.post("/mines", status_code=201)
def create_mine(body: MineCreate):
    global _mine_id_counter
    rows, cols = map_state["rows"], map_state["cols"]
    if not (0 <= body.row < rows and 0 <= body.col < cols):
        raise HTTPException(status_code=400, detail="Coordinates out of map bounds")
    if get_mine_at(body.row, body.col):
        raise HTTPException(status_code=409, detail="A mine already exists at that location")
    mine_id = _mine_id_counter
    _mine_id_counter += 1
    mines[mine_id] = {"id": mine_id, "row": body.row, "col": body.col, "serial": body.serial}
    rebuild_grid()
    return {"id": mine_id}

@app.put("/mines/{mine_id}")
def update_mine(mine_id: int, body: MineUpdate):
    if mine_id not in mines:
        raise HTTPException(status_code=404, detail=f"Mine {mine_id} not found")
    mine = mines[mine_id]
    if body.row is not None:
        mine["row"] = body.row
    if body.col is not None:
        mine["col"] = body.col
    if body.serial is not None:
        mine["serial"] = body.serial
    rebuild_grid()
    return mine

@app.delete("/mines/{mine_id}", status_code=204)
def delete_mine(mine_id: int):
    if mine_id not in mines:
        raise HTTPException(status_code=404, detail=f"Mine {mine_id} not found")
    del mines[mine_id]
    rebuild_grid()
    return None


# ---------------------------------------------------------------------------
# Rover Routes
# ---------------------------------------------------------------------------

@app.get("/rovers")
def get_rovers():
    return [
        {"id": r["id"], "status": r["status"]}
        for r in rovers.values()
    ]

@app.get("/rovers/{rover_id}")
def get_rover(rover_id: int):
    if rover_id not in rovers:
        raise HTTPException(status_code=404, detail=f"Rover {rover_id} not found")
    r = rovers[rover_id]
    return {
        "id": r["id"],
        "status": r["status"],
        "position": {"row": r["row"], "col": r["col"]},
        "commands": r["commands"],
    }

@app.post("/rovers", status_code=201)
def create_rover(body: RoverCreate):
    global _rover_id_counter
    rover_id = _rover_id_counter
    _rover_id_counter += 1
    rovers[rover_id] = {
        "id": rover_id,
        "status": "Not Started",
        "row": 0,
        "col": 0,
        "direction": 2,
        "commands": body.commands,
        "path": None,
        "executed_commands": "",
        "disarmed_mines": [],
    }
    return {"id": rover_id}

@app.put("/rovers/{rover_id}")
def update_rover_commands(rover_id: int, body: RoverCommandUpdate):
    if rover_id not in rovers:
        raise HTTPException(status_code=404, detail=f"Rover {rover_id} not found")
    r = rovers[rover_id]
    if r["status"] not in ("Not Started", "Finished"):
        raise HTTPException(status_code=409, detail=f"Rover {rover_id} is currently {r['status']}; cannot update commands")
    r["commands"] = body.commands
    r["status"] = "Not Started"
    r["row"] = 0
    r["col"] = 0
    r["path"] = None
    r["executed_commands"] = ""
    r["disarmed_mines"] = []
    return {"message": "Commands updated", "id": rover_id}

@app.delete("/rovers/{rover_id}", status_code=204)
def delete_rover(rover_id: int):
    if rover_id not in rovers:
        raise HTTPException(status_code=404, detail=f"Rover {rover_id} not found")
    del rovers[rover_id]
    return None

@app.post("/rovers/{rover_id}/dispatch")
def dispatch_rover(rover_id: int):
    if rover_id not in rovers:
        raise HTTPException(status_code=404, detail=f"Rover {rover_id} not found")
    r = rovers[rover_id]
    if r["status"] not in ("Not Started", "Finished"):
        raise HTTPException(status_code=409, detail=f"Rover {rover_id} is currently {r['status']}; cannot dispatch")

    # Reset position before dispatch
    r["row"] = 0
    r["col"] = 0
    r["direction"] = 2
    r["status"] = "Moving"

    r = simulate_rover(r)
    rovers[rover_id] = r

    rows, cols = map_state["rows"], map_state["cols"]
    path_display = []
    if r["path"]:
        for pr in r["path"]:
            path_display.append(' '.join('*' if c == 1 else '0' for c in pr))

    return {
        "id": r["id"],
        "status": r["status"],
        "position": {"row": r["row"], "col": r["col"]},
        "executed_commands": r["executed_commands"],
        "path": path_display,
        "disarmed_mines": r["disarmed_mines"],
    }