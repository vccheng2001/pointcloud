import os
import numpy as np
import torch
from torch import nn
from torch.optim import Adam
from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import ReduceLROnPlateau
from scipy.spatial.transform import Rotation as R
import time
import pickle
import argparse 
from utils import *

from deepVCP import DeepVCP
from ModelNet40Dataset import ModelNet40Dataset
from KITTIDataset import KITTIDataset
from deepVCP_loss import deepVCP_loss

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

# setup train 
parser = argparse.ArgumentParser()
parser.add_argument('-d', '--dataset', default="modelnet", help='dataset (specify modelnet or kitti)')
parser.add_argument('-r', '--retrain_path', action = "store", type = str, help='specify a saved model to retrain on')
parser.add_argument('-m', '--model_path', default="final_model.pt", action = "store", type = str, help='specify path to save final model')

args = parser.parse_args()

def main():
    # hyper-parameters
    num_epochs = 10
    batch_size = 1
    init_lr = 0.01
    decay_factor = 0.7
    # loss balancing factor 
    alpha = 0.5

    print(f"Params: ep: {num_epochs}, batch: {batch_size}, init_lr:{init_lr}, decay:{decay_factor},alpha:{alpha}")

    # check if cuda is available
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"device: {device}")

    # dataset 
    if args.dataset == "modelnet":
        root = '/home/zheruiz/datasets/modelnet40_normal_resampled/'
        shape_names = np.loadtxt(root+"modelnet10_shape_names.txt", dtype="str")
        train_data= ModelNet40Dataset(root=root, augment=True, split='train')
        test_data = ModelNet40Dataset(root=root, augment=True,  split='test')
    else:
        root = '/data/dataset/'
        train_data= KITTIDataset(root=root, N=10000, augment=True, split="train")
        test_data = KITTIDataset(root=root, N=10000, augment=True, split="test")


    train_loader = DataLoader(dataset=train_data, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(dataset=test_data, batch_size=batch_size, shuffle=False)


    num_train = len(train_data)
    num_test = len(test_data)
    print('Train dataset size: ', num_train)
    print('Test dataset size: ', num_test)

    use_normal = False if args.dataset == "kitti" else True

    # Initialize the model
    model = DeepVCP(use_normal=use_normal) 
    model.to(device)

    # Retrain
    if args.retrain_path:
        print("Retrain on ", args.retrain_path)
        model.load_state_dict(torch.load(args.retrain_path))
    else:
        print("No retrain")

    # Define the optimizer
    optim = Adam(model.parameters(), lr=init_lr)
    scheduler = ReduceLROnPlateau(optim, 'min',  factor=decay_factor, patience=1)

    # begin train 
    model.train()
    loss_epoch_avg = []
    for epoch in range(num_epochs):
        print(f"epoch #{epoch}")
        loss_epoch = []
        running_loss = 0.0
        
        for n_batch, (src, target, R_gt, t_gt, ) in enumerate(train_loader):
            start_time = time.time()
            # mini batch
            src, target, R_gt, t_gt = src.to(device), target.to(device), R_gt.to(device), t_gt.to(device)
            t_init = torch.zeros(1, 3)
            src_keypts, target_vcp = model(src, target, R_gt, t_init)
            # print('src_keypts shape', src_keypts.shape)
            # print('target_vcp shape', target_vcp.shape)
            # zero gradient 
            optim.zero_grad()
            loss, R_pred, t_pred = deepVCP_loss(src_keypts, target_vcp, R_gt, t_gt, alpha=0.5)

            # error metric for rigid body transformation
            r_pred = R.from_matrix(R_pred.squeeze(0).cpu().detach().numpy())
            r_pred_arr = torch.tensor(r_pred.as_euler('xyz', degrees=True)).reshape(1, 3)
            r_gt = R.from_matrix(R_pred.squeeze(0).cpu().detach().numpy())
            r_gt_arr = torch.tensor(r_gt.as_euler('xyz', degrees=True)).reshape(1, 3)
            pdist = nn.PairwiseDistance(p = 2)
            
            print("rotation error: ", pdist(r_pred_arr, r_gt_arr).item())
            print("translation error: ", pdist(t_pred, t_gt).item())

            # backward pass
            loss.backward()
            # update parameters 
            optim.step()
            scheduler.step(loss)

            running_loss += loss.item()
            loss_epoch += [loss.item()]
            print("--- %s seconds ---" % (time.time() - start_time))
            if (n_batch + 1) % 5 == 0:
                print("Epoch: [{}/{}], Batch: {}, Loss: {}".format(
                    epoch, num_epochs, n_batch, loss.item()))
                running_loss = 0.0
        
        torch.save(model.state_dict(), "epoch_" + str(epoch) + "_model.pt")
        loss_epoch_avg += [sum(loss_epoch) / len(loss_epoch)]
        with open("training_loss_v1_" + str(epoch) + ".txt", "wb") as fp:   #Pickling
            pickle.dump(loss_epoch, fp)
        

    # save 
    print("Finished Training")
    torch.save(model.state_dict(), args.model_path)
    
    # begin test 
    model.eval()
    loss_test = []
    with torch.no_grad():
        for n_batch, (src, target, R_gt, t_gt) in enumerate(test_loader):
            # mini batch
            src, target, R_gt, t_gt = src.to(device), target.to(device), R_gt.to(device), t_gt.to(device)
            t_init = torch.zeros(1, 3)
            src_keypts, target_vcp = model.test(src, target, R_gt, t_init)

            loss, R_pred, t_pred = deepVCP_loss(src_keypts, target_vcp, R_gt, t_gt, alpha=0.5)
            # error metric for rigid body transformation
            r_pred = R.from_matrix(R_pred.squeeze(0).cpu().detach().numpy())
            r_pred_arr = torch.tensor(r_pred.as_euler('xyz', degrees=True)).reshape(1, 3)
            r_gt = R.from_matrix(R_pred.squeeze(0).cpu().detach().numpy())
            r_gt_arr = torch.tensor(r_gt.as_euler('xyz', degrees=True)).reshape(1, 3)
            pdist = nn.PairwiseDistance(p = 2)
            
            print("rotation error test: ", pdist(r_pred_arr, r_gt_arr).item())
            print("translation error test: ", pdist(t_pred, t_gt).item())

            loss_test += [loss.item()]

    with open("test_loss.txt", "wb") as fp_test:   #Pickling
        pickle.dump(loss_test, fp_test)
    print("Test loss:", loss)

if __name__ == "__main__":
    main()
