import os

import torch
import torch.nn as nn
import torchvision.transforms as transforms
from torch.utils.data import DataLoader
from torchvision import datasets

import config
from model import DigitNet


def load_model():
    model = DigitNet()

    if not os.path.exists(config.MODEL_PATH):
        print(f"No trained model found. Training CNN on MNIST using {config.DEVICE}...")
        model = model.to(config.DEVICE)

        # Data augmentation for better generalization
        train_transform = transforms.Compose(
            [
                transforms.RandomRotation(10),
                transforms.RandomAffine(
                    degrees=0, translate=(0.1, 0.1), scale=(0.9, 1.1)
                ),
                transforms.ToTensor(),
                transforms.Normalize((0.1307,), (0.3081,)),
            ]
        )

        train_dataset = datasets.MNIST(
            root=config.DATA_ROOT,
            train=True,
            download=True,
            transform=train_transform,
        )
        train_loader = DataLoader(
            train_dataset, batch_size=config.BATCH_SIZE, shuffle=True
        )

        # Test dataset for validation
        test_transform = transforms.Compose(
            [transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))]
        )
        test_dataset = datasets.MNIST(
            root=config.DATA_ROOT,
            train=False,
            download=True,
            transform=test_transform,
        )
        test_loader = DataLoader(test_dataset, batch_size=1000, shuffle=False)

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.LEARNING_RATE,
            weight_decay=config.WEIGHT_DECAY,
        )
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer,
            max_lr=config.MAX_LR,
            epochs=config.EPOCHS,
            steps_per_epoch=len(train_loader),
        )
        criterion = nn.CrossEntropyLoss()

        model.train()
        for epoch in range(config.EPOCHS):
            total_loss = 0
            for data, target in train_loader:
                data, target = data.to(config.DEVICE), target.to(config.DEVICE)
                optimizer.zero_grad()
                output, _ = model(data)
                loss = criterion(output, target)
                loss.backward()
                optimizer.step()
                scheduler.step()
                total_loss += loss.item()

            # Validation
            model.eval()
            correct = 0
            total = 0
            with torch.no_grad():
                for data, target in test_loader:
                    data, target = data.to(config.DEVICE), target.to(config.DEVICE)
                    output, _ = model(data)
                    pred = output.argmax(dim=1)
                    correct += (pred == target).sum().item()
                    total += target.size(0)
            accuracy = 100 * correct / total
            model.train()

            print(
                f"Epoch {epoch + 1}/{config.EPOCHS} - Loss: {total_loss / len(train_loader):.4f} - Accuracy: {accuracy:.2f}%"
            )

        # Move model back to CPU for inference and save
        model = model.to("cpu")
        torch.save(model.state_dict(), config.MODEL_PATH)
        print(f"Model trained and saved as {config.MODEL_PATH}")

    else:
        print(f"Loading trained MNIST model from {config.MODEL_PATH}...")
        model.load_state_dict(
            torch.load(config.MODEL_PATH, map_location="cpu", weights_only=True)
        )

    model.eval()
    return model


def train_simple_model():
    """
    Optional function to train the CNN model on MNIST dataset.
    """
    # Data augmentation for better generalization
    train_transform = transforms.Compose(
        [
            transforms.RandomRotation(10),
            transforms.RandomAffine(degrees=0, translate=(0.1, 0.1), scale=(0.9, 1.1)),
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,)),
        ]
    )

    train_dataset = datasets.MNIST(
        root=config.DATA_ROOT, train=True, download=True, transform=train_transform
    )
    train_loader = DataLoader(train_dataset, batch_size=config.BATCH_SIZE, shuffle=True)

    model = DigitNet()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.LEARNING_RATE, weight_decay=config.WEIGHT_DECAY
    )
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=config.MAX_LR,
        epochs=config.EPOCHS,
        steps_per_epoch=len(train_loader),
    )
    criterion = nn.CrossEntropyLoss()

    # Train for EPOCHS
    model.train()
    for epoch in range(config.EPOCHS):
        for batch_idx, (data, target) in enumerate(train_loader):
            optimizer.zero_grad()
            output, _ = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()
            scheduler.step()

            if batch_idx % 100 == 0:
                print(f"Epoch {epoch}, Batch {batch_idx}, Loss: {loss.item():.4f}")

    torch.save(model.state_dict(), config.MODEL_PATH)
    print(f"Model saved as '{config.MODEL_PATH}'")
