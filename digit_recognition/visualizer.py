import threading
import tkinter as tk

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.gridspec import GridSpec
from PIL import Image, ImageDraw

import config
from utils import load_model

# Set dark style for matplotlib
plt.style.use("dark_background")


class NeuralNetVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Neural Network Visualization - Draw Digits")
        self.root.configure(bg=config.BG_COLOR)

        # Load model
        self.model = load_model()

        # Throttle updates for performance
        self.update_pending = False

        # Create main frame with dark theme
        main_frame = tk.Frame(root, bg=config.BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left side - Drawing canvas
        left_frame = tk.Frame(main_frame, bg=config.BG_COLOR)
        left_frame.pack(side=tk.LEFT, padx=20, pady=20)

        title_label = tk.Label(
            left_frame,
            text="✏️ Draw a Digit (0-9)",
            font=("Segoe UI", 18, "bold"),
            bg=config.BG_COLOR,
            fg=config.ACCENT_COLOR,
        )
        title_label.pack(pady=(0, 15))

        # Canvas with border effect
        canvas_frame = tk.Frame(left_frame, bg=config.ACCENT_COLOR, padx=3, pady=3)
        canvas_frame.pack()

        self.canvas_size = 280
        self.canvas = tk.Canvas(
            canvas_frame,
            width=self.canvas_size,
            height=self.canvas_size,
            bg="#0f0f1a",
            highlightthickness=0,
            cursor="cross",
        )
        self.canvas.pack()

        # PIL Image for drawing
        self.image = Image.new("L", (self.canvas_size, self.canvas_size), "black")
        self.draw = ImageDraw.Draw(self.image)

        # Track last mouse position for smooth lines
        self.last_x = None
        self.last_y = None

        # Bind mouse events - drawing is immediate, prediction is throttled
        self.canvas.bind("<B1-Motion>", self.paint)
        self.canvas.bind("<Button-1>", self.paint_start)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # Buttons with modern styling
        btn_frame = tk.Frame(left_frame, bg=config.BG_COLOR)
        btn_frame.pack(pady=20)

        clear_btn = tk.Button(
            btn_frame,
            text="🗑️ Clear",
            command=self.clear_canvas,
            width=12,
            height=2,
            font=("Segoe UI", 11, "bold"),
            bg=config.SECONDARY_BG,
            fg="white",
            activebackground=config.ACCENT_COLOR,
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
        )
        clear_btn.pack(side=tk.LEFT, padx=10)

        # Prediction display with modern card design
        pred_frame = tk.Frame(left_frame, bg=config.SECONDARY_BG, padx=20, pady=15)
        pred_frame.pack(fill=tk.X, pady=10)

        self.pred_label = tk.Label(
            pred_frame,
            text="Draw to predict...",
            font=("Segoe UI", 20, "bold"),
            bg=config.SECONDARY_BG,
            fg=config.PRED_COLOR,
        )
        self.pred_label.pack()

        self.conf_label = tk.Label(
            pred_frame,
            text="",
            font=("Segoe UI", 12),
            bg=config.SECONDARY_BG,
            fg="#888",
        )
        self.conf_label.pack()

        # Right side - Visualization with dark theme
        right_frame = tk.Frame(main_frame, bg=config.BG_COLOR)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create matplotlib figure with dark theme
        self.fig = plt.figure(figsize=(14, 10), facecolor=config.BG_COLOR)
        self.gs = GridSpec(3, 4, figure=self.fig, hspace=0.4, wspace=0.3)

        # Embed in tkinter
        self.canvas_plot = FigureCanvasTkAgg(self.fig, right_frame)
        self.canvas_plot.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas_plot.get_tk_widget().configure(bg=config.BG_COLOR)

        # Pre-create all axes and artists for fast updates
        self._init_plot_axes()

        # Initial empty state
        self._show_empty_state()

    def _init_plot_axes(self):
        """Initialize all plot axes once - we'll just update data, not recreate"""
        # Custom colormap
        self.cmap_activation = mcolors.LinearSegmentedColormap.from_list(
            "activation", config.ACTIVATION_COLORS
        )

        # Create all axes
        self.ax_input = self.fig.add_subplot(self.gs[0, 0])
        self.ax_conv1 = self.fig.add_subplot(self.gs[0, 1:3])
        self.ax_conv2 = self.fig.add_subplot(self.gs[0, 3])
        self.ax_conv3 = self.fig.add_subplot(self.gs[1, 0])
        self.ax_fc1 = self.fig.add_subplot(self.gs[1, 1:3])
        self.ax_fc2 = self.fig.add_subplot(self.gs[1, 3])
        self.ax_probs = self.fig.add_subplot(self.gs[2, :])

        # Setup static properties for each axis
        for ax in [
            self.ax_input,
            self.ax_conv1,
            self.ax_conv2,
            self.ax_conv3,
            self.ax_fc1,
            self.ax_fc2,
        ]:
            ax.set_facecolor(config.BG_COLOR)
            ax.axis("off")

        # Titles
        self.ax_input.set_title(
            "Input (28×28)",
            fontsize=11,
            fontweight="bold",
            color=config.ACCENT_COLOR,
            pad=8,
        )
        self.ax_conv1.set_title(
            "Conv1 (16/32 filters)",
            fontsize=11,
            fontweight="bold",
            color=config.PRED_COLOR,
            pad=8,
        )
        self.ax_conv2.set_title(
            "Conv2 (16/64)",
            fontsize=11,
            fontweight="bold",
            color=config.PRED_COLOR,
            pad=8,
        )
        self.ax_conv3.set_title(
            "Conv3 (16/128)",
            fontsize=11,
            fontweight="bold",
            color=config.PRED_COLOR,
            pad=8,
        )
        self.ax_fc1.set_title(
            "FC1 (256→16×16)", fontsize=11, fontweight="bold", color="#ff6b6b", pad=8
        )
        self.ax_fc2.set_title(
            "FC2 (128→8×16)", fontsize=11, fontweight="bold", color="#ff6b6b", pad=8
        )

        # Create image artists with placeholder data
        self.im_input = self.ax_input.imshow(
            np.zeros((28, 28)), cmap="gray", interpolation="nearest", vmin=0, vmax=1
        )
        self.im_conv1 = self.ax_conv1.imshow(
            np.zeros((56, 56)), cmap=self.cmap_activation, interpolation="nearest"
        )
        self.im_conv2 = self.ax_conv2.imshow(
            np.zeros((28, 28)), cmap=self.cmap_activation, interpolation="nearest"
        )
        self.im_conv3 = self.ax_conv3.imshow(
            np.zeros((28, 28)), cmap=self.cmap_activation, interpolation="nearest"
        )
        self.im_fc1 = self.ax_fc1.imshow(
            np.zeros((16, 16)),
            cmap=self.cmap_activation,
            aspect="auto",
            interpolation="nearest",
        )
        self.im_fc2 = self.im_fc2 = self.ax_fc2.imshow(
            np.zeros((8, 16)),
            cmap=self.cmap_activation,
            aspect="auto",
            interpolation="nearest",
        )

        # Setup probability bar chart
        self.ax_probs.set_facecolor(config.BG_COLOR)
        self.bars = self.ax_probs.bar(
            range(10),
            [0] * 10,
            color=config.SECONDARY_BG,
            edgecolor="#2a4a8e",
            linewidth=2,
            alpha=0.9,
        )
        self.bar_texts = []
        for i in range(10):
            txt = self.ax_probs.text(
                i,
                0.02,
                "",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
                color="#888",
            )
            self.bar_texts.append(txt)

        self.ax_probs.set_title(
            "🎯 Output Probabilities",
            fontsize=14,
            fontweight="bold",
            color=config.ACCENT_COLOR,
            pad=15,
        )
        self.ax_probs.set_xlabel("Digit Class", fontsize=11, color="#888")
        self.ax_probs.set_ylabel("Probability", fontsize=11, color="#888")
        self.ax_probs.set_xticks(range(10))
        self.ax_probs.set_xticklabels(
            [str(i) for i in range(10)], fontsize=12, fontweight="bold", color="white"
        )
        self.ax_probs.set_ylim(0, 1.15)
        self.ax_probs.tick_params(colors="#888")
        self.ax_probs.spines["bottom"].set_color("#333")
        self.ax_probs.spines["left"].set_color("#333")
        self.ax_probs.spines["top"].set_visible(False)
        self.ax_probs.spines["right"].set_visible(False)
        self.ax_probs.yaxis.grid(True, linestyle="--", alpha=0.3, color="#444")
        self.ax_probs.set_axisbelow(True)

        self.fig.patch.set_facecolor(config.BG_COLOR)
        self.fig.tight_layout(pad=2.0)
        self.canvas_plot.draw()

        # Cache background for blitting
        self.bg_cache = None

    def _cache_background(self):
        """Cache the static background for blitting"""
        self.canvas_plot.draw()
        self.bg_cache = self.canvas_plot.copy_from_bbox(self.fig.bbox)

    def _show_empty_state(self):
        """Show placeholder state"""
        self.im_input.set_data(np.zeros((28, 28)))
        self.im_conv1.set_data(np.zeros((56, 56)))
        self.im_conv2.set_data(np.zeros((28, 28)))
        self.im_conv3.set_data(np.zeros((28, 28)))
        self.im_fc1.set_data(np.zeros((16, 16)))
        self.im_fc2.set_data(np.zeros((8, 16)))
        for bar, txt in zip(self.bars, self.bar_texts):
            bar.set_height(0)
            bar.set_color(config.SECONDARY_BG)
            bar.set_edgecolor("#2a4a8e")
            txt.set_text("")
        self.ax_probs.set_title(
            "🎯 Output Probabilities",
            fontsize=14,
            fontweight="bold",
            color=config.ACCENT_COLOR,
            pad=15,
        )
        self.canvas_plot.draw()
        self.bg_cache = None  # Reset cache

    def paint_start(self, event):
        """Handle mouse button press - start of a stroke"""
        self.last_x = event.x
        self.last_y = event.y
        r = 14
        # Draw initial dot
        self.canvas.create_oval(
            event.x - r,
            event.y - r,
            event.x + r,
            event.y + r,
            fill="#ffffff",
            outline="",
            width=0,
        )
        self.draw.ellipse(
            [event.x - r, event.y - r, event.x + r, event.y + r], fill="white"
        )

        # Schedule prediction
        if not self.update_pending:
            self.update_pending = True
            self.root.after_idle(self._schedule_update)

    def paint(self, event):
        x, y = event.x, event.y
        r = 14  # brush size

        # Draw a line from last position to current for smooth strokes
        if self.last_x is not None and self.last_y is not None:
            # Draw line on canvas
            self.canvas.create_line(
                self.last_x,
                self.last_y,
                x,
                y,
                fill="#ffffff",
                width=r * 2,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
            )
            # Draw line on PIL image
            self.draw.line([self.last_x, self.last_y, x, y], fill="white", width=r * 2)

        # Update last position
        self.last_x = x
        self.last_y = y

        # Schedule prediction update with throttle (doesn't block drawing)
        if not self.update_pending:
            self.update_pending = True
            self.root.after_idle(self._schedule_update)

    def _schedule_update(self):
        # Use after to delay the heavy computation
        self.root.after(300, self.do_update)  # 200ms delay - updates ~5 times/sec

    def do_update(self):
        self.update_pending = False
        # Run inference in a separate thread to not block UI at all
        threading.Thread(target=self._run_inference, daemon=True).start()

    def on_release(self, event=None):
        # Reset last position for next stroke
        self.last_x = None
        self.last_y = None
        # Force immediate update when mouse is released
        self.update_pending = False
        self._run_inference()

    def clear_canvas(self):
        self.canvas.delete("all")
        self.image = Image.new("L", (self.canvas_size, self.canvas_size), "black")
        self.draw = ImageDraw.Draw(self.image)
        self.last_x = None
        self.last_y = None
        self.pred_label.config(text="Draw to predict...")
        self.conf_label.config(text="")
        self._show_empty_state()

    def preprocess_image(self):
        # Resize to 28x28
        img = self.image.resize((28, 28), Image.Resampling.LANCZOS)
        img_array = np.array(img).astype("float32") / 255.0

        # Convert to tensor and normalize (same as training)
        img_tensor = torch.from_numpy(img_array).unsqueeze(0).unsqueeze(0)
        img_tensor = (img_tensor - 0.1307) / 0.3081
        return img_tensor, img_array

    def _run_inference(self):
        """Run inference - can be called from thread"""
        img_tensor, img_array = self.preprocess_image()

        with torch.no_grad():
            output, activations = self.model(img_tensor)
            probs = F.softmax(output, dim=1)
            pred = int(torch.argmax(probs, dim=1).item())
            confidence = probs[0][pred].item() * 100

        # Prepare data for visualization
        viz_data = {
            "img": img_array,
            "conv1": activations["conv1"].numpy()[0],
            "conv2": activations["conv2"].numpy()[0],
            "conv3": activations["conv3"].numpy()[0],
            "fc1": activations["fc1"].numpy()[0],
            "fc2": activations["fc2"].numpy()[0],
            "probs": probs.numpy()[0],
            "pred": pred,
            "confidence": confidence,
        }

        # Schedule UI update on main thread
        self.root.after_idle(lambda: self._update_ui(viz_data))

    def _update_ui(self, viz_data):
        """Update UI elements - must run on main thread"""
        pred = viz_data["pred"]
        confidence = viz_data["confidence"]

        # Update prediction labels
        self.pred_label.config(text=f"Prediction: {pred}")

        # Color code confidence
        if confidence >= 80:
            conf_color = config.CONF_HIGH
        elif confidence >= 50:
            conf_color = config.CONF_MID
        else:
            conf_color = config.CONF_LOW
        self.conf_label.config(text=f"Confidence: {confidence:.1f}%", fg=conf_color)

        # Update visualization
        self.update_visualization(viz_data)

    def create_activation_grid(self, activations, num_show=16):
        """Create a grid image from conv layer activations"""
        n_filters = min(num_show, activations.shape[0])
        grid_size = int(np.ceil(np.sqrt(n_filters)))
        h, w = activations.shape[1], activations.shape[2]

        grid = np.zeros((grid_size * h, grid_size * w))

        for i in range(n_filters):
            row = i // grid_size
            col = i % grid_size
            grid[row * h : (row + 1) * h, col * w : (col + 1) * w] = activations[i]

        return grid

    def update_visualization(self, data):
        """Fast update - only change data, don't recreate plots"""
        if data is None:
            self._show_empty_state()
            return

        # Update images with new data (very fast - no redraw of axes)
        self.im_input.set_data(data["img"])

        conv1_grid = self.create_activation_grid(data["conv1"], num_show=16)
        self.im_conv1.set_data(conv1_grid)
        self.im_conv1.set_clim(conv1_grid.min(), conv1_grid.max())

        conv2_grid = self.create_activation_grid(data["conv2"], num_show=16)
        self.im_conv2.set_data(conv2_grid)
        self.im_conv2.set_clim(conv2_grid.min(), conv2_grid.max())

        conv3_grid = self.create_activation_grid(data["conv3"], num_show=16)
        self.im_conv3.set_data(conv3_grid)
        self.im_conv3.set_clim(conv3_grid.min(), conv3_grid.max())

        fc1_reshaped = data["fc1"].reshape(16, 16)
        self.im_fc1.set_data(fc1_reshaped)
        self.im_fc1.set_clim(fc1_reshaped.min(), fc1_reshaped.max())

        fc2_reshaped = data["fc2"].reshape(8, 16)
        self.im_fc2.set_data(fc2_reshaped)
        self.im_fc2.set_clim(fc2_reshaped.min(), fc2_reshaped.max())

        # Update bar chart
        probs = data["probs"]
        pred = data["pred"]

        for i, (bar, txt, p) in enumerate(zip(self.bars, self.bar_texts, probs)):
            bar.set_height(p)
            if i == pred:
                bar.set_color(config.ACCENT_COLOR)
                bar.set_edgecolor("#ff6b6b")
            else:
                bar.set_color(config.SECONDARY_BG)
                bar.set_edgecolor("#2a4a8e")

            if p > 0.01:
                txt.set_text(f"{p * 100:.0f}%")
                txt.set_y(p + 0.02)
                txt.set_color("white" if i == pred else "#888")
            else:
                txt.set_text("")

        self.ax_probs.set_title(
            f"🎯 Output Probabilities — Predicted: {pred}",
            fontsize=14,
            fontweight="bold",
            color=config.ACCENT_COLOR,
            pad=15,
        )

        # Fast redraw
        self.canvas_plot.draw_idle()
