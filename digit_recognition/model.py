import torch.nn as nn
import torch.nn.functional as F


class DigitNet(nn.Module):
    def __init__(self):
        super(DigitNet, self).__init__()
        # Convolutional layers
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(64)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(128)
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.25)

        # Fully connected layers
        self.fc1 = nn.Linear(128 * 3 * 3, 256)
        self.fc_bn = nn.BatchNorm1d(256)
        self.fc2 = nn.Linear(256, 128)
        self.fc3 = nn.Linear(128, 10)
        self.dropout_fc = nn.Dropout(0.5)

    def forward(self, x):
        # Ensure input is 4D: (batch, channel, height, width)
        if x.dim() == 3:
            x = x.unsqueeze(1)
        elif x.dim() == 2:
            x = x.view(-1, 1, 28, 28)

        # Conv block 1: 28x28 -> 14x14
        c1 = F.relu(self.bn1(self.conv1(x)))
        p1 = self.pool(c1)
        p1 = self.dropout(p1)

        # Conv block 2: 14x14 -> 7x7
        c2 = F.relu(self.bn2(self.conv2(p1)))
        p2 = self.pool(c2)
        p2 = self.dropout(p2)

        # Conv block 3: 7x7 -> 3x3
        c3 = F.relu(self.bn3(self.conv3(p2)))
        p3 = self.pool(c3)
        p3 = self.dropout(p3)

        # Flatten
        flat = p3.view(-1, 128 * 3 * 3)

        # FC layers
        x1 = F.relu(self.fc_bn(self.fc1(flat)))
        x1 = self.dropout_fc(x1)
        x2 = F.relu(self.fc2(x1))
        x3 = self.fc3(x2)

        # Return all activations for visualization
        return x3, {"conv1": c1, "conv2": c2, "conv3": c3, "fc1": x1, "fc2": x2}
