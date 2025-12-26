from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Circle
from matplotlib.widgets import Button, RadioButtons, Slider
from scipy.integrate import odeint


class DoublePendulum:
    def __init__(
        self,
        m1: float,
        m2: float,
        L1: float,
        L2: float,
        theta1: float,
        theta2: float,
        color_line: str,
        color_sphere: str,
        trace: bool,
        max_trail: int,
    ) -> None:
        """
        Initialize a double pendulum

        :param m1: mass of first bob
        :type m1: float
        :param m2: mass of second bob
        :type m2: float
        :param L1: length of first rod
        :type L1: float
        :param L2: length of second rod
        :type L2: float
        :param theta1: initial angle of first rod (degrees)
        :type theta1: float
        :param theta2: initial angle of second rod (degrees)
        :type theta2: float
        :param color_line: color of rods
        :type color_line: str
        :param color_sphere: color of bobs
        :type color_sphere: str
        :param trace: show motion trail
        :type trace: bool
        :param max_trail: number of trail points
        :type max_trail: int
        """
        self.m1 = m1
        self.m2 = m2
        self.L1 = L1
        self.L2 = L2
        self.g = 9.81

        # Convert angles to radians
        self.theta1 = np.radians(theta1)
        self.theta2 = np.radians(theta2)
        self.initial_theta1 = self.theta1
        self.initial_theta2 = self.theta2
        self.omega1 = 0.0
        self.omega2 = 0.0

        self.color_line = color_line
        self.color_sphere = color_sphere
        self.trace = trace
        self.max_trail = max_trail

        # Trail storage
        self.trail_x = []
        self.trail_y = []

        # Current positions
        self.x1 = 0
        self.y1 = 0
        self.x2 = 0
        self.y2 = 0
        self._calculate_positions()

    def _calculate_positions(self) -> None:
        """Calculate Cartesian positions from angles"""
        self.x1 = self.L1 * np.sin(self.theta1)
        self.y1 = -self.L1 * np.cos(self.theta1)
        self.x2 = self.x1 + self.L2 * np.sin(self.theta2)
        self.y2 = self.y1 - self.L2 * np.cos(self.theta2)

    def reset(self) -> None:
        """Reset pendulum to initial state"""
        self.theta1 = self.initial_theta1
        self.theta2 = self.initial_theta2
        self.omega1 = 0.0
        self.omega2 = 0.0
        self.trail_x = []
        self.trail_y = []
        self._calculate_positions()

    def derivatives(
        self, state: list[float], t: float
    ) -> tuple[float, float, float, float]:
        """
        Calculate derivatives for the equations of motion

        :param state: current state [theta1, omega1, theta2, omega2]
        :type state: list[float]
        :param t: current time
        :type t: float
        :return: derivatives [dtheta1, domega1, dtheta2, domega2]
        :rtype: tuple[float, float, float, float]
        """
        theta1, omega1, theta2, omega2 = state

        delta = theta2 - theta1
        den1 = (self.m1 + self.m2) * self.L1 - self.m2 * self.L1 * np.cos(
            delta
        ) * np.cos(delta)
        den2 = (self.L2 / self.L1) * den1

        # Derivatives
        dtheta1 = omega1
        dtheta2 = omega2

        domega1 = (
            self.m2 * self.L1 * omega1 * omega1 * np.sin(delta) * np.cos(delta)
            + self.m2 * self.g * np.sin(theta2) * np.cos(delta)
            + self.m2 * self.L2 * omega2 * omega2 * np.sin(delta)
            - (self.m1 + self.m2) * self.g * np.sin(theta1)
        ) / den1

        domega2 = (
            -self.m2 * self.L2 * omega2 * omega2 * np.sin(delta) * np.cos(delta)
            + (self.m1 + self.m2) * self.g * np.sin(theta1) * np.cos(delta)
            - (self.m1 + self.m2) * self.L1 * omega1 * omega1 * np.sin(delta)
            - (self.m1 + self.m2) * self.g * np.sin(theta2)
        ) / den2

        return dtheta1, domega1, dtheta2, domega2

    def update(self, dt: float) -> None:
        """
        Update pendulum state using numerical integration

        :param dt: time step
        :type dt: float
        """
        state = [self.theta1, self.omega1, self.theta2, self.omega2]
        t = np.array([0, dt])
        solution = odeint(self.derivatives, state, t)

        self.theta1, self.omega1, self.theta2, self.omega2 = solution[1]

        # Calculate positions
        self._calculate_positions()

        # Update trail
        if self.trace:
            self.trail_x.append(self.x2)
            self.trail_y.append(self.y2)
            if len(self.trail_x) > self.max_trail:
                self.trail_x.pop(0)
                self.trail_y.pop(0)


