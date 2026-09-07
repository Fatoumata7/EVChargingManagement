"""
visualizer.py — Real-time pygame visualizer of the simulation.
"""

import pygame
import numpy as np

COLORS = {
    'DRIVING':            (55, 138, 221),   # blue
    'DRIVING_TO_STATION': (239, 159, 39),   # orange
    'CHARGING':           (99, 153, 34),    # olive green
    'WAITING':            (136, 135, 128),  # grey
    'BREAKDOWN':          (220, 53, 69),    # red
    'AT_STATION':         (212, 83, 126),   # pink / magenta
    'PARKED_SEARCHING':   (146, 109, 222),  # purple — parked, searching further
    'PARKED_NO_SHOW':     (120, 118, 112),  # dark grey — parked, will not show up
}

STATION_COLOR = (216, 90, 48)


class Visualizer:
    def __init__(self, config, W=800, H=800):
        pygame.init()

        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("EV Charging Simulation")

        self.W, self.H = W, H
        self.config = config

        self.font = pygame.font.SysFont(None, 16)
        self.clock = pygame.time.Clock()

        # =========================
        # Padding around the grid
        # =========================
        self.padding = 40

        # Area actually used by the simulation
        self.grid_w = self.W - 2 * self.padding
        self.grid_h = self.H - 2 * self.padding

    # =========================
    # Transform world coordinates -> screen
    # =========================
    def _tx(self, x):
        return int(
            self.padding +
            (x / self.config.C_GRID) * self.grid_w
        )

    def _ty(self, y):
        return int(
            self.padding +
            (y / self.config.C_GRID) * self.grid_h
        )

    # =========================
    # Dashed line drawing
    # =========================
    def _draw_dashed_line(
        self,
        surface,
        color,
        start_pos,
        end_pos,
        dash_length=6,
        width=1
    ):
        x1, y1 = start_pos
        x2, y2 = end_pos

        dx = x2 - x1
        dy = y2 - y1

        dist = np.hypot(dx, dy)

        if dist == 0:
            return

        for i in np.arange(0, dist, dash_length * 2):
            start_x = x1 + dx * (i / dist)
            start_y = y1 + dy * (i / dist)

            end_i = min(i + dash_length, dist)

            end_x = x1 + dx * (end_i / dist)
            end_y = y1 + dy * (end_i / dist)

            pygame.draw.line(
                surface,
                color,
                (start_x, start_y),
                (end_x, end_y),
                width
            )

    def draw(self, cars, stations, slot):

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return False

        self.screen.fill((245, 244, 240))

        # =========================
        # Grid with padding
        # =========================
        grid_color = (200, 198, 192)

        for i in range(11):

            x = self.padding + i * self.grid_w // 10
            y = self.padding + i * self.grid_h // 10

            pygame.draw.line(
                self.screen,
                grid_color,
                (x, self.padding),
                (x, self.H - self.padding),
                1
            )

            pygame.draw.line(
                self.screen,
                grid_color,
                (self.padding, y),
                (self.W - self.padding, y),
                1
            )

        # Outer border
        pygame.draw.rect(
            self.screen,
            (170, 168, 160),
            (
                self.padding,
                self.padding,
                self.grid_w,
                self.grid_h
            ),
            2
        )

        # =========================
        # Stations
        # =========================
        for s in stations:

            x, y = self._tx(s.loc[0]), self._ty(s.loc[1])

            pygame.draw.rect(
                self.screen,
                STATION_COLOR,
                (x - 10, y - 10, 20, 20),
                border_radius=3
            )

            lbl = self.font.render(
                str(s.m),
                True,
                (250, 236, 231)
            )

            self.screen.blit(lbl, (x - 4, y - 6))

        # =========================
        # Vehicles
        # =========================
        for car in cars:

            x, y = self._tx(car.x), self._ty(car.y)

            col = COLORS.get(car.state, COLORS['DRIVING'])

            # ======================================
            # Dashed trajectory
            # ======================================
            # Assumes that:
            # car.prev_x and car.prev_y exist
            # ======================================

            if hasattr(car, "prev_x") and hasattr(car, "prev_y"):

                px = self._tx(car.prev_x)
                py = self._ty(car.prev_y)

                self._draw_dashed_line(
                    self.screen,
                    col,
                    (px, py),
                    (x, y),
                    dash_length=5,
                    width=1
                )

            # Vehicle
            pygame.draw.circle(
                self.screen,
                col,
                (x, y),
                5
            )

            # =========================
            # SoC bar
            # =========================
            pygame.draw.rect(
                self.screen,
                (180, 178, 170),
                (x - 6, y + 7, 12, 3)
            )

            car_soc = car.soc_m / car.autonomy

            soc_w = int(12 * car_soc)

            soc_col = (
                (226, 75, 74)
                if car_soc < 0.2 else
                (239, 159, 39)
                if car_soc < 0.5 else
                (99, 153, 34)
            )

            pygame.draw.rect(
                self.screen,
                soc_col,
                (x - 6, y + 7, soc_w, 3)
            )

        # =========================
        # HUD
        # =========================
        hud = self.font.render(
            f"Slot {slot} | "
            f"{sum(1 for c in cars if c.state == 'CHARGING')} charging",
            True,
            (80, 79, 76)
        )

        self.screen.blit(hud, (8, 8))

        pygame.display.flip()

        self.clock.tick(30)

        return True