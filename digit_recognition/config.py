import torch

# Device detection
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Paths
MODEL_PATH = "digit_model.pth"
DATA_ROOT = "./data"

# UI Colors
BG_COLOR = "#1a1a2e"
ACCENT_COLOR = "#e94560"
SECONDARY_BG = "#16213e"
TEXT_COLOR = "white"
PRED_COLOR = "#00d9ff"
CONF_LOW = "#ff4444"
CONF_MID = "#ffaa00"
CONF_HIGH = "#00ff88"

# Visualization Colors
ACTIVATION_COLORS = ["#0a0a1a", "#1a1a4e", "#2a4a8e", "#00d9ff", "#ffffff"]

# Model Hyperparameters
BATCH_SIZE = 128
EPOCHS = 15
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-4
MAX_LR = 0.01