class DoublePendulumSimulation:
    def __init__(self, pendulums: list[DoublePendulum], dt: float) -> None:
        """
        Create a simulation with multiple pendulums

        :param pendulums: list of DoublePendulum objects
        :type pendulums: list[DoublePendulum]
        :param dt: time step for integration
        :type dt: float
        """
        self.pendulums = pendulums
        self.dt = dt
        self.paused = False
        self.active_idx = 0
        self.ani = None

        # Setup figure
        plt.style.use("dark_background")
        self.fig, self.ax = plt.subplots(figsize=(12, 8))
        self.fig.patch.set_facecolor("#121212")
        plt.subplots_adjust(left=0.35, bottom=0.1)
        self.ax.set_xlim(-4, 4)
        self.ax.set_ylim(-4, 4)
        self.ax.set_aspect("equal")
        self.ax.set_facecolor("#1e1e1e")
        self.ax.grid(True, alpha=0.2, color="gray")
        self.ax.set_title("Double Pendulum Simulation", fontsize=14, pad=20)

        # Create plot elements for each pendulum
        self.lines = []
        self.circles1 = []
        self.circles2 = []
        self.trails = []

        for p in self.pendulums:
            self._add_pendulum_artists(p)

        self._setup_widgets()

    def _add_pendulum_artists(self, p: DoublePendulum) -> None:
        # Pendulum rods
        (line,) = self.ax.plot(
            [], [], "o-", lw=2, color=p.color_line, markersize=0, zorder=3
        )
        self.lines.append(line)

        # Bobs
        circle1 = Circle((0, 0), 0.08, color=p.color_sphere, zorder=4)
        circle2 = Circle((0, 0), 0.08, color=p.color_sphere, zorder=4)
        self.ax.add_patch(circle1)
        self.ax.add_patch(circle2)
        self.circles1.append(circle1)
        self.circles2.append(circle2)

        # Trail
        (trail,) = self.ax.plot(
            [], [], "-", lw=1, alpha=0.6, color=p.color_sphere, zorder=1
        )
        self.trails.append(trail)

    def _setup_widgets(self) -> None:
        # Colors
        accent_color = "#007acc"
        bg_color = "#252526"
        hover_color = "#3e3e42"
        text_color = "white"

        # Control Buttons
        ax_pause = plt.axes([0.05, 0.85, 0.1, 0.04])
        self.btn_pause = Button(
            ax_pause, "Pause", color=bg_color, hovercolor=hover_color
        )
        self.btn_pause.label.set_color(text_color)
        self.btn_pause.on_clicked(self.toggle_pause)

        ax_restart = plt.axes([0.16, 0.85, 0.1, 0.04])
        self.btn_restart = Button(
            ax_restart, "Restart", color=bg_color, hovercolor=hover_color
        )
        self.btn_restart.label.set_color(text_color)
        self.btn_restart.on_clicked(self.restart_sim)

        ax_add = plt.axes([0.05, 0.80, 0.1, 0.04])
        self.btn_add = Button(ax_add, "Add", color=bg_color, hovercolor=hover_color)
        self.btn_add.label.set_color(text_color)
        self.btn_add.on_clicked(self.add_pendulum)

        ax_remove = plt.axes([0.16, 0.80, 0.1, 0.04])
        self.btn_remove = Button(
            ax_remove, "Remove", color=bg_color, hovercolor=hover_color
        )
        self.btn_remove.label.set_color(text_color)
        self.btn_remove.on_clicked(self.remove_pendulum)

        # Pendulum Selector
        ax_selector = plt.axes([0.05, 0.70, 0.2, 0.03])
        self.slider_selector = Slider(
            ax_selector,
            "Select #",
            0,
            max(0, len(self.pendulums) - 1),
            valinit=0,
            valstep=1,
            color=accent_color,
            track_color=bg_color,
        )
        self.slider_selector.label.set_color(text_color)

        self.slider_selector.on_changed(self.change_active_pendulum)

        # Parameters Sliders
        p = self.pendulums[self.active_idx]

        ax_l1 = plt.axes([0.1, 0.60, 0.15, 0.03])
        self.slider_l1 = Slider(
            ax_l1,
            "L1",
            0.1,
            2.0,
            valinit=p.L1,
            color=accent_color,
            track_color=bg_color,
        )
        self.slider_l1.label.set_color(text_color)
        self.slider_l1.on_changed(self.update_params)

        ax_l2 = plt.axes([0.1, 0.55, 0.15, 0.03])
        self.slider_l2 = Slider(
            ax_l2,
            "L2",
            0.1,
            2.0,
            valinit=p.L2,
            color=accent_color,
            track_color=bg_color,
        )
        self.slider_l2.label.set_color(text_color)
        self.slider_l2.on_changed(self.update_params)

        ax_m1 = plt.axes([0.1, 0.50, 0.15, 0.03])
        self.slider_m1 = Slider(
            ax_m1,
            "m1",
            0.1,
            5.0,
            valinit=p.m1,
            color=accent_color,
            track_color=bg_color,
        )
        self.slider_m1.label.set_color(text_color)
        self.slider_m1.on_changed(self.update_params)

        ax_m2 = plt.axes([0.1, 0.45, 0.15, 0.03])
        self.slider_m2 = Slider(
            ax_m2,
            "m2",
            0.1,
            5.0,
            valinit=p.m2,
            color=accent_color,
            track_color=bg_color,
        )
        self.slider_m2.label.set_color(text_color)
        self.slider_m2.on_changed(self.update_params)

        # Color Selector
        ax_color = plt.axes([0.05, 0.25, 0.2, 0.15], facecolor=bg_color)
        self.radio_color = RadioButtons(
            ax_color,
            ("royalblue", "crimson", "forestgreen", "orange", "purple"),
            activecolor=accent_color,
        )
        for label in self.radio_color.labels:
            label.set_color(text_color)
        self.radio_color.on_clicked(self.change_color)

    def toggle_pause(self, event) -> None:
        self.paused = not self.paused
        self.btn_pause.label.set_text("Resume" if self.paused else "Pause")
        self.fig.canvas.draw_idle()

    def restart_sim(self, event) -> None:
        for p in self.pendulums:
            p.reset()

    def add_pendulum(self, event) -> None:
        p_active = self.pendulums[self.active_idx]
        new_p = DoublePendulum(
            m1=p_active.m1,
            m2=p_active.m2,
            L1=p_active.L1,
            L2=p_active.L2,
            theta1=np.degrees(p_active.theta1) + np.random.uniform(-0.1, 0.1),
            theta2=np.degrees(p_active.theta2),
            color_line=p_active.color_line,
            color_sphere=p_active.color_sphere,
            trace=True,
            max_trail=400,
        )
        self.pendulums.append(new_p)
        self._add_pendulum_artists(new_p)
        self.slider_selector.valmax = len(self.pendulums) - 1
        self.slider_selector.ax.set_xlim(0, self.slider_selector.valmax)
        self.fig.canvas.draw_idle()

    def remove_pendulum(self, event) -> None:
        if len(self.pendulums) > 1:
            idx = int(self.slider_selector.val)
            self.pendulums.pop(idx)
            self.lines.pop(idx).remove()
            self.circles1.pop(idx).remove()
            self.circles2.pop(idx).remove()
            self.trails.pop(idx).remove()

            self.active_idx = min(idx, len(self.pendulums) - 1)
            self.slider_selector.valmax = len(self.pendulums) - 1
            self.slider_selector.ax.set_xlim(0, self.slider_selector.valmax)
            self.slider_selector.set_val(self.active_idx)
            self.fig.canvas.draw_idle()

    def change_active_pendulum(self, val) -> None:
        self.active_idx = int(val)
        p = self.pendulums[self.active_idx]
        # Update sliders to match active pendulum without triggering update_params
        self.slider_l1.eventson = False
        self.slider_l1.set_val(p.L1)
        self.slider_l1.eventson = True

        self.slider_l2.eventson = False
        self.slider_l2.set_val(p.L2)
        self.slider_l2.eventson = True

        self.slider_m1.eventson = False
        self.slider_m1.set_val(p.m1)
        self.slider_m1.eventson = True

        self.slider_m2.eventson = False
        self.slider_m2.set_val(p.m2)
        self.slider_m2.eventson = True

    def update_params(self, val) -> None:
        p = self.pendulums[self.active_idx]
        p.L1 = self.slider_l1.val
        p.L2 = self.slider_l2.val
        p.m1 = self.slider_m1.val
        p.m2 = self.slider_m2.val
        p._calculate_positions()

    def change_color(self, label) -> None:
        p = self.pendulums[self.active_idx]
        p.color_line = label
        p.color_sphere = label
        self.lines[self.active_idx].set_color(label)
        self.circles1[self.active_idx].set_color(label)
        self.circles2[self.active_idx].set_color(label)
        self.trails[self.active_idx].set_color(label)

    def init(self) -> list:
        """
        Initialize animation

        :return: list of matplotlib artists
        :rtype: list
        """
        for line in self.lines:
            line.set_data([], [])
        for trail in self.trails:
            trail.set_data([], [])
        return self.lines + self.trails + self.circles1 + self.circles2

    def animate(self, frame: int) -> list:
        """
        Update animation frame

        :param frame: current frame number
        :type frame: int
        :return: list of matplotlib artists
        :rtype: list
        """
        for i, p in enumerate(self.pendulums):
            if not self.paused:
                # Update physics
                p.update(self.dt)
            else:
                # Even if paused, ensure positions are correct if params changed
                p._calculate_positions()

            # Update pendulum rods
            self.lines[i].set_data([0, p.x1, p.x2], [0, p.y1, p.y2])

            # Update bobs
            self.circles1[i].center = (p.x1, p.y1)
            self.circles2[i].center = (p.x2, p.y2)

            # Update trail
            if p.trace and len(p.trail_x) > 1:
                self.trails[i].set_data(p.trail_x, p.trail_y)

        return self.lines + self.trails + self.circles1 + self.circles2

    def run(self, frames: int, interval: int) -> None:
        """
        Run the simulation

        :param frames: number of frames to animate
        :type frames: int
        :param interval: delay between frames in milliseconds
        :type interval: int
        """
        self.ani = FuncAnimation(
            self.fig,
            self.animate,
            init_func=self.init,
            frames=frames,
            interval=interval,
            blit=False,
            cache_frame_data=False,
        )
        plt.show()


# Example usage: Create multiple pendulums with different colors and settings
if __name__ == "__main__":
    pendulums = [
        DoublePendulum(
            m1=1.0,
            m2=1.0,
            L1=1.0,
            L2=1.0,
            theta1=120,
            theta2=-10,
            color_line="royalblue",
            color_sphere="darkblue",
            trace=True,
            max_trail=400,
        ),
        DoublePendulum(
            m1=1.0,
            m2=1.0,
            L1=1.0,
            L2=1.0,
            theta1=120.1,
            theta2=-10,
            color_line="crimson",
            color_sphere="darkred",
            trace=True,
            max_trail=400,
        ),
    ]

    # Create and run simulation
    sim = DoublePendulumSimulation(pendulums, dt=0.02)
    sim.run(frames=3000, interval=20)
