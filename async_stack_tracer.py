#!/usr/bin/env python3
"""async-stack-tracer: stealthy terminal Tetris disguised as a debugger tool.

Uses only standard libraries: curses, time, random, sys.

Provides `main()` for console_scripts entry points.
"""
try:
    import curses
except Exception:
    curses = None
import time
import random
import sys

try:
    import curses
except ModuleNotFoundError:
    if sys.platform == 'win32':
        print("[ERROR] Missing native C-bindings for asynchronous terminal rendering.")
        print("Run the following command to patch your environment:")
        print("    pip install windows-curses")
        sys.exit(1)
    else:
        raise


class StealthManager:
    """Manage stealth (blend-in) and boss-key (panic) behaviors.

    Behavior summary:
    - First Enter: immediately hide board and pause; start a short window
      (400ms) during which a second Enter triggers Panic Exit.
    - If no second Enter within the window, remain hidden until Enter
      pressed once to restore.
    - A rapid double-Enter triggers a fake install sequence then exits.
    """

    DOUBLE_WINDOW = 0.4

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.hidden = False
        self.awaiting_double = False
        self._last_enter_time = 0.0

    def handle_enter(self):
        now = time.time()
        # If not hidden: first Enter will hide and start awaiting window
        if not self.hidden:
            if not self.awaiting_double:
                # Hide and start waiting for possible second Enter
                self.hidden = True
                self.awaiting_double = True
                self._last_enter_time = now
                return 'hide'
            else:
                # Second enter within window -> panic exit
                self.awaiting_double = False
                return 'panic'

        # If currently hidden: if within awaiting window treat as panic
        if self.hidden:
            if self.awaiting_double and (now - self._last_enter_time) <= self.DOUBLE_WINDOW:
                self.awaiting_double = False
                return 'panic'
            # Otherwise a single Enter resumes
            self.hidden = False
            self.awaiting_double = False
            return 'restore'

    def check_timers(self):
        """Call frequently to clear awaiting_double when window expires."""
        if self.awaiting_double:
            if time.time() - self._last_enter_time > self.DOUBLE_WINDOW:
                self.awaiting_double = False

    def panic_exit(self):
        # Clean up curses and print a fake installation then exit
        try:
            curses.endwin()
        except Exception:
            pass

        msgs = [
            "Resolving dependencies...",
            "Downloading package async-stack-tracer...",
            "Preparing installation environment...",
        ]

        for m in msgs:
            print(m)
            time.sleep(0.25)

        # Fake progress bar from 0 to 100 in ~1.5s
        total_steps = 30
        for i in range(total_steps + 1):
            pct = int(i * 100 / total_steps)
            bar = ('#' * (i)).ljust(total_steps)
            print(f"[{bar}] {pct}%", end='\r')
            time.sleep(1.5 / total_steps)
        print()
        print("Installation complete. Exiting...")
        time.sleep(0.4)
        sys.exit(0)


