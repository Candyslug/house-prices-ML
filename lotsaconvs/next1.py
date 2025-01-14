import sys
import time
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision.datasets import CIFAR100
from torchvision.transforms import ToTensor, RandomResizedCrop, Compose
import matplotlib.pyplot as plt

class NextBlock(nn.Module):
    def __init__(self, groups, inc, outc):
        super().__init__()
        self.layer_stack = nn.Sequential(
            nn.Conv2d(in_channels=inc, out_channels=outc, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(num_features=outc),
            nn.ReLU(),

            nn.Conv2d(in_channels=outc, out_channels=outc, groups=groups, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(num_features=outc),
            nn.ReLU()
        )
        self.shortcut = nn.Sequential(
            nn.Conv2d(in_channels=inc, out_channels=outc, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(num_features=outc),
            nn.ReLU()
        )
        self.relu = nn.ReLU()
    def forward(self, x):
        return self.relu(self.layer_stack(x) + self.shortcut(x))

class DaNet(nn.Module):
    def __init__(self, path):
        super().__init__()
        self.layer_stack = nn.Sequential(
            NextBlock(8, 3, 24),
            nn.MaxPool2d(kernel_size=2, stride=2),
            NextBlock(16, 24, 48),
            nn.MaxPool2d(kernel_size=2, stride=2),
            NextBlock(16, 48, 64),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Conv2d(in_channels=64, out_channels=100, kernel_size=1, stride=1, padding=0),
            nn.BatchNorm2d(num_features=100),
            nn.ReLU(),

            nn.AdaptiveAvgPool2d(output_size=(1,1)),
            nn.Flatten(),
            nn.LogSoftmax(dim=1)
        )
        self.path = path
        if os.path.exists(path) and len(sys.argv) == 3 and sys.argv[2] == "old":
            self.load_state_dict(torch.load(self.path))
            print("Loaded existing model:", self.path)
        elif len(sys.argv) == 3 and sys.argv[2] == "new":
            torch.save(self.state_dict(), self.path)
            print("Created new model:", self.path)
    def forward(self, x):
        return self.layer_stack(x)

if __name__ == "__main__":

    BS = 128
    EVAL_BS = 128
    LR = 0.1
    MOM = 0.0

    N_EPOCHS = 20

    device = torch.device("mps")

    train_dataloader = DataLoader(CIFAR100(root="../datasets/", train=True, download=False, transform=ToTensor()),
                                  batch_size=BS, shuffle=True)
    test_dataloader = DataLoader(CIFAR100(root="../datasets/", train=False, download=False, transform=ToTensor()),
                                  batch_size=EVAL_BS, shuffle=True)

    model = DaNet("nets/next1.pt").to(device)
    print(model)
    model.train()

    optim = torch.optim.SGD(params=model.parameters(), lr=LR, momentum=MOM)
    criterion = nn.NLLLoss()

    losses = []
    accs = []
    eval_accs = []

    if sys.argv[1] == "train":
        start_time = time.time()
        for n_epoch in range(N_EPOCHS):
            plt.title(f"Epoch: 1-{n_epoch+1}")
            for n_batch, (x, y) in enumerate(train_dataloader):

                # train
                model.train()
                optim.zero_grad()
                x = x.to(device)
                pred = model(x)
                loss = criterion(pred, y.to(device))
                loss.backward()
                optim.step()
                # ----

                # eval
                model.eval()
                acc = (pred.detach().cpu().argmax(dim=1)==y).sum().item()
                x_eval, y_eval = next(iter(test_dataloader))
                pred_eval = model(x_eval.to(device))
                eval_acc = (pred_eval.detach().cpu().argmax(dim=1)==y_eval).sum().item()
                if n_batch % 2 == 0:
                    print(f"Epoch: {n_epoch+1:8}/{N_EPOCHS}, Batch: {n_batch:8}/{len(train_dataloader):4} --- Loss: {loss.detach().cpu().item()/float(BS):20f}, Acc: {acc/float(BS):10f} {acc:4}/{BS}, Eval Acc: {eval_acc:4}/{EVAL_BS} {eval_acc/float(EVAL_BS):10f}")
                if n_batch % 5 == 0:
                    losses.append(loss.detach().cpu().item()/BS)
                    eval_accs.append(eval_acc/float(EVAL_BS))
                    accs.append(acc/BS)
                # ----

            plt.plot(losses, 'r')
            plt.plot(accs, 'g')
            plt.plot(eval_accs, 'b')
            plt.savefig("recent_plot.png")
            print("Model saved:", model.path)
            torch.save(model.state_dict(), model.path)

        end_time = time.time()
        print(f"Execution time: {end_time - start_time} seconds.")
    elif sys.argv[1] == "eval":
        model.eval()
        score = 0
        for i, (x, y) in enumerate(test_dataloader):
            preds = model(x.to(device))
            acc = (preds.detach().cpu().argmax(dim=1)==y).sum().item()
            print(f"Batch: {i}, Acc:{acc}/{len(y)}")
            score += acc
        print(score, '/', len(test_dataloader.dataset.targets))