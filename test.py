import torch
from pointnet2_utils import index_points, query_ball_point
from utils import knn

# y_true = torch.rand(1,3,4)
# y_pred1 = torch.rand(1,3,5)
# print('ytrue', y_true)
# print('ypred1', y_pred1)

# # dist: B x querynum xK

# N = 2

# dist, idx = knn(qry=y_pred1.permute(0,2,1), ref=y_true.permute(0,2,1), K=1, return_ref_pts=False)          # BxKxN



# print('dist', dist.shape, dist)
# print('idx',idx.shape, idx)
# # eliminate 20% outliers (keep 80% points with smallest 1-NN distance)
# num_inliers = int(N*0.8)
# print('num_inliers', num_inliers)
# inliers = torch.topk(dist.permute(0,2,1), k=num_inliers, dim=-1,\
#                     largest=False, sorted=True).indices

# print('inliers', inliers.shape,inliers)
# inliers = inliers.repeat(1,3,1)#.to(device) # repeat for x y z

# y_pred1 = torch.gather(y_pred1, dim=-1, index = inliers) # Bx3xN'

# print('y_pred1 after gather', y_pred1.shape)
# print(y_pred1)


device = 'cuda'

B = 1
K_topK = 6
K_knn=3
C = 27
N2 =  100

tgt_pts_xyz = torch.rand(B, N2, 3)
tgt_deep_feat_pts = torch.rand(B, N2, 32)
D_radius = 1 # 1 meter search radius

candidate_pts = torch.rand(B, K_topK, C, 3)
B, K_topk, C, _ = candidate_pts.shape
# # (B x (K_topk x C) x 3)

src_transformed_T = torch.rand(B, K_topk, 3)

candidate_pts_flat = torch.flatten(candidate_pts, start_dim = 1, end_dim = 2) # (B x (K_topk x C) x 3)

        
# Se    # Search among all original N2 target points for each candidate's nearest neighbors 
# nn_idx: (B x (K_topk x C) x K_knn)
nn_idx = query_ball_point(radius=D_radius,
                            nsample=K_knn, 
                            xyz=tgt_pts_xyz.float(),             # (B x N2 x 3) 
                            new_xyz=candidate_pts_flat.float())  # (B x (K_topk x C) x 3)


# Index into tgt_pts_xyz   
# (B x K_topk x C x K_knn x 3)
nn_idx_xyz = nn_idx.reshape(B, K_topk, C, K_knn).unsqueeze(-1).repeat(1,1,1,1,3)
# (B x N2 x C x K_knn x 3 )
tgt_pts_xyz = tgt_pts_xyz.unsqueeze(-2).unsqueeze(-2).repeat(1,1,C, K_knn,1)

# (B x K_topk x C x K_knn x 3)
nn_candidate_pts = torch.gather(tgt_pts_xyz, dim=1, index=nn_idx_xyz)
# should be local, which means each <K_topk> keypoint is the origin
# (B x K_topk x C x K_knn x 3) - (B x K_topk C x K_knn x 3)
nn_candidate_pts_local = nn_candidate_pts - src_transformed_T.unsqueeze(-2).unsqueeze(-2).repeat(1,1,C, K_knn,1)
# normalize by search radius 
nn_candidate_pts_norm = nn_candidate_pts_local / D_radius

# Index into tgt_deep_feat_pts
nn_idx_deep_feat_pts = nn_idx.reshape(B, K_topk, C, K_knn).unsqueeze(-1).repeat(1,1,1,1,32)
# (B x N2 x C x K_knn x num_feats)
tgt_deep_feat_pts = tgt_deep_feat_pts.unsqueeze(-2).unsqueeze(-2).repeat(1,1,C,K_knn, 1)
nn_tgt_deep_feat_pts = torch.gather(tgt_deep_feat_pts, dim=1, index=nn_idx_deep_feat_pts)

# normalize FE extracted features
nn_tgt_deep_feat_pts_norm = nn_tgt_deep_feat_pts / D_radius

# concat
tgt_keyfeats_cat = torch.cat((nn_candidate_pts_norm, nn_tgt_deep_feat_pts_norm), dim = 4)
print('tgt', tgt_keyfeats_cat.shape)