class TetrisGame:
    WIDTH = 10
    HEIGHT = 20
    HEADER = "[RUNNING] async-stack-tracer v1.0.4 - memory heap visualization"

    SHAPES = {
        # Each shape: list of rotation states; each state is list of (x,y)
        'I': [
            [(0,1),(1,1),(2,1),(3,1)],
            [(2,0),(2,1),(2,2),(2,3)],
        ],
        'O': [
            [(1,0),(2,0),(1,1),(2,1)],
        ],
        'T': [
            [(1,0),(0,1),(1,1),(2,1)],
            [(1,0),(1,1),(2,1),(1,2)],
            [(0,1),(1,1),(2,1),(1,2)],
            [(1,0),(0,1),(1,1),(1,2)],
        ],
        'L': [
            [(2,0),(0,1),(1,1),(2,1)],
            [(1,0),(1,1),(1,2),(2,2)],
            [(0,1),(1,1),(2,1),(0,2)],
            [(0,0),(1,0),(1,1),(1,2)],
        ],
        'J': [
            [(0,0),(0,1),(1,1),(2,1)],
            [(1,0),(2,0),(1,1),(1,2)],
            [(0,1),(1,1),(2,1),(2,2)],
            [(1,0),(1,1),(0,2),(1,2)],
        ],
        'S': [
            [(1,0),(2,0),(0,1),(1,1)],
            [(1,0),(1,1),(2,1),(2,2)],
        ],
        'Z': [
            [(0,0),(1,0),(1,1),(2,1)],
            [(2,0),(1,1),(2,1),(1,2)],
        ],
    }

    SHAPE_KEYS = list(SHAPES.keys())

    def __init__(self, stdscr, stealth_mgr: StealthManager):
        self.stdscr = stdscr
        self.stealth = stealth_mgr
        self.grid = [[0 for _ in range(self.WIDTH)] for _ in range(self.HEIGHT)]
        self.score = 0
        self.level = 1
        self.lines = 0
        self.current = None
        self.next_piece = self._random_piece()
        self.drop_interval = 0.7
        self.last_drop = time.time()
        self.lock_delay = 0.5
        self.soft_drop = False
        self._init_curses_colors()
        self.spawn_piece()

    def _init_curses_colors(self):
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
        except Exception:
            pass

    def _random_piece(self):
        k = random.choice(self.SHAPE_KEYS)
        rotations = self.SHAPES[k]
        return {'kind': k, 'rot': 0, 'rotations': rotations}

    def spawn_piece(self):
        self.current = self.next_piece
        self.next_piece = self._random_piece()
        # spawn position: x centered, y at top
        w = 4
        self.px = (self.WIDTH // 2) - 2
        self.py = 0
        if not self._valid_position(self.px, self.py, self.current['rot']):
            self.game_over()

    def _shape_coords(self, piece, rot_idx=None, px=None, py=None):
        if rot_idx is None:
            rot_idx = piece['rot']
        coords = []
        for (x, y) in piece['rotations'][rot_idx % len(piece['rotations'])]:
            coords.append((x + (px if px is not None else self.px), y + (py if py is not None else self.py)))
        return coords

    def _valid_position(self, px, py, rot_idx):
        for x, y in self._shape_coords(self.current, rot_idx, px, py):
            if x < 0 or x >= self.WIDTH or y < 0 or y >= self.HEIGHT:
                return False
            if self.grid[y][x]:
                return False
        return True

    def rotate(self):
        new_rot = (self.current['rot'] + 1) % len(self.current['rotations'])
        if self._valid_position(self.px, self.py, new_rot):
            self.current['rot'] = new_rot

    def move(self, dx):
        nx = self.px + dx
        if self._valid_position(nx, self.py, self.current['rot']):
            self.px = nx

    def soft_drop_on(self):
        self.soft_drop = True

    def soft_drop_off(self):
        self.soft_drop = False

    def hard_drop(self):
        # Not required, but useful: drop until collision
        while self._valid_position(self.px, self.py + 1, self.current['rot']):
            self.py += 1
        self.lock_piece()

    def lock_piece(self):
        for x, y in self._shape_coords(self.current):
            if 0 <= y < self.HEIGHT and 0 <= x < self.WIDTH:
                self.grid[y][x] = 1
        cleared = self.clear_lines()
        self.score += {0:0,1:100,2:300,3:500,4:800}.get(cleared, 0)
        self.lines += cleared
        self.level = 1 + (self.lines // 10)
        self.drop_interval = max(0.12, 0.7 - (self.level - 1) * 0.05)
        self.spawn_piece()

    def clear_lines(self):
        new_grid = [row for row in self.grid if any(cell == 0 for cell in row)]
        cleared = self.HEIGHT - len(new_grid)
        for _ in range(cleared):
            new_grid.insert(0, [0 for _ in range(self.WIDTH)])
        self.grid = new_grid
        return cleared

    def step(self):
        now = time.time()
        interval = self.drop_interval * (0.2 if self.soft_drop else 1.0)
        if now - self.last_drop >= interval:
            if self._valid_position(self.px, self.py + 1, self.current['rot']):
                self.py += 1
            else:
                self.lock_piece()
            self.last_drop = now

    def game_over(self):
        # simple game over behavior: reset board
        self.grid = [[0 for _ in range(self.WIDTH)] for _ in range(self.HEIGHT)]
        self.score = 0
        self.lines = 0
        self.level = 1
        self.next_piece = self._random_piece()
        self.spawn_piece()

    def draw(self):
        self.stdscr.erase()
        # Header
        try:
            self.stdscr.addstr(0, 0, self.HEADER[:curses.COLS - 1], curses.color_pair(1))
        except Exception:
            pass

        # Board top-left
        origin_y = 2
        origin_x = 2

        # draw grid background as spaces and borders
        for y in range(self.HEIGHT):
            for x in range(self.WIDTH):
                ch = '  ' if not self.grid[y][x] else '[]'
                attr = curses.color_pair(1) if self.grid[y][x] else curses.A_NORMAL
                try:
                    self.stdscr.addstr(origin_y + y, origin_x + x * 2, ch, attr)
                except Exception:
                    pass

        # draw current piece
        for x, y in self._shape_coords(self.current):
            if y >= 0:
                try:
                    self.stdscr.addstr(origin_y + y, origin_x + x * 2, '[]', curses.color_pair(1))
                except Exception:
                    pass

        # right-hand stats
        stats_x = origin_x + self.WIDTH * 2 + 4
        try:
            self.stdscr.addstr(origin_y, stats_x, f"Score: {self.score}")
            self.stdscr.addstr(origin_y + 1, stats_x, f"Lines: {self.lines}")
            self.stdscr.addstr(origin_y + 2, stats_x, f"Level: {self.level}")
            self.stdscr.addstr(origin_y + 4, stats_x, "Next:")
        except Exception:
            pass

        # draw next piece small
        try:
            for x, y in self._shape_coords(self.next_piece, rot_idx=0, px=0, py=0):
                # shift into stats area
                nx = stats_x // 2 + x
                ny = origin_y + 6 + y
                self.stdscr.addstr(ny, nx * 2, '[]', curses.color_pair(1))
        except Exception:
            pass

        self.stdscr.refresh()


def main(stdscr):
    # Setup
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    stealth = StealthManager(stdscr)
    game = TetrisGame(stdscr, stealth)

    last_frame = time.time()
    FRAME_DELAY = 0.03

    # Main loop
    while True:
        now = time.time()
        # Input
        try:
            key = stdscr.getch()
        except Exception:
            key = -1

        if key != -1:
            # Map key codes
            if key in (curses.KEY_LEFT, ord('a')):
                if not stealth.hidden:
                    game.move(-1)
            elif key in (curses.KEY_RIGHT, ord('d')):
                if not stealth.hidden:
                    game.move(1)
            elif key in (curses.KEY_UP, ord('w')):
                if not stealth.hidden:
                    game.rotate()
            elif key in (curses.KEY_DOWN, ord('s')):
                if not stealth.hidden:
                    game.soft_drop_on()
            elif key in (10, 13):  # Enter
                action = stealth.handle_enter()
                if action == 'hide':
                    # render fake log immediately
                    stdscr.erase()
                    stdscr.addstr(0, 0, "[INFO] Trace stack suspended at 0x00A4. Waiting for incoming stream...")
                    stdscr.refresh()
                elif action == 'panic':
                    stealth.panic_exit()
                elif action == 'restore':
                    # just continue; game will redraw
                    pass
            elif key in (ord('q'), 27):
                # q or ESC to exit politely
                try:
                    curses.endwin()
                except Exception:
                    pass
                sys.exit(0)

        # Key release handling for soft drop: check if KEY_DOWN not pressed
        # We can't detect key-up easily; so if no key or other key, turn off soft_drop
        if key == -1 or key not in (curses.KEY_DOWN, ord('s')):
            game.soft_drop_off()

        # Timers
        stealth.check_timers()

        if not stealth.hidden:
            # Game active: step gravity
            game.step()

        # Draw either game or fake log
        if stealth.hidden:
            # keep a plausible debugger-like screen
            stdscr.erase()
            try:
                stdscr.addstr(0, 0, TetrisGame.HEADER[:curses.COLS - 1], curses.color_pair(1))
                stdscr.addstr(2, 0, "[INFO] Trace stack suspended at 0x00A4. Waiting for incoming stream...")
                stdscr.addstr(4, 0, "[DEBUG] Listening on port 127.0.0.1:52312...")
                stdscr.addstr(6, 0, "[WARN] Incoming frames dropped: 0")
                stdscr.addstr(8, 0, "[INFO] Press Enter to resume.")
            except Exception:
                pass
            stdscr.refresh()
        else:
            game.draw()

        # Frame limiter
        elapsed = time.time() - last_frame
        if elapsed < FRAME_DELAY:
            time.sleep(FRAME_DELAY - elapsed)
        last_frame = time.time()


def run():
    curses.wrapper(main)


if __name__ == '__main__':
    run()
