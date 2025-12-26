import torch

# Device detection
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Paths
MODEL_PATH = "digit_model.pth"
DATA_ROOT = "./data"

# UI Colors
BG_COLOR = "#0f172a"  # Deeper navy
ACCENT_COLOR = "#38bdf8"  # Sky blue
SECONDARY_BG = "#1e293b"  # Slate 800
TEXT_COLOR = "#f8fafc"
PRED_COLOR = "#22d3ee"
CONF_LOW = "#f87171"
CONF_MID = "#fbbf24"
CONF_HIGH = "#4ade80"
SIDEBAR_COLOR = "#111827"
CANVAS_BG = "#020617"

# Visualization Colors
ACTIVATION_COLORS = ["#0f172a", "#1e293b", "#334155", "#38bdf8", "#f8fafc"]

# Model Hyperparameters
BATCH_SIZE = 128
EPOCHS = 15
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-4
MAX_LR = 0.01
