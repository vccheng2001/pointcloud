import torch
import torch.nn as nn
import torch.nn.functional as F
from knn_cuda import KNN

from pointnet2_utils import sample_and_group
from deep_feat_extraction import feat_extraction_layer
from weighting_layer import weighting_layer
from voxelize import voxelize
from sampling_module import Sampling_Module

class DeepVCP(nn.Module):
    def __init__(self): 
        super(DeepVCP, self).__init__()
        self.FE1 = feat_extraction_layer()
        self.WL = weighting_layer()
    
    def forward(self, src_pts, tgt_pts):
        B, _, _ = src_pts.shape
        src_deep_feat_xyz, src_deep_feat_pts = self.FE1(src_pts)
        # obtain the top k indices for src point clouds
        src_keypts_idx = self.WL(src_deep_feat_pts)
        src_keypts = src_pts[:, :, src_keypts_idx]
        src_keypts = src_keypts.permute(0, 2, 1)
        # group the keypoints
        src_keypts_grouped_xyz, src_keypts_grouped_pts = sample_and_group(npoint = 64, radius = 1, nsample = 32, \
                                                                          xyz = src_keypts[:, :, :3], \
                                                                          points = src_keypts[:, :, 3:])
        
        tgt_pts_xyz = tgt_pts[:, :3, :]
        tgt_pts_xyz = tgt_pts_xyz.permute(0, 2, 1)
        tgt_deep_feat_xyz, tgt_deep_feat_pts = self.FE1(tgt_pts)
        # get candidate points for corresponding points of the keypts in src
        r = 2.0
        s = 0.4
        ###########################
        # seems to not taking batch size in voxelize.py
        ###########################
        # candidate_pts = voxelize(src_keypts, r, s)
        candidate_pts = torch.randn(B, src_keypts.shape[1], 552, 3)

        sm = Sampling_Module()
        tgt_pts_grouped = sm(candidate_pts, src_keypts, tgt_pts_xyz, tgt_deep_feat_pts)
        print("tgt_pts_grouped", tgt_pts_grouped.shape)

        # obtain the top k indices for tgt point clouds
        tgt_keypts_idx = self.WL(tgt_deep_feat_pts)
        tgt_keypts = tgt_pts[:, :, tgt_keypts_idx]
        tgt_keypts = tgt_keypts.permute(0, 2, 1)
        # group the keypoints
        tgt_keypts_grouped_xyz, tgt_keypts_grouped_pts = sample_and_group(npoint = 64, radius = 1, nsample = 32, xyz = tgt_keypts[:, :, :3], points = tgt_keypts[:, :, 3:])
        return src_keypts