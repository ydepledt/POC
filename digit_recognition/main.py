import tkinter as tk

from visualizer import NeuralNetVisualizer


def main():
    root = tk.Tk()
    app = NeuralNetVisualizer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